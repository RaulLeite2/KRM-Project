# ESTE COG NÃO SÃO COMANDOS DE RAID! E SIM DE NOTIFICAÇÃO DE INVASÃO!
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

class Invasion(commands.Cog):
    PARTICIPANTS_FIELD_NAME = "Participantes"

    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        pool = self._get_pool()
        if pool is None:
            return

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS invasions (
                guild_id BIGINT PRIMARY KEY,
                invasion_channel_id BIGINT NOT NULL,
                absence_channel_id BIGINT NOT NULL,
                notify_role_id BIGINT
            )
            """
        )
        await pool.execute(
            "ALTER TABLE invasions ADD COLUMN IF NOT EXISTS notify_role_id BIGINT"
        )

    def _get_pool(self):
        # Compatibilidade com projetos que usem bot.pool ou bot.db.
        return getattr(self.bot, "pool", None) or getattr(self.bot, "db", None)

    @staticmethod
    def _parse_hex_color(color_input: str) -> int:
        cleaned = color_input.strip().lstrip("#")
        parsed = int(cleaned, 16)
        if parsed < 0 or parsed > 0xFFFFFF:
            raise ValueError("Color out of range")
        return parsed

    @staticmethod
    def _validate_time(time_input: str) -> bool:
        try:
            datetime.strptime(time_input, "%H:%M")
            return True
        except ValueError:
            return False

    async def _fetch_invasion_config(self, guild_id: int) -> Optional[dict]:
        pool = self._get_pool()
        if pool is None:
            return None

        async with pool.acquire() as connection:
            return await connection.fetchrow(
                """
                SELECT invasion_channel_id, absence_channel_id, notify_role_id
                FROM invasions
                WHERE guild_id = $1
                """,
                guild_id,
            )

    def _build_participants_embed(self, source_embed: discord.Embed, member: discord.Member) -> tuple[discord.Embed, bool]:
        updated_embed = discord.Embed.from_dict(source_embed.to_dict())
        participants = []
        participants_index = None

        for index, field in enumerate(updated_embed.fields):
            if field.name != self.PARTICIPANTS_FIELD_NAME:
                continue
            participants_index = index
            participants = [line.strip() for line in field.value.splitlines() if line.strip()]
            break

        if member.mention in participants:
            return updated_embed, False

        participants.append(member.mention)
        participants_value = "\n".join(participants)

        if participants_index is None:
            updated_embed.add_field(
                name=self.PARTICIPANTS_FIELD_NAME,
                value=participants_value,
                inline=False,
            )
            return updated_embed, True

        updated_embed.set_field_at(
            participants_index,
            name=self.PARTICIPANTS_FIELD_NAME,
            value=participants_value,
            inline=False,
        )
        return updated_embed, True

async def setup(bot):
    await bot.add_cog(Invasion(bot))
