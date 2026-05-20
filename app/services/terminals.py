import secrets
import json
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.transaction import Transaction, TransactionType
from app.models.terminal import Terminal, TerminalType, ShopListing, BuybackListing, ServiceListing, ServiceSide
from app.models.guild import Guild
from app.models.pending_withdrawal import PendingWithdrawal, WithdrawalStatus
from app.ws.manager import manager
from app.services.materials import process_withdrawal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def _get_terminal(session: Session, terminal_id: int) -> Terminal:
    terminal = session.get(Terminal, terminal_id)
    if not terminal:
        raise ValueError(f"Terminal {terminal_id} not found")
    return terminal


def _get_terminal_by_token(session: Session, token: str) -> Terminal:
    terminal = session.scalar(select(Terminal).where(Terminal.token == token))
    if not terminal:
        raise ValueError("Invalid terminal token")
    if not terminal.active:
        raise ValueError("Terminal is inactive")
    return terminal


def create_terminal(
    session: Session,
    name: str,
    type: TerminalType,
    guild_id: int | None = None,
    location: str | None = None,
) -> Terminal:
    if session.scalar(select(Terminal).where(Terminal.name == name)):
        raise ValueError(f"Terminal '{name}' already exists")

    if type != TerminalType.bank and guild_id is None:
        raise ValueError("Non-bank terminals must be associated with a guild")

    if guild_id and not session.get(Guild, guild_id):
        raise ValueError(f"Guild {guild_id} not found")

    terminal = Terminal(
        name=name,
        type=type,
        token=generate_token(),
        guild_id=guild_id,
        location=location,
    )
    session.add(terminal)
    session.commit()
    return terminal


def regenerate_token(session: Session, terminal_id: int) -> Terminal:
    terminal = _get_terminal(session, terminal_id)
    terminal.token = generate_token()
    session.commit()
    return terminal


def set_terminal_active(session: Session, terminal_id: int, active: bool) -> Terminal:
    terminal = _get_terminal(session, terminal_id)
    terminal.active = active
    session.commit()
    return terminal


# ── Shop listings ─────────────────────────────────────────────────────────────

def add_shop_listing(
    session: Session,
    terminal_id: int,
    item_name: str,
    quantity: int,
    price: Decimal,
    nbt: str | None = None,
) -> ShopListing:
    terminal = _get_terminal(session, terminal_id)
    if terminal.type != TerminalType.shop:
        raise ValueError("Terminal is not a shop")

    listing = ShopListing(
        terminal_id=terminal_id,
        item_name=item_name,
        nbt=nbt,
        quantity=quantity,
        price=price,
    )
    session.add(listing)
    session.commit()
    return listing


def remove_shop_listing(session: Session, listing_id: int):
    listing = session.get(ShopListing, listing_id)
    if not listing:
        raise ValueError("Listing not found")
    session.delete(listing)
    session.commit()


# ── Buyback listings ──────────────────────────────────────────────────────────

def add_buyback_listing(
    session: Session,
    terminal_id: int,
    mc_id: str,
    price_per_item: Decimal,
    limit: int | None = None,
) -> BuybackListing:
    terminal = _get_terminal(session, terminal_id)
    if terminal.type != TerminalType.buyback:
        raise ValueError("Terminal is not a buyback")

    listing = BuybackListing(
        terminal_id=terminal_id,
        mc_id=mc_id,
        price_per_item=price_per_item,
        limit=limit,
    )
    session.add(listing)
    session.commit()
    return listing


def remove_buyback_listing(session: Session, listing_id: int):
    listing = session.get(BuybackListing, listing_id)
    if not listing:
        raise ValueError("Listing not found")
    session.delete(listing)
    session.commit()


# ── Service listings ──────────────────────────────────────────────────────────

def add_service_listing(
    session: Session,
    terminal_id: int,
    name: str,
    side: ServiceSide,
    signal_strength: int,
    duration_ticks: int,
    price: Decimal,
) -> ServiceListing:
    terminal = _get_terminal(session, terminal_id)
    if terminal.type != TerminalType.service:
        raise ValueError("Terminal is not a service terminal")

    existing_sides = session.scalars(
        select(ServiceListing).where(ServiceListing.terminal_id == terminal_id)
    ).all()
    if len(existing_sides) >= 4:
        raise ValueError("Service terminals can have at most 4 listings")
    if any(s.side == side for s in existing_sides):
        raise ValueError(f"Side {side.value} is already in use on this terminal")

    if not 1 <= signal_strength <= 15:
        raise ValueError("Signal strength must be between 1 and 15")
    if duration_ticks <= 0:
        raise ValueError("Duration must be positive")

    listing = ServiceListing(
        terminal_id=terminal_id,
        name=name,
        side=side,
        signal_strength=signal_strength,
        duration_ticks=duration_ticks,
        price=price,
    )
    session.add(listing)
    session.commit()
    return listing


def remove_service_listing(session: Session, listing_id: int):
    listing = session.get(ServiceListing, listing_id)
    if not listing:
        raise ValueError("Listing not found")
    session.delete(listing)
    session.commit()


