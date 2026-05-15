import os
import discord
from discord import app_commands
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from dotenv import load_dotenv
from app.database import SessionLocal

from app.services.banking import (
    register_player,
    get_player,
    get_player_bal,
    get_guild_bal,
    player_transfer,
    guild_deposit,
    guild_withdraw,
    admin_change_player_bal
)

from app.models.guild import GuildRole
from bot.cogs.ui.guild_views import (
    GuildJoinRequestView,
    TransferCaptaincyView,
    GuildWithdrawRequestView
)
from app.services.guild import (
    get_guild,
    get_member_role,
    create_guild,
    leave_guild,
    disband_guild,
    get_guild_by_name,
    get_guild_captain,
    is_in_guild,
    set_member_role,
    can_manage_members,
    can_withdraw,
    remove_member,
    get_all_guilds,
    get_guild_members
)

load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GUILD = discord.Object(id=int(os.getenv('DISCORD_SERVER_ID')))
ADMIN_IDS = [
    int(user_id.strip())
    for user_id in os.getenv("ADMIN_IDS", "").split(",")
    if user_id.strip()
]

intents = discord.Intents.default()
intents.members = True 
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

def is_admin(interaction: discord.Interaction) -> bool:
    if interaction.user.id not in ADMIN_IDS:
        raise app_commands.CheckFailure(
            "You are not authorized to use this command."
        )
    return True

@tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(
            str(error),
            ephemeral=True
        )

# HELPERS
async def get_or_fetch_member(discord_id: int):
    """Checks for server member in cache, if not present requests."""
    guild = client.get_guild(GUILD.id) or await client.fetch_guild(GUILD.id)
    member = guild.get_member(discord_id)
    if member is not None:
        return member

    try:
        member = await guild.fetch_member(discord_id)
        return member
    except (discord.NotFound, discord.HTTPException):
        return None


# -------- PLAYER/GUILD COMMANDS --------

# @tree.command(name="info", description="Get info about CapitalTwo")
# async def info(interaction: discord.Interaction):
#     '''Returns an embed of information about the bot.'''
#     capitaltwo_desc=(
#         "CapitalTwo is a bank that will be on the BraxtonCraft 2 Minecraft server powered by ComputerCraft and Create. "
#         "Money is backed by copper and can be exchanged for other precious metals based on the bank's supply. "
#         "No verification is necessary to view your balance and other details, just commands in Discord.\n\n"
#     )
#     embed = discord.Embed(
#         title="CapitalTwo Info",
#         description=capitaltwo_desc,
#         color=discord.Color.blurple()
#     )
#     embed.add_field(name="Exchange Currency 💴", value="The bank holds copper, iron, zinc, brass, and gold, allowing you to withdraw whatever you need.", inline=False)
#     embed.add_field(name="Send Money 💸", value="Send money to other players instantly.", inline=False)
#     embed.add_field(name="Guilds 🏛️", value="Create or join a guild to gain access to extra perks and aim to become the wealthiest.", inline=False)
#     embed.add_field(name="Shop 🛒", value="Buy items from in-game shops using your digital currency.", inline=False)

#     try:
#         await interaction.response.send_message("Check your DMs!", ephemeral=True)
#         await interaction.user.send(embed=embed)
#     except discord.Forbidden:
#         await interaction.response.send_message("I couldn't DM you! Make sure your DMs are open.", ephemeral=True)


@tree.command(name="register", description="Register for a bank account")
async def register(interaction: discord.Interaction):
    '''Creates a user and gives them a bank account.'''
    await interaction.response.defer()
    with SessionLocal() as session:
        try:
            register_player(session, str(interaction.user.id))
            await interaction.followup.send(f"<@{interaction.user.id}> has registered with CapitalTwo! 🥳")
        except ValueError as e:
            await interaction.followup.send(str(e))


@tree.command(name="balance", description="View current balance")
async def balance(interaction: discord.Interaction):
    '''Return's a player's balance.'''
    await interaction.response.defer()
    with SessionLocal() as session:
        try:
            balance = get_player_bal(session, str(interaction.user.id))
            avatar_url = interaction.user.display_avatar.url
            embed = discord.Embed(
                title=f"{interaction.user.display_name}'s Balance",
                description=f"# ${balance:,.2f}",
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=avatar_url)

            await interaction.followup.send(embed=embed)
        except ValueError as e:
            msg = str(e)
            if "No player account" in msg:
                await interaction.followup.send("You do not have an account! Use `/register` !", ephemeral=True)
            else:
                await interaction.followup.send(msg)

