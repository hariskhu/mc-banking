from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.account import Account, AccountType
from app.models.player import Player
from app.models.guild import Guild, GuildMember, GuildRole
from app.models.transaction import Transaction, TransactionType


def clean_note(note: str | None) -> str | None:
    return note.strip()[:255] if note else None


def _get_player_id(session: Session, discord_id: str) -> int:
    player_id = session.scalar(
        select(Player.id).where(Player.discord_id == discord_id)
    )
    if not player_id:
        raise ValueError(f"Player {discord_id} is not registered")
    return player_id


def _get_player_account(session: Session, discord_id: str) -> Account:
    """Locked — use for any read-then-write operation."""
    account = session.scalar(
        select(Account)
        .join(Player, Player.id == Account.owner_id)
        .where(
            Player.discord_id == discord_id,
            Account.owner_type == AccountType.player,
        )
        .with_for_update()
    )
    if not account:
        raise ValueError(f"No player account found for Discord user {discord_id}")
    return account


def _get_player_account_readonly(session: Session, discord_id: str) -> Account:
    """Unlocked, use for balance checks and history only."""
    account = session.scalar(
        select(Account)
        .join(Player, Player.id == Account.owner_id)
        .where(
            Player.discord_id == discord_id,
            Account.owner_type == AccountType.player,
        )
    )
    if not account:
        raise ValueError(f"No player account found for Discord user {discord_id}")
    return account


def _get_guild_account(session: Session, player_id: int) -> Account:
    """Locked, use for any read-then-write operation."""
    account = session.scalar(
        select(Account)
        .join(GuildMember, GuildMember.guild_id == Account.owner_id)
        .where(
            GuildMember.player_id == player_id,
            Account.owner_type == AccountType.guild,
        )
        .with_for_update()
    )
    if not account:
        raise ValueError("Guild account not found")
    return account


# ── Player registration ───────────────────────────────────────────────────────

def register_player(session: Session, discord_id: str, mc_username: str | None = None) -> Player:
    existing = session.scalar(
        select(Player).where(Player.discord_id == discord_id)
    )
    if existing:
        raise ValueError(f"Player {discord_id} is already registered")

    player = Player(discord_id=discord_id, mc_username=mc_username)
    session.add(player)
    session.flush()

    session.add(Account(
        owner_type=AccountType.player,
        owner_id=player.id,
        balance=Decimal("0.00"),
    ))
    session.commit()
    return player


def get_player(session: Session, discord_id: str) -> Player:
    player = session.scalar(
        select(Player).where(Player.discord_id == discord_id)
    )
    if not player:
        raise ValueError(f"Player {discord_id} is not registered")
    return player


def update_username(session: Session, discord_id: str, new_username: str) -> Player:
    player = get_player(session, discord_id)
    player.mc_username = new_username
    session.commit()
    return player


# ── Balances ──────────────────────────────────────────────────────────────────

def get_player_bal(session: Session, discord_id: str) -> Decimal:
    return _get_player_account_readonly(session, discord_id).balance


def get_guild_bal(session: Session, discord_id: str) -> Decimal:
    player_id = _get_player_id(session, discord_id)
    account = session.scalar(
        select(Account)
        .join(GuildMember, GuildMember.guild_id == Account.owner_id)
        .where(
            GuildMember.player_id == player_id,
            Account.owner_type == AccountType.guild,
        )
    )
    if not account:
        raise ValueError("You are not in a guild")
    return account.balance


# ── Player transfers ──────────────────────────────────────────────────────────

def player_transfer(
    session: Session,
    from_discord_id: str,
    to_discord_id: str,
    amount: Decimal,
    note: str = None,
):
    if amount <= 0:
        raise ValueError("Transfer amount must be positive")
    if from_discord_id == to_discord_id:
        raise ValueError("Cannot transfer to yourself")

    # Resolve IDs first without locking
    from_id = _get_player_id(session, from_discord_id)
    to_id = _get_player_id(session, to_discord_id)

    # Lock in consistent order to prevent deadlocks
    first_id, second_id = min(from_id, to_id), max(from_id, to_id)
    first = session.scalar(select(Account).where(Account.id == first_id).with_for_update())
    second = session.scalar(select(Account).where(Account.id == second_id).with_for_update())

    src = first if first.id == from_id else second
    dst = first if first.id == to_id else second

    if src.balance < amount:
        raise ValueError("Insufficient funds to transfer")

    src.balance -= amount
    dst.balance += amount

    txn = Transaction(
        from_account=src.id,
        to_account=dst.id,
        amount=amount,
        type=TransactionType.transfer,
        note=clean_note(note),
    )
    session.add(txn)
    session.commit()
    return txn


# ── Deposits / withdrawals ────────────────────────────────────────────────────

