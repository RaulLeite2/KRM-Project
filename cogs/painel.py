from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

from .aniversary import BirthdayEmbedBuilder, BirthdayRepository, BirthdayView, parse_hex_color
from .entry import (
    ExitModal,
    WelcomeEmbedExtrasModal,
    WelcomeEmbedFieldAddModal,
    WelcomeEmbedFieldEditModal,
    WelcomeEmbedFieldMoveModal,
    WelcomeEmbedFieldRemoveModal,
    WelcomeEmbedImportJsonModal,
    WelcomeEmbedModal,
    WelcomeModal,
    apply_step_footer,
    build_welcome_embed_from_payload,
    check_manage_or_admin,
    clear_welcome_embed_draft,
    ensure_welcome_embed_draft,
    get_previous_welcome_embed_state,
    get_welcome_embed_draft,
    list_embed_fields_text,
    render_template_text,
    save_welcome_embed_payload,
    set_welcome_embed_draft,
    validate_welcome_embed_payload,
)


class PanelBaseView(discord.ui.View):
    def __init__(self, cog: "Painel", owner_id: int, timeout: float = 600):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            "Esse painel pertence a quem executou o comando.",
            ephemeral=True,
        )
        return False


class MainPanelSelect(discord.ui.Select):
    def __init__(self, cog: "Painel", owner_id: int):
        self.cog = cog
        self.owner_id = owner_id
        options = [
            discord.SelectOption(label="Entrada", value="entry", description="Configurar entrada e saida", emoji="📥"),
            discord.SelectOption(label="Aniversario", value="birthday", description="Configurar painel e canal", emoji="🎂"),
            discord.SelectOption(label="Invasao", value="invasion", description="Configurar canais da invasao", emoji="⚔️"),
        ]
        super().__init__(placeholder="Escolha uma area para configurar", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        if selected == "entry":
            await interaction.response.edit_message(
                embed=self.cog._entry_embed(),
                view=EntryMainView(self.cog, self.owner_id),
            )
            return
        if selected == "birthday":
            await interaction.response.edit_message(
                embed=self.cog._birthday_embed(),
                view=BirthdayPanelView(self.cog, self.owner_id),
            )
            return
        await interaction.response.edit_message(
            embed=self.cog._invasion_embed(),
            view=InvasionPanelView(self.cog, self.owner_id),
        )


class MainPanelView(PanelBaseView):
    def __init__(self, cog: "Painel", owner_id: int, timeout: float = 600):
        super().__init__(cog, owner_id, timeout=timeout)
        self.add_item(MainPanelSelect(cog, owner_id))


class EntryMainSelect(discord.ui.Select):
    def __init__(self, cog: "Painel", owner_id: int):
        self.cog = cog
        self.owner_id = owner_id
        options = [
            discord.SelectOption(label="Boas-vindas texto", value="welcome_text", description="Editar mensagem de boas-vindas"),
            discord.SelectOption(label="Boas-vindas embed", value="welcome_embed", description="Editar embed de boas-vindas"),
            discord.SelectOption(label="Extras do embed", value="embed_extras", description="Autor, thumbnail e imagem"),
            discord.SelectOption(label="Fields do embed", value="fields", description="Adicionar, mover e remover fields"),
            discord.SelectOption(label="Importar JSON", value="import_json", description="Importar configuracao de embed"),
            discord.SelectOption(label="Configurar saida", value="exit_config", description="Definir mensagem de saida"),
            discord.SelectOption(label="Simular embed", value="simulate_embed", description="Enviar simulacao no canal configurado"),
            discord.SelectOption(label="Testar entrada", value="test_welcome", description="Enviar teste de boas-vindas"),
            discord.SelectOption(label="Testar saida", value="test_exit", description="Enviar teste de saida"),
            discord.SelectOption(label="Ver configuracao", value="view_config", description="Mostrar resumo da configuracao"),
        ]
        super().__init__(placeholder="Escolha uma acao da entrada/saida", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        if selected == "welcome_text":
            await self.cog._open_welcome_text_modal(interaction)
            return
        if selected == "welcome_embed":
            await interaction.response.send_modal(WelcomeEmbedModal(self.cog.bot))
            return
        if selected == "embed_extras":
            await interaction.response.send_modal(WelcomeEmbedExtrasModal(self.cog.bot))
            return
        if selected == "fields":
            await interaction.response.edit_message(
                embed=self.cog._entry_fields_embed(),
                view=EntryFieldsView(self.cog, self.owner_id),
            )
            return
        if selected == "import_json":
            await interaction.response.send_modal(WelcomeEmbedImportJsonModal(self.cog.bot))
            return
        if selected == "exit_config":
            await self.cog._open_exit_config_modal(interaction)
            return
        if selected == "simulate_embed":
            await self.cog._entry_simulate(interaction)
            return
        if selected == "test_welcome":
            await self.cog._entry_test_welcome(interaction)
            return
        if selected == "test_exit":
            await self.cog._entry_test_exit(interaction)
            return
        await self.cog._entry_view_config(interaction)


class EntryMainView(PanelBaseView):
    def __init__(self, cog: "Painel", owner_id: int, timeout: float = 600):
        super().__init__(cog, owner_id, timeout=timeout)
        self.add_item(EntryMainSelect(cog, owner_id))

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.danger, row=2)
    async def back(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=self.cog._main_embed(),
            view=MainPanelView(self.cog, self.owner_id),
        )


class EntryFieldsSelect(discord.ui.Select):
    def __init__(self, cog: "Painel"):
        self.cog = cog
        options = [
            discord.SelectOption(label="Adicionar field", value="add", description="Adicionar novo field no rascunho"),
            discord.SelectOption(label="Editar field", value="edit", description="Editar field existente"),
            discord.SelectOption(label="Mover field", value="move", description="Mudar ordem dos fields"),
            discord.SelectOption(label="Remover field", value="remove", description="Excluir field do rascunho"),
            discord.SelectOption(label="Listar fields", value="list", description="Mostrar fields atuais"),
            discord.SelectOption(label="Restaurar anterior", value="restore", description="Carregar versao anterior salva"),
            discord.SelectOption(label="Confirmar embed", value="confirm", description="Salvar rascunho no banco"),
            discord.SelectOption(label="Cancelar rascunho", value="cancel", description="Descartar rascunho atual"),
            discord.SelectOption(label="Resetar embed", value="reset", description="Remover embed salvo"),
            discord.SelectOption(label="Simular embed", value="simulate", description="Enviar simulacao no canal"),
        ]
        super().__init__(placeholder="Escolha uma acao dos fields", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        if selected == "add":
            await interaction.response.send_modal(WelcomeEmbedFieldAddModal(self.cog.bot))
            return
        if selected == "edit":
            await interaction.response.send_modal(WelcomeEmbedFieldEditModal(self.cog.bot))
            return
        if selected == "move":
            await interaction.response.send_modal(WelcomeEmbedFieldMoveModal(self.cog.bot))
            return
        if selected == "remove":
            await interaction.response.send_modal(WelcomeEmbedFieldRemoveModal(self.cog.bot))
            return
        if selected == "list":
            await self.cog._entry_list_fields(interaction)
            return
        if selected == "restore":
            await self.cog._entry_restore_previous(interaction)
            return
        if selected == "confirm":
            await self.cog._entry_confirm_embed(interaction)
            return
        if selected == "cancel":
            await self.cog._entry_cancel_draft(interaction)
            return
        if selected == "reset":
            await self.cog._entry_reset_embed(interaction)
            return
        await self.cog._entry_simulate(interaction)


class EntryFieldsView(PanelBaseView):
    def __init__(self, cog: "Painel", owner_id: int, timeout: float = 600):
        super().__init__(cog, owner_id, timeout=timeout)
        self.add_item(EntryFieldsSelect(cog))

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.danger, row=2)
    async def back(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=self.cog._entry_embed(),
            view=EntryMainView(self.cog, self.owner_id),
        )


class BirthdayChannelModal(discord.ui.Modal, title="Canal de aniversario"):
    channel_id_input = discord.ui.TextInput(
        label="ID do canal",
        placeholder="Cole o ID do canal de aniversario",
        required=True,
        max_length=20,
    )

    def __init__(self, cog: "Painel"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Este comando so funciona em servidor.", ephemeral=True)
            return

        try:
            channel_id = int(str(self.channel_id_input.value).strip())
        except ValueError:
            await interaction.response.send_message("ID do canal invalido.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Canal de texto nao encontrado.", ephemeral=True)
            return

        repo = BirthdayRepository(self.cog.bot.pool)
        await repo.set_birthday_channel(interaction.guild.id, channel.id)

        embed = self.cog._panel_embed(
            "Canal de aniversario salvo",
            f"O canal de aniversario agora e {channel.mention}.",
            4,
            4,
            "Configuracao concluida.",
            discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class BirthdayPanelModal(discord.ui.Modal, title="Criar painel de aniversario"):
    title_input = discord.ui.TextInput(
        label="Titulo do embed",
        placeholder="Ex: Painel de aniversario",
        required=True,
        max_length=256,
    )
    description_input = discord.ui.TextInput(
        label="Descricao",
        placeholder="Explique como usar o painel",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=2000,
    )
    color_input = discord.ui.TextInput(
        label="Cor HEX",
        placeholder="#FFAA00",
        required=False,
        max_length=7,
    )
    footer_input = discord.ui.TextInput(
        label="Footer",
        placeholder="Opcional",
        required=False,
        max_length=2048,
    )
    image_url_input = discord.ui.TextInput(
        label="Imagem URL",
        placeholder="https://...",
        required=False,
        max_length=300,
    )

    def __init__(self, cog: "Painel"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild or not interaction.channel:
            await interaction.response.send_message("Este comando so funciona em canal de servidor.", ephemeral=True)
            return

        color = parse_hex_color(str(self.color_input.value).strip())
        if self.color_input.value and color is None:
            await interaction.response.send_message(
                "Cor invalida. Use hexadecimal de 6 digitos, por exemplo #FFAA00.",
                ephemeral=True,
            )
            return

        embed = BirthdayEmbedBuilder(
            title=str(self.title_input.value),
            description=str(self.description_input.value),
            color=color,
            footer=str(self.footer_input.value).strip() or None,
            image_url=str(self.image_url_input.value).strip() or None,
        ).build()

        repo = BirthdayRepository(self.cog.bot.pool)
        view = BirthdayView(repo)
        message = await interaction.channel.send(embed=embed, view=view)
        await repo.save_panel(interaction.guild.id, interaction.channel.id, message.id)

        result_embed = self.cog._panel_embed(
            "Painel de aniversario criado",
            f"O painel foi enviado em {interaction.channel.mention}.",
            4,
            4,
            "Criacao concluida.",
            discord.Color.green(),
        )
        await interaction.response.send_message(embed=result_embed, ephemeral=True)


class BirthdayPanelView(PanelBaseView):
    def __init__(self, cog: "Painel", owner_id: int, timeout: float = 600):
        super().__init__(cog, owner_id, timeout=timeout)
        options = [
            discord.SelectOption(label="Criar painel", value="create", description="Criar mensagem interativa de aniversario"),
            discord.SelectOption(label="Definir canal", value="channel", description="Salvar canal de aniversario"),
        ]
        self.add_item(BirthdayActionSelect(cog, options))

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.danger, row=1)
    async def back(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=self.cog._main_embed(),
            view=MainPanelView(self.cog, self.owner_id),
        )


class BirthdayActionSelect(discord.ui.Select):
    def __init__(self, cog: "Painel", options: list[discord.SelectOption]):
        self.cog = cog
        super().__init__(placeholder="Escolha uma acao de aniversario", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        if selected == "create":
            await interaction.response.send_modal(BirthdayPanelModal(self.cog))
            return
        await interaction.response.send_modal(BirthdayChannelModal(self.cog))


class InvasionSetupModal(discord.ui.Modal, title="Configurar invasao"):
    channel_id_input = discord.ui.TextInput(
        label="ID do canal da invasao",
        placeholder="Canal onde o aviso sera enviado",
        required=True,
        max_length=20,
    )
    absence_channel_id_input = discord.ui.TextInput(
        label="ID do canal de ausencia",
        placeholder="Canal das justificativas",
        required=True,
        max_length=20,
    )
    notify_role_id_input = discord.ui.TextInput(
        label="ID do cargo (opcional)",
        placeholder="Cargo que sera marcado",
        required=False,
        max_length=20,
    )

    def __init__(self, cog: "Painel"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Esse comando so pode ser usado em servidor.", ephemeral=True)
            return

        try:
            channel_id = int(str(self.channel_id_input.value).strip())
            absence_channel_id = int(str(self.absence_channel_id_input.value).strip())
        except ValueError:
            await interaction.response.send_message("Os IDs dos canais precisam ser numericos.", ephemeral=True)
            return

        notify_role_id_raw = str(self.notify_role_id_input.value).strip() if self.notify_role_id_input.value else ""
        notify_role_id = None
        if notify_role_id_raw:
            try:
                notify_role_id = int(notify_role_id_raw)
            except ValueError:
                await interaction.response.send_message("O ID do cargo precisa ser numerico.", ephemeral=True)
                return

        channel = interaction.guild.get_channel(channel_id)
        absence_channel = interaction.guild.get_channel(absence_channel_id)
        notify_role = interaction.guild.get_role(notify_role_id) if notify_role_id else None

        if not isinstance(channel, discord.TextChannel) or not isinstance(absence_channel, discord.TextChannel):
            await interaction.response.send_message("Um dos canais informados nao foi encontrado.", ephemeral=True)
            return

        pool = self.cog._get_pool()
        if pool is None:
            await interaction.response.send_message("Banco de dados indisponivel no momento.", ephemeral=True)
            return

        async with pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO invasions (guild_id, invasion_channel_id, absence_channel_id, notify_role_id)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (guild_id) DO UPDATE
                SET invasion_channel_id = EXCLUDED.invasion_channel_id,
                    absence_channel_id = EXCLUDED.absence_channel_id,
                    notify_role_id = EXCLUDED.notify_role_id
                """,
                interaction.guild.id,
                channel.id,
                absence_channel.id,
                notify_role.id if notify_role else None,
            )

        role_text = notify_role.mention if notify_role else "nenhum cargo"
        embed = self.cog._panel_embed(
            "Invasao configurada",
            f"Canal: {channel.mention}\nAusencias: {absence_channel.mention}\nCargo: {role_text}",
            4,
            4,
            "Configuracao concluida.",
            discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class InvasionPanelView(PanelBaseView):
    @discord.ui.button(label="Configurar invasao", style=discord.ButtonStyle.primary, row=0)
    async def setup_invasion(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(InvasionSetupModal(self.cog))

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.danger, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=self.cog._main_embed(),
            view=MainPanelView(self.cog, self.owner_id),
        )


class Painel(commands.Cog):
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
        await pool.execute("ALTER TABLE invasions ADD COLUMN IF NOT EXISTS notify_role_id BIGINT")

    def _get_pool(self):
        return getattr(self.bot, "pool", None) or getattr(self.bot, "db", None)

    def _panel_embed(
        self,
        title: str,
        description: str,
        step: int,
        total_steps: int,
        prompt: str,
        color: discord.Color | None = None,
    ) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            description=description,
            color=color or discord.Color.blurple(),
        )
        apply_step_footer(embed, step, total_steps, prompt)
        return embed

    def _main_embed(self) -> discord.Embed:
        return self._panel_embed(
            "Painel de configuracao",
            "Escolha qual area voce quer configurar. Os botoes abaixo mudam o painel sem criar outro comando.",
            1,
            4,
            "Clique em Entrada, Aniversario ou Invasao.",
        )

    def _entry_embed(self) -> discord.Embed:
        return self._panel_embed(
            "Painel de Entrada e Saida",
            "Use os botoes para abrir o que deseja editar: texto, embed, saida, testes ou importacao.",
            2,
            4,
            "Escolha a parte da entrada/saida que voce quer configurar agora.",
        )

    def _entry_fields_embed(self) -> discord.Embed:
        return self._panel_embed(
            "Painel de Fields do Embed",
            "Aqui voce ajusta os fields do embed de boas-vindas e tambem controla o rascunho atual.",
            3,
            4,
            "Adicione, edite, mova ou confirme os fields do embed.",
        )

    def _birthday_embed(self) -> discord.Embed:
        return self._panel_embed(
            "Painel de Aniversario",
            "Use os botoes para criar o painel interativo de aniversario ou definir o canal das mensagens.",
            2,
            4,
            "Escolha se voce quer criar o painel ou definir o canal de aniversario.",
        )

    def _invasion_embed(self) -> discord.Embed:
        return self._panel_embed(
            "Painel de Invasao",
            "Use os botoes para configurar os canais e o cargo da invasao. O envio do aviso fica no comando /invasion notify.",
            2,
            4,
            "Configure os canais da invasao aqui e use /invasion notify para disparar o aviso.",
        )

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
            updated_embed.add_field(name=self.PARTICIPANTS_FIELD_NAME, value=participants_value, inline=False)
            return updated_embed, True

        updated_embed.set_field_at(
            participants_index,
            name=self.PARTICIPANTS_FIELD_NAME,
            value=participants_value,
            inline=False,
        )
        return updated_embed, True

    async def _entry_list_fields(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Este painel so funciona em servidor.", ephemeral=True)
            return

        draft = await ensure_welcome_embed_draft(self.bot.pool, interaction.guild.id, interaction.user.id)
        if not draft:
            await interaction.response.send_message(
                "Nao existe rascunho ativo. Crie ou importe um embed antes de listar os fields.",
                ephemeral=True,
            )
            return

        fields_text = list_embed_fields_text(draft["payload"].get("fields", []))
        embed = self._panel_embed(
            "Fields atuais do rascunho",
            fields_text,
            3,
            4,
            "Revise os fields e escolha a proxima acao no painel.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _open_welcome_text_modal(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Este painel so funciona em servidor.", ephemeral=True)
            return

        pool = self._get_pool()
        if pool is None:
            await interaction.response.send_message("Banco de dados indisponivel no momento.", ephemeral=True)
            return

        row = await pool.fetchrow(
            "SELECT welcome_channel_id, welcome_message FROM guild_settings WHERE guild_id = $1",
            interaction.guild.id,
        )
        channel_id = row["welcome_channel_id"] if row else None
        message = row["welcome_message"] if row else None
        await interaction.response.send_modal(
            WelcomeModal(self.bot, default_channel_id=channel_id, default_message=message)
        )

    async def _open_exit_config_modal(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Este painel so funciona em servidor.", ephemeral=True)
            return

        pool = self._get_pool()
        if pool is None:
            await interaction.response.send_message("Banco de dados indisponivel no momento.", ephemeral=True)
            return

        row = await pool.fetchrow(
            "SELECT exit_channel_id, exit_message FROM guild_settings WHERE guild_id = $1",
            interaction.guild.id,
        )
        channel_id = row["exit_channel_id"] if row else None
        message = row["exit_message"] if row else None
        await interaction.response.send_modal(
            ExitModal(self.bot, default_channel_id=channel_id, default_message=message)
        )

    async def _entry_restore_previous(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Este painel so funciona em servidor.", ephemeral=True)
            return

        prev_channel_id, prev_payload = await get_previous_welcome_embed_state(self.bot.pool, interaction.guild.id)
        if not prev_payload or not prev_channel_id:
            await interaction.response.send_message("Nao existe versao anterior registrada ainda.", ephemeral=True)
            return

        validation_error = validate_welcome_embed_payload(prev_payload)
        if validation_error:
            await interaction.response.send_message(
                "A versao anterior esta invalida: " + validation_error,
                ephemeral=True,
            )
            return

        set_welcome_embed_draft(interaction.guild.id, interaction.user.id, prev_channel_id, prev_payload)
        preview_embed = build_welcome_embed_from_payload(prev_payload, interaction.user)
        if not preview_embed:
            await interaction.response.send_message("Falha ao carregar a versao anterior.", ephemeral=True)
            return

        apply_step_footer(preview_embed, 3, 4, "Versao anterior carregada. Revise e confirme.")
        await interaction.response.send_message(embed=preview_embed, ephemeral=True)

    async def _entry_confirm_embed(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Este painel so funciona em servidor.", ephemeral=True)
            return

        draft = get_welcome_embed_draft(interaction.guild.id, interaction.user.id)
        if not draft:
            await interaction.response.send_message("Nenhum rascunho encontrado para confirmar.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(draft["channel_id"])
        if not channel:
            await interaction.response.send_message("Canal do rascunho nao encontrado.", ephemeral=True)
            return

        payload = draft["payload"]
        validation_error = validate_welcome_embed_payload(payload)
        if validation_error:
            await interaction.response.send_message(validation_error, ephemeral=True)
            return

        preview_embed = build_welcome_embed_from_payload(payload, interaction.user)
        if not preview_embed:
            await interaction.response.send_message("Falha ao montar o embed para confirmacao.", ephemeral=True)
            return

        await save_welcome_embed_payload(self.bot.pool, interaction.guild.id, draft["channel_id"], payload)
        clear_welcome_embed_draft(interaction.guild.id, interaction.user.id)
        apply_step_footer(preview_embed, 4, 4, "Embed salvo com sucesso.")
        await interaction.response.send_message(
            f"Embed de boas-vindas salvo com sucesso em {channel.mention}.",
            embed=preview_embed,
            ephemeral=True,
        )

    async def _entry_cancel_draft(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Este painel so funciona em servidor.", ephemeral=True)
            return

        clear_welcome_embed_draft(interaction.guild.id, interaction.user.id)
        embed = self._panel_embed(
            "Rascunho descartado",
            "O rascunho atual do embed de boas-vindas foi removido.",
            4,
            4,
            "Se quiser continuar, crie um novo rascunho no painel.",
            discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _entry_reset_embed(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Este painel so funciona em servidor.", ephemeral=True)
            return

        clear_welcome_embed_draft(interaction.guild.id, interaction.user.id)
        await self.bot.pool.execute(
            "UPDATE guild_settings SET welcome_embed = NULL WHERE guild_id = $1",
            interaction.guild.id,
        )
        embed = self._panel_embed(
            "Embed resetado",
            "O embed de boas-vindas salvo foi removido do banco.",
            4,
            4,
            "Se quiser usar novamente, recrie o embed no painel.",
            discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _entry_simulate(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Este painel so funciona em servidor.", ephemeral=True)
            return

        draft = get_welcome_embed_draft(interaction.guild.id, interaction.user.id)
        if draft:
            channel = interaction.guild.get_channel(draft["channel_id"])
            payload = draft["payload"]
        else:
            row = await self.bot.pool.fetchrow(
                "SELECT welcome_channel_id, welcome_embed FROM guild_settings WHERE guild_id = $1",
                interaction.guild.id,
            )
            if not row:
                await interaction.response.send_message("Nenhuma configuracao de embed encontrada.", ephemeral=True)
                return
            channel = interaction.guild.get_channel(row["welcome_channel_id"])
            payload = row["welcome_embed"]

        if not channel:
            await interaction.response.send_message("Canal de boas-vindas nao encontrado.", ephemeral=True)
            return

        simulated_embed = build_welcome_embed_from_payload(payload, interaction.user)
        if not simulated_embed:
            await interaction.response.send_message("Nao foi possivel simular o embed atual.", ephemeral=True)
            return

        await channel.send(embed=simulated_embed)
        embed = self._panel_embed(
            "Simulacao enviada",
            f"A simulacao do embed foi enviada em {channel.mention}.",
            4,
            4,
            "Revise no canal se o resultado ficou como esperado.",
            discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _entry_test_welcome(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Este painel so funciona em servidor.", ephemeral=True)
            return

        draft = get_welcome_embed_draft(interaction.guild.id, interaction.user.id)
        row = None
        if draft:
            channel = interaction.guild.get_channel(draft["channel_id"])
            welcome_payload = draft["payload"]
            welcome_message = None
        else:
            row = await self.bot.pool.fetchrow(
                "SELECT welcome_channel_id, welcome_message, welcome_embed FROM guild_settings WHERE guild_id = $1",
                interaction.guild.id,
            )
            if not row or not row["welcome_channel_id"]:
                await interaction.response.send_message("Boas-vindas nao configuradas.", ephemeral=True)
                return
            channel = interaction.guild.get_channel(row["welcome_channel_id"])
            welcome_payload = row["welcome_embed"]
            welcome_message = row["welcome_message"]

        if not channel:
            await interaction.response.send_message("Canal configurado nao encontrado.", ephemeral=True)
            return

        welcome_embed = build_welcome_embed_from_payload(welcome_payload, interaction.user)
        if welcome_embed:
            await channel.send(content="*(teste de embed de boas-vindas)*", embed=welcome_embed)
        elif welcome_message:
            text = render_template_text(welcome_message, interaction.user)
            await channel.send((text or "") + " *(teste)*")
        else:
            await interaction.response.send_message("Boas-vindas nao configuradas.", ephemeral=True)
            return

        embed = self._panel_embed(
            "Teste de entrada enviado",
            f"O teste foi enviado em {channel.mention}.",
            4,
            4,
            "Confira a mensagem no canal configurado.",
            discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _entry_test_exit(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Este painel so funciona em servidor.", ephemeral=True)
            return

        row = await self.bot.pool.fetchrow(
            "SELECT exit_channel_id, exit_message FROM guild_settings WHERE guild_id = $1",
            interaction.guild.id,
        )
        if not row or not row["exit_channel_id"] or not row["exit_message"]:
            await interaction.response.send_message("Saida nao configurada.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(row["exit_channel_id"])
        if not channel:
            await interaction.response.send_message("Canal configurado nao encontrado.", ephemeral=True)
            return

        await channel.send(row["exit_message"].replace("{member}", str(interaction.user)) + " *(teste)*")
        embed = self._panel_embed(
            "Teste de saida enviado",
            f"O teste foi enviado em {channel.mention}.",
            4,
            4,
            "Confira a mensagem no canal configurado.",
            discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _entry_view_config(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Este painel so funciona em servidor.", ephemeral=True)
            return

        draft = get_welcome_embed_draft(interaction.guild.id, interaction.user.id)
        row = await self.bot.pool.fetchrow(
            "SELECT welcome_channel_id, welcome_message, welcome_embed, exit_channel_id, exit_message FROM guild_settings WHERE guild_id = $1",
            interaction.guild.id,
        )

        embed = self._panel_embed(
            "Configuracao atual",
            "Resumo das configuracoes de entrada e saida do servidor.",
            3,
            4,
            "Revise as informacoes antes de editar ou testar novamente.",
        )

        if row:
            welcome_channel = f"<#{row['welcome_channel_id']}>" if row["welcome_channel_id"] else "Nao configurado"
            welcome_message = row["welcome_message"] if row["welcome_message"] else "Nao configurado"
            welcome_embed = "Configurado" if row["welcome_embed"] else "Nao configurado"
            welcome_embed_fields = len(row["welcome_embed"].get("fields", [])) if row["welcome_embed"] else 0
            exit_channel = f"<#{row['exit_channel_id']}>" if row["exit_channel_id"] else "Nao configurado"
            exit_message = row["exit_message"] if row["exit_message"] else "Nao configurado"
        else:
            welcome_channel = "Nao configurado"
            welcome_message = "Nao configurado"
            welcome_embed = "Nao configurado"
            welcome_embed_fields = 0
            exit_channel = "Nao configurado"
            exit_message = "Nao configurado"

        draft_status = "Sim" if draft else "Nao"
        draft_channel = f"<#{draft['channel_id']}>" if draft and draft.get("channel_id") else "-"
        draft_fields = draft["payload"].get("fields", []) if draft else (row["welcome_embed"].get("fields", []) if row and row["welcome_embed"] else [])

        embed.add_field(name="Canal de boas-vindas", value=welcome_channel, inline=True)
        embed.add_field(name="Boas-vindas em texto", value=welcome_message[:1024], inline=False)
        embed.add_field(name="Embed de boas-vindas", value=welcome_embed, inline=True)
        embed.add_field(name="Fields do embed", value=str(welcome_embed_fields), inline=True)
        embed.add_field(name="Rascunho em edicao", value=draft_status, inline=True)
        embed.add_field(name="Canal do rascunho", value=draft_channel, inline=True)
        embed.add_field(name="Lista de fields", value=list_embed_fields_text(draft_fields)[:1024], inline=False)
        embed.add_field(name="Canal de saida", value=exit_channel, inline=True)
        embed.add_field(name="Mensagem de saida", value=exit_message[:1024], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="painel", description="Abre o painel unico de configuracao do servidor.")
    @app_commands.check(check_manage_or_admin)
    async def painel(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=self._main_embed(),
            view=MainPanelView(self, interaction.user.id),
            ephemeral=True,
        )

    @painel.error
    async def painel_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            if interaction.response.is_done():
                await interaction.followup.send(
                    "Voce precisa de permissao para gerenciar o servidor antes de abrir este painel.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "Voce precisa de permissao para gerenciar o servidor antes de abrir este painel.",
                    ephemeral=True,
                )


async def setup(bot):
    await bot.add_cog(Painel(bot))
