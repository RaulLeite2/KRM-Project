import discord
from discord.ext import commands
from discord import app_commands
import os
from pathlib import Path
import dotenv
import asyncpg

dotenv.load_dotenv()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="$", intents=intents)
TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")


async def init_database(pool: asyncpg.Pool):
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id BIGINT PRIMARY KEY,
            welcome_channel_id BIGINT,
            welcome_message TEXT,
            exit_channel_id BIGINT,
            exit_message TEXT
        )
        """
    )
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS member_joins (
            id SERIAL PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            member_id BIGINT NOT NULL,
            joined_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS user_birthdays (
            guild_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            day INTEGER NOT NULL CHECK (day BETWEEN 1 AND 31),
            month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (guild_id, user_id)
        )
        """
    )
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS birthday_settings (
            guild_id BIGINT PRIMARY KEY,
            channel_id BIGINT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    print("[DB] Tabelas verificadas.")


@bot.event
async def on_ready():
    print(f"[BOT] Logado como {bot.user} (ID: {bot.user.id})")
    print("------")


async def setup_cogs(bot):
    cogs = [
        path.with_suffix("").as_posix().replace("/", ".")
        for path in Path("cogs").rglob("*.py")
        if path.name != "__init__.py"
    ]

    for cog in cogs:
        await bot.load_extension(cog)
        print(f"[COGS] Carregado: {cog}")

    print(f"[COGS] {len(cogs)} cog(s) carregado(s).")


async def setup_hook():
    bot.pool = await asyncpg.create_pool(DATABASE_URL)
    print("[DB] Pool de conexoes criado.")

    await init_database(bot.pool)
    await setup_cogs(bot)

    try:
        synced = await bot.tree.sync()
        names = [c.name for c in synced]
        print(f"[SYNC] {len(synced)} comando(s) sincronizado(s): {names}")
    except Exception as e:
        print(f"[SYNC] Falha ao sincronizar comandos: {e}")


bot.setup_hook = setup_hook

bot.run(TOKEN)