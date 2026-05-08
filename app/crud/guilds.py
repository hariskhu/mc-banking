import models.guilds as gm
from models.enums import GuildRoleEnum
from crud.players import get_player_with_id
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import HTTPException
from decimal import Decimal

# Helpers
def in_guild(db: Session, discord_id: str) -> bool:
    '''Returns a boolean based on whether or not a player is in a guild.'''
    player = get_player_with_id(db, discord_id)
    curr_guild_id = player._mapping['guild_id']
    return curr_guild_id is not None

def remove_from_guild(db: Session, discord_id: str):
    '''Removes a player from their current guild.'''
    if not in_guild(db, discord_id):
        raise HTTPException(status_code=409, detail="Player is not in a guild.")
    
    db.execute(
        text("""
             UPDATE players SET guild_id = NULL WHERE id = :discord_id;
             DELETE FROM guild_roles WHERE player_id = :discord_id;
             """),
        {'discord_id': discord_id}
    )

    db.commit()

def guild_empty(db: Session, guild_id: int):
    '''Returns a boolean based on if there's only one guild member (the captain).'''
    rows = db.execute(
        text("""
            SELECT COUNT(*)
            FROM (
                SELECT 1
                FROM guild_roles
                WHERE guild_id = :guild_id
                LIMIT 2
            );
            """),
        {'guild_id': guild_id}
    ).fetchall()

    return len(rows) == 1


# Funcs
def create_guild(db: Session, entry: gm.GuildCreate):
    '''Creates a new guild with the creator as leader/captain.'''
    player = get_player_with_id(db, entry.leader_discord_id)
    curr_guild_id = player._mapping['guild_id']
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

def join_guild(db: Session, entry: gm.GuildJoin):
    '''Adds a player to a guild.'''
    player = get_player_with_id(db, entry.discord_id)
    player_data = player._mapping

    if player_data['guild_id'] is not None:
        raise HTTPException(status_code=409, detail="Player is already in a guild.")

    guild = get_guild(db, entry.guild_id)
    if guild is None:
        raise HTTPException(status_code=404, detail="Guild not found.")

    if guild._mapping['status'] != 'active':
        raise HTTPException(status_code=403, detail="Guild is not active.")

    db.execute(
        text("UPDATE players SET guild_id = :guild_id WHERE discord_id = :discord_id;"),
        {'guild_id': entry.guild_id, 'discord_id': entry.discord_id}
    )

    db.execute(
        text("""
             INSERT INTO guild_roles (guild_id, player_id, role, granted_by)
             VALUES (:guild_id, :player_id, :role, :granted_by);
             """),
        {
            'guild_id': entry.guild_id,
            'player_id': player_data['id'],
            'role': GuildRoleEnum('member'),
            'granted_by': player_data['id']  # self-joined
        }
    )

    db.commit()
    return {'guild_name': guild._mapping['name'], 'status': 'joined'}

def get_guilds(db: Session):
    '''Returns all rows of the guilds table.'''
    return db.execute(text("SELECT * FROM guilds")).fetchall()

def get_guild(db: Session, guild_id: int):
    '''Retrieves the guild with the given guild ID.'''
    row = db.execute(
        text("SELECT * FROM guilds WHERE id = :id"),
        {'id': guild_id}
    ).fetchone()

    db.commit()
    return row

def get_player_role(db: Session, discord_id: str):
    '''Retrieves a player's guild role given their discord_id.'''
    return db.execute(
        text("""
             SELECT gr.role 
             FROM guild_roles gr
             JOIN players p ON p.id = gr.player_id
             WHERE p.discord_id = :discord_id
             """),
        {"discord_id": discord_id}
    ).fetchone()

def leave_guild(db: Session, entry: gm.GuildLeave):
    '''Handles logic for a player leaving a guild.'''
    player = get_player_with_id(db, entry.discord_id)
    role_row = get_player_role(db, entry.discord_id)
    if role_row is None:
        raise HTTPException(status_code=409, detail="Player is not in a guild.")
    is_captain = role_row._mapping['role'] == 'captain'
    
    guild_id = player._mapping['guild_id']
    is_empty = guild_empty(db, guild_id)
    guild = get_guild(db, guild_id)
    guild_balance = Decimal(guild._mapping['balance'])

    if is_captain:
        if not is_empty:
            raise HTTPException(
                status_code=403,
                detail="Leader cannot leave their guild with other players in it."
            )
        if guild_balance > 0:
            raise HTTPException(
                status_code=409,
                detail="Balance must be empty for leader to leave."
            )
        db.execute(
            text("DELETE FROM guilds WHERE id = :guild_id;"), 
            {'guild_id': guild_id}
        )
        db.commit()
    else:
        remove_from_guild(db, entry.discord_id)

    
    return {'guild_name': guild._mapping['name'], 'is_captain': is_captain}