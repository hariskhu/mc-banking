import models.players as pm
from app.database import get_db
from sqlalchemy import text
from sqlalchemy.orm import Session

def get_player(db: Session, entry: pm.PlayerGet):
    query = text("SELECT * FROM players WHERE discord_id = :discord_id")
    return db.query(query, entry.model_dump())

def create_player(db: Session, entry: pm.PlayerCreate):
    exists_query = text("IF EXISTS (SELECT 1 FROM players WHERE discord_id = :discord_id)")
    exists = db.query(exists_query, {'discord_id': entry.discord_id})
    print(exists)
    if exists:
        query = text("""
                     INSERT INTO players (discord_id, discord_username)
                     VALUES (:discord_id, :discord_username)
                     """
                    )
        return db.query(query, entry.model_dump())


if __name__ == "__main__":
    create_player()