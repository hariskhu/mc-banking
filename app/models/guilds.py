from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Annotated
from models.enums import GuildRoleEnum
from datetime import datetime

class GuildGet(BaseModel):
    guild_id: int

class GuildCreate(BaseModel):
    leader_id: str
    name: str