from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import select, delete
from app.models.guild import Guild, GuildMember, GuildRole
from app.models.account import Account, AccountType
from app.models.player import Player


def _get_player_id(session: Session, discord_id: str) -> int:
    player_id = session.scalar(
        select(Player.id).where(Player.discord_id == discord_id)
    )
    if not player_id:
        raise ValueError(f"Player {discord_id} is not registered")
    return player_id


def get_guild(session: Session, discord_id: str) -> Guild:
    player_id = _get_player_id(session, discord_id)
    membership = _get_membership(session, player_id)
    return session.get(Guild, membership.guild_id)

def get_guild_by_name(session: Session, name: str) -> Guild:
    guild = session.scalar(select(Guild).where(Guild.name == name))
    if not guild:
        raise ValueError(f"No guild named '{name}' exists")
    return guild


def get_guild_captain(session: Session, guild_id: int) -> Player:
    captain_membership = session.scalar(
        select(GuildMember).where(
            GuildMember.guild_id == guild_id,
            GuildMember.role == GuildRole.captain,
        )
    )
    if not captain_membership:
        raise ValueError("This guild has no captain")
    return session.get(Player, captain_membership.player_id)


def is_in_guild(session: Session, discord_id: str) -> bool:
    player_id = _get_player_id(session, discord_id)
    return session.scalar(
        select(GuildMember).where(GuildMember.player_id == player_id)
    ) is not None


def _get_membership(session: Session, player_id: int) -> GuildMember:
    membership = session.scalar(
        select(GuildMember).where(GuildMember.player_id == player_id)
    )
    if not membership:
        raise ValueError("You are not in a guild")
    return membership


def get_member_role(session: Session, discord_id: str) -> GuildRole:
    player_id = _get_player_id(session, discord_id)
    return _get_membership(session, player_id).role


def can_withdraw(session: Session, discord_id: str) -> bool:
    return get_member_role(session, discord_id) in (GuildRole.officer, GuildRole.captain)


def can_manage_members(session: Session, discord_id: str) -> bool:
    return get_member_role(session, discord_id) == GuildRole.captain


def create_guild(session: Session, name: str, captain_discord_id: str) -> Guild:
    if session.scalar(select(Guild).where(Guild.name == name)):
        raise ValueError(f"Guild '{name}' already exists")

    captain_id = _get_player_id(session, captain_discord_id)

    if session.scalar(select(GuildMember).where(GuildMember.player_id == captain_id)):
        raise ValueError("You are already in a guild")

    guild = Guild(name=name)
    session.add(guild)
    session.flush()

    session.add(Account(owner_type=AccountType.guild, owner_id=guild.id, balance=Decimal("0")))
    session.add(GuildMember(guild_id=guild.id, player_id=captain_id, role=GuildRole.captain))
    session.commit()
    return guild


def add_member(session: Session, requestor_discord_id: str, new_discord_id: str):
    if not can_manage_members(session, requestor_discord_id):
        raise PermissionError("Only captains can add members")

    requestor_id = _get_player_id(session, requestor_discord_id)
    new_player_id = _get_player_id(session, new_discord_id)

    requestor_membership = _get_membership(session, requestor_id)

    if session.scalar(select(GuildMember).where(GuildMember.player_id == new_player_id)):
        raise ValueError("That player is already in a guild")

    session.add(GuildMember(
        guild_id=requestor_membership.guild_id,
        player_id=new_player_id,
        role=GuildRole.member,
    ))
    session.commit()


def remove_member(session: Session, requestor_discord_id: str, target_discord_id: str):
    if requestor_discord_id == target_discord_id:
        raise ValueError("Use leave_guild to remove yourself")
    if not can_manage_members(session, requestor_discord_id):
        raise PermissionError("Only captains can remove members")

    requestor_id = _get_player_id(session, requestor_discord_id)
    target_id = _get_player_id(session, target_discord_id)

    requestor_membership = _get_membership(session, requestor_id)
    target_membership = session.scalar(
        select(GuildMember).where(
            GuildMember.guild_id == requestor_membership.guild_id,
            GuildMember.player_id == target_id,
        )
    )

    if not target_membership:
        raise ValueError("That player is not in your guild")
    if target_membership.role == GuildRole.captain:
        raise ValueError("Cannot remove the captain")

    session.delete(target_membership)
    session.commit()


