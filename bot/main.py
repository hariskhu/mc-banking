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

@tree.command(name="api_test", description="Tests the bank API")
@is_me
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