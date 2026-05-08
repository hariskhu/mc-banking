import models.players as pm
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import HTTPException

# Helpers
def player_exists(db: Session, discord_id: str) -> bool:
    '''Returns a boolean based on if a player exists in the database.'''
    return db.execute(
        text("SELECT 1 FROM players WHERE discord_id = :discord_id"),
        {"discord_id": discord_id}
    ).fetchone() is not None

def get_player_with_id(db: Session, discord_id: str):
    '''Retrieves a player based off their discord ID.'''
    '''Returns a row for a player.'''
    if not player_exists(db, discord_id):
        raise HTTPException(status_code=404, detail="Player is not in the database.")
    query = text("SELECT * FROM players WHERE discord_id = :discord_id")
    return db.execute(query, {"discord_id": discord_id}).fetchone()

def get_player_with_guild(db: Session, discord_id: str):
    if not player_exists(db, discord_id):
        raise HTTPException(status=404, detail="Player does not exist in the database.")
    return db.execute(
        text("""
            SELECT 
                p.*,
                g.name AS guild_name,
                g.balance AS guild_balance,
                gr.role AS guild_role
            FROM players p
            LEFT JOIN guilds g ON g.id = p.guild_id
            LEFT JOIN guild_roles gr ON gr.player_id = p.id AND gr.guild_id = p.guild_id
            WHERE p.discord_id = :discord_id
        """),
        {"discord_id": discord_id}
    ).fetchone()

def create_player(db: Session, entry: pm.PlayerCreate):
    '''Creates a new player in the database.'''
    if player_exists(db, entry.discord_id):
        raise HTTPException(status_code=409, detail="Player has already registered.")
    
    db.execute(
        text("""
             INSERT INTO players (discord_id, discord_username)
             VALUES (:discord_id, :discord_username)
             """),
        entry.model_dump()
    )
    db.commit()
    return {"status": "created"}

# Funcs
def get_player(db: Session, entry: pm.PlayerGet):
    '''Returns a row for a player.'''
    if not player_exists(db, entry.discord_id):
        raise HTTPException(status_code=404, detail="Player is not in the database.")
    query = text("SELECT * FROM players WHERE discord_id = :discord_id")
    return db.execute(query, {"discord_id": entry.discord_id}).fetchone()

def player_to_player_transfer(db: Session, entry: pm.PlayerToPlayerTransfer):
    if entry.sender_discord_id == entry.receiver_discord_id:
        raise HTTPException(status_code=400, detail="Cannot transfer to yourself")

    sender = get_player_with_id(db, entry.sender_discord_id)
    receiver = get_player_with_id(db, entry.receiver_discord_id)

    result = db.execute(
        text("""
            UPDATE players
            SET balance = balance - :transfer_amount
            WHERE discord_id = :sender_discord_id
              AND balance >= :transfer_amount
        """),
        entry.model_dump()
    )

    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=402, detail="Insufficient balance")

    db.execute(
        text("""
            UPDATE players
            SET balance = balance + :transfer_amount
            WHERE discord_id = :receiver_discord_id
        """),
        entry.model_dump()
    )

    db.execute(
        text("""
            INSERT INTO transactions 
                (type, from_entity_type, from_entity_id, to_entity_type, to_entity_id, amount)
            VALUES 
                ('transfer', 'player', :sender_id, 'player', :receiver_id, :transfer_amount)
        """),
        {
            'sender_id': sender._mapping['id'],
            'receiver_id': receiver._mapping['id'],
            'transfer_amount': entry.transfer_amount
        }
    )

    db.commit()
    return {"status": "successful"}

    db.commit()
    return {"status": "successful"}