def leave_guild(session: Session, discord_id: str):
    player_id = _get_player_id(session, discord_id)
    membership = _get_membership(session, player_id)

    if membership.role == GuildRole.captain:
        raise ValueError("Captains cannot leave — transfer captaincy first or disband the guild")

    session.delete(membership)
    session.commit()


def get_guild_members(session: Session, discord_id: str) -> list[tuple[Player, GuildMember]]:
    """Returns all members of the caller's guild with their membership info."""
    player_id = _get_player_id(session, discord_id)
    membership = _get_membership(session, player_id)

    rows = session.execute(
        select(Player, GuildMember)
        .join(GuildMember, GuildMember.player_id == Player.id)
        .where(GuildMember.guild_id == membership.guild_id)
        .order_by(GuildMember.role)
    ).all()
    return rows


def get_all_guilds(session: Session) -> list[tuple[Guild, Decimal]]:
    """Returns all guilds with their account balances, sorted by balance descending."""
    rows = session.execute(
        select(Guild, Account.balance)
        .join(Account, Account.owner_id == Guild.id)
        .where(Account.owner_type == AccountType.guild)
        .order_by(Account.balance.desc())
    ).all()
    return rows


def transfer_captaincy(session: Session, captain_discord_id: str, new_captain_discord_id: str):
    if not can_manage_members(session, captain_discord_id):
        raise PermissionError("Only the captain can transfer captaincy")

    captain_id = _get_player_id(session, captain_discord_id)
    new_captain_id = _get_player_id(session, new_captain_discord_id)

    captain_membership = _get_membership(session, captain_id)
    new_captain_membership = session.scalar(
        select(GuildMember).where(
            GuildMember.guild_id == captain_membership.guild_id,
            GuildMember.player_id == new_captain_id,
        )
    )

    if not new_captain_membership:
        raise ValueError("That player is not in your guild")

    captain_membership.role = GuildRole.officer
    new_captain_membership.role = GuildRole.captain
    session.commit()


def disband_guild(session: Session, captain_discord_id: str) -> str:
    """Returns the guild name so the caller can use it in messages."""
    captain_id = _get_player_id(session, captain_discord_id)
    membership = session.scalar(
        select(GuildMember).where(GuildMember.player_id == captain_id)
    )
    if not membership or membership.role != GuildRole.captain:
        raise PermissionError("Only the captain can disband the guild")

    guild_id = membership.guild_id
    guild = session.get(Guild, guild_id)
    guild_name = guild.name

    guild_account = session.scalar(
        select(Account).where(
            Account.owner_type == AccountType.guild,
            Account.owner_id == guild_id,
        )
    )
    if guild_account and guild_account.balance > 0:
        raise ValueError("Drain the guild account before disbanding")

    members = session.scalars(
        select(GuildMember).where(GuildMember.guild_id == guild_id)
    ).all()
    for m in members:
        session.delete(m)

    if guild_account:
        session.delete(guild_account)

    session.delete(guild)
    session.commit()
    return guild_name


def set_member_role(session: Session, captain_discord_id: str, target_discord_id: str, new_role: GuildRole):
    if captain_discord_id == target_discord_id:
        raise ValueError("You cannot change your own role")
    if not can_manage_members(session, captain_discord_id):
        raise PermissionError("Only the captain can change member roles")

    captain_id = _get_player_id(session, captain_discord_id)
    target_id = _get_player_id(session, target_discord_id)

    captain_membership = _get_membership(session, captain_id)
    target_membership = session.scalar(
        select(GuildMember).where(
            GuildMember.guild_id == captain_membership.guild_id,
            GuildMember.player_id == target_id,
        )
    )

    if not target_membership:
        raise ValueError("That player is not in your guild")
    if new_role == GuildRole.captain:
        raise ValueError("Use /transfer_captaincy to transfer leadership")

    target_membership.role = new_role
    session.commit()