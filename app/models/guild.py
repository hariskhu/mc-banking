from sqlalchemy import String, Enum, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum

class GuildRole(enum.Enum):
    member  = "member"
    officer = "officer"
    captain = "captain"

class Guild(Base):
    __tablename__ = "guilds"

    id:         Mapped[int] = mapped_column(primary_key=True)
    name:       Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    members: Mapped[list["GuildMember"]] = relationship(back_populates="guild")

class GuildMember(Base):
    __tablename__ = "guild_members"

    guild_id:   Mapped[int]       = mapped_column(ForeignKey("guilds.id"), primary_key=True)
    player_id:  Mapped[int]       = mapped_column(ForeignKey("players.id"), primary_key=True)
    role:       Mapped[GuildRole] = mapped_column(Enum(GuildRole), nullable=False, default=GuildRole.member)
    joined_at:  Mapped[DateTime]  = mapped_column(DateTime, server_default=func.now())

    guild:  Mapped["Guild"]  = relationship(back_populates="members")
    player: Mapped["Player"] = relationship()