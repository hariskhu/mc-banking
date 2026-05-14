# tests/test_guild.py
import pytest
from decimal import Decimal
from app.models.player import Player
from app.models.account import Account, AccountType
from app.models.guild import Guild, GuildMember, GuildRole
from app.services.guild import (
    get_member_role,
    can_withdraw,
    can_manage_members,
    create_guild,
    add_member,
    remove_member,
    leave_guild,
    transfer_captaincy,
    disband_guild,
)
from app.services.banking import (
    get_player_bal, 
    get_guild_bal, 
    guild_deposit, 
    guild_withdraw
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def captain(session):
    p = Player(discord_id="111", mc_username="alice")
    session.add(p)
    session.flush()
    session.add(Account(owner_type=AccountType.player, owner_id=p.id, balance=Decimal("200.00")))
    session.commit()
    return p

@pytest.fixture
def officer(session):
    p = Player(discord_id="222", mc_username="bob")
    session.add(p)
    session.flush()
    session.add(Account(owner_type=AccountType.player, owner_id=p.id, balance=Decimal("100.00")))
    session.commit()
    return p

@pytest.fixture
def member(session):
    p = Player(discord_id="333", mc_username="charlie")
    session.add(p)
    session.flush()
    session.add(Account(owner_type=AccountType.player, owner_id=p.id, balance=Decimal("100.00")))
    session.commit()
    return p

@pytest.fixture
def outsider(session):
    p = Player(discord_id="444", mc_username="dave")
    session.add(p)
    session.flush()
    session.add(Account(owner_type=AccountType.player, owner_id=p.id, balance=Decimal("100.00")))
    session.commit()
    return p

@pytest.fixture
def guild(session, captain, officer, member):
    """A guild with captain, one officer, and one member already set up."""
    g = create_guild(session, "TestGuild", captain.discord_id)
    add_member(session, captain.discord_id, officer.discord_id)
    add_member(session, captain.discord_id, member.discord_id)

    # Promote bob to officer
    officer_membership = session.scalar(
        __import__("sqlalchemy", fromlist=["select"]).select(GuildMember).where(
            GuildMember.player_id == officer.id
        )
    )
    officer_membership.role = GuildRole.officer
    session.commit()
    return g


# ── get_member_role ───────────────────────────────────────────────────────────

def test_captain_role(session, guild, captain):
    assert get_member_role(session, captain.discord_id) == GuildRole.captain

def test_officer_role(session, guild, officer):
    assert get_member_role(session, officer.discord_id) == GuildRole.officer

def test_member_role(session, guild, member):
    assert get_member_role(session, member.discord_id) == GuildRole.member

def test_outsider_has_no_role(session, guild, outsider):
    with pytest.raises(ValueError, match="not in a guild"):
        get_member_role(session, outsider.discord_id)

def test_unknown_player_raises(session):
    with pytest.raises(ValueError, match="not registered"):
        get_member_role(session, "nonexistent")


# ── can_withdraw / can_manage_members ─────────────────────────────────────────

def test_captain_can_withdraw(session, guild, captain):
    assert can_withdraw(session, captain.discord_id) is True

def test_officer_can_withdraw(session, guild, officer):
    assert can_withdraw(session, officer.discord_id) is True

def test_member_cannot_withdraw(session, guild, member):
    assert can_withdraw(session, member.discord_id) is False

def test_captain_can_manage_members(session, guild, captain):
    assert can_manage_members(session, captain.discord_id) is True

def test_officer_cannot_manage_members(session, guild, officer):
    assert can_manage_members(session, officer.discord_id) is False

def test_member_cannot_manage_members(session, guild, member):
    assert can_manage_members(session, member.discord_id) is False


# ── create_guild ──────────────────────────────────────────────────────────────

def test_create_guild_creates_guild(session, captain):
    g = create_guild(session, "NewGuild", captain.discord_id)
    assert g.name == "NewGuild"

def test_create_guild_creates_account(session, captain):
    g = create_guild(session, "NewGuild", captain.discord_id)
    account = session.scalar(
        __import__("sqlalchemy", fromlist=["select"]).select(Account).where(
            Account.owner_type == AccountType.guild,
            Account.owner_id == g.id,
        )
    )
    assert account is not None
    assert account.balance == Decimal("0")

def test_create_guild_assigns_captain(session, captain):
    create_guild(session, "NewGuild", captain.discord_id)
    assert get_member_role(session, captain.discord_id) == GuildRole.captain

def test_create_guild_duplicate_name_raises(session, captain, outsider):
    create_guild(session, "NewGuild", captain.discord_id)
    with pytest.raises(ValueError, match="already exists"):
        create_guild(session, "NewGuild", outsider.discord_id)

def test_create_guild_already_in_guild_raises(session, guild, captain):
    with pytest.raises(ValueError, match="already in a guild"):
        create_guild(session, "AnotherGuild", captain.discord_id)


# ── add_member ────────────────────────────────────────────────────────────────

def test_add_member_succeeds(session, guild, captain, outsider):
    add_member(session, captain.discord_id, outsider.discord_id)
    assert get_member_role(session, outsider.discord_id) == GuildRole.member

def test_add_member_default_role_is_member(session, guild, captain, outsider):
    add_member(session, captain.discord_id, outsider.discord_id)
    assert get_member_role(session, outsider.discord_id) == GuildRole.member

def test_add_member_officer_cannot_add(session, guild, officer, outsider):
    with pytest.raises(PermissionError, match="Only captains"):
        add_member(session, officer.discord_id, outsider.discord_id)

def test_add_member_member_cannot_add(session, guild, member, outsider):
    with pytest.raises(PermissionError, match="Only captains"):
        add_member(session, member.discord_id, outsider.discord_id)

def test_add_member_already_in_guild_raises(session, guild, captain, member):
    with pytest.raises(ValueError, match="already in a guild"):
        add_member(session, captain.discord_id, member.discord_id)

def test_add_member_unknown_player_raises(session, guild, captain):
    with pytest.raises(ValueError, match="not registered"):
        add_member(session, captain.discord_id, "nonexistent")


# ── remove_member ─────────────────────────────────────────────────────────────

def test_remove_member_succeeds(session, guild, captain, member):
    remove_member(session, captain.discord_id, member.discord_id)
    with pytest.raises(ValueError, match="not in a guild"):
        get_member_role(session, member.discord_id)

def test_remove_member_officer_cannot_remove(session, guild, officer, member):
    with pytest.raises(PermissionError, match="Only captains"):
        remove_member(session, officer.discord_id, member.discord_id)

def test_remove_member_cannot_remove_captain(session, guild, captain, member):
    with pytest.raises(ValueError, match="leave_guild"):
        remove_member(session, captain.discord_id, captain.discord_id)

def test_remove_member_cannot_remove_captain_via_officer(session, guild, captain, officer):
    with pytest.raises(PermissionError, match="Only captains"):
        remove_member(session, officer.discord_id, captain.discord_id)

def test_remove_member_not_in_guild_raises(session, guild, captain, outsider):
    with pytest.raises(ValueError, match="not in your guild"):
        remove_member(session, captain.discord_id, outsider.discord_id)

def test_remove_self_raises(session, guild, captain, member):
    with pytest.raises(ValueError, match="leave_guild"):
        remove_member(session, captain.discord_id, captain.discord_id)


# ── leave_guild ───────────────────────────────────────────────────────────────

def test_member_can_leave(session, guild, member):
    leave_guild(session, member.discord_id)
    with pytest.raises(ValueError, match="not in a guild"):
        get_member_role(session, member.discord_id)

def test_officer_can_leave(session, guild, officer):
    leave_guild(session, officer.discord_id)
    with pytest.raises(ValueError, match="not in a guild"):
        get_member_role(session, officer.discord_id)

def test_captain_cannot_leave(session, guild, captain):
    with pytest.raises(ValueError, match="transfer captaincy"):
        leave_guild(session, captain.discord_id)

def test_not_in_guild_raises(session, outsider):
    with pytest.raises(ValueError, match="not in a guild"):
        leave_guild(session, outsider.discord_id)


# ── transfer_captaincy ────────────────────────────────────────────────────────

def test_transfer_captaincy_succeeds(session, guild, captain, officer):
    transfer_captaincy(session, captain.discord_id, officer.discord_id)
    assert get_member_role(session, officer.discord_id) == GuildRole.captain
    assert get_member_role(session, captain.discord_id) == GuildRole.officer

def test_transfer_captaincy_to_member(session, guild, captain, member):
    transfer_captaincy(session, captain.discord_id, member.discord_id)
    assert get_member_role(session, member.discord_id) == GuildRole.captain
    assert get_member_role(session, captain.discord_id) == GuildRole.officer

def test_transfer_captaincy_officer_cannot_transfer(session, guild, officer, member):
    with pytest.raises(PermissionError, match="Only the captain"):
        transfer_captaincy(session, officer.discord_id, member.discord_id)

def test_transfer_captaincy_to_outsider_raises(session, guild, captain, outsider):
    with pytest.raises(ValueError, match="not in your guild"):
        transfer_captaincy(session, captain.discord_id, outsider.discord_id)


# ── disband_guild ─────────────────────────────────────────────────────────────

def test_disband_empty_guild(session, captain):
    create_guild(session, "EmptyGuild", captain.discord_id)
    disband_guild(session, captain.discord_id)
    with pytest.raises(ValueError, match="not in a guild"):
        get_member_role(session, captain.discord_id)

def test_disband_removes_all_members(session, guild, captain, officer, member):
    # Drain guild account first
    guild_account = session.scalar(
        __import__("sqlalchemy", fromlist=["select"]).select(Account).where(
            Account.owner_type == AccountType.guild
        )
    )
    guild_account.balance = Decimal("0")
    session.commit()

    disband_guild(session, captain.discord_id)

    for discord_id in (captain.discord_id, officer.discord_id, member.discord_id):
        with pytest.raises(ValueError, match="not in a guild"):
            get_member_role(session, discord_id)

def test_disband_with_funds_raises(session, guild, captain):
    guild_deposit(session, captain.discord_id, Decimal("50.00"))
    with pytest.raises(ValueError, match="Drain the guild account"):
        disband_guild(session, captain.discord_id)

def test_disband_officer_cannot_disband(session, guild, officer):
    with pytest.raises(PermissionError, match="Only the captain"):
        disband_guild(session, officer.discord_id)

def test_disband_member_cannot_disband(session, guild, member):
    with pytest.raises(PermissionError, match="Only the captain"):
        disband_guild(session, member.discord_id)


# ── guild_deposit / guild_withdraw (via banking service) ──────────────────────

def test_guild_deposit_increases_guild_balance(session, guild, member):
    guild_deposit(session, member.discord_id, Decimal("50.00"))
    assert get_guild_bal(session, member.discord_id) == Decimal("50.00")

def test_guild_deposit_decreases_player_balance(session, guild, member):
    guild_deposit(session, member.discord_id, Decimal("50.00"))
    assert get_player_bal(session, member.discord_id) == Decimal("50.00")

def test_guild_deposit_outsider_raises(session, guild, outsider):
    with pytest.raises(PermissionError, match="not a member"):
        guild_deposit(session, outsider.discord_id, Decimal("10.00"))

def test_guild_deposit_insufficient_funds_raises(session, guild, member):
    with pytest.raises(ValueError, match="Insufficient funds"):
        guild_deposit(session, member.discord_id, Decimal("999.00"))

def test_guild_withdraw_captain_succeeds(session, guild, captain):
    guild_deposit(session, captain.discord_id, Decimal("50.00"))
    bal_before = get_player_bal(session, captain.discord_id)
    guild_withdraw(session, captain.discord_id, Decimal("50.00"))
    assert get_player_bal(session, captain.discord_id) == bal_before + Decimal("50.00")

def test_guild_withdraw_officer_succeeds(session, guild, captain, officer):
    guild_deposit(session, captain.discord_id, Decimal("50.00"))
    bal_before = get_player_bal(session, officer.discord_id)
    guild_withdraw(session, officer.discord_id, Decimal("50.00"))
    assert get_player_bal(session, officer.discord_id) == bal_before + Decimal("50.00")

def test_guild_withdraw_member_raises(session, guild, captain, member):
    guild_deposit(session, captain.discord_id, Decimal("50.00"))
    with pytest.raises(PermissionError, match="officers and captains"):
        guild_withdraw(session, member.discord_id, Decimal("10.00"))

def test_guild_withdraw_insufficient_funds_raises(session, guild, captain):
    with pytest.raises(ValueError, match="Insufficient"):
        guild_withdraw(session, captain.discord_id, Decimal("999.00"))

def test_guild_withdraw_outsider_raises(session, guild, outsider):
    with pytest.raises(PermissionError, match="officers and captains"):
        guild_withdraw(session, outsider.discord_id, Decimal("10.00"))