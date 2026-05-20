from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.database import SessionLocal
from app.models.terminal import Terminal
from app.models.pending_withdrawal import PendingWithdrawal, WithdrawalStatus
from app.ws.manager import manager
from datetime import datetime, timezone
import json
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/terminal/{terminal_id}")
async def terminal_websocket(
    terminal_id: int,
    websocket: WebSocket,
    token: str = Query(...),
):
    with SessionLocal() as session:
        terminal = session.get(Terminal, terminal_id)
        if not terminal or terminal.token != token or not terminal.active:
            await websocket.close(code=4001)
            return

    await manager.connect(terminal_id, websocket)
    logger.info(f"Terminal {terminal_id} connected")

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            await handle_terminal_message(terminal_id, data)
    except WebSocketDisconnect:
        logger.info(f"Terminal {terminal_id} disconnected")
        manager.disconnect(terminal_id)
    except Exception as e:
        logger.error(f"Terminal {terminal_id} error: {e}", exc_info=True)
        manager.disconnect(terminal_id)


async def handle_terminal_message(terminal_id: int, data: dict):
    msg_type = data.get("type")
    payload  = data.get("payload", {})
    conn     = manager.connections.get(terminal_id)

    if not conn:
        return

    if msg_type == "ping":
        await manager.send(terminal_id, {"type": "pong"})

    elif msg_type == "dispense_confirm":
        conn.in_transaction = False

        with SessionLocal() as session:
            # Find the most recent pending withdrawal for this terminal
            withdrawal = session.scalar(
                select(PendingWithdrawal)
                .where(
                    PendingWithdrawal.terminal_id == terminal_id,
                    PendingWithdrawal.discord_id  == payload.get("discord_id"),
                    PendingWithdrawal.status      == WithdrawalStatus.pending,
                )
                .order_by(PendingWithdrawal.created_at.desc())
            )
            if withdrawal:
                withdrawal.status       = WithdrawalStatus.confirmed
                withdrawal.confirmed_at = datetime.now(timezone.utc)
                session.commit()
                logger.info(f"Withdrawal {withdrawal.id} confirmed by terminal {terminal_id}")

        # If token was regenerated while transaction was in flight, disconnect now
        if conn.pending_disconnect:
            await conn.websocket.send_json({
                "type": "disconnect",
                "reason": "token_regenerated",
            })
            await conn.websocket.close()
            manager.disconnect(terminal_id)

    elif msg_type == "deposit_ready":
        discord_id = payload.get("discord_id")
        items      = payload.get("items", [])

        with SessionLocal() as session:
            from app.services.materials import process_deposit
            try:
                result = process_deposit(session, discord_id, items)
                await manager.send(terminal_id, {
                    "type": "deposit_accepted",
                    "payload": {
                        "total": str(result["total"]),
                        "breakdown": [
                            {
                                "material": b["material"],
                                "quantity": b["quantity"],
                                "value":    str(b["value"]),
                            }
                            for b in result["breakdown"]
                        ],
                    },
                })
                logger.info(f"Deposit accepted for {discord_id} at terminal {terminal_id}")
            except Exception as e:
                await manager.send(terminal_id, {
                    "type": "deposit_rejected",
                    "payload": {"reason": str(e)},
                })
                logger.warning(f"Deposit rejected for {discord_id}: {e}")

    else:
        logger.warning(f"Terminal {terminal_id} sent unknown message type: {msg_type}")