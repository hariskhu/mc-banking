import models.players as pm
from database import get_db
from sqlalchemy import text
from sqlalchemy.orm import Session

def get_player(db: Session, entry: pm.PlayerGet):
    query = text("SELECT * FROM players WHERE discord_id = :discord_id")
    return db.execute(query, entry.model_dump()).fetchone()

def create_player(db: Session, entry: pm.PlayerCreate):
    exists = db.execute(
        text("SELECT 1 FROM players WHERE discord_id = :discord_id"),
        {"discord_id": entry.discord_id}
    ).fetchone()

    if not exists:
        db.execute(
            text("""
                INSERT INTO players (discord_id, discord_username)
                VALUES (:discord_id, :discord_username)
                """),
            entry.model_dump()
        )
        db.commit()