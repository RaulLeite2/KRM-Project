import discord
from discord.ext import commands
from discord import app_commands


class Entry(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── Eventos ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member):
        row = await self.bot.pool.fetchrow(
            "SELECT welcome_channel_id, welcome_message FROM guild_settings WHERE guild_id = $1",
            member.guild.id,
        )
        if row and row["welcome_channel_id"] and row["welcome_message"]:
            channel = member.guild.get_channel(row["welcome_channel_id"])
            if channel:
                await channel.send(row["welcome_message"].replace("{member}", member.mention))

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        row = await self.bot.pool.fetchrow(
            "SELECT exit_channel_id, exit_message FROM guild_settings WHERE guild_id = $1",
            member.guild.id,
        )
        if row and row["exit_channel_id"] and row["exit_message"]:
            channel = member.guild.get_channel(row["exit_channel_id"])
            if channel:
                await channel.send(row["exit_message"].replace("{member}", str(member)))

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

                await cog.bot.pool.execute(
                    """
                    INSERT INTO guild_settings (guild_id, welcome_channel_id, welcome_message)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (guild_id) DO UPDATE SET
                        welcome_channel_id = EXCLUDED.welcome_channel_id,
                        welcome_message    = EXCLUDED.welcome_message
                    """,
                    interaction.guild.id, channel_id, self.message_input.value,
                )
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

                await cog.bot.pool.execute(
                    """
                    INSERT INTO guild_settings (guild_id, exit_channel_id, exit_message)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (guild_id) DO UPDATE SET
                        exit_channel_id = EXCLUDED.exit_channel_id,
                        exit_message    = EXCLUDED.exit_message
                    """,
                    interaction.guild.id, channel_id, self.message_input.value,
                )
                await interaction.response.send_message(
                    f"Saída configurada! Canal: {channel.mention}", ephemeral=True
                )

        # ── Select ────────────────────────────────────────────────────────────

        class SetupSelect(discord.ui.Select):
            def __init__(self):
                options = [
                    discord.SelectOption(label="Configurar Boas-Vindas",  description="Define canal e mensagem de entrada.",          value="welcome",        emoji="👋"),
                    discord.SelectOption(label="Configurar Saída",        description="Define canal e mensagem de saída.",            value="exit",           emoji="🚪"),
                    discord.SelectOption(label="Testar Boas-Vindas",      description="Envia mensagem de teste no canal configurado.", value="test_welcome",  emoji="🧪"),
                    discord.SelectOption(label="Testar Saída",            description="Envia mensagem de teste no canal configurado.", value="test_exit",     emoji="🧪"),
                    discord.SelectOption(label="Ver Configuração",        description="Mostra as configurações atuais.",              value="view",           emoji="📋"),
                    discord.SelectOption(label="Remover Boas-Vindas",     description="Remove a configuração de entrada.",            value="remove_welcome", emoji="🗑️"),
                    discord.SelectOption(label="Remover Saída",           description="Remove a configuração de saída.",              value="remove_exit",    emoji="🗑️"),
                ]
                super().__init__(placeholder="Escolha uma opção...", options=options)

            async def callback(self, interaction: discord.Interaction):
                choice = self.values[0]
                pool = cog.bot.pool

                if choice == "welcome":
                    await interaction.response.send_modal(WelcomeModal())

                elif choice == "exit":
                    await interaction.response.send_modal(ExitModal())

                elif choice == "test_welcome":
                    row = await pool.fetchrow(
                        "SELECT welcome_channel_id, welcome_message FROM guild_settings WHERE guild_id = $1",
                        interaction.guild.id,
                    )
                    if not row or not row["welcome_channel_id"] or not row["welcome_message"]:
                        await interaction.response.send_message("Boas-vindas não configuradas.", ephemeral=True)
                        return
                    channel = interaction.guild.get_channel(row["welcome_channel_id"])
                    if not channel:
                        await interaction.response.send_message("Canal configurado não encontrado.", ephemeral=True)
                        return
                    await channel.send(row["welcome_message"].replace("{member}", interaction.user.mention) + " *(teste)*")
                    await interaction.response.send_message(f"Teste enviado em {channel.mention}!", ephemeral=True)

                elif choice == "test_exit":
                    row = await pool.fetchrow(
                        "SELECT exit_channel_id, exit_message FROM guild_settings WHERE guild_id = $1",
                        interaction.guild.id,
                    )
                    if not row or not row["exit_channel_id"] or not row["exit_message"]:
                        await interaction.response.send_message("Saída não configurada.", ephemeral=True)
                        return
                    channel = interaction.guild.get_channel(row["exit_channel_id"])
                    if not channel:
                        await interaction.response.send_message("Canal configurado não encontrado.", ephemeral=True)
                        return
                    await channel.send(row["exit_message"].replace("{member}", str(interaction.user)) + " *(teste)*")
                    await interaction.response.send_message(f"Teste enviado em {channel.mention}!", ephemeral=True)

                elif choice == "view":
                    row = await pool.fetchrow(
                        "SELECT welcome_channel_id, welcome_message, exit_channel_id, exit_message FROM guild_settings WHERE guild_id = $1",
                        interaction.guild.id,
                    )
                    embed = discord.Embed(title="Configuração Atual", color=discord.Color.blurple())
                    if row:
                        w_ch  = f"<#{row['welcome_channel_id']}>" if row["welcome_channel_id"] else "Não configurado"
                        w_msg = row["welcome_message"]             if row["welcome_message"]    else "Não configurado"
                        e_ch  = f"<#{row['exit_channel_id']}>"      if row["exit_channel_id"]    else "Não configurado"
                        e_msg = row["exit_message"]                if row["exit_message"]       else "Não configurado"
                    else:
                        w_ch = w_msg = e_ch = e_msg = "Não configurado"
                    embed.add_field(name="👋 Canal de Boas-Vindas", value=w_ch,  inline=True)
                    embed.add_field(name="Mensagem",                value=w_msg, inline=False)
                    embed.add_field(name="🚪 Canal de Saída",       value=e_ch,  inline=True)
                    embed.add_field(name="Mensagem",                value=e_msg, inline=False)
                    await interaction.response.send_message(embed=embed, ephemeral=True)

                elif choice == "remove_welcome":
                    await pool.execute(
                        "UPDATE guild_settings SET welcome_channel_id = NULL, welcome_message = NULL WHERE guild_id = $1",
                        interaction.guild.id,
                    )
                    await interaction.response.send_message("Configuração de boas-vindas removida.", ephemeral=True)

                elif choice == "remove_exit":
                    await pool.execute(
                        "UPDATE guild_settings SET exit_channel_id = NULL, exit_message = NULL WHERE guild_id = $1",
                        interaction.guild.id,
                    )
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

