import enum
from decimal import Decimal
from sqlalchemy import Numeric, Enum, ForeignKey, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class TransactionType(enum.Enum):
    transfer   = "transfer"
    deposit    = "deposit"
    withdrawal = "withdrawal"
    fee        = "fee"

class Transaction(Base):
    __tablename__ = "transactions"

    id:           Mapped[int]             = mapped_column(primary_key=True)
    from_account: Mapped[int | None]      = mapped_column(ForeignKey("accounts.id"), nullable=True)
    to_account:   Mapped[int | None]      = mapped_column(ForeignKey("accounts.id"), nullable=True)
    amount:       Mapped[Decimal]         = mapped_column(Numeric(18, 2), nullable=False)
    type:         Mapped[TransactionType] = mapped_column(Enum(TransactionType), nullable=False)
    note:         Mapped[str | None]      = mapped_column(String(256), nullable=True)
    created_at:   Mapped[DateTime]        = mapped_column(DateTime, server_default=func.now())