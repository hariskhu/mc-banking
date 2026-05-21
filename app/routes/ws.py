from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.database import SessionLocal
from app.models.terminal import Terminal
from app.models.pending_withdrawal import PendingWithdrawal, WithdrawalStatus
from app.ws.manager import manager
from datetime import datetime, timezone
from bot.main import client
from bot.cogs.ui.terminal_views import DepositConfirmView
from app.services.materials import _get_copper, _integrated_value, get_material
from decimal import Decimal, ROUND_HALF_UP
import json
import logging
import discord as discord_lib

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

        claimant = manager.get_claimant(terminal_id)
        if claimant != discord_id:
            await manager.send(terminal_id, {
                "type": "deposit_rejected",
                "payload": {"reason": "Terminal not claimed by this player or claim expired."}
            })
            return

        await manager.send(terminal_id, {"type": "deposit_ready_ack", "payload": {}})

        channel = client.get_channel(conn.claim_channel_id)
        if not channel:
            await manager.send(terminal_id, {
                "type": "deposit_rejected",
                "payload": {"reason": "Could not find Discord channel. Please try again."}
            })
            return

        with SessionLocal() as session:
            try:
                copper    = _get_copper(session)
                breakdown = []
                total     = Decimal("0")

                for item in items:
                    mc_id    = item["mc_id"]
                    quantity = int(item["quantity"])
                    if quantity <= 0:
                        continue

                    if mc_id == "create:copper_nugget":
                        value = Decimal("0.01") * quantity
                        name  = "Copper Nugget"
                    else:
                        material = get_material(session, mc_id)
                        value    = _integrated_value(material, copper, quantity, withdrawing=False)
                        value    = value.quantize(Decimal("0.01"), ROUND_HALF_UP)
                        name     = material.name

                    total += value
                    breakdown.append({
                        "material": name,
                        "quantity": quantity,
                        "value":    value,
                    })

                total = total.quantize(Decimal("0.01"), ROUND_HALF_UP)

            except Exception as e:
                await manager.send(terminal_id, {
                    "type": "deposit_rejected",
                    "payload": {"reason": str(e)}
                })
                logger.warning(f"Deposit preview failed for {discord_id}: {e}")
                return

        lines = [
            f"**{b['material']}** x{b['quantity']:,} — **${b['value']:,.2f}**"
            for b in breakdown
        ]
        embed = discord_lib.Embed(
            title="💰 Deposit Confirmation",
            description="\n".join(lines),
            color=discord_lib.Color.green(),
        )
        embed.add_field(name="Total", value=f"**${total:,.2f}**", inline=False)
        embed.set_footer(text="You have 60 seconds to confirm.")

        view = DepositConfirmView(
            discord_id=discord_id,
            terminal_id=terminal_id,
            items=items,
            total=total,
        )
        msg = await channel.send(f"<@{discord_id}>", embed=embed, view=view)
        view.message = msg

    elif msg_type == "dispense_failed":
        discord_id = payload.get("discord_id")
        reason     = payload.get("reason", "Terminal error")
        logger.warning(f"Dispense failed at terminal {terminal_id} for {discord_id}: {reason}")

        # Refund the most recent pending withdrawal for this player
        with SessionLocal() as session:
            withdrawal = session.scalar(
                select(PendingWithdrawal)
                .where(
                    PendingWithdrawal.terminal_id == terminal_id,
                    PendingWithdrawal.discord_id  == discord_id,
                    PendingWithdrawal.status      == WithdrawalStatus.pending,
                )
                .order_by(PendingWithdrawal.created_at.desc())
            )
            if withdrawal:
                from app.services.terminals import refund_pending_withdrawal
                refund_pending_withdrawal(session, withdrawal.id)
                logger.info(f"Auto-refunded withdrawal {withdrawal.id} due to dispense failure")

        # Notify the player via Discord
        channel = client.get_channel(conn.claim_channel_id) if conn.claim_channel_id else None
        if channel:
            await channel.send(
                f"<@{discord_id}> Your withdrawal could not be completed — {reason}. "
                f"Your funds have been refunded."
            )

    else:
        logger.warning(f"Terminal {terminal_id} sent unknown message type: {msg_type}")