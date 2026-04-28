from pydantic import BaseModel
from decimal import Decimal
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
    balance: Decimal
    created_at: datetime