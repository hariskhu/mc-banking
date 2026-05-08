import models.guilds as gm
import crud.guilds as crud
from database import get_db
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

router = APIRouter()


# GET Methods
@router.get("/all", response_model=gm.GuildLeaderboard)
async def get_guilds(db: Session = Depends(get_db)):
    data = crud.get_guilds(db)
    return {'items': data}


# POST Methods
@router.post("/")
async def create_guild(entry: gm.GuildCreate, db: Session = Depends(get_db)):
    return crud.create_guild(db, entry)

@router.post("/leave", response_model=gm.GuildLeaveReturn)
async def leave_guild(entry: gm.GuildLeave, db: Session = Depends(get_db)):
    return crud.leave_guild(db, entry)

@router.post("/join")
async def join(entry: gm.GuildJoin, db: Session = Depends(get_db)):
    return crud.join_guild(db, entry)