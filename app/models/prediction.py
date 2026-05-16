import enum
from decimal import Decimal
from sqlalchemy import Numeric, Enum, ForeignKey, DateTime, String, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class PredictionSide(enum.Enum):
    yes = "yes"
    no = "no"

class Prediction(Base):
    __tablename__ = "predictions"

    id:         Mapped[int]  = mapped_column(primary_key=True)
    question:   Mapped[str]  = mapped_column(String(256), nullable=False)
    created_by: Mapped[str]  = mapped_column(String(32), nullable=False)  # discord_id
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    closed:     Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    outcome:    Mapped[PredictionSide | None] = mapped_column(Enum(PredictionSide), nullable=True)

class PredictionBet(Base):
    __tablename__ = "prediction_bets"

    id:            Mapped[int]            = mapped_column(primary_key=True)
    prediction_id: Mapped[int]            = mapped_column(ForeignKey("predictions.id"), nullable=False)
    discord_id:    Mapped[str]            = mapped_column(String(32), nullable=False)
    amount:        Mapped[Decimal]        = mapped_column(Numeric(18, 4), nullable=False)
    side:          Mapped[PredictionSide] = mapped_column(Enum(PredictionSide), nullable=False)
    created_at:    Mapped[DateTime]       = mapped_column(DateTime, server_default=func.now())