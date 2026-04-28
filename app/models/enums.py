from enum import Enum

class GuildRoleEnum(str, Enum):
    member = 'member'
    officer = 'officer'
    captain = 'captain'