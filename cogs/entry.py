import discord
from discord.ext import commands
from discord import app_commands
import sqlite3

DB_PATH = "bot.db"

class Entry(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_conn(self):
        return sqlite3.connect(DB_PATH)

    # ── Eventos ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member):
        conn = self._get_conn()
        row = conn.execute(
            "SELECT welcome_channel_id, welcome_message FROM guild_settings WHERE guild_id = ?",
            (member.guild.id,),
        ).fetchone()
        conn.close()

        if row and row[0] and row[1]:
            channel = member.guild.get_channel(row[0])
            if channel:
                await channel.send(row[1].replace("{member}", member.mention))

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        conn = self._get_conn()
        row = conn.execute(
            "SELECT exit_channel_id, exit_message FROM guild_settings WHERE guild_id = ?",
            (member.guild.id,),
        ).fetchone()
        conn.close()

        if row and row[0] and row[1]:
            channel = member.guild.get_channel(row[0])
            if channel:
                await channel.send(row[1].replace("{member}", str(member)))

    # ── Comando principal ─────────────────────────────────────────────────────

    @app_commands.command(name="setup", description="Configura as mensagens de entrada e saída do servidor.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup(self, interaction: discord.Interaction):
        cog = self

        # ── Modais ────────────────────────────────────────────────────────────

        class WelcomeModal(discord.ui.Modal, title="Configurar Boas-Vindas"):
            channel_id_input = discord.ui.TextInput(
                label="ID do Canal",
                placeholder="Cole o ID do canal de boas-vindas",
                required=True,
                max_length=20,
            )
            message_input = discord.ui.TextInput(
                label="Mensagem",
                placeholder="Use {member} para mencionar o novo membro",
                style=discord.TextStyle.paragraph,
                required=True,
                max_length=2000,
            )

            async def on_submit(self, interaction: discord.Interaction):
                try:
                    channel_id = int(self.channel_id_input.value.strip())
                except ValueError:
                    await interaction.response.send_message("ID do canal inválido.", ephemeral=True)
                    return

                channel = interaction.guild.get_channel(channel_id)
                if not channel:
                    await interaction.response.send_message("Canal não encontrado.", ephemeral=True)
                    return

                conn = cog._get_conn()
                conn.execute(
                    """
                    INSERT INTO guild_settings (guild_id, welcome_channel_id, welcome_message)
                    VALUES (?, ?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        welcome_channel_id = excluded.welcome_channel_id,
                        welcome_message    = excluded.welcome_message
                    """,
                    (interaction.guild.id, channel_id, self.message_input.value),
                )
                conn.commit()
                conn.close()
                await interaction.response.send_message(
                    f"Boas-vindas configuradas! Canal: {channel.mention}", ephemeral=True
                )

        class ExitModal(discord.ui.Modal, title="Configurar Saída"):
            channel_id_input = discord.ui.TextInput(
                label="ID do Canal",
                placeholder="Cole o ID do canal de saída",
                required=True,
                max_length=20,
            )
            message_input = discord.ui.TextInput(
                label="Mensagem",
                placeholder="Use {member} para o nome do membro que saiu",
                style=discord.TextStyle.paragraph,
                required=True,
                max_length=2000,
            )

            async def on_submit(self, interaction: discord.Interaction):
                try:
                    channel_id = int(self.channel_id_input.value.strip())
                except ValueError:
                    await interaction.response.send_message("ID do canal inválido.", ephemeral=True)
                    return

                channel = interaction.guild.get_channel(channel_id)
                if not channel:
                    await interaction.response.send_message("Canal não encontrado.", ephemeral=True)
                    return

                conn = cog._get_conn()
                conn.execute(
                    """
                    INSERT INTO guild_settings (guild_id, exit_channel_id, exit_message)
                    VALUES (?, ?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        exit_channel_id = excluded.exit_channel_id,
                        exit_message    = excluded.exit_message
                    """,
                    (interaction.guild.id, channel_id, self.message_input.value),
                )
                conn.commit()
                conn.close()
                await interaction.response.send_message(
                    f"Saída configurada! Canal: {channel.mention}", ephemeral=True
                )

        # ── Select ────────────────────────────────────────────────────────────

        class SetupSelect(discord.ui.Select):
            def __init__(self):
                options = [
                    discord.SelectOption(label="Configurar Boas-Vindas",  description="Define canal e mensagem de entrada.",        value="welcome",        emoji="👋"),
                    discord.SelectOption(label="Configurar Saída",        description="Define canal e mensagem de saída.",          value="exit",           emoji="🚪"),
                    discord.SelectOption(label="Testar Boas-Vindas",      description="Envia mensagem de teste no canal configurado.", value="test_welcome", emoji="🧪"),
                    discord.SelectOption(label="Testar Saída",            description="Envia mensagem de teste no canal configurado.", value="test_exit",    emoji="🧪"),
                    discord.SelectOption(label="Ver Configuração",        description="Mostra as configurações atuais.",            value="view",           emoji="📋"),
                    discord.SelectOption(label="Remover Boas-Vindas",     description="Remove a configuração de entrada.",          value="remove_welcome", emoji="🗑️"),
                    discord.SelectOption(label="Remover Saída",           description="Remove a configuração de saída.",            value="remove_exit",    emoji="🗑️"),
                ]
                super().__init__(placeholder="Escolha uma opção...", options=options)

            async def callback(self, interaction: discord.Interaction):
                choice = self.values[0]
                conn = cog._get_conn()

                if choice == "welcome":
                    conn.close()
                    await interaction.response.send_modal(WelcomeModal())

                elif choice == "exit":
                    conn.close()
                    await interaction.response.send_modal(ExitModal())

                elif choice == "test_welcome":
                    row = conn.execute(
                        "SELECT welcome_channel_id, welcome_message FROM guild_settings WHERE guild_id = ?",
                        (interaction.guild.id,),
                    ).fetchone()
                    conn.close()
                    if not row or not row[0] or not row[1]:
                        await interaction.response.send_message("Boas-vindas não configuradas.", ephemeral=True)
                        return
                    channel = interaction.guild.get_channel(row[0])
                    if not channel:
                        await interaction.response.send_message("Canal configurado não encontrado.", ephemeral=True)
                        return
                    await channel.send(row[1].replace("{member}", interaction.user.mention) + " *(teste)*")
                    await interaction.response.send_message(f"Teste enviado em {channel.mention}!", ephemeral=True)

                elif choice == "test_exit":
                    row = conn.execute(
                        "SELECT exit_channel_id, exit_message FROM guild_settings WHERE guild_id = ?",
                        (interaction.guild.id,),
                    ).fetchone()
                    conn.close()
                    if not row or not row[0] or not row[1]:
                        await interaction.response.send_message("Saída não configurada.", ephemeral=True)
                        return
                    channel = interaction.guild.get_channel(row[0])
                    if not channel:
                        await interaction.response.send_message("Canal configurado não encontrado.", ephemeral=True)
                        return
                    await channel.send(row[1].replace("{member}", str(interaction.user)) + " *(teste)*")
                    await interaction.response.send_message(f"Teste enviado em {channel.mention}!", ephemeral=True)

                elif choice == "view":
                    row = conn.execute(
                        "SELECT welcome_channel_id, welcome_message, exit_channel_id, exit_message FROM guild_settings WHERE guild_id = ?",
                        (interaction.guild.id,),
                    ).fetchone()
                    conn.close()
                    embed = discord.Embed(title="Configuração Atual", color=discord.Color.blurple())
                    if row:
                        w_ch  = f"<#{row[0]}>" if row[0] else "Não configurado"
                        w_msg = row[1]          if row[1] else "Não configurado"
                        e_ch  = f"<#{row[2]}>" if row[2] else "Não configurado"
                        e_msg = row[3]          if row[3] else "Não configurado"
                    else:
                        w_ch = w_msg = e_ch = e_msg = "Não configurado"
                    embed.add_field(name="👋 Canal de Boas-Vindas", value=w_ch,  inline=True)
                    embed.add_field(name="Mensagem",                value=w_msg, inline=False)
                    embed.add_field(name="🚪 Canal de Saída",       value=e_ch,  inline=True)
                    embed.add_field(name="Mensagem",                value=e_msg, inline=False)
                    await interaction.response.send_message(embed=embed, ephemeral=True)

                elif choice == "remove_welcome":
                    conn.execute(
                        "UPDATE guild_settings SET welcome_channel_id = NULL, welcome_message = NULL WHERE guild_id = ?",
                        (interaction.guild.id,),
                    )
                    conn.commit()
                    conn.close()
                    await interaction.response.send_message("Configuração de boas-vindas removida.", ephemeral=True)

                elif choice == "remove_exit":
                    conn.execute(
                        "UPDATE guild_settings SET exit_channel_id = NULL, exit_message = NULL WHERE guild_id = ?",
                        (interaction.guild.id,),
                    )
                    conn.commit()
                    conn.close()
                    await interaction.response.send_message("Configuração de saída removida.", ephemeral=True)

        # ── View + resposta ───────────────────────────────────────────────────

        class SetupView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=120)
                self.add_item(SetupSelect())

        embed = discord.Embed(
            title="⚙️ Configuração de Entrada/Saída",
            description="Selecione uma opção abaixo para gerenciar as mensagens do servidor.",
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, view=SetupView(), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Entry(bot))

