from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class Player(Base):
    __tablename__ = "players"

    id:           Mapped[int] = mapped_column(primary_key=True)
    discord_id:   Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    mc_username:  Mapped[str] = mapped_column(String(64), nullable=True)
    created_at:   Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())