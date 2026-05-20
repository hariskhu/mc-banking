import enum
from decimal import Decimal
from sqlalchemy import String, Boolean, Numeric, ForeignKey, DateTime, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class TerminalType(enum.Enum):
    bank    = "bank"
    shop    = "shop"
    buyback = "buyback"
    service = "service"


class ServiceSide(enum.Enum):
    north = "north"
    south = "south"
    east  = "east"
    west  = "west"


class Terminal(Base):
    __tablename__ = "terminals"

    id:         Mapped[int]          = mapped_column(primary_key=True)
    name:       Mapped[str]          = mapped_column(String(64), unique=True, nullable=False)
    type:       Mapped[TerminalType] = mapped_column(nullable=False)
    token:      Mapped[str]          = mapped_column(String(64), unique=True, nullable=False)
    location:   Mapped[str | None]   = mapped_column(String(256), nullable=True)
    guild_id:   Mapped[int | None]   = mapped_column(ForeignKey("guilds.id"), nullable=True)
    active:     Mapped[bool]         = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[DateTime]     = mapped_column(DateTime, server_default=func.now())

    shop_listings:    Mapped[list["ShopListing"]]    = relationship(back_populates="terminal")
    buyback_listings: Mapped[list["BuybackListing"]] = relationship(back_populates="terminal")
    service_listings: Mapped[list["ServiceListing"]] = relationship(back_populates="terminal")


class ShopListing(Base):
    __tablename__ = "shop_listings"

    id:          Mapped[int]     = mapped_column(primary_key=True)
    terminal_id: Mapped[int]     = mapped_column(ForeignKey("terminals.id"), nullable=False)
    item_name:   Mapped[str]     = mapped_column(String(128), nullable=False)
    nbt:         Mapped[str | None] = mapped_column(String(1024), nullable=True)
    quantity:    Mapped[int]     = mapped_column(Integer, nullable=False)
    price:       Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    active:      Mapped[bool]    = mapped_column(Boolean, default=True, nullable=False)

    terminal: Mapped["Terminal"] = relationship(back_populates="shop_listings")


class BuybackListing(Base):
    __tablename__ = "buyback_listings"

    id:             Mapped[int]          = mapped_column(primary_key=True)
    terminal_id:    Mapped[int]          = mapped_column(ForeignKey("terminals.id"), nullable=False)
    mc_id:          Mapped[str]          = mapped_column(String(128), nullable=False)
    price_per_item: Mapped[Decimal]      = mapped_column(Numeric(18, 4), nullable=False)
    limit:          Mapped[int | None]   = mapped_column(Integer, nullable=True)
    purchased:      Mapped[int]          = mapped_column(Integer, default=0, nullable=False)
    active:         Mapped[bool]         = mapped_column(Boolean, default=True, nullable=False)

    terminal: Mapped["Terminal"] = relationship(back_populates="buyback_listings")


class ServiceListing(Base):
    __tablename__ = "service_listings"

    __table_args__ = (
        UniqueConstraint("terminal_id", "side", name="uq_service_terminal_side"),
    )

    id:              Mapped[int]         = mapped_column(primary_key=True)
    terminal_id:     Mapped[int]         = mapped_column(ForeignKey("terminals.id"), nullable=False)
    name:            Mapped[str]         = mapped_column(String(64), nullable=False)
    side:            Mapped[ServiceSide] = mapped_column(nullable=False)
    signal_strength: Mapped[int]         = mapped_column(Integer, nullable=False)
    duration_ticks:  Mapped[int]         = mapped_column(Integer, nullable=False)
    price:           Mapped[Decimal]     = mapped_column(Numeric(18, 4), nullable=False)
    active:          Mapped[bool]        = mapped_column(Boolean, default=True, nullable=False)

    terminal: Mapped["Terminal"] = relationship(back_populates="service_listings")