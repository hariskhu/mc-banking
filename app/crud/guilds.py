import models.guilds as gm
from models.enums import GuildRoleEnum
from crud.players import get_player_with_id
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import HTTPException

# Helpers
def is_in_guild(db: Session, discord_id: str) -> bool:
    '''Returns a boolean based on whether or not a player is in a guild.'''
    player = get_player_with_id(db, discord_id)
    curr_guild_id = player._mapping['discord_id']
    return curr_guild_id is not None

# Funcs
def create_guild(db: Session, entry: gm.GuildCreate):
    '''Creates a new guild with the creator as leader/captain.'''
    player = get_player_with_id(db, entry.leader_discord_id)
    curr_guild_id = player._mapping['discord_id']
    leader_id = player._mapping['id']

    if curr_guild_id is not None:
        raise HTTPException(status_code=409, detail="Player is already in a guild.")

    new_guild = db.execute(
        text("INSERT INTO guilds (leader_id, name) VALUES (:leader_discord_id, :name) RETURNING *;"),
        entry.model_dump()
    ).fetchone()

    db.execute(
        text("UPDATE players SET guild_id = :new_guild_id WHERE discord_id = :leader_discord_id;"),
        {
            'new_guild_id': new_guild.id,
            'leader_discord_id': entry.leader_discord_id
        }
    )

    db.execute(
        text("""
             INSERT INTO guild_roles (guild_id, player_id, role, granted_by)
             VALUES (:new_guild_id, :leader_id, :leader_role, :leader_id);
             """),
        {
            'new_guild_id': new_guild.id,
            'leader_id': leader_id,
            'leader_role': GuildRoleEnum('captain')
        }
    )

    db.commit()
    return {"status": "created"}

def get_guilds(db: Session):
    '''Returns all rows of the guilds table.'''
    return db.execute(text("SELECT * FROM guilds")).fetchall()