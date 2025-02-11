import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from chode import commands as chode_commands

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise Exception("Discord token not found in .env file.")

# Set up intents (including voice_states for voice channel functionality)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True
intents.voice_states = True

# Create the bot instance; allow invocation by prefix "!!" or by mentioning the bot.
bot = commands.Bot(command_prefix=commands.when_mentioned_or("!!"), intents=intents)

# Register commands and event handlers from our commands module
chode_commands.setup_commands(bot)

# Run the bot
bot.run(TOKEN)
