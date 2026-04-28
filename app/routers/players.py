import models.players as pm
import crud.players as crud
from database import get_db
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

router = APIRouter()

@router.get("/", response_model=pm.PlayerInDB)
async def get_user(entry: pm.PlayerGet, db: Session = Depends(get_db)):
    return crud.get_player(db, entry)

@router.post("/")
async def create_user(entry: pm.PlayerCreate, db: Session = Depends(get_db)):
    return crud.create_player(db, entry)