import models.guilds as gm
from models.enums import GuildRoleEnum
from players import player_exists, get_player
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import HTTPException

# Helpers

# Funcs
def create_guild(db: Session, entry: gm.GuildCreate):
    '''Creates a new guild with the creator as leader/captain.'''
    player = get_player(db, entry.leader_id)
    curr_guild_id = player._mapping['leader_id']
    if curr_guild_id is not None:
        raise HTTPException(status_code=409, detail="Player is already in a guild.")

    new_guild = db.execute(
        text("INSERT INTO guilds (leader_id, name) VALUES (:leader_discord_id, :name);"),
        entry.model_dump()
    ).fetchone()

    db.execute(
        text("UPDATE players SET guild_id = :new_guild_id WHERE discord_id = :leader_discord_id;"),
        {
            'new_guild_id': new_guild.leader_id, 
            'leader_discord_id': entry.leader_id
        }
    )

    db.execute(
        text("""
             INSERT INTO guild_roles (guild_id, player_id, role, granted_by)
             VALUES (:new_guild_id, :leader_discord_id, :leader_role, :leader_discord_id);
             """),
        {
            'new_guild_id': new_guild.leader_id,
            'leader_discord_id': entry.leader_id,
            'leader_role': GuildRoleEnum('captain')
        }
    )

    db.commit()
    return {"status": "created"}