@tree.command(name="profile", description="View your details")
async def details(interaction: discord.Interaction):
    """Returns a player's name, minecraft name, balance, guild, and guild role."""
    await interaction.response.defer()

    with SessionLocal() as session:
        try:
            discord_id = str(interaction.user.id)

            p = get_player(session, discord_id)
            balance = get_player_bal(session, discord_id)

            # Guild info optional, player may not be in one
            try:
                role = get_member_role(session, discord_id)
                guild = get_guild(session, discord_id)
                guild_name = guild.name
                guild_role = role.value
            except ValueError:
                guild_name = None
                guild_role = None

            # Build title
            name = interaction.user.display_name
            if guild_role and guild_role != "member":
                name = guild_role.capitalize() + " " + name
            title = name + (f" ({p.mc_username})" if p.mc_username else "")

            # Build embed
            profile = f"# Balance: ${balance:,.2f}"
            if guild_name:
                profile += f"\n### Guild: {guild_name}"

            embed = discord.Embed(
                title=title,
                description=profile,
                color=discord.Color.blue(),
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            await interaction.followup.send(embed=embed)

        except ValueError:
            await interaction.followup.send(
                "That player has not registered for an account yet. They can use `/register` to sign up!"
            )


@tree.command(name="transfer", description="Transfer money to another player")
@app_commands.describe(amount="Amount of money to transfer", receiver="Transfer receiver")
async def transfer(interaction: discord.Interaction, amount: str, receiver: discord.Member):
    await interaction.response.defer()

    # Validate amount
    try:
        decimal_amount = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        await interaction.followup.send("Invalid transfer amount.")
        return

    if decimal_amount < Decimal("0.01"):
        await interaction.followup.send("Transfer amount must be $0.01 or more when rounded.")
        return

    if receiver.id == interaction.user.id:
        await interaction.followup.send("You can't transfer money to yourself.")
        return

    with SessionLocal() as session:
        try:
            player_transfer(
                session,
                from_discord_id=str(interaction.user.id),
                to_discord_id=str(receiver.id),
                amount=decimal_amount,
            )
            await interaction.followup.send(
                f"Successfully transferred ${decimal_amount:,.2f} to <@{receiver.id}>! 🤑"
            )
        except ValueError as e:
            msg = str(e)
            if "Insufficient" in msg:
                await interaction.followup.send(f"Insufficient balance to transfer ${decimal_amount:,.2f}.")
            elif "not registered" in msg:
                await interaction.followup.send(f"<@{receiver.id}> doesn't have a bank account yet.")
            else:
                await interaction.followup.send(msg)


# GUILD COMMANDS
@tree.command(name="create_guild", description="Create a new guild")
@app_commands.describe(name="Guild name")
async def create_guild_cmd(interaction: discord.Interaction, name: str):
    await interaction.response.defer()

    stripped = name.strip()
    if not 0 < len(stripped) <= 30:
        await interaction.followup.send("Guild name must be 30 characters or less.")
        return

    with SessionLocal() as session:
        try:
            create_guild(session, name=stripped, captain_discord_id=str(interaction.user.id))
            await interaction.followup.send(f"Successfully created your guild: **{stripped}**! 🏛️")
        except ValueError as e:
            msg = str(e)
            if "already exists" in msg:
                await interaction.followup.send(f"A guild named **{stripped}** already exists.")
            elif "already in a guild" in msg:
                await interaction.followup.send("You're already in a guild.")
            elif "not registered" in msg:
                await interaction.followup.send("You don't have a bank account yet. Use `/register` first!")
            else:
                await interaction.followup.send(msg)


@tree.command(name="leaderboard", description="View guild leaderboard (WIP)")
async def leaderboard(interaction: discord.Interaction):
    await interaction.response.defer()
    await interaction.followup.send("WIP: check again later", ephemeral=True)

@tree.command(name="join_guild", description="Request to join a guild")
@app_commands.describe(guild_name="Name of the guild you want to join")
async def join_guild_cmd(interaction: discord.Interaction, guild_name: str):
    await interaction.response.defer()
    with SessionLocal() as session:
        try:
            discord_id = str(interaction.user.id)
            get_player(session, discord_id)

            if is_in_guild(session, discord_id):
                await interaction.followup.send("You're already in a guild.")
                return

            guild = get_guild_by_name(session, guild_name)
            captain_player = get_guild_captain(session, guild.id)
            captain_discord = await interaction.guild.fetch_member(int(captain_player.discord_id))

        except ValueError as e:
            await interaction.followup.send(str(e))
            return

    # Build the request embed
    embed = discord.Embed(
        title="Guild Join Request",
        description=(
            f"<@{interaction.user.id}> wants to join **{guild_name}**.\n\n"
            f"<@{captain_discord.id}>, do you want to accept them?"
        ),
        color=discord.Color.blue(),
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text="This request expires in 5 minutes.")

    view = GuildJoinRequestView(
        applicant=interaction.user,
        captain=captain_discord,
        timeout=300,
    )
    msg = await interaction.followup.send(embed=embed, view=view)
    view.message = msg


@tree.command(name="leave_guild", description="Leave the guild you're currently in")
async def leave_guild_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    with SessionLocal() as session:
        try:
            discord_id = str(interaction.user.id)
            guild = get_guild(session, discord_id)
            guild_name = guild.name
            leave_guild(session, discord_id)
            await interaction.followup.send(f"<@{interaction.user.id}> has left **{guild_name}**.")
        except ValueError as e:
            msg = str(e)
            if "transfer captaincy" in msg:
                await interaction.followup.send(
                    "You're the captain — transfer captaincy or disband the guild before leaving."
                )
            elif "not in a guild" in msg:
                await interaction.followup.send("You're not in a guild.")
            elif "not registered" in msg:
                await interaction.followup.send("You don't have a bank account yet. Use `/register` first!")
            else:
                await interaction.followup.send(msg)


@tree.command(name="disband_guild", description="Disband your guild (captain only)")
async def disband_guild_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    with SessionLocal() as session:
        try:
            discord_id = str(interaction.user.id)
            guild = get_guild(session, discord_id)
            guild_name = guild.name
            disband_guild(session, discord_id)
            await interaction.followup.send(f"**{guild_name}** has been disbanded.")
        except PermissionError:
            await interaction.followup.send("Only the captain can disband the guild.")
        except ValueError as e:
            msg = str(e)
            if "Drain the guild account" in msg:
                await interaction.followup.send(
                    "Your guild account must be empty before disbanding. Withdraw all funds first."
                )
            elif "not in a guild" in msg:
                await interaction.followup.send("You're not in a guild.")
            elif "not registered" in msg:
                await interaction.followup.send("You don't have a bank account yet. Use `/register` first!")
            else:
                await interaction.followup.send(msg)


@tree.command(name="set_role", description="Change a guild member's role (captain only)")
@app_commands.describe(
    member="Member to update",
    role="New role to assign"
)
@app_commands.choices(role=[
    app_commands.Choice(name="Officer", value="officer"),
    app_commands.Choice(name="Member", value="member"),
])
async def set_role_cmd(interaction: discord.Interaction, member: discord.Member, role: app_commands.Choice[str]):
    await interaction.response.defer()

    if member.id == interaction.user.id:
        await interaction.followup.send("You cannot change your own role.")
        return

    with SessionLocal() as session:
        try:
            set_member_role(
                session,
                captain_discord_id=str(interaction.user.id),
                target_discord_id=str(member.id),
                new_role=GuildRole[role.value],
            )
            await interaction.followup.send(
                f"<@{member.id}> is now a guild **{role.name}**."
            )
        except PermissionError:
            await interaction.followup.send("Only the captain can change member roles.")
        except ValueError as e:
            msg = str(e)
            if "not in your guild" in msg:
                await interaction.followup.send(f"<@{member.id}> is not in your guild.")
            elif "transfer_captaincy" in msg:
                await interaction.followup.send("Use `/transfer_captaincy` to transfer leadership.")
            elif "not registered" in msg:
                await interaction.followup.send(f"<@{member.id}> doesn't have a bank account.")
            else:
                await interaction.followup.send(msg)


@tree.command(name="transfer_captaincy", description="Transfer guild leadership to another member (captain only)")
@app_commands.describe(member="Member to transfer captaincy to")
async def transfer_captaincy_cmd(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer()

    if member.id == interaction.user.id:
        await interaction.followup.send("You cannot transfer captaincy to yourself.")
        return

    with SessionLocal() as session:
        try:
            discord_id = str(interaction.user.id)
            if not can_manage_members(session, discord_id):
                await interaction.followup.send("Only the captain can transfer captaincy.")
                return

            if not is_in_guild(session, str(member.id)):
                await interaction.followup.send(f"<@{member.id}> is not in your guild.")
                return

            guild = get_guild(session, discord_id)
            guild_name = guild.name

        except ValueError as e:
            await interaction.followup.send(str(e))
            return

    embed = discord.Embed(
        title="⚠️ Transfer Captaincy",
        description=(
            f"Are you sure you want to transfer captaincy of **{guild_name}** to <@{member.id}>?\n\n"
            f"You will be demoted to officer. This cannot be undone without their cooperation."
        ),
        color=discord.Color.orange(),
    )
    embed.set_footer(text="This confirmation expires in 2 minutes.")

    view = TransferCaptaincyView(captain=interaction.user, new_captain=member, timeout=120)
    msg = await interaction.followup.send(embed=embed, view=view)
    view.message = msg


@tree.command(name="guild_deposit", description="Deposit money into your guild account")
@app_commands.describe(amount="Amount to deposit")
async def guild_deposit_cmd(interaction: discord.Interaction, amount: str):
    await interaction.response.defer()

    try:
        decimal_amount = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        await interaction.followup.send("Invalid amount.")
        return

    if decimal_amount < Decimal("0.01"):
        await interaction.followup.send("Amount must be $0.01 or more.")
        return

    with SessionLocal() as session:
        try:
            discord_id = str(interaction.user.id)

            if not is_in_guild(session, discord_id):
                await interaction.followup.send("You are not in a guild.")
                return

            guild = get_guild(session, discord_id)
            guild_deposit(session, discord_id, decimal_amount)

            await interaction.followup.send(
                f"Successfully deposited **${decimal_amount:,.2f}** into **{guild.name}**."
            )

        except ValueError as e:
            msg = str(e)
            if "Insufficient" in msg:
                await interaction.followup.send(f"Insufficient funds to deposit **${decimal_amount:,.2f}**.")
            elif "not registered" in msg:
                await interaction.followup.send("You don't have a bank account yet. Use `/register` first!", ephemeral=True)
            else:
                await interaction.followup.send(msg)


@tree.command(name="guild_withdraw", description="Withdraw money from your guild account")
@app_commands.describe(amount="Amount to withdraw")
async def guild_withdraw_cmd(interaction: discord.Interaction, amount: str):
    await interaction.response.defer()

    try:
        decimal_amount = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        await interaction.followup.send("Invalid amount.")
        return

    if decimal_amount < Decimal("0.01"):
        await interaction.followup.send("Amount must be $0.01 or more.")
        return

    with SessionLocal() as session:
        try:
            discord_id = str(interaction.user.id)
            get_player(session, discord_id)

            if not is_in_guild(session, discord_id):
                await interaction.followup.send("You are not in a guild.")
                return

            guild = get_guild(session, discord_id)
            guild_name = guild.name

            # Officers and captains go through immediately
            if can_withdraw(session, discord_id):
                guild_withdraw(session, discord_id, decimal_amount)
                await interaction.followup.send(
                    f"Successfully withdrew **${decimal_amount:,.2f}** from **{guild_name}**."
                )
                return

            # Members need approval, check guild funds before creating the request
            guild_bal = get_guild_bal(session, discord_id)
            if guild_bal < decimal_amount:
                await interaction.followup.send(
                    f"Insufficient guild funds. The guild balance is **${guild_bal:,.2f}**."
                )
                return

        except ValueError as e:
            await interaction.followup.send(str(e))
            return

    embed = discord.Embed(
        title="Guild Withdrawal Request",
        description=(
            f"<@{interaction.user.id}> is requesting a withdrawal of **${decimal_amount:,.2f}** "
            f"from **{guild_name}**.\n\n"
            f"An officer or captain must approve this request."
        ),
        color=discord.Color.blue(),
    )
    embed.set_footer(text="This request expires in 5 minutes.")

    view = GuildWithdrawRequestView(
        applicant=interaction.user,
        guild_name=guild_name,
        amount=decimal_amount,
        timeout=300,
    )
    msg = await interaction.followup.send(embed=embed, view=view)
    view.message = msg

@tree.command(name="guild_info", description="View your guild's details")
async def guild_info_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    with SessionLocal() as session:
        try:
            discord_id = str(interaction.user.id)

            if not is_in_guild(session, discord_id):
                await interaction.followup.send("You are not in a guild.")
                return

            guild = get_guild(session, discord_id)
            guild_bal = get_guild_bal(session, discord_id)
            members = get_guild_members(session, discord_id)

        except ValueError as e:
            await interaction.followup.send(str(e))
            return

    role_order = {GuildRole.captain: 0, GuildRole.officer: 1, GuildRole.member: 2}
    role_emoji = {GuildRole.captain: "👑", GuildRole.officer: "⚔️", GuildRole.member: "🛡️"}

    member_lines = [
        f"{role_emoji[m.role]} <@{p.discord_id}>"
        + (f" ({p.mc_username})" if p.mc_username else "")
        + f" — {m.role.value.capitalize()}"
        for p, m in sorted(members, key=lambda x: role_order[x[1].role])
    ]

    embed = discord.Embed(
        title=f"🏛️ {guild.name}",
        description="\n".join(member_lines),
        color=discord.Color.blue(),
    )
    embed.add_field(name="Treasury", value=f"${guild_bal:.2f}", inline=True)
    embed.add_field(name="Members", value=str(len(members)), inline=True)
    await interaction.followup.send(embed=embed)


@tree.command(name="guild_leaderboard", description="View the guild leaderboard")
async def guild_leaderboard_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    with SessionLocal() as session:
        try:
            guilds = get_all_guilds(session)
        except ValueError as e:
            await interaction.followup.send(str(e))
            return

    if not guilds:
        await interaction.followup.send("No guilds exist yet.")
        return

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = [
        f"{medals.get(i + 1, f'`#{i + 1}`')} **{guild.name}** — ${balance:,.2f}"
        for i, (guild, balance) in enumerate(guilds)
    ]

    embed = discord.Embed(
        title="🏆 Guild Leaderboard",
        description="\n".join(lines),
        color=discord.Color.gold(),
    )
    embed.set_footer(text=f"{len(guilds)} guild{'s' if len(guilds) != 1 else ''} total")
    await interaction.followup.send(embed=embed)


@tree.command(name="kick_member", description="Kick a member from your guild (captain only)")
@app_commands.describe(member="Member to kick")
async def kick_member_cmd(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer()

    if member.id == interaction.user.id:
        await interaction.followup.send("You cannot kick yourself. Use `/leave_guild` instead.")
        return

    with SessionLocal() as session:
        try:
            remove_member(session, str(interaction.user.id), str(member.id))
            await interaction.followup.send(
                f"<@{member.id}> has been kicked from the guild."
            )
            try:
                await member.send("You have been kicked from your guild.")
            except discord.Forbidden:
                pass
        except PermissionError:
            await interaction.followup.send("Only captains can kick members.")
        except ValueError as e:
            msg = str(e)
            if "not in your guild" in msg:
                await interaction.followup.send(f"<@{member.id}> is not in your guild.")
            elif "leave_guild" in msg:
                await interaction.followup.send("You cannot kick yourself.")
            elif "not registered" in msg:
                await interaction.followup.send(f"<@{member.id}> doesn't have a bank account.")
            else:
                await interaction.followup.send(msg)

# -------- ADMIN COMMANDS --------
@tree.command(name="zz_change_player_bal")
@app_commands.describe(amount="Amount of money to change by", member="Player's account you want to adjust")
@app_commands.check(is_admin)
async def zz_change_player_bal(interaction: discord.Interaction, member: discord.Member, amount: str):
    await interaction.response.defer()
    try:
        decimal_amount = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        await interaction.followup.send("Invalid amount.")
        return

    try:
        with SessionLocal() as session:
            new_bal = admin_change_player_bal(session, str(member.id), decimal_amount)
            await interaction.followup.send(f"<@{member.id}>'s balance has been changed by ${decimal_amount:,.2f} to ${new_bal:,.2f}.")
    except ValueError as e:
        msg = str(e)
        await interaction.followup.send(msg)



# READY
@client.event
async def on_ready():
    tree.copy_global_to(guild=GUILD)
    await tree.sync(guild=GUILD)
    print(f'Logged in as {client.user}')

client.run(DISCORD_TOKEN)