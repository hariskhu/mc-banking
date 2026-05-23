from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.material import Material
from app.models.account import Account
from app.models.transaction import Transaction, TransactionType
from app.services.banking import _get_player_account, _get_player_id
import math

ELASTICITY = Decimal("0.5")
COPPER_INFLUENCE = Decimal("0")
PRICE_CAP_MULTIPLIER = Decimal("5") # max price is 4x base price

def seed_materials(session: Session):
    '''Seeds the database with material values.'''
    # Calculate ideals
    ideal_copper = 54*64*9*9 # A double chests of copper blocks
    ideal_zinc = 54*64*9 # A double chest of zinc ingots
    ideal_iron = 2*54*64*9 # Two double chests of iron ingots
    ideal_gold = 54*64*9 # A chest of gold ingots
    ideal_diamond = 64*3 # Three stacks of diamonds

    # Fix wrong copper nugget tag
    wrong_copper = session.scalar(
        select(Material).where(Material.mc_id == "create:copper_nugget")
    )
    if wrong_copper:
        wrong_copper.mc_id = "create:copper_nugget"
        session.commit()

    defaults = [
        {"name": "Copper Nugget",  "mc_id": "create:copper_nugget",    "base_price": Decimal("0.01"),  "ideal_supply": ideal_copper},
        {"name": "Iron Nugget",    "mc_id": "minecraft:iron_nugget",   "base_price": Decimal("0.08"),  "ideal_supply": ideal_iron},
        {"name": "Gold Nugget",    "mc_id": "minecraft:gold_nugget",   "base_price": Decimal("0.12"), "ideal_supply": ideal_gold},
        {"name": "Zinc Nugget",    "mc_id": "create:zinc_nugget",      "base_price": Decimal("1.00"),  "ideal_supply": ideal_zinc},
        {"name": "Diamond",        "mc_id": "minecraft:diamond",       "base_price": Decimal("16.00"), "ideal_supply": ideal_diamond},
    ]
    for d in defaults:
        existing = session.scalar(select(Material).where(Material.mc_id == d["mc_id"]))
        if not existing:
            session.add(Material(**d, elasticity=Decimal("0.5")))
    session.commit()


def get_material(session: Session, mc_id: str) -> Material:
    material = session.scalar(select(Material).where(Material.mc_id == mc_id))
    if not material:
        raise ValueError(f"Unknown material: {mc_id}")
    return material


def _get_copper(session: Session) -> Material:
    copper = session.scalar(select(Material).where(Material.mc_id == "create:copper_nugget"))
    if not copper:
        raise ValueError("Copper not found in materials table")
    return copper


