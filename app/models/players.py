from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Annotated
from models.enums import GuildRoleEnum
from datetime import datetime

class PlayerGet(BaseModel):
    discord_id: str

class PlayerCreate(BaseModel):
    discord_id: str
    discord_username: str

class PlayerInDB(BaseModel):
    id: int
    discord_id: str
    discord_username: str
    mc_username: str | None = None
    guild_id: int | None = None
    guild_role: GuildRoleEnum | None = None
    balance: Annotated[
        Decimal,
        Field(max_digits=12, decimal_places=2)
    ]
    created_at: datetime

class PlayerToPlayerTransfer(BaseModel):
    sender_discord_id: str
    receiver_discord_id: str
    transfer_amount: Annotated[
        Decimal,
        Field(max_digits=12, decimal_places=2)
    ]

class PlayerWithGuild(BaseModel):
    id: int
    discord_id: str
    discord_username: str
    mc_username: str | None = None
    balance: Decimal
    guild_id: int | None = None
    guild_name: str | None = None
    guild_balance: Decimal | None = None
    guild_role: GuildRoleEnum | None = None
    created_at: datetime