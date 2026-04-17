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

    invasion = app_commands.Group(name="invasion", description="Comandos relacionados a invasões")

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

    @invasion.command(name="setup", description="Configura invasão e o chat de ausencias")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        channel="Canal onde as notificações de invasão serão enviadas",
        absence_channel="Canal onde os membros podem justificar suas ausências",
        notify_role="Cargo que será marcado nas notificações de invasão"
    )
    async def setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        absence_channel: discord.TextChannel,
        notify_role: Optional[discord.Role] = None,
    ):
        if interaction.guild is None:
            await interaction.response.send_message("Esse comando só pode ser usado em servidor.", ephemeral=True)
            return

        pool = self._get_pool()
        if pool is None:
            await interaction.response.send_message("Banco de dados indisponível no momento.", ephemeral=True)
            return

        async with pool.acquire() as connection:
            await connection.execute("""
                INSERT INTO invasions (guild_id, invasion_channel_id, absence_channel_id, notify_role_id)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (guild_id) DO UPDATE
                SET invasion_channel_id = EXCLUDED.invasion_channel_id,
                    absence_channel_id = EXCLUDED.absence_channel_id,
                    notify_role_id = EXCLUDED.notify_role_id
            """, interaction.guild.id, channel.id, absence_channel.id, notify_role.id if notify_role else None)

        role_message = notify_role.mention if notify_role else "nenhum cargo"
        await interaction.response.send_message(
            f"Invasão configurada para o canal {channel.mention}, justificativas para {absence_channel.mention} e cargo notificado: {role_message}.",
            ephemeral=True,
        )

    @invasion.command(name="notify", description="Notifique sobre uma invasão iminente!")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        titulo="Título da invasão",
        time="Hora da invasão (formato: HH:MM)",
        cor="Cor do embed (formato hexadecimal, ex: FF0000)",
        description="Descrição adicional sobre a invasão(exemplo o jogo que irá ser invadido)"
    )
    async def notify(self, interaction: discord.Interaction, titulo: str, time: str, cor: str, description: str = None):
        if interaction.guild is None:
            await interaction.response.send_message("Esse comando só pode ser usado em servidor.", ephemeral=True)
            return

        if self._get_pool() is None:
            await interaction.response.send_message("Banco de dados indisponível no momento.", ephemeral=True)
            return

        if not self._validate_time(time):
            await interaction.response.send_message("Hora inválida. Use o formato HH:MM (24h).", ephemeral=True)
            return

        try:
            embed_color = self._parse_hex_color(cor)
        except ValueError:
            await interaction.response.send_message("Cor inválida. Use hexadecimal, por exemplo: FF0000 ou #FF0000.", ephemeral=True)
            return

        config = await self._fetch_invasion_config(interaction.guild.id)
        if config is None:
            await interaction.response.send_message(
                "Invasão ainda não configurada. Use /invasion setup primeiro.",
                ephemeral=True,
            )
            return

        invasion_channel = interaction.guild.get_channel(config["invasion_channel_id"])
        absence_channel = interaction.guild.get_channel(config["absence_channel_id"])
        notify_role = interaction.guild.get_role(config["notify_role_id"]) if config["notify_role_id"] else None

        if invasion_channel is None or absence_channel is None:
            await interaction.response.send_message(
                "Não encontrei os canais configurados. Rode /invasion setup novamente.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=titulo,
            description=f"**Hora:** {time}\n**Descrição:** {description if description else 'Nenhuma descrição adicional fornecida.'}",
            color=discord.Color(embed_color)
        )
        cog = self

        class IdleInvasionJustification(discord.ui.Modal):
            def __init__(self):
                super().__init__(title="Justificativa para ficar de fora da invasão")

                self.justification = discord.ui.TextInput(
                    label="Motivo da ausência",
                    style=discord.TextStyle.paragraph,
                    required=True,
                    max_length=500
                )
                self.add_item(self.justification)

            async def on_submit(self, interaction: discord.Interaction):
                justification_embed = discord.Embed(
                    title="Justificativa de ausência",
                    description=self.justification.value,
                    color=discord.Color.orange(),
                )
                justification_embed.add_field(name="Membro", value=interaction.user.mention, inline=False)
                justification_embed.add_field(name="Invasão", value=titulo, inline=False)
                justification_embed.add_field(name="Hora", value=time, inline=True)

                try:
                    await absence_channel.send(embed=justification_embed)
                except discord.Forbidden:
                    await interaction.response.send_message(
                        "Não consegui enviar sua justificativa no canal de ausências (permissão negada).",
                        ephemeral=True,
                    )
                    return

                await interaction.response.send_message("Justificativa recebida e enviada para o canal de ausências.", ephemeral=True)

        class InvasionButtons(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=3600)

            @discord.ui.button(label="Participar", style=discord.ButtonStyle.green)
            async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
                if not interaction.message or not interaction.message.embeds:
                    await interaction.response.send_message("Não consegui atualizar a mensagem da invasão.", ephemeral=True)
                    return

                updated_embed, added = cog._build_participants_embed(interaction.message.embeds[0], interaction.user)
                if not added:
                    await interaction.response.send_message("Você já está marcado como participante dessa invasão.", ephemeral=True)
                    return

                await interaction.response.edit_message(embed=updated_embed, view=self)
                await interaction.followup.send("Você se juntou à invasão!", ephemeral=True)

            @discord.ui.button(label="Ficar de fora", style=discord.ButtonStyle.red)
            async def idle(self, interaction: discord.Interaction, button: discord.ui.Button):
                await interaction.response.send_modal(IdleInvasionJustification())

        try:
            await invasion_channel.send(
                content=notify_role.mention if notify_role else None,
                embed=embed,
                view=InvasionButtons(),
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "Não tenho permissão para enviar mensagens no canal de invasão configurado.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Notificação enviada em {invasion_channel.mention}.",
            ephemeral=True,
        )

    @setup.error
    @notify.error
    async def invasion_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            if interaction.response.is_done():
                await interaction.followup.send(
                    "Você precisa da permissão 'Gerenciar Servidor' para usar este comando.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "Você precisa da permissão 'Gerenciar Servidor' para usar este comando.",
                    ephemeral=True,
                )


async def setup(bot):
    await bot.add_cog(Invasion(bot))
