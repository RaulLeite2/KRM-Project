from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

from .aniversary import BirthdayEmbedBuilder, BirthdayRepository, BirthdayView, parse_hex_color
from .entry import (
    ExitModal,
    SetupView,
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


class MainPanelView(PanelBaseView):
    @discord.ui.button(label="Entrada", style=discord.ButtonStyle.primary, row=0)
    async def entrada(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=self.cog._entry_embed(),
            view=EntryMainView(self.cog, self.owner_id),
        )

    @discord.ui.button(label="Aniversario", style=discord.ButtonStyle.success, row=0)
    async def aniversario(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=self.cog._birthday_embed(),
            view=BirthdayPanelView(self.cog, self.owner_id),
        )

    @discord.ui.button(label="Invasao", style=discord.ButtonStyle.danger, row=0)
    async def invasao(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=self.cog._invasion_embed(),
            view=InvasionPanelView(self.cog, self.owner_id),
        )


class EntryMainView(PanelBaseView):
    @discord.ui.button(label="Boas-vindas texto", style=discord.ButtonStyle.primary, row=0)
    async def welcome_text(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WelcomeModal(self.cog.bot))

    @discord.ui.button(label="Boas-vindas embed", style=discord.ButtonStyle.primary, row=0)
    async def welcome_embed(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WelcomeEmbedModal(self.cog.bot))

    @discord.ui.button(label="Extras do embed", style=discord.ButtonStyle.secondary, row=0)
    async def embed_extras(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WelcomeEmbedExtrasModal(self.cog.bot))

    @discord.ui.button(label="Fields do embed", style=discord.ButtonStyle.secondary, row=0)
    async def fields_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=self.cog._entry_fields_embed(),
            view=EntryFieldsView(self.cog, self.owner_id),
        )

    @discord.ui.button(label="Importar JSON", style=discord.ButtonStyle.secondary, row=0)
    async def import_json(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WelcomeEmbedImportJsonModal(self.cog.bot))

    @discord.ui.button(label="Configurar saida", style=discord.ButtonStyle.primary, row=1)
    async def exit_config(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ExitModal(self.cog.bot))

    @discord.ui.button(label="Simular embed", style=discord.ButtonStyle.secondary, row=1)
    async def simulate_embed(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._entry_simulate(interaction)

    @discord.ui.button(label="Testar entrada", style=discord.ButtonStyle.secondary, row=1)
    async def test_welcome(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._entry_test_welcome(interaction)

    @discord.ui.button(label="Testar saida", style=discord.ButtonStyle.secondary, row=1)
    async def test_exit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._entry_test_exit(interaction)

    @discord.ui.button(label="Ver configuracao", style=discord.ButtonStyle.secondary, row=1)
    async def view_config(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._entry_view_config(interaction)

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.danger, row=2)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=self.cog._main_embed(),
            view=MainPanelView(self.cog, self.owner_id),
        )


class EntryFieldsView(PanelBaseView):
    @discord.ui.button(label="Adicionar field", style=discord.ButtonStyle.primary, row=0)
    async def add_field(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WelcomeEmbedFieldAddModal(self.cog.bot))

    @discord.ui.button(label="Editar field", style=discord.ButtonStyle.primary, row=0)
    async def edit_field(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WelcomeEmbedFieldEditModal(self.cog.bot))

    @discord.ui.button(label="Mover field", style=discord.ButtonStyle.primary, row=0)
    async def move_field(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WelcomeEmbedFieldMoveModal(self.cog.bot))

    @discord.ui.button(label="Remover field", style=discord.ButtonStyle.primary, row=0)
    async def remove_field(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WelcomeEmbedFieldRemoveModal(self.cog.bot))

    @discord.ui.button(label="Listar fields", style=discord.ButtonStyle.secondary, row=0)
    async def list_fields(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._entry_list_fields(interaction)

    @discord.ui.button(label="Restaurar anterior", style=discord.ButtonStyle.secondary, row=1)
    async def restore_previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._entry_restore_previous(interaction)

    @discord.ui.button(label="Confirmar embed", style=discord.ButtonStyle.success, row=1)
    async def confirm_embed(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._entry_confirm_embed(interaction)

    @discord.ui.button(label="Cancelar rascunho", style=discord.ButtonStyle.secondary, row=1)
    async def cancel_draft(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._entry_cancel_draft(interaction)

    @discord.ui.button(label="Resetar embed", style=discord.ButtonStyle.danger, row=1)
    async def reset_embed(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._entry_reset_embed(interaction)

    @discord.ui.button(label="Simular embed", style=discord.ButtonStyle.secondary, row=1)
    async def simulate_embed(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._entry_simulate(interaction)

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.danger, row=2)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
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
    @discord.ui.button(label="Criar painel", style=discord.ButtonStyle.success, row=0)
    async def create_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BirthdayPanelModal(self.cog))

    @discord.ui.button(label="Definir canal", style=discord.ButtonStyle.primary, row=0)
    async def set_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BirthdayChannelModal(self.cog))

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.danger, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=self.cog._main_embed(),
            view=MainPanelView(self.cog, self.owner_id),
        )


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


class InvasionNotifyModal(discord.ui.Modal, title="Notificar invasao"):
    title_input = discord.ui.TextInput(
        label="Titulo da invasao",
        placeholder="Ex: Ataque ao servidor X",
        required=True,
        max_length=256,
    )
    time_input = discord.ui.TextInput(
        label="Hora (HH:MM)",
        placeholder="21:30",
        required=True,
        max_length=5,
    )
    color_input = discord.ui.TextInput(
        label="Cor HEX",
        placeholder="#FF0000",
        required=True,
        max_length=7,
    )
    description_input = discord.ui.TextInput(
        label="Descricao",
        placeholder="Detalhes da invasao",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000,
    )

    def __init__(self, cog: "Painel"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog._send_invasion_notification(
            interaction,
            str(self.title_input.value),
            str(self.time_input.value),
            str(self.color_input.value),
            str(self.description_input.value).strip() or None,
        )


class InvasionPanelView(PanelBaseView):
    @discord.ui.button(label="Configurar invasao", style=discord.ButtonStyle.primary, row=0)
    async def setup_invasion(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(InvasionSetupModal(self.cog))

    @discord.ui.button(label="Enviar notificacao", style=discord.ButtonStyle.success, row=0)
    async def notify_invasion(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(InvasionNotifyModal(self.cog))

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
            "Use os botoes para configurar os canais/cargo da invasao ou para enviar uma nova notificacao.",
            2,
            4,
            "Escolha se voce vai configurar a invasao ou enviar a notificacao.",
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
                "Invasao ainda nao configurada. Volte ao painel e configure a invasao primeiro.",
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
        apply_step_footer(embed, 4, 4, "Aguardando respostas dos membros nos botoes abaixo.")
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
                apply_step_footer(justification_embed, 4, 4, "Justificativa registrada no canal de ausencia.")

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

        result_embed = self._panel_embed(
            "Notificacao enviada",
            f"A notificacao de invasao foi enviada em {invasion_channel.mention}.",
            4,
            4,
            "Agora acompanhe as respostas dos membros na mensagem enviada.",
            discord.Color.green(),
        )
        await interaction.response.send_message(embed=result_embed, ephemeral=True)

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
