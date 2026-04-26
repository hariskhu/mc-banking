import os
import aiohttp
import discord
from discord import app_commands
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



@tree.command(name="hello", description="Says hello!")
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message("Hello!")

@tree.command(name="info", description="Get info about this bot!")
async def info(interaction: discord.Interaction):
    capitaltwo_desc=(
        "CapitalTwo is a bank that will be on the BraxtonCraft 2 Minecraft server powered by ComputerCraft and Create. "
        "Money is backed by copper and can be exchanged for other precious metals based on the bank's supply.\n\n"
        "On the Discord server, no verification is necessary to view your balance and other details. "
        "All you need to access your account in-game is your Discord username, tag, and a password (WIP).\n\n"
    )
    embed = discord.Embed(
        title="CapitalTwo Info",
        description=capitaltwo_desc,
        color=discord.Color.blurple()
    )
    embed.add_field(name="Exchange currency", value="The bank holds copper, iron, nickel, brass, and gold, allowing you to withdraw whatever you need.", inline=False)
    embed.add_field(name="Shop", value="Automate your stores to work offline and deposit profits straight into your account.", inline=False)
    embed.add_field(name="Send money", value="Send money to other players instantly, even when you aren't playing.", inline=False)
    embed.add_field(name="Loans", value="Take out loans to fund your big projects. No interest, just a one-time fee.", inline=False)

    try:
        await interaction.response.send_message("Check your DMs!", ephemeral=True)
        await interaction.user.send(embed=embed)
    except discord.Forbidden:
        await interaction.response.send_message("I couldn't DM you! Make sure your DMs are open.", ephemeral=True)

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