def spot_price(material: Material, copper: Material) -> Decimal:
    if material.mc_id == copper.mc_id:
        return Decimal("0.01")

    cap = PRICE_CAP_MULTIPLIER
    supply_floor = Decimal(str(material.ideal_supply)) / (cap ** (Decimal("1") / material.elasticity))

    effective_supply = max(Decimal(str(material.current_supply)), supply_floor)
    material_ratio = Decimal(str(material.ideal_supply)) / effective_supply

    if copper.current_supply <= 0:
        copper_ratio = Decimal("1")
    else:
        copper_ratio = Decimal(str(copper.current_supply / copper.ideal_supply))

    price = material.base_price * (material_ratio ** material.elasticity) * (copper_ratio ** COPPER_INFLUENCE)
    return price.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _integrated_value(material: Material, copper: Material, quantity: int, withdrawing: bool) -> Decimal:
    e = float(material.elasticity)
    ideal = float(material.ideal_supply)
    base = float(material.base_price)
    current = float(material.current_supply)
    n = float(quantity)
    cap = float(PRICE_CAP_MULTIPLIER)

    # Copper inflation multiplier — fixed for this transaction
    if copper.current_supply <= 0:
        copper_factor = 1.0
    else:
        copper_factor = (copper.current_supply / copper.ideal_supply) ** float(COPPER_INFLUENCE)

    if withdrawing:
        q_start = max(current - n, 1.0)
        q_end = max(current, 1.0)
    else:
        q_start = max(current, 1.0)
        q_end = current + n

    # Clamp prices to cap by clamping supply to the floor where price = cap
    supply_floor = ideal / (cap ** (1 / e))
    q_start = max(q_start, supply_floor)
    q_end = max(q_end, supply_floor)

    # If both ends are at the floor (zero supply depositing small amount)
    # just use flat cap price * quantity
    if q_start >= q_end:
        value = base * cap * n
        return Decimal(str(abs(value * copper_factor))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    if abs(e - 1.0) < 1e-9:
        value = base * (ideal ** e) * math.log(q_end / q_start)
    else:
        coeff = base * (ideal ** e) / (1 - e)
        value = coeff * (q_end ** (1 - e) - q_start ** (1 - e))

    return Decimal(str(abs(value * copper_factor))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def calculate_deposit_value(session: Session, mc_id: str, quantity: int) -> Decimal:
    """How much copper a deposit of `quantity` units should credit."""
    material = get_material(session, mc_id)
    return _integrated_value(material, quantity, withdrawing=False)


def calculate_withdrawal_cost(session: Session, mc_id: str, quantity: int) -> Decimal:
    """How much copper a withdrawal of `quantity` units should cost."""
    material = get_material(session, mc_id)
    if material.current_supply < quantity:
        raise ValueError(f"Insufficient vault supply of {material.name}")
    return _integrated_value(material, quantity, withdrawing=True)


def process_deposit(session: Session, discord_id: str, items: list[dict]) -> dict:
    account = _get_player_account(session, discord_id)

    # Separate copper from other materials — copper deposits don't pay out,
    # they just increase supply and cause mild deflation for other materials
    copper = session.scalar(
        select(Material).where(Material.mc_id == "create:copper_nugget").with_for_update()
    )

    breakdown = []
    total = Decimal("0")
    items_str_parts = []

    for item in items:
        mc_id = item["mc_id"]
        quantity = int(item["quantity"])

        if quantity <= 0:
            continue

        material = session.scalar(
            select(Material).where(Material.mc_id == mc_id).with_for_update()
        )
        if not material:
            raise ValueError(f"Unknown material: {mc_id}")

        if mc_id == "create:copper_nugget":
            # Copper deposits credit 1:1 and update supply
            value = Decimal("0.01") * quantity
            material.current_supply += quantity
        else:
            value = _integrated_value(material, copper, quantity, withdrawing=False)
            material.current_supply += quantity

        total += value
        items_str_parts.append(f"{quantity}x {mc_id}")
        breakdown.append({
            "material": material.name,
            "quantity": quantity,
            "value": value,
            "new_supply": material.current_supply,
            "spot_price": spot_price(material, copper),
        })

    account.balance += total
    session.add(Transaction(
        from_account=None,
        to_account=account.id,
        amount=total,
        type=TransactionType.deposit,
        note=f"Material deposit: {', '.join(items_str_parts)}",
    ))
    session.commit()
    return {"total": total, "breakdown": breakdown}


def process_withdrawal(session: Session, discord_id: str, items: list[dict]) -> dict:
    account = _get_player_account(session, discord_id)
    copper = session.scalar(
        select(Material).where(Material.mc_id == "create:copper_nugget").with_for_update()
    )

    costs = []
    total_cost = Decimal("0")

    for item in items:
        mc_id = item["mc_id"]
        quantity = int(item["quantity"])

        material = session.scalar(
            select(Material).where(Material.mc_id == mc_id).with_for_update()
        )
        if not material:
            raise ValueError(f"Unknown material: {mc_id}")
        if material.current_supply < quantity:
            raise ValueError(f"Insufficient vault supply of {material.name}")

        if mc_id == "create:copper_nugget":
            cost = Decimal("0.01") * quantity
        else:
            cost = _integrated_value(material, copper, quantity, withdrawing=True)

        costs.append((material, quantity, cost))
        total_cost += cost

    total_cost = total_cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if account.balance < total_cost:
        raise ValueError(f"Insufficient funds. Costs ${total_cost:,.2f}, balance is ${account.balance:,.2f}")

    breakdown = []
    items_str_parts = []
    for material, quantity, cost in costs:
        material.current_supply -= quantity
        items_str_parts.append(f"{quantity}x {material.mc_id}")
        breakdown.append({
            "material": material.name,
            "quantity": quantity,
            "cost": cost,
            "new_supply": material.current_supply,
            "spot_price": spot_price(material, copper),
        })

    account.balance -= total_cost
    session.add(Transaction(
        from_account=account.id,
        to_account=None,
        amount=total_cost,
        type=TransactionType.withdrawal,
        note=f"Material withdrawal: {', '.join(items_str_parts)}",
    ))
    session.commit()
    return {"total_cost": total_cost, "breakdown": breakdown}


def get_all_spot_prices(session: Session) -> list[dict]:
    copper = _get_copper(session)
    materials = session.scalars(select(Material)).all()
    return [
        {
            "name": m.name,
            "mc_id": m.mc_id,
            "spot_price": spot_price(m, copper),
            "base_price": m.base_price,
            "current_supply": m.current_supply,
            "ideal_supply": m.ideal_supply,
        }
        for m in materials
    ]