import os
import aiohttp
import discord
from discord import app_commands
from decimal import Decimal
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

def is_me():
    def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.id == MY_USER_ID
    return app_commands.check(predicate)

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



@tree.command(name="hello", description="Says hello!")
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message("Hello!")

@tree.command(name="info", description="Get info about this bot!")
async def info(interaction: discord.Interaction):
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
                    "You already registered!"
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

# Debug commmands
@tree.command(name="api_test", description="Tests the bank API")
@is_me()
async def api_test(interaction: discord.Interaction):
    await interaction.response.defer()
    async with aiohttp.ClientSession() as session:
        async with session.get(API_URL) as resp:
            text = await resp.text()
            await interaction.followup.send(f"API RESPONSE:\n{text}")

@client.event
async def on_ready():
    tree.copy_global_to(guild=GUILD)
    await tree.sync(guild=GUILD)

    print(f'Logged in as {client.user}')

client.run(DISCORD_TOKEN)