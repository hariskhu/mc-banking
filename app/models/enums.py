from enum import Enum

class GuildRoleEnum(str, Enum):
    member = 'member'
    officer = 'officer'
    captain = 'captain'

class GuildStatusEnum(str, Enum):
    active = 'active'
    suspended = 'suspended'
    dissolved = 'dissolved'