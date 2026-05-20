import enum
from sqlalchemy import String, ForeignKey, DateTime, Enum, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class WithdrawalStatus(enum.Enum):
    pending   = "pending"
    confirmed = "confirmed"
    failed    = "failed"

class PendingWithdrawal(Base):
    __tablename__ = "pending_withdrawals"

    id:           Mapped[int]              = mapped_column(primary_key=True)
    discord_id:   Mapped[str]              = mapped_column(String(32), nullable=False)
    terminal_id:  Mapped[int]              = mapped_column(ForeignKey("terminals.id"), nullable=False)
    items:        Mapped[str]              = mapped_column(String(1024), nullable=False)
    status:       Mapped[WithdrawalStatus] = mapped_column(Enum(WithdrawalStatus), default=WithdrawalStatus.pending, nullable=False)
    created_at:   Mapped[DateTime]         = mapped_column(DateTime, server_default=func.now())
    confirmed_at: Mapped[DateTime | None]  = mapped_column(DateTime, nullable=True)