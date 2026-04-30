from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Annotated, List
from models.enums import GuildStatusEnum
from datetime import datetime

class GuildGet(BaseModel):
    guild_id: int

class GuildCreate(BaseModel):
    leader_discord_id: str
    name: str

class GuildLeaderboardRow(BaseModel):
    id: int
    name: str
    leader_id: str
    balance: Annotated[
        Decimal,
        Field(max_digits=12, decimal_places=2)
    ]
    status: GuildStatusEnum
    created_at: datetime

class GuildLeaderboard(BaseModel):
    items: List[GuildLeaderboardRow]