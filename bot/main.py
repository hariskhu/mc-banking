import os
import discord
from discord import app_commands
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from dotenv import load_dotenv
from app.database import SessionLocal
from sqlalchemy import select, func

from app.services.banking import (
    register_player,
    get_player,
    get_player_bal,
    get_guild_bal,
    player_transfer,
    guild_deposit,
    guild_withdraw,
    admin_change_player_bal,
    update_username,
    Account
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

from app.services.predictions import (
    get_active_prediction,
    create_prediction,
    place_bet,
    get_bets,
    get_prediction_totals,
    resolve_prediction,
    refund_prediction,
    PredictionSide,
)

from app.services.materials import (
    get_all_spot_prices,
    process_deposit,
    process_withdrawal,
    Material
)

load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GUILD = discord.Object(id=int(os.getenv('DISCORD_SERVER_ID')))
ADMIN_IDS = [
    int(user_id.strip())
    for user_id in os.getenv("ADMIN_IDS", "").split(",")
    if user_id.strip()
]
material_choices = [
    app_commands.Choice(name="Copper Nugget", value="minecraft:copper_nugget"),
    app_commands.Choice(name="Zinc Nugget",   value="create:zinc_nugget"),
    app_commands.Choice(name="Iron Nugget",   value="minecraft:iron_nugget"),
    app_commands.Choice(name="Gold Nugget",   value="minecraft:gold_nugget"),
    app_commands.Choice(name="Diamond",       value="minecraft:diamond"),
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
                await interaction.followup.send("You do not have an account! Use `/register` !")
            else:
                await interaction.followup.send(msg)

@tree.command(name="set_minecraft_name", description="Link your Minecraft username to your bank account")
@app_commands.describe(username="Your Minecraft username")
async def set_minecraft_name_cmd(interaction: discord.Interaction, username: str):
    await interaction.response.defer()

    with SessionLocal() as session:
        try:
            update_username(session, str(interaction.user.id), username.strip())
            await interaction.followup.send(
                f"Minecraft username set to **{username.strip()}**! "
                f"It will now appear on your profile."
            )
        except ValueError as e:
            await interaction.followup.send(str(e))

@tree.command(name="profile", description="View a player's profile")
@app_commands.describe(player="Player you want details about")
async def details(interaction: discord.Interaction, player: discord.Member):
    """Returns a player's name, minecraft name, balance, guild, and guild role."""
    await interaction.response.defer()

    with SessionLocal() as session:
        try:
            discord_id = str(player.id)

            p = get_player(session, discord_id)
            balance = get_player_bal(session, discord_id)

            try:
                role = get_member_role(session, discord_id)
                guild = get_guild(session, discord_id)
                guild_name = guild.name
                guild_role = role.value
            except ValueError:
                guild_name = None
                guild_role = None

        except ValueError:
            await interaction.followup.send(
                "That player has not registered for an account yet. They can use `/register` to sign up!"
            )
            return

    # Build title
    name = player.display_name
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

    if p.mc_username:
        skin_url = f"https://mineskin.eu/helm/{p.mc_username}"
        embed.set_thumbnail(url=skin_url)
        embed.set_footer(text=player.display_name, icon_url=player.display_avatar.url)
    else:
        embed.set_thumbnail(url=player.display_avatar.url)

    await interaction.followup.send(embed=embed)


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
                await interaction.followup.send(f"Transfer failed, make sure you both have a bank account (`/register`).")
            else:
                await interaction.followup.send(msg)


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
            msg = str(e)
            if "not registered" in msg:
                await interaction.followup.send("You do not have an account! Use `/register` !")
            else:
                await interaction.followup.send(msg)
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
                await interaction.followup.send("One of you has not registered, use `/register` first.")
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
            msg = str(e)
            if "not registered" in msg:
                await interaction.followup.send("One of you has not registered, use `/register` first.")
            else:
                await interaction.followup.send(msg)

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
                await interaction.followup.send("You don't have a bank account yet. Use `/register` first!")
            elif "already registered" in msg:
                await interaction.followup.send("You already registered!")
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
            msg = str(e)
            if "not registered" in msg:
                await interaction.followup.send("You don't have a bank account yet. Use `/register` first!")
            else:
                await interaction.followup.send(msg)
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
            msg = str(e)
            if "not registered" in msg:
                await interaction.followup.send("You don't have a bank account yet. Use `/register` first!")
            else:
                await interaction.followup.send(msg)
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
            msg = str(e)
            if "not registered" in msg:
                await interaction.followup.send("You don't have a bank account yet. Use `/register` first!")
            else:
                await interaction.followup.send(msg)
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
                await interaction.followup.send(f"One of you does not have a bank account. Use `/register`.")
            else:
                await interaction.followup.send(msg)


# Admin commands (zz_ prefix)

@tree.command(name="zz_change_player_bal", description="[ADMIN] Change's a user's account balance by a given quantity")
@app_commands.describe(amount="Amount of money", member="Player's account you want to adjust")
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
        if "not registered" in msg:
                await interaction.followup.send("You don't have a bank account yet. Use `/register` first!")
        else:
            await interaction.followup.send(msg)


# -------- PREDICTION MARKET COMMANDS --------

@tree.command(name="prediction_bet", description="Place a bet on the active prediction")
@app_commands.describe(side="Side to bet on", amount="Amount to bet")
@app_commands.choices(side=[
    app_commands.Choice(name="Yes", value="yes"),
    app_commands.Choice(name="No", value="no"),
])
async def bet_cmd(interaction: discord.Interaction, side: app_commands.Choice[str], amount: str):
    await interaction.response.defer()

    try:
        decimal_amount = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        await interaction.followup.send("Invalid amount.")
        return

    if decimal_amount < Decimal("0.01"):
        await interaction.followup.send("Bet must be at least $0.01.")
        return

    with SessionLocal() as session:
        try:
            place_bet(session, str(interaction.user.id), decimal_amount, PredictionSide[side.value])
            await interaction.followup.send(
                f"<@{interaction.user.id}> placed a **${decimal_amount:,.2f}** bet on **{side.name}**! 🎲"
            )
        except ValueError as e:
            msg = str(e)
            if "No player account" in msg:
                await interaction.followup.send("You don't have a bank account yet. Use `/register` first!")
            else:
                await interaction.followup.send(msg)


@tree.command(name="prediction", description="View the active prediction and all bets")
async def prediction_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    with SessionLocal() as session:
        prediction = get_active_prediction(session)
        if not prediction:
            await interaction.followup.send("There is no active prediction right now.")
            return

        bets = get_bets(session, prediction.id)
        totals = get_prediction_totals(session, prediction.id)

    total_pot = totals[PredictionSide.yes] + totals[PredictionSide.no]

    yes_bets = [b for b in bets if b.side == PredictionSide.yes]
    no_bets  = [b for b in bets if b.side == PredictionSide.no]

    def bet_lines(bet_list):
        if not bet_list:
            return "*No bets yet*"
        return "\n".join(
            f"<@{b.discord_id}> — **${b.amount:,.2f}**"
            for b in bet_list
        )

    embed = discord.Embed(
        title=f"🎲 {prediction.question}",
        color=discord.Color.blue(),
    )
    embed.add_field(
        name=f"✅ Yes — ${totals[PredictionSide.yes]:,.2f}",
        value=bet_lines(yes_bets),
        inline=True,
    )
    embed.add_field(
        name=f"❌ No — ${totals[PredictionSide.no]:,.2f}",
        value=bet_lines(no_bets),
        inline=True,
    )
    embed.set_footer(text=f"Total pot: ${total_pot:,.2f}")
    await interaction.followup.send(embed=embed)


# Admin commands (zz_ prefix)

@tree.command(name="zz_create_prediction", description="[ADMIN] Create a new prediction market")
@app_commands.describe(question="The prediction question")
@app_commands.check(is_admin)
async def zz_create_prediction(interaction: discord.Interaction, question: str):
    await interaction.response.defer()
    with SessionLocal() as session:
        try:
            prediction = create_prediction(session, question.strip(), str(interaction.user.id))
            embed = discord.Embed(
                title="Prediction created! 🎲",
                description=f"# **{prediction.question}**",
                color=discord.Color.pink(),
            )
            embed.set_footer(text="Use /prediction_bet to place a bet!")

            await interaction.followup.send(embed=embed)
        except ValueError as e:
            await interaction.followup.send(str(e))


@tree.command(name="zz_resolve_prediction", description="[ADMIN] Resolve the active prediction")
@app_commands.choices(outcome=[
    app_commands.Choice(name="Yes", value="yes"),
    app_commands.Choice(name="No", value="no"),
])
@app_commands.check(is_admin)
async def zz_resolve_prediction(interaction: discord.Interaction, outcome: app_commands.Choice[str]):
    await interaction.response.defer()

    with SessionLocal() as session:
        try:
            prediction = get_active_prediction(session)
            if not prediction:
                await interaction.followup.send("There is no active prediction to resolve.")
                return

            totals = get_prediction_totals(session, prediction.id)
            total_pot = totals[PredictionSide.yes] + totals[PredictionSide.no]
            question = prediction.question

            results = resolve_prediction(session, prediction.id, PredictionSide[outcome.value])

        except ValueError as e:
            await interaction.followup.send(str(e))
            return

    color = discord.Color.red() if outcome.name == "No" else discord.Color.green()
    embed = discord.Embed(
                title="Prediction resolved! 🎲",
                description=(
                    f"**{question}** resolved as **{outcome.name}**!\n\n"
                    f"Total pot of **${total_pot:,.2f}** distributed to winners. 🏆"
                ),
                color=color,
    )

    await interaction.followup.send(embed=embed)

    # DM each participant
    for discord_id, result in results.items():
        try:
            user = await interaction.client.fetch_user(int(discord_id))
            if user is None:
                print(f"User {discord_id} not found, skipping")
                continue

            winning_bet = result["winning_bet"]
            losing_bet  = result["losing_bet"]
            payout      = result["payout"]
            won         = result["won"]
            net         = payout - (winning_bet + losing_bet)

            if won is None:
                dm_embed = discord.Embed(
                    title="Prediction Resolved",
                    description=question,
                    color=discord.Color.gold()
                )
                dm_embed.add_field(
                    name="Result",
                    value=(
                        "Nobody bet on the winning side.\n"
                        f"Your total bet of **${result['refund']:,.2f}** has been refunded."
                    ),
                    inline=False
                )
            elif won:
                dm_embed = discord.Embed(
                    title="Prediction Resolved ✅",
                    description=f"{question}",
                    color=discord.Color.green()
                )
                dm_embed.add_field(name="Outcome", value=f"**{outcome.name}**", inline=False)
                if winning_bet > 0:
                    dm_embed.add_field(
                        name="Winning Bet",
                        value=f"**${winning_bet:,.2f}** → **${payout:,.2f}**",
                        inline=True
                    )
                if losing_bet > 0:
                    dm_embed.add_field(
                        name="Losing Bet",
                        value=f"**${losing_bet:,.2f}** → **$0.00**",
                        inline=True
                    )
                dm_embed.add_field(
                    name="Net Result",
                    value=f"**{'+' if net >= 0 else ''}${net:,.2f}** 🎉",
                    inline=False
                )
            else:
                total_bet = winning_bet + losing_bet
                dm_embed = discord.Embed(
                    title="Prediction Resolved ❌",
                    description=f"{question}",
                    color=discord.Color.red()
                )
                dm_embed.add_field(name="Outcome", value=f"**{outcome.name}** — You lost", inline=False)
                dm_embed.add_field(
                    name="Bet Summary",
                    value=(
                        f"Total Bet: **${total_bet:,.2f}**\n"
                        f"Payout: **$0.00**\n"
                        f"Loss: **-${total_bet:,.2f}** 😔"
                    ),
                    inline=False
                )

            await user.send(embed=dm_embed)
            print(f"DM sent to {discord_id}")

        except discord.Forbidden:
            print(f"Forbidden — {discord_id} has DMs closed")
        except discord.NotFound:
            print(f"NotFound — {discord_id} doesn't exist")
        except Exception as e:
            print(f"Unexpected error DMing {discord_id}: {e}")


@tree.command(name="zz_refund_prediction", description="[ADMIN] Refund all bets on the active prediction")
@app_commands.check(is_admin)
async def zz_refund_prediction(interaction: discord.Interaction):
    await interaction.response.defer()

    with SessionLocal() as session:
        try:
            prediction = get_active_prediction(session)
            if not prediction:
                await interaction.followup.send("There is no active prediction to refund.")
                return

            question = prediction.question
            bets = refund_prediction(session, prediction.id)

        except ValueError as e:
            await interaction.followup.send(str(e))
            return

    embed = discord.Embed(
        title=f"Prediction for **{question}** cancelled",
        description=f"All **{len(bets)}** bet{'s' if len(bets) != 1 else ''} have been refunded. 💸",
        color=discord.Color.yellow()
    )
    await interaction.followup.send(embed=embed)

    for bet in bets:
        try:
            user = await interaction.client.fetch_user(int(bet.discord_id))
            dm_embed = discord.Embed(
                title=f"Prediction cancelled: **{question}**",
                description=f"Your bets have been refunded. 💸",
                color=discord.Color.yellow()
            )
            await user.send(embed=dm_embed)
        except (discord.Forbidden, discord.NotFound):
            pass


# -------- MATERIALS MARKET/BANK TERMINAL COMMANDS --------
# Regular commands
@tree.command(name="exchange_rates", description="View current material exchange rates")
async def exchange_rates_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    with SessionLocal() as session:
        try:
            rates = get_all_spot_prices(session)
        except ValueError as e:
            await interaction.followup.send(str(e))
            return

    lines = ["**Copper Nugget** — $0.01"]
    for r in rates:
        if r["mc_id"] == "minecraft:copper_nugget":
            continue
        else:
            factor = r["spot_price"] / Decimal("0.0100")
            lines.append(f"**{r['name']}** — ${r['spot_price']:,.2f} ({factor:,.1f}x)")

    embed = discord.Embed(
        title="📊 Exchange Rates",
        description="\n".join(lines),
        color=discord.Color.gold(),
    )
    await interaction.followup.send(embed=embed)


# Admin commands

@tree.command(name="zz_sim_deposit", description="[ADMIN] Simulate a material deposit")
@app_commands.describe(member="Player to deposit for", material="Material to deposit", quantity="Quantity to deposit")
@app_commands.choices(material=material_choices)
@app_commands.check(is_admin)
async def zz_sim_deposit(interaction: discord.Interaction, member: discord.Member, material: app_commands.Choice[str], quantity: int):
    await interaction.response.defer()

    if quantity <= 0:
        await interaction.followup.send("Quantity must be positive.")
        return

    with SessionLocal() as session:
        try:
            result = process_deposit(
                session,
                str(member.id),
                [{"mc_id": material.value, "quantity": quantity}]
            )
        except ValueError as e:
            await interaction.followup.send(str(e))
            return

    b = result["breakdown"][0]
    embed = discord.Embed(
        title="🧪 Simulated Deposit",
        description=f"Deposited on behalf of <@{member.id}>",
        color=discord.Color.green(),
    )
    embed.add_field(name="Material", value=b["material"], inline=True)
    embed.add_field(name="Quantity", value=f"{quantity:,}", inline=True)
    embed.add_field(name="Value", value=f"**${b['value']:,.2f}**", inline=True)
    embed.add_field(name="New Supply", value=f"{b['new_supply']:,}", inline=True)
    embed.add_field(name="New Spot Price", value=f"${b['spot_price']:,.2f}", inline=True)
    embed.add_field(name="Total Credited", value=f"**${result['total']:,.2f}**", inline=False)
    await interaction.followup.send(embed=embed)


@tree.command(name="zz_sim_withdrawal", description="[ADMIN] Simulate a material withdrawal")
@app_commands.describe(member="Player to withdraw for", material="Material to withdraw", quantity="Quantity to withdraw")
@app_commands.choices(material=material_choices)
@app_commands.check(is_admin)
async def zz_sim_withdrawal(interaction: discord.Interaction, member: discord.Member, material: app_commands.Choice[str], quantity: int):
    await interaction.response.defer()

    if quantity <= 0:
        await interaction.followup.send("Quantity must be positive.")
        return

    with SessionLocal() as session:
        try:
            result = process_withdrawal(
                session,
                str(member.id),
                [{"mc_id": material.value, "quantity": quantity}]
            )
        except ValueError as e:
            await interaction.followup.send(str(e))
            return

    b = result["breakdown"][0]
    embed = discord.Embed(
        title="🧪 Simulated Withdrawal",
        description=f"Withdrawn on behalf of <@{member.id}>",
        color=discord.Color.red(),
    )
    embed.add_field(name="Material", value=b["material"], inline=True)
    embed.add_field(name="Quantity", value=f"{quantity:,}", inline=True)
    embed.add_field(name="Cost", value=f"**${b['cost']:,.2f}**", inline=True)
    embed.add_field(name="New Supply", value=f"{b['new_supply']:,}", inline=True)
    embed.add_field(name="New Spot Price", value=f"${b['spot_price']:,.2f}", inline=True)
    embed.add_field(name="Total Debited", value=f"**${result['total_cost']:,.2f}**", inline=False)
    await interaction.followup.send(embed=embed)


@tree.command(name="zz_bank_supply", description="[ADMIN] View current vault supply for all materials")
@app_commands.describe(ephemeral="Send as ephemeral message (default: DM)")
@app_commands.check(is_admin)
async def zz_bank_supply(interaction: discord.Interaction, ephemeral: bool = False):
    await interaction.response.defer(ephemeral=ephemeral)

    with SessionLocal() as session:
        try:
            rates = get_all_spot_prices(session)
        except ValueError as e:
            await interaction.followup.send(str(e), ephemeral=ephemeral)
            return

    embed = discord.Embed(
        title="🏦 Vault Supply",
        color=discord.Color.blue(),
    )

    for r in rates:
        supply_pct = (r["current_supply"] / r["ideal_supply"] * 100) if r["ideal_supply"] > 0 else 0
        bar_filled = min(int(supply_pct / 10), 10)
        oversupply = supply_pct > 100
        bar = "█" * bar_filled + ("░" * (10 - bar_filled) if not oversupply else "")
        supply_str = f"{r['current_supply']:,} / {r['ideal_supply']:,}"

        embed.add_field(
            name=r["name"],
            value=(
                f"`{bar}` {supply_pct:.1f}%{'  ⚠️ OVERSUPPLIED' if oversupply else ''}\n"
                f"{r['current_supply']:,} / {r['ideal_supply']:,}\n"
                f"Spot: **${r['spot_price']:,.2f}**"
            ),
            inline=True,
        )

    if ephemeral:
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.followup.send("Check your DMs!", ephemeral=True)
        await interaction.user.send(embed=embed)

@tree.command(name="zz_sync_copper_supply", description="[ADMIN] Sync copper vault supply to total money in economy")
@app_commands.check(is_admin)
async def zz_sync_copper_supply(interaction: discord.Interaction):
    await interaction.response.defer()

    with SessionLocal() as session:
        try:
            # Sum all account balances
            total_money = session.scalar(
                select(func.sum(Account.balance))
            ) or Decimal("0")

            # Convert dollars to copper nuggets (1 nugget = $0.01)
            total_nuggets = int((total_money / Decimal("0.01")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

            copper = session.scalar(
                select(Material).where(Material.mc_id == "minecraft:copper_nugget")
            )
            if not copper:
                await interaction.followup.send("Copper not found in materials table.")
                return

            old_supply = copper.current_supply
            copper.current_supply = total_nuggets
            session.commit()

            await interaction.followup.send(
                f"Copper supply synced.\n"
                f"Total money in economy: **${total_money:,.2f}**\n"
                f"Old supply: **{old_supply:,}** nuggets\n"
                f"New supply: **{total_nuggets:,}** nuggets"
            )
        except Exception as e:
            await interaction.followup.send(str(e))

# READY
@client.event
async def on_ready():
    tree.copy_global_to(guild=GUILD)
    await tree.sync(guild=GUILD)
    print(f'Logged in as {client.user}')

client.run(DISCORD_TOKEN)