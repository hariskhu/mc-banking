from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.models.prediction import Prediction, PredictionBet, PredictionSide
from app.models.player import Player
from app.models.account import Account, AccountType
from app.models.transaction import Transaction, TransactionType
from app.services.banking import _get_player_account, _get_player_id


def get_active_prediction(session: Session) -> Prediction | None:
    return session.scalar(
        select(Prediction).where(Prediction.closed == False)
    )


def create_prediction(session: Session, question: str, creator_discord_id: str) -> Prediction:
    existing = get_active_prediction(session)
    if existing:
        raise ValueError("There is already an active prediction. Close it before creating a new one.")

    prediction = Prediction(question=question, created_by=creator_discord_id)
    session.add(prediction)
    session.commit()
    return prediction


def place_bet(session: Session, discord_id: str, amount: Decimal, side: PredictionSide) -> PredictionBet:
    if amount <= 0:
        raise ValueError("Bet amount must be positive")

    prediction = get_active_prediction(session)
    if not prediction:
        raise ValueError("There is no active prediction to bet on")

    account = _get_player_account(session, discord_id)
    if account.balance < amount:
        raise ValueError("Insufficient funds")

    account.balance -= amount

    txn = Transaction(
        from_account=account.id,
        to_account=None,
        amount=amount,
        type=TransactionType.withdrawal,
        note=f"Bet on prediction #{prediction.id}: {side.value}",
    )
    session.add(txn)

    bet = PredictionBet(
        prediction_id=prediction.id,
        discord_id=discord_id,
        amount=amount,
        side=side,
    )
    session.add(bet)
    session.commit()
    return bet


def get_bets(session: Session, prediction_id: int) -> list[PredictionBet]:
    return session.scalars(
        select(PredictionBet)
        .where(PredictionBet.prediction_id == prediction_id)
        .order_by(PredictionBet.side, PredictionBet.amount.desc())
    ).all()


def get_prediction_totals(session: Session, prediction_id: int) -> dict:
    rows = session.execute(
        select(PredictionBet.side, func.sum(PredictionBet.amount))
        .where(PredictionBet.prediction_id == prediction_id)
        .group_by(PredictionBet.side)
    ).all()

    totals = {PredictionSide.yes: Decimal("0"), PredictionSide.no: Decimal("0")}
    for side, total in rows:
        totals[side] = total or Decimal("0")
    return totals


def resolve_prediction(session: Session, prediction_id: int, outcome: PredictionSide) -> dict:
    prediction = session.get(Prediction, prediction_id)
    if not prediction:
        raise ValueError("Prediction not found")
    if prediction.closed:
        raise ValueError("This prediction is already closed")

    bets = get_bets(session, prediction_id)
    totals = get_prediction_totals(session, prediction_id)

    winning_side = outcome
    losing_side = PredictionSide.no if outcome == PredictionSide.yes else PredictionSide.yes
    total_pot = totals[PredictionSide.yes] + totals[PredictionSide.no]
    winning_pot = totals[winning_side]

    # Aggregate each player's bets per side
    player_bets = {}  # discord_id -> {yes: Decimal, no: Decimal}
    for bet in bets:
        if bet.discord_id not in player_bets:
            player_bets[bet.discord_id] = {PredictionSide.yes: Decimal("0"), PredictionSide.no: Decimal("0")}
        player_bets[bet.discord_id][bet.side] += bet.amount

    results = {}  # discord_id -> {winning_bet, losing_bet, payout, net}

    if winning_pot == 0:
        _refund_all(session, bets, prediction, reason="No winners, full refund issued")
        for discord_id, sides in player_bets.items():
            total_bet = sides[PredictionSide.yes] + sides[PredictionSide.no]
            results[discord_id] = {
                "winning_bet": Decimal("0"),
                "losing_bet": Decimal("0"),
                "refund": total_bet,
                "payout": total_bet,
                "won": None,
            }
    else:
        for discord_id, sides in player_bets.items():
            winning_bet = sides[winning_side]
            losing_bet = sides[losing_side]
            payout = Decimal("0")

            if winning_bet > 0:
                share = winning_bet / winning_pot
                payout = (share * total_pot).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                account = _get_player_account(session, discord_id)
                account.balance += payout
                session.add(Transaction(
                    from_account=None,
                    to_account=account.id,
                    amount=payout,
                    type=TransactionType.deposit,
                    note=f"Prediction #{prediction.id} winnings",
                ))

            results[discord_id] = {
                "winning_bet": winning_bet,
                "losing_bet": losing_bet,
                "payout": payout,
                "won": winning_bet > 0,
            }

    prediction.closed = True
    prediction.outcome = outcome
    session.commit()
    return results


def refund_prediction(session: Session, prediction_id: int) -> list[PredictionBet]:
    """Returns the list of bets so the caller can DM participants."""
    prediction = session.get(Prediction, prediction_id)
    if not prediction:
        raise ValueError("Prediction not found")
    if prediction.closed:
        raise ValueError("This prediction is already closed")

    bets = get_bets(session, prediction_id)
    _refund_all(session, bets, prediction, reason="Prediction refunded by admin")

    prediction.closed = True
    session.commit()
    return bets


def _refund_all(session: Session, bets: list[PredictionBet], prediction: Prediction, reason: str):
    for bet in bets:
        account = _get_player_account(session, bet.discord_id)
        account.balance += bet.amount
        session.add(Transaction(
            from_account=None,
            to_account=account.id,
            amount=bet.amount,
            type=TransactionType.deposit,
            note=f"Prediction #{prediction.id} refund: {reason}",
        ))