def deposit(session: Session, discord_id: str, amount: Decimal, note: str = None):
    if amount <= 0:
        raise ValueError("Deposit amount must be positive")

    account = _get_player_account(session, discord_id)
    account.balance += amount

    txn = Transaction(
        from_account=None,
        to_account=account.id,
        amount=amount,
        type=TransactionType.deposit,
        note=clean_note(note),
    )
    session.add(txn)
    session.commit()
    return txn


def withdraw(session: Session, discord_id: str, amount: Decimal, note: str = None):
    if amount <= 0:
        raise ValueError("Withdrawal amount must be positive")

    account = _get_player_account(session, discord_id)
    if account.balance < amount:
        raise ValueError("Insufficient funds")

    account.balance -= amount

    txn = Transaction(
        from_account=account.id,
        to_account=None,
        amount=amount,
        type=TransactionType.withdrawal,
        note=clean_note(note),
    )
    session.add(txn)
    session.commit()
    return txn

def admin_change_player_bal(session: Session, discord_id: str, amount: Decimal) -> Decimal:
    '''Function used for admin command to edit balances.'''
    account = _get_player_account(session, discord_id)
    account.balance += amount
    new_bal = account.balance
    session.commit()
    return new_bal

# ── Guild transfers ───────────────────────────────────────────────────────────

def guild_deposit(session: Session, discord_id: str, amount: Decimal, note: str = None):
    if amount <= 0:
        raise ValueError("Deposit amount must be positive")

    player_id = _get_player_id(session, discord_id)
    membership = session.scalar(
        select(GuildMember).where(GuildMember.player_id == player_id)
    )
    if not membership:
        raise PermissionError("You are not a member of this guild")

    guild = session.get(Guild, membership.guild_id)
    player_account = _get_player_account(session, discord_id)
    if player_account.balance < amount:
        raise ValueError("Insufficient funds")

    guild_account = _get_guild_account(session, player_id)
    player_account.balance -= amount
    guild_account.balance += amount

    txn = Transaction(
        from_account=player_account.id,
        to_account=guild_account.id,
        amount=amount,
        type=TransactionType.transfer,
        note=clean_note(note) or f"Deposit to guild {guild.name}",
    )
    session.add(txn)
    session.commit()
    return txn


def guild_withdraw(session: Session, discord_id: str, amount: Decimal, note: str = None):
    if amount <= 0:
        raise ValueError("Withdrawal amount must be positive")

    player_id = _get_player_id(session, discord_id)
    membership = session.scalar(
        select(GuildMember).where(GuildMember.player_id == player_id)
    )
    if not membership or membership.role not in (GuildRole.officer, GuildRole.captain):
        raise PermissionError("Only officers and captains can withdraw from the guild")

    guild = session.get(Guild, membership.guild_id)
    guild_account = _get_guild_account(session, player_id)
    if guild_account.balance < amount:
        raise ValueError("Insufficient guild funds")

    player_account = _get_player_account(session, discord_id)
    guild_account.balance -= amount
    player_account.balance += amount

    txn = Transaction(
        from_account=guild_account.id,
        to_account=player_account.id,
        amount=amount,
        type=TransactionType.transfer,
        note=clean_note(note) or f"Withdrawal from guild {guild.name}",
    )
    session.add(txn)
    session.commit()
    return txn

def guild_withdraw_approved(session: Session, discord_id: str, amount: Decimal, note: str = None):
    """
    Executes a guild withdrawal without role check.
    Only call this from an already-authorized approval flow.
    """
    if amount <= 0:
        raise ValueError("Withdrawal amount must be positive")

    player_id = _get_player_id(session, discord_id)
    membership = session.scalar(
        select(GuildMember).where(GuildMember.player_id == player_id)
    )
    if not membership:
        raise PermissionError("You are not a member of this guild")

    guild = session.get(Guild, membership.guild_id)
    guild_account = _get_guild_account(session, player_id)
    if guild_account.balance < amount:
        raise ValueError("Insufficient guild funds")

    player_account = _get_player_account(session, discord_id)
    guild_account.balance -= amount
    player_account.balance += amount

    txn = Transaction(
        from_account=guild_account.id,
        to_account=player_account.id,
        amount=amount,
        type=TransactionType.transfer,
        note=clean_note(note) or f"Approved withdrawal from guild {guild.name}",
    )
    session.add(txn)
    session.commit()
    return txn


# ── History ───────────────────────────────────────────────────────────────────

def get_transaction_history(
    session: Session, discord_id: str, limit: int = 50
) -> list[Transaction]:
    account = _get_player_account_readonly(session, discord_id)
    return session.scalars(
        select(Transaction)
        .where(
            (Transaction.from_account == account.id)
            | (Transaction.to_account == account.id)
        )
        .order_by(Transaction.created_at.desc())
        .limit(limit)
    ).all()