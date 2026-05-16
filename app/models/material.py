from decimal import Decimal
from sqlalchemy import String, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class Material(Base):
    __tablename__ = "materials"

    id:            Mapped[int]     = mapped_column(primary_key=True)
    name:          Mapped[str]     = mapped_column(String(64), unique=True, nullable=False)
    mc_id:         Mapped[str]     = mapped_column(String(128), unique=True, nullable=False)  # e.g. "minecraft:diamond"
    base_price:    Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)  # price in copper at ideal supply
    ideal_supply:  Mapped[int]     = mapped_column(nullable=False)   # vault quantity considered "ideal"
    current_supply: Mapped[int]    = mapped_column(default=0, nullable=False)
    elasticity:    Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.5"), nullable=False)