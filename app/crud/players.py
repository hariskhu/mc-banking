import models.players as pm
from database import get_db
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import HTTPException

def exists(db: Session, discord_id: str) -> bool:
    '''Returns a boolean based on if a player exists in the database.'''
    return db.execute(
        text("SELECT 1 FROM players WHERE discord_id = :discord_id"),
        {"discord_id": discord_id}
    ).fetchone() is not None

def get_player(db: Session, entry: pm.PlayerGet):
    '''Returns a row for a player.'''
    if not exists(db, entry.discord_id):
        raise HTTPException(status_code=404, detail="Player is not in the database.")
    query = text("SELECT * FROM players WHERE discord_id = :discord_id")
    return db.execute(query, entry.discord_id).fetchone()

def create_player(db: Session, entry: pm.PlayerCreate):
    if exists(db, entry.discord_id):
        raise HTTPException(status_code=409, detail="Player has already registered.")
    
    db.execute(
        text("INSERT INTO players (discord_id, discord_username) VALUES (:discord_id, :discord_username)"),
        entry.model_dump()
    )
    db.commit()
    return {"status": "created"}