# ── Queries ───────────────────────────────────────────────────────────────────

def get_all_terminals(session: Session) -> list[Terminal]:
    return session.scalars(select(Terminal).order_by(Terminal.type, Terminal.name)).all()


def get_terminals_by_guild(session: Session, guild_id: int) -> list[Terminal]:
    return session.scalars(
        select(Terminal).where(Terminal.guild_id == guild_id)
    ).all()


def get_shop_listings(session: Session, terminal_id: int) -> list[ShopListing]:
    return session.scalars(
        select(ShopListing)
        .where(ShopListing.terminal_id == terminal_id, ShopListing.active == True)
    ).all()


def get_buyback_listings(session: Session, terminal_id: int) -> list[BuybackListing]:
    return session.scalars(
        select(BuybackListing)
        .where(BuybackListing.terminal_id == terminal_id, BuybackListing.active == True)
    ).all()


def get_service_listings(session: Session, terminal_id: int) -> list[ServiceListing]:
    return session.scalars(
        select(ServiceListing)
        .where(ServiceListing.terminal_id == terminal_id, ServiceListing.active == True)
    ).all()

# -------- BANK TERMINALS --------
async def request_withdrawal(
    session: Session,
    discord_id: str,
    terminal_id: int,
    items: list[dict],
) -> PendingWithdrawal:
    terminal = _get_terminal(session, terminal_id)
    if terminal.type != TerminalType.bank:
        raise ValueError("Withdrawals can only be made at bank terminals")
    if not terminal.active:
        raise ValueError("This terminal is currently inactive")
    if not manager.is_connected(terminal_id):
        raise ValueError("This terminal is not currently online")

    # Deduct from balance first
    process_withdrawal(session, discord_id, items)

    # Record the pending withdrawal
    withdrawal = PendingWithdrawal(
        discord_id=discord_id,
        terminal_id=terminal_id,
        items=json.dumps(items),
        status=WithdrawalStatus.pending,
    )
    session.add(withdrawal)
    session.commit()

    # Push dispense message to terminal
    conn = manager.connections.get(terminal_id)
    conn.in_transaction = True
    await manager.send(terminal_id, {
        "type": "dispense",
        "payload": {
            "discord_id": discord_id,
            "items": items,
        },
    })

    return withdrawal

def get_pending_withdrawals(session: Session, terminal_id: int | None = None) -> list[PendingWithdrawal]:
    stmt = select(PendingWithdrawal).where(PendingWithdrawal.status == WithdrawalStatus.pending)
    if terminal_id:
        stmt = stmt.where(PendingWithdrawal.terminal_id == terminal_id)
    return session.scalars(stmt.order_by(PendingWithdrawal.created_at)).all()


def refund_pending_withdrawal(session: Session, withdrawal_id: int) -> PendingWithdrawal:
    withdrawal = session.get(PendingWithdrawal, withdrawal_id)
    if not withdrawal:
        raise ValueError("Pending withdrawal not found")
    if withdrawal.status != WithdrawalStatus.pending:
        raise ValueError(f"Withdrawal is already {withdrawal.status.value}")

    items = json.loads(withdrawal.items)

    # Refund each item's cost back to the player
    from app.services.materials import _get_player_account, _get_copper, _integrated_value
    from app.models.material import Material

    account = _get_player_account(session, withdrawal.discord_id)
    copper = _get_copper(session)
    total_refund = Decimal("0")

    for item in items:
        mc_id = item["mc_id"]
        quantity = int(item["quantity"])

        if mc_id == "create:copper_nugget":
            refund = Decimal("0.01") * quantity
        else:
            material = session.scalar(
                select(Material).where(Material.mc_id == mc_id).with_for_update()
            )
            if material:
                # Restore supply and calculate refund
                material.current_supply += quantity
                refund = _integrated_value(material, copper, quantity, withdrawing=False)
            else:
                refund = Decimal("0")

        total_refund += refund

    total_refund = total_refund.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    account.balance += total_refund

    session.add(Transaction(
        from_account=None,
        to_account=account.id,
        amount=total_refund,
        type=TransactionType.deposit,
        note=f"Refund for failed withdrawal #{withdrawal.id}",
    ))

    withdrawal.status = WithdrawalStatus.failed
    session.commit()
    return withdrawal


def fail_stale_withdrawals(session: Session, older_than_minutes: int = 10) -> list[PendingWithdrawal]:
    """Refunds all pending withdrawals older than the given threshold."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
    stale = session.scalars(
        select(PendingWithdrawal)
        .where(
            PendingWithdrawal.status == WithdrawalStatus.pending,
            PendingWithdrawal.created_at < cutoff,
        )
    ).all()

    refunded = []
    for w in stale:
        try:
            refund_pending_withdrawal(session, w.id)
            refunded.append(w)
        except Exception as e:
            logger.error(f"Failed to refund withdrawal {w.id}: {e}")

    return refunded