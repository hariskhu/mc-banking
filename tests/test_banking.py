# tests/test_banking.py
import pytest
from decimal import Decimal
from app.models.player import Player
from app.models.account import Account, AccountType
from app.models.transaction import Transaction, TransactionType
from app.services.banking import (
    get_player_bal,
    player_transfer,
    deposit,
    withdraw,
    get_transaction_history,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def player_a(session):
    p = Player(discord_id="111", mc_username="alice")
    session.add(p)
    session.flush()
    a = Account(owner_type=AccountType.player, owner_id=p.id, balance=Decimal("100.00"))
    session.add(a)
    session.commit()
    return p

@pytest.fixture
def player_b(session):
    p = Player(discord_id="222", mc_username="bob")
    session.add(p)
    session.flush()
    a = Account(owner_type=AccountType.player, owner_id=p.id, balance=Decimal("50.00"))
    session.add(a)
    session.commit()
    return p

@pytest.fixture
def broke_player(session):
    p = Player(discord_id="333", mc_username="charlie")
    session.add(p)
    session.flush()
    a = Account(owner_type=AccountType.player, owner_id=p.id, balance=Decimal("0.00"))
    session.add(a)
    session.commit()
    return p


# ── get_player_bal ────────────────────────────────────────────────────────────

def test_get_player_bal(session, player_a):
    assert get_player_bal(session, "111") == Decimal("100.00")

def test_get_player_bal_unknown_discord_id(session):
    with pytest.raises(ValueError, match="No player account found"):
        get_player_bal(session, "nonexistent")


# ── deposit ───────────────────────────────────────────────────────────────────

def test_deposit_increases_balance(session, player_a):
    deposit(session, "111", Decimal("25.00"))
    assert get_player_bal(session, "111") == Decimal("125.00")

def test_deposit_records_transaction(session, player_a):
    deposit(session, "111", Decimal("25.00"), note="test deposit")
    txn = session.query(Transaction).filter_by(type=TransactionType.deposit).first()
    assert txn is not None
    assert txn.from_account is None
    assert txn.amount == Decimal("25.00")
    assert txn.note == "test deposit"

def test_deposit_zero_raises(session, player_a):
    with pytest.raises(ValueError, match="must be positive"):
        deposit(session, "111", Decimal("0.00"))

def test_deposit_negative_raises(session, player_a):
    with pytest.raises(ValueError, match="must be positive"):
        deposit(session, "111", Decimal("-10.00"))

def test_deposit_unknown_player_raises(session):
    with pytest.raises(ValueError, match="No player account found"):
        deposit(session, "nonexistent", Decimal("10.00"))

def test_deposit_strips_note_whitespace(session, player_a):
    deposit(session, "111", Decimal("10.00"), note="  padded  ")
    txn = session.query(Transaction).filter_by(type=TransactionType.deposit).first()
    assert txn.note == "padded"

def test_deposit_truncates_long_note(session, player_a):
    long_note = "x" * 300
    deposit(session, "111", Decimal("10.00"), note=long_note)
    txn = session.query(Transaction).filter_by(type=TransactionType.deposit).first()
    assert len(txn.note) == 255


# ── withdraw ──────────────────────────────────────────────────────────────────

def test_withdraw_decreases_balance(session, player_a):
    withdraw(session, "111", Decimal("40.00"))
    assert get_player_bal(session, "111") == Decimal("60.00")

def test_withdraw_records_transaction(session, player_a):
    withdraw(session, "111", Decimal("40.00"), note="test withdrawal")
    txn = session.query(Transaction).filter_by(type=TransactionType.withdrawal).first()
    assert txn is not None
    assert txn.to_account is None
    assert txn.amount == Decimal("40.00")

def test_withdraw_exact_balance(session, player_a):
    withdraw(session, "111", Decimal("100.00"))
    assert get_player_bal(session, "111") == Decimal("0.00")

def test_withdraw_insufficient_funds(session, broke_player):
    with pytest.raises(ValueError, match="Insufficient funds"):
        withdraw(session, "333", Decimal("1.00"))

def test_withdraw_zero_raises(session, player_a):
    with pytest.raises(ValueError, match="must be positive"):
        withdraw(session, "111", Decimal("0.00"))

def test_withdraw_negative_raises(session, player_a):
    with pytest.raises(ValueError, match="must be positive"):
        withdraw(session, "111", Decimal("-10.00"))

def test_withdraw_unknown_player_raises(session):
    with pytest.raises(ValueError, match="No player account found"):
        withdraw(session, "nonexistent", Decimal("10.00"))


# ── player_transfer ───────────────────────────────────────────────────────────

def test_transfer_moves_funds(session, player_a, player_b):
    player_transfer(session, "111", "222", Decimal("30.00"))
    assert get_player_bal(session, "111") == Decimal("70.00")
    assert get_player_bal(session, "222") == Decimal("80.00")

def test_transfer_records_transaction(session, player_a, player_b):
    player_transfer(session, "111", "222", Decimal("30.00"), note="payment")
    txn = session.query(Transaction).filter_by(type=TransactionType.transfer).first()
    assert txn is not None
    assert txn.amount == Decimal("30.00")
    assert txn.note == "payment"

def test_transfer_exact_balance(session, player_a, player_b):
    player_transfer(session, "111", "222", Decimal("100.00"))
    assert get_player_bal(session, "111") == Decimal("0.00")
    assert get_player_bal(session, "222") == Decimal("150.00")

def test_transfer_insufficient_funds(session, broke_player, player_b):
    with pytest.raises(ValueError, match="Insufficient funds"):
        player_transfer(session, "333", "222", Decimal("1.00"))

def test_transfer_to_self_raises(session, player_a):
    with pytest.raises(ValueError, match="Cannot transfer to yourself"):
        player_transfer(session, "111", "111", Decimal("10.00"))

def test_transfer_zero_raises(session, player_a, player_b):
    with pytest.raises(ValueError, match="must be positive"):
        player_transfer(session, "111", "222", Decimal("0.00"))

def test_transfer_negative_raises(session, player_a, player_b):
    with pytest.raises(ValueError, match="must be positive"):
        player_transfer(session, "111", "222", Decimal("-10.00"))

def test_transfer_unknown_sender_raises(session, player_b):
    with pytest.raises(ValueError, match="not registered"):
        player_transfer(session, "nonexistent", "222", Decimal("10.00"))

def test_transfer_unknown_recipient_raises(session, player_a):
    with pytest.raises(ValueError, match="not registered"):
        player_transfer(session, "111", "nonexistent", Decimal("10.00"))

def test_transfer_does_not_affect_third_party(session, player_a, player_b, broke_player):
    player_transfer(session, "111", "222", Decimal("30.00"))
    assert get_player_bal(session, "333") == Decimal("0.00")


# ── get_transaction_history ───────────────────────────────────────────────────

def test_transaction_history_includes_sent(session, player_a, player_b):
    player_transfer(session, "111", "222", Decimal("10.00"))
    history = get_transaction_history(session, "111")
    assert len(history) == 1

def test_transaction_history_includes_received(session, player_a, player_b):
    player_transfer(session, "111", "222", Decimal("10.00"))
    history = get_transaction_history(session, "222")
    assert len(history) == 1

def test_transaction_history_ordered_newest_first(session, player_a, player_b):
    player_transfer(session, "111", "222", Decimal("10.00"))
    player_transfer(session, "111", "222", Decimal("20.00"))
    history = get_transaction_history(session, "111")
    assert history[0].amount == Decimal("20.00")
    assert history[1].amount == Decimal("10.00")

def test_transaction_history_respects_limit(session, player_a, player_b):
    for _ in range(10):
        player_transfer(session, "111", "222", Decimal("1.00"))
        # give bob funds back so alice can keep transferring
        player_transfer(session, "222", "111", Decimal("1.00"))
    history = get_transaction_history(session, "111", limit=5)
    assert len(history) == 5

def test_transaction_history_empty_for_new_account(session, player_a):
    history = get_transaction_history(session, "111")
    assert history == []

def test_transaction_history_unknown_player_raises(session):
    with pytest.raises(ValueError, match="No player account found"):
        get_transaction_history(session, "nonexistent")