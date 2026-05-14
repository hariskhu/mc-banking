from pydantic import BaseModel, ConfigDict
from decimal import Decimal
from datetime import datetime

class AccountResponse(BaseModel):
    id: int
    owner_type: str
    balance: Decimal
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)