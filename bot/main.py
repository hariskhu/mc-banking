import os
import aiohttp
import discord
from discord import app_commands
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
MY_USER_ID = int(os.getenv('DISCORD_USER_ID'))
API_URL = os.getenv('BANK_API_URL')
GUILD = discord.Object(id=int(os.getenv('DISCORD_SERVER_ID')))

intents = discord.Intents.default()
intents.members = True 
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# DECORATOR FOR TEST COMMANDS
def is_me():
    def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.id == MY_USER_ID
    return app_commands.check(predicate)



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



# ERROR HANDLING
@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("You don't have permission to use this command!", ephemeral=True)
    else:
        print(f"Unhandled error: {error}")


@tree.error
async def on_client_connector_error(interaction: discord.Interaction, error: aiohttp.ClientConnectorError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("Error connecting to the bank, please try again later.", ephemeral=True)
    else:
        print(f"Unhandled error: {error}")



# PLAYER COMMANDS
@tree.command(name="info", description="Get info about CapitalTwo")
async def info(interaction: discord.Interaction):
    '''Returns an embed of information about the bot.'''
    capitaltwo_desc=(
        "CapitalTwo is a bank that will be on the BraxtonCraft 2 Minecraft server powered by ComputerCraft and Create. "
        "Money is backed by copper and can be exchanged for other precious metals based on the bank's supply. "
        "No verification is necessary to view your balance and other details, just commands in Discord.\n\n"
    )
    embed = discord.Embed(
        title="CapitalTwo Info",
        description=capitaltwo_desc,
        color=discord.Color.blurple()
    )
    embed.add_field(name="Exchange Currency 💴", value="The bank holds copper, iron, zinc, brass, and gold, allowing you to withdraw whatever you need.", inline=False)
    embed.add_field(name="Send Money 💸", value="Send money to other players instantly.", inline=False)
    embed.add_field(name="Guilds 🏛️", value="Create or join a guild to gain access to extra perks and aim to become the wealthiest.", inline=False)
    embed.add_field(name="Shop 🛒", value="Buy items from in-game shops using your digital currency.", inline=False)

    try:
        await interaction.response.send_message("Check your DMs!", ephemeral=True)
        await interaction.user.send(embed=embed)
    except discord.Forbidden:
        await interaction.response.send_message("I couldn't DM you! Make sure your DMs are open.", ephemeral=True)


@tree.command(name="register", description="Register for a bank account")
async def register(interaction: discord.Interaction):
    '''Creates a bank account for the user.'''
    await interaction.response.defer()
    async with aiohttp.ClientSession() as session:
        json={
            'discord_id': str(interaction.user.id),
            'discord_username': interaction.user.name
        }

        async with session.post(f"{API_URL}/players", json=json) as resp:
            if resp.status == 200:
                await interaction.followup.send(
                    f"🎊 <@{interaction.user.id}> has registered with CapitalTwo! 🎉"
                )
            elif resp.status == 409:
                await interaction.followup.send(
                    "You are already registered!"
                )
            else:
                await interaction.followup.send(
                    "Something went wrong while registering, please try again later."
                )


@tree.command(name="balance", description="View current balance")
async def balance(interaction: discord.Interaction):
    '''Return's a player's balance.'''
    await interaction.response.defer()
    async with aiohttp.ClientSession() as session:
        json={
            'discord_id': str(interaction.user.id),
        }

        async with session.get(f"{API_URL}/players", json=json) as resp:
            if resp.status == 200:
                data = await resp.json()
                balance = Decimal(data['balance'])
                avatar_url = interaction.user.display_avatar.url

                embed = discord.Embed(
                    title=f"{interaction.user.display_name}'s Balance",
                    description=f"# ${balance:.2f}",
                    color=discord.Color.green()
                )
                embed.set_thumbnail(url=avatar_url)
                await interaction.followup.send(embed=embed)
            elif resp.status == 404:
                await interaction.followup.send(
                    "You have not registered for an account yet, use `/register` !"
                )
            else:
                await interaction.followup.send(
                    "Could not retrieve your balance, please try again later."
                )


@tree.command(name="transfer", description="Transfer money to another player")
@app_commands.describe(amount="Amount of money to transfer", receiver="Transfer receiver")
async def transfer(interaction: discord.Interaction, amount: str, receiver: discord.Member):
    await interaction.response.defer()
    try:
        decimal_amount = Decimal(amount)
        rounded = decimal_amount.quantize(Decimal("0.00"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        await interaction.followup.send(
            "Invalid transfer amount."
        )
        return

    if rounded < Decimal("0.01"):
        await interaction.followup.send(
            "Transfer amount must be $0.01 or more when rounded."
        )
        return
        
    async with aiohttp.ClientSession() as session:
        json={
            'sender_discord_id': str(interaction.user.id),
            'receiver_discord_id': str(receiver.id),
            'transfer_amount': str(rounded)
        }

        async with session.post(f"{API_URL}/players/transfer", json=json) as resp:
            if resp.status == 200:
                await interaction.followup.send(
                    f"Sucessfully transferred ${rounded:.2f} to <@{receiver.id}>! 🤑"
                )
            elif resp.status == 402:
                await interaction.followup.send(
                    f"Insufficient balance to transfer ${rounded:.2f}."
                )
            elif resp.status == 404:
                await interaction.followup.send(
                    f"Could not find <@{receiver.id}>."
                )
            else:
                await interaction.followup.send(
                    "Transfer failed, please try again later."
                )


# GUILD COMMANDS
@tree.command(name="create_guild", description="Create a new guild")
@app_commands.describe(name="Guild name")
async def create_guild(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    stripped = name.strip()
    if len(stripped) > 30:
        await interaction.followup.send(
            "Guild name must be 30 characters or less."
        )
        return

    async with aiohttp.ClientSession() as session:
        json={
            'leader_discord_id': str(interaction.user.id),
            'name': name,
        }

        async with session.post(f"{API_URL}/guilds", json=json) as resp:
            if resp.status == 200:
                await interaction.followup.send(
                    f"Successfully created your guild: **{name}**! 🏛️"
                )
            elif resp.status == 409:
                await interaction.followup.send(
                    "You're already in a guild!"
                )
            else:
                await interaction.followup.send(
                    "Something went wrong when creating your guild, please try again later."
                )


@tree.command(name="leaderboard", description="View guild leaderboard")
async def leaderboard(interaction: discord.Interaction):
    await interaction.response.defer()
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_URL}/guilds/all") as resp:
            if resp.status == 200:
                items = await resp.json()
                rows = items['items']
                rows.sort(key=lambda x: Decimal(x['balance']), reverse=True)
                captain_names = {}
                for row in rows:
                    member = await get_or_fetch_member(int(row['leader_id']))
                    captain_names[row['id']] = member.global_name if member else "Unknown"

                # Lengths
                max_len_name = max(max(len(row['name']) for row in rows), len('NAME'))
                max_len_balance = max(max(len(str(row['balance'])) for row in rows), len("BALANCE")) + 1
                max_len_captain = max(max(len(name) for name in captain_names.values()), len("CAPTAIN"))

                COLSPACE = " " * 5
                columns = (
                    f"RANK{COLSPACE}{'NAME':^{max_len_name}}{COLSPACE}"
                    f"{'CAPTAIN':^{max_len_captain}}{COLSPACE}"
                    f"{'BALANCE':^{max_len_balance}}{COLSPACE}ID\n"
                )
                
                title = f"{'🏆 Guild Leaderboard 🏆':^{len(columns)}}\n\n"
                big_line = "-" * len(columns) + "\n"
                lb = ""

                i = 1
                last_bal = Decimal(rows[0]['balance']) if rows else 0
                for row in rows:
                    cap_name = captain_names[row['id']]
                    
                    entry = (
                        f"{i:^4}{COLSPACE}"
                        f"{row['name']:^{max_len_name}}{COLSPACE}"
                        f"{cap_name:^{max_len_captain}}{COLSPACE}"
                        f"{('$' + row['balance']):^{max_len_balance}}{COLSPACE}"
                        f"{row['id']:^3}\n"
                    )
                    lb += entry

                    bal_val = Decimal(row['balance'])
                    if bal_val != last_bal:
                        i += 1
                    last_bal = bal_val

                await interaction.followup.send(f"```\n{title}{columns}{big_line}{lb}```")
            else:
                await interaction.followup.send("Could not retrieve leaderboard.")



# READY
@client.event
async def on_ready():
    tree.copy_global_to(guild=GUILD)
    await tree.sync(guild=GUILD)
    print(f'Logged in as {client.user}')

client.run(DISCORD_TOKEN)