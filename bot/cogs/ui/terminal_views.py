import discord
from decimal import Decimal
from app.database import SessionLocal
from app.services.materials import process_deposit, process_withdrawal
from app.ws.manager import manager


class DepositConfirmView(discord.ui.View):
    def __init__(self, discord_id: str, terminal_id: int, items: list, total: Decimal, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.discord_id  = discord_id
        self.terminal_id = terminal_id
        self.items       = items
        self.total       = total
        self.responded   = False
        self.message     = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.discord_id:
            await interaction.response.send_message(
                "Only the player who claimed this terminal can confirm.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Confirm Deposit", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.responded:
            return
        self.responded = True
        self.stop()

        await interaction.response.defer()

        with SessionLocal() as session:
            try:
                result = process_deposit(session, self.discord_id, self.items)
                await manager.send(self.terminal_id, {
                    "type": "deposit_accepted",
                    "payload": {
                        "total": str(result["total"]),
                        "breakdown": [
                            {"material": b["material"], "quantity": b["quantity"], "value": str(b["value"])}
                            for b in result["breakdown"]
                        ],
                    },
                })
                manager.release_claim(self.terminal_id, self.discord_id)

                await interaction.edit_original_response(
                    embed=discord.Embed(
                        title="✅ Deposit Confirmed",
                        description=f"**${result['total']:,.2f}** has been credited to your account.",
                        color=discord.Color.green(),
                    ),
                    view=None,
                )
            except Exception as e:
                await manager.send(self.terminal_id, {
                    "type": "deposit_rejected",
                    "payload": {"reason": str(e)},
                })
                manager.release_claim(self.terminal_id, self.discord_id)
                await interaction.edit_original_response(
                    embed=discord.Embed(
                        title="❌ Deposit Failed",
                        description=str(e),
                        color=discord.Color.red(),
                    ),
                    view=None,
                )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.responded:
            return
        self.responded = True
        self.stop()

        await manager.send(self.terminal_id, {
            "type": "deposit_rejected",
            "payload": {"reason": "Player cancelled the deposit."},
        })
        manager.release_claim(self.terminal_id, self.discord_id)

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Deposit Cancelled",
                description="Your items have not been deposited. You may collect them from the barrel.",
                color=discord.Color.dark_gray(),
            ),
            view=None,
        )

    async def on_timeout(self):
        if self.responded:
            return
        self.responded = True

        await manager.send(self.terminal_id, {
            "type": "deposit_rejected",
            "payload": {"reason": "Deposit confirmation timed out."},
        })
        manager.release_claim(self.terminal_id, self.discord_id)

        if self.message:
            await self.message.edit(
                embed=discord.Embed(
                    title="⏰ Deposit Timed Out",
                    description="You did not confirm in time. Your items have not been deposited. You may collect them from the barrel.",
                    color=discord.Color.orange(),
                ),
                view=None,
            )


class WithdrawalConfirmView(discord.ui.View):
    def __init__(self, discord_id: str, terminal_id: int, items: list, total_cost: Decimal, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.discord_id  = discord_id
        self.terminal_id = terminal_id
        self.items       = items
        self.total_cost  = total_cost
        self.responded   = False
        self.message     = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.discord_id:
            await interaction.response.send_message(
                "This is not your withdrawal confirmation.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Confirm Withdrawal", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.responded:
            return
        self.responded = True
        self.stop()

        await interaction.response.defer()

        if not manager.is_connected(self.terminal_id):
            manager.release_claim(self.terminal_id, self.discord_id)
            await manager.send(self.terminal_id, {"type": "claim_released", "payload": {}})
            await interaction.edit_original_response(
                embed=discord.Embed(
                    title="❌ Terminal Offline",
                    description="The terminal went offline before your withdrawal could be processed.",
                    color=discord.Color.red(),
                ),
                view=None,
            )
            return

        with SessionLocal() as session:
            try:
                from app.services.terminals import request_withdrawal
                await request_withdrawal(session, self.discord_id, self.terminal_id, self.items)
                # Release claim after dispense is sent to terminal
                manager.release_claim(self.terminal_id, self.discord_id)
                await manager.send(self.terminal_id, {"type": "claim_released", "payload": {}})
                await interaction.edit_original_response(
                    embed=discord.Embed(
                        title="✅ Withdrawal Confirmed",
                        description=f"**${self.total_cost:,.2f}** has been deducted. Collect your items from the terminal barrel.",
                        color=discord.Color.green(),
                    ),
                    view=None,
                )
            except Exception as e:
                manager.release_claim(self.terminal_id, self.discord_id)
                await manager.send(self.terminal_id, {"type": "claim_released", "payload": {}})
                await interaction.edit_original_response(
                    embed=discord.Embed(
                        title="❌ Withdrawal Failed",
                        description=str(e),
                        color=discord.Color.red(),
                    ),
                    view=None,
                )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.responded:
            return
        self.responded = True
        self.stop()

        manager.release_claim(self.terminal_id, self.discord_id)
        await manager.send(self.terminal_id, {"type": "claim_released", "payload": {}})
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Withdrawal Cancelled",
                description="Your withdrawal has been cancelled. No funds were deducted.",
                color=discord.Color.dark_gray(),
            ),
            view=None,
        )

    async def on_timeout(self):
        if self.responded:
            return
        self.responded = True

        manager.release_claim(self.terminal_id, self.discord_id)
        await manager.send(self.terminal_id, {"type": "claim_released", "payload": {}})
        if self.message:
            await self.message.edit(
                embed=discord.Embed(
                    title="⏰ Withdrawal Timed Out",
                    description="You did not confirm in time. No funds were deducted.",
                    color=discord.Color.orange(),
                ),
                view=None,
            )