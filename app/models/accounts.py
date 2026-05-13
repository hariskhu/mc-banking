# app/models/account.py
from sqlalchemy import Numeric, Enum, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from decimal import Decimal
import enum

class AccountType(enum.Enum):
    player = "player"
    guild  = "guild"

class Account(Base):
    __tablename__ = "accounts"

    id:          Mapped[int]         = mapped_column(primary_key=True)
    owner_type:  Mapped[AccountType] = mapped_column(Enum(AccountType), nullable=False)
    owner_id:    Mapped[int]         = mapped_column(ForeignKey("players.id"), nullable=False)
    balance:     Mapped[Decimal]     = mapped_column(Numeric(18, 2), default=0, nullable=False)
    created_at:  Mapped[DateTime]    = mapped_column(DateTime, server_default=func.now())