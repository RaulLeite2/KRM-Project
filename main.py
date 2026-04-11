import discord
from discord.ext import commands
from discord import app_commands
import os
from pathlib import Path
import dotenv
import sqlite3

dotenv.load_dotenv()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="$", intents=intents)
TOKEN = os.getenv("TOKEN")
DB_PATH = "bot.db"

def init_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER PRIMARY KEY,
            welcome_channel_id INTEGER,
            welcome_message TEXT,
            exit_channel_id INTEGER,
            exit_message TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS member_joins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            member_id INTEGER NOT NULL,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()
    conn.close()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

async def setup_cogs(bot):
    cogs = [
        path.with_suffix("").as_posix().replace("/", ".")
        for path in Path("cogs").rglob("*.py")
        if path.name != "__init__.py"
    ]

    for cog in cogs:
        await bot.load_extension(cog)

    print(f"{len(cogs)} cog(s) carregado(s).")

async def setup_hook():
    await setup_cogs(bot)

bot.setup_hook = setup_hook

init_database()
bot.run(TOKEN)