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

    invasion = app_commands.Group(name="invasion", description="Comandos relacionados a invasoes")

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

    async def _send_invasion_notification(
        self,
        interaction: discord.Interaction,
        titulo: str,
        time: str,
        cor: str,
        description: str | None = None,
    ):
        if interaction.guild is None:
            await interaction.response.send_message("Esse comando so pode ser usado em servidor.", ephemeral=True)
            return

        if self._get_pool() is None:
            await interaction.response.send_message("Banco de dados indisponivel no momento.", ephemeral=True)
            return

        if not self._validate_time(time):
            await interaction.response.send_message("Hora invalida. Use o formato HH:MM (24h).", ephemeral=True)
            return

        try:
            embed_color = self._parse_hex_color(cor)
        except ValueError:
            await interaction.response.send_message(
                "Cor invalida. Use hexadecimal, por exemplo FF0000 ou #FF0000.",
                ephemeral=True,
            )
            return

        config = await self._fetch_invasion_config(interaction.guild.id)
        if config is None:
            await interaction.response.send_message(
                "Invasao ainda nao configurada. Use o painel para configurar primeiro.",
                ephemeral=True,
            )
            return

        invasion_channel = interaction.guild.get_channel(config["invasion_channel_id"])
        absence_channel = interaction.guild.get_channel(config["absence_channel_id"])
        notify_role = interaction.guild.get_role(config["notify_role_id"]) if config["notify_role_id"] else None

        if invasion_channel is None or absence_channel is None:
            await interaction.response.send_message(
                "Nao encontrei os canais configurados. Refaca a configuracao da invasao no painel.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=titulo,
            description=f"**Hora:** {time}\n**Descricao:** {description if description else 'Nenhuma descricao adicional fornecida.'}",
            color=discord.Color(embed_color),
        )
        cog = self

        class IdleInvasionJustification(discord.ui.Modal):
            def __init__(self):
                super().__init__(title="Justificativa de ausencia")
                self.justification = discord.ui.TextInput(
                    label="Motivo da ausencia",
                    style=discord.TextStyle.paragraph,
                    required=True,
                    max_length=500,
                )
                self.add_item(self.justification)

            async def on_submit(self, interaction: discord.Interaction):
                justification_embed = discord.Embed(
                    title="Justificativa de ausencia",
                    description=self.justification.value,
                    color=discord.Color.orange(),
                )
                justification_embed.add_field(name="Membro", value=interaction.user.mention, inline=False)
                justification_embed.add_field(name="Invasao", value=titulo, inline=False)
                justification_embed.add_field(name="Hora", value=time, inline=True)

                try:
                    await absence_channel.send(embed=justification_embed)
                except discord.Forbidden:
                    await interaction.response.send_message(
                        "Nao consegui enviar a justificativa no canal de ausencias.",
                        ephemeral=True,
                    )
                    return

                await interaction.response.send_message(
                    "Justificativa recebida e enviada para o canal de ausencias.",
                    ephemeral=True,
                )

        class InvasionButtons(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=3600)

            @discord.ui.button(label="Participar", style=discord.ButtonStyle.green)
            async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
                if not interaction.message or not interaction.message.embeds:
                    await interaction.response.send_message("Nao consegui atualizar a mensagem da invasao.", ephemeral=True)
                    return

                updated_embed, added = cog._build_participants_embed(interaction.message.embeds[0], interaction.user)
                if not added:
                    await interaction.response.send_message("Voce ja esta marcado como participante dessa invasao.", ephemeral=True)
                    return

                await interaction.response.edit_message(embed=updated_embed, view=self)
                await interaction.followup.send("Voce se juntou a invasao!", ephemeral=True)

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
                "Nao tenho permissao para enviar mensagens no canal de invasao configurado.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Notificacao enviada em {invasion_channel.mention}.",
            ephemeral=True,
        )

    @invasion.command(name="notify", description="Notifique sobre uma invasao iminente!")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        titulo="Titulo da invasao",
        time="Hora da invasao (formato: HH:MM)",
        cor="Cor do embed (formato hexadecimal, ex: FF0000)",
        description="Descricao adicional sobre a invasao",
    )
    async def notify(self, interaction: discord.Interaction, titulo: str, time: str, cor: str, description: str | None = None):
        await self._send_invasion_notification(interaction, titulo, time, cor, description)

    @notify.error
    async def invasion_notify_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            if interaction.response.is_done():
                await interaction.followup.send(
                    "Voce precisa da permissao de Gerenciar Servidor para usar este comando.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "Voce precisa da permissao de Gerenciar Servidor para usar este comando.",
                    ephemeral=True,
                )
    
    

async def setup(bot):
    await bot.add_cog(Invasion(bot))
