from fastapi import WebSocket
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

@dataclass
class TerminalConnection:
    terminal_id: int
    websocket: WebSocket
    pending_disconnect: bool = False
    in_transaction: bool = False
    claimed_by: str | None = None      # discord_id
    claimed_at: datetime | None = None  # for timeout checking

class TerminalConnectionManager:
    def __init__(self):
        self.connections: dict[int, TerminalConnection] = {}

    async def connect(self, terminal_id: int, websocket: WebSocket):
        await websocket.accept()
        self.connections[terminal_id] = TerminalConnection(
            terminal_id=terminal_id,
            websocket=websocket,
        )

    def disconnect(self, terminal_id: int):
        self.connections.pop(terminal_id, None)

    def is_connected(self, terminal_id: int) -> bool:
        return terminal_id in self.connections

    async def send(self, terminal_id: int, data: dict):
        conn = self.connections.get(terminal_id)
        if not conn:
            raise RuntimeError(f"Terminal {terminal_id} is not connected")
        await conn.websocket.send_json(data)

    async def disconnect_after_transaction(self, terminal_id: int):
        conn = self.connections.get(terminal_id)
        if not conn:
            return
        if conn.in_transaction:
            conn.pending_disconnect = True
        else:
            await conn.websocket.send_json({
                "type": "disconnect",
                "reason": "token_regenerated"
            })
            await conn.websocket.close()
            self.disconnect(terminal_id)

def claim(self, terminal_id: int, discord_id: str) -> bool:
    """Returns False if already claimed by someone else."""
    conn = self.connections.get(terminal_id)
    if not conn:
        return False
    # Check if existing claim has expired (2 minutes)
    if conn.claimed_by and conn.claimed_at:
        if datetime.now(timezone.utc) - conn.claimed_at < timedelta(minutes=2):
            if conn.claimed_by != discord_id:
                return False  # claimed by someone else
    conn.claimed_by = discord_id
    conn.claimed_at = datetime.now(timezone.utc)
    return True

def release_claim(self, terminal_id: int, discord_id: str):
    conn = self.connections.get(terminal_id)
    if conn and conn.claimed_by == discord_id:
        conn.claimed_by = None
        conn.claimed_at = None

def get_claimant(self, terminal_id: int) -> str | None:
    conn = self.connections.get(terminal_id)
    if not conn:
        return None
    if conn.claimed_by and conn.claimed_at:
        if datetime.now(timezone.utc) - conn.claimed_at < timedelta(minutes=2):
            return conn.claimed_by
    return None

manager = TerminalConnectionManager()