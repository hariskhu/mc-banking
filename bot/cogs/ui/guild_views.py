import discord
from decimal import Decimal
from app.database import SessionLocal
from app.services.guild import add_member, transfer_captaincy, can_withdraw
from app.services.banking import guild_withdraw

class GuildJoinRequestView(discord.ui.View):
    def __init__(self, applicant: discord.Member, captain: discord.Member, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.applicant = applicant
        self.captain = captain
        self.responded = False
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.captain.id:
            await interaction.response.send_message(
                "Only the guild captain can respond to this request.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, emoji="✅")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.responded:
            return
        self.responded = True
        self.stop()

        with SessionLocal() as session:
            try:
                add_member(session, str(self.captain.id), str(self.applicant.id))
                await interaction.response.edit_message(
                    embed=discord.Embed(
                        title="Request Accepted",
                        description=f"<@{self.applicant.id}> has been added to the guild! 🎉",
                        color=discord.Color.green(),
                    ),
                    view=None,
                )
                try:
                    await self.applicant.send(
                        f"Your request to join the guild was **accepted** by <@{self.captain.id}>!"
                    )
                except discord.Forbidden:
                    pass
            except ValueError as e:
                await interaction.response.edit_message(
                    embed=discord.Embed(
                        title="Failed to add member",
                        description=str(e),
                        color=discord.Color.red(),
                    ),
                    view=None,
                )

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, emoji="❌")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.responded:
            return
        self.responded = True
        self.stop()

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Request Denied",
                description=f"<@{self.applicant.id}>'s request to join the guild was denied.",
                color=discord.Color.red(),
            ),
            view=None,
        )
        try:
            await self.applicant.send(
                f"Your request to join the guild was **denied** by <@{self.captain.id}>."
            )
        except discord.Forbidden:
            pass

    async def on_timeout(self):
        self.responded = True
        for item in self.children:
            item.disabled = True
        if self.message:
            await self.message.edit(
                embed=discord.Embed(
                    title="Request Expired",
                    description=f"<@{self.applicant.id}>'s join request has expired.",
                    color=discord.Color.dark_gray(),
                ),
                view=self,  # pass disabled buttons so Discord removes interactivity
            )


class TransferCaptaincyView(discord.ui.View):
    def __init__(self, captain: discord.Member, new_captain: discord.Member, timeout: float = 120):
        super().__init__(timeout=timeout)
        self.captain = captain
        self.new_captain = new_captain
        self.responded = False
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.captain.id:
            await interaction.response.send_message(
                "Only the current captain can confirm this transfer.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Confirm Transfer", style=discord.ButtonStyle.danger, emoji="👑")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.responded:
            return
        self.responded = True
        self.stop()

        with SessionLocal() as session:
            try:
                transfer_captaincy(session, str(self.captain.id), str(self.new_captain.id))
                await interaction.response.edit_message(
                    embed=discord.Embed(
                        title="Captaincy Transferred",
                        description=(
                            f"<@{self.new_captain.id}> is now the guild captain.\n"
                            f"<@{self.captain.id}> has been demoted to officer."
                        ),
                        color=discord.Color.gold(),
                    ),
                    view=None,
                )
                try:
                    await self.new_captain.send(
                        f"You have been made captain of the guild by <@{self.captain.id}>! 👑"
                    )
                except discord.Forbidden:
                    pass
            except (PermissionError, ValueError) as e:
                await interaction.response.edit_message(
                    embed=discord.Embed(
                        title="Transfer Failed",
                        description=str(e),
                        color=discord.Color.red(),
                    ),
                    view=None,
                )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.responded:
            return
        self.responded = True
        self.stop()

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Transfer Cancelled",
                description="Captaincy transfer has been cancelled.",
                color=discord.Color.dark_gray(),
            ),
            view=None,
        )

    async def on_timeout(self):
        self.responded = True
        for item in self.children:
            item.disabled = True
        if self.message:
            await self.message.edit(
                embed=discord.Embed(
                    title="Transfer Expired",
                    description="The captaincy transfer request has expired.",
                    color=discord.Color.dark_gray(),
                ),
                view=self,
            )


class GuildWithdrawRequestView(discord.ui.View):
    def __init__(self, applicant: discord.Member, guild_name: str, amount: Decimal, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.applicant = applicant
        self.guild_name = guild_name
        self.amount = amount
        self.responded = False
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        with SessionLocal() as session:
            try:
                if not can_withdraw(session, str(interaction.user.id)):
                    await interaction.response.send_message(
                        "Only officers and captains can approve withdrawal requests.", ephemeral=True
                    )
                    return False
            except ValueError:
                await interaction.response.send_message(
                    "You are not in a guild.", ephemeral=True
                )
                return False
        return True

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, emoji="✅")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.responded:
            return
        self.responded = True
        self.stop()

        with SessionLocal() as session:
            try:
                guild_withdraw(session, str(self.applicant.id), self.amount)
                await interaction.response.edit_message(
                    embed=discord.Embed(
                        title="Withdrawal Approved",
                        description=(
                            f"<@{self.applicant.id}>'s withdrawal of **${self.amount:.2f}** "
                            f"from **{self.guild_name}** was approved by <@{interaction.user.id}>."
                        ),
                        color=discord.Color.green(),
                    ),
                    view=None,
                )
                try:
                    await self.applicant.send(
                        f"Your withdrawal of **${self.amount:.2f}** from **{self.guild_name}** was approved!"
                    )
                except discord.Forbidden:
                    pass
            except ValueError as e:
                await interaction.response.edit_message(
                    embed=discord.Embed(
                        title="Withdrawal Failed",
                        description=str(e),
                        color=discord.Color.red(),
                    ),
                    view=None,
                )

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, emoji="❌")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.responded:
            return
        self.responded = True
        self.stop()

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Withdrawal Denied",
                description=(
                    f"<@{self.applicant.id}>'s withdrawal request of **${self.amount:.2f}** "
                    f"from **{self.guild_name}** was denied by <@{interaction.user.id}>."
                ),
                color=discord.Color.red(),
            ),
            view=None,
        )
        try:
            await self.applicant.send(
                f"Your withdrawal request of **${self.amount:.2f}** from **{self.guild_name}** was denied."
            )
        except discord.Forbidden:
            pass

    async def on_timeout(self):
        self.responded = True
        for item in self.children:
            item.disabled = True
        if self.message:
            await self.message.edit(
                embed=discord.Embed(
                    title="Withdrawal Request Expired",
                    description=f"<@{self.applicant.id}>'s withdrawal request has expired.",
                    color=discord.Color.dark_gray(),
                ),
                view=self,
            )