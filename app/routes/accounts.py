from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_session
from app.services.banking import get_player_bal

router = APIRouter(prefix="/accounts")

@router.get("/{discord_id}/balance")
def get_balance(discord_id: str, session: Session = Depends(get_session)):
    try:
        balance = get_player_bal(session, discord_id)
        return {"discord_id": discord_id, "balance": str(balance)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))