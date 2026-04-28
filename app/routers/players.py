import models.players as pm
from app.crud import users as crud
from app.database import get_db
from fastapi import APIRouter, Depends
from sqlalchemy import Session

router = APIRouter()

@router.get("/", response_model=pm.PlayerInDB)
async def get_user(entry: pm.PlayerGet, db: Session = Depends(get_db)):
    return crud.get_user(db, entry)

@router.post("/")
async def create_user(entry: pm.PlayerInDB, db: Session = Depends(get_db)):
    return crud.create_user(db, entry)