from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from .entry import apply_step_footer, check_manage_or_admin


def _short_text(text: str | None, fallback: str = "Nao configurado") -> str:
    if not text:
        return fallback
    return text if len(text) <= 1024 else text[:1021] + "..."


def _sanitize_channel_name(name: str) -> str:
    lowered = name.lower()
    cleaned = re.sub(r"[^a-z0-9-]", "-", lowered)
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned or "ticket"


def _normalize_open_embed(raw: object) -> dict | None:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


class PanelBaseView(discord.ui.View):
    def __init__(self, cog: "Ticket", owner_id: int, timeout: float = 600):
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


class TicketPanelPostView(discord.ui.View):
    def __init__(self, cog: "Ticket", source_channel_id: int, buttons: list[dict]):
        super().__init__(timeout=None)
        for button_cfg in buttons[:25]:
            self.add_item(TicketOpenButton(cog, source_channel_id, button_cfg))


class TicketOpenButton(discord.ui.Button):
    STYLE_MAP = {
        "primary": discord.ButtonStyle.primary,
        "secondary": discord.ButtonStyle.secondary,
        "success": discord.ButtonStyle.success,
        "danger": discord.ButtonStyle.danger,
    }

    def __init__(self, cog: "Ticket", source_channel_id: int, button_cfg: dict):
        self.cog = cog
        self.source_channel_id = source_channel_id
        self.button_key = str(button_cfg["button_key"])
        style = self.STYLE_MAP.get(str(button_cfg.get("style", "primary")), discord.ButtonStyle.primary)
        super().__init__(
            label=str(button_cfg["button_label"]),
            style=style,
            emoji=(str(button_cfg["emoji"]) if button_cfg.get("emoji") else None),
            custom_id=f"ticket:open:{source_channel_id}:{self.button_key}",
        )

    async def callback(self, interaction: discord.Interaction):
        if self.cog is None:
            await interaction.response.send_message("Sistema de ticket indisponivel no momento.", ephemeral=True)
            return
        await self.cog._open_ticket_from_panel(interaction, self.source_channel_id, self.button_key)


class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Fechar Ticket",
        style=discord.ButtonStyle.red,
        emoji="🔒",
        custom_id="ticket:close",
    )
    async def close_ticket(self, interaction: discord.Interaction, _button: discord.ui.Button):
        cog: Optional[Ticket] = interaction.client.get_cog("Ticket")  # type: ignore[attr-defined]
        if cog is None:
            await interaction.response.send_message("Sistema de ticket indisponivel no momento.", ephemeral=True)
            return
        await interaction.response.send_modal(TicketCloseModal(cog))


class TicketGeneralModal(discord.ui.Modal, title="Configuracao geral de ticket"):
    open_mode_input = discord.ui.TextInput(
        label="Tipo de abertura (texto/embed)",
        placeholder="texto",
        required=True,
        max_length=5,
    )
    use_same_message_input = discord.ui.TextInput(
        label="Mesma mensagem em todos os paineis? (sim/nao)",
        placeholder="sim",
        required=True,
        max_length=3,
    )
    archive_category_input = discord.ui.TextInput(
        label="ID da categoria de arquivamento (opcional)",
        placeholder="Categoria para mover ticket fechado",
        required=False,
        max_length=20,
    )
    log_channel_input = discord.ui.TextInput(
        label="ID do canal de logs (opcional)",
        placeholder="Canal para registrar fechamentos",
        required=False,
        max_length=20,
    )
    close_message_input = discord.ui.TextInput(
        label="Mensagem de fechamento",
        placeholder="Ticket fechado por {staff}. Motivo: {reason}",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000,
    )

    def __init__(self, cog: "Ticket", defaults: dict):
        super().__init__()
        self.cog = cog
        self.open_mode_input.default = str(defaults.get("open_mode", "texto"))
        self.use_same_message_input.default = "sim" if defaults.get("use_same_message", True) else "nao"
        if defaults.get("archive_category_id"):
            self.archive_category_input.default = str(defaults["archive_category_id"])
        if defaults.get("log_channel_id"):
            self.log_channel_input.default = str(defaults["log_channel_id"])
        self.close_message_input.default = (
            defaults.get("close_message")
            or "Ticket fechado por {staff}.\nMotivo: {reason}"
        )[:1000]

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Esse comando so funciona em servidor.", ephemeral=True)
            return

        raw_mode = str(self.open_mode_input.value).strip().lower()
        if raw_mode not in {"texto", "text", "embed"}:
            await interaction.response.send_message("Tipo invalido. Use 'texto' ou 'embed'.", ephemeral=True)
            return
        open_mode = "embed" if raw_mode == "embed" else "text"

        raw_same = str(self.use_same_message_input.value).strip().lower()
        if raw_same not in {"sim", "s", "nao", "n"}:
            await interaction.response.send_message("Use 'sim' ou 'nao' no campo da mensagem global.", ephemeral=True)
            return
        use_same_message = raw_same in {"sim", "s"}

        archive_category_id = None
        archive_raw = str(self.archive_category_input.value).strip()
        if archive_raw:
            try:
                archive_category_id = int(archive_raw)
            except ValueError:
                await interaction.response.send_message("ID da categoria de arquivamento invalido.", ephemeral=True)
                return
            archive_category = interaction.guild.get_channel(archive_category_id)
            if not isinstance(archive_category, discord.CategoryChannel):
                await interaction.response.send_message("Categoria de arquivamento nao encontrada.", ephemeral=True)
                return

        log_channel_id = None
        log_raw = str(self.log_channel_input.value).strip()
        if log_raw:
            try:
                log_channel_id = int(log_raw)
            except ValueError:
                await interaction.response.send_message("ID do canal de logs invalido.", ephemeral=True)
                return
            log_channel = interaction.guild.get_channel(log_channel_id)
            if not isinstance(log_channel, discord.TextChannel):
                await interaction.response.send_message("Canal de logs nao encontrado.", ephemeral=True)
                return

        close_message = str(self.close_message_input.value).strip()
        if not close_message:
            await interaction.response.send_message("Mensagem de fechamento obrigatoria.", ephemeral=True)
            return

        await self.cog._upsert_ticket_settings(
            interaction.guild.id,
            open_mode=open_mode,
            use_same_message=use_same_message,
            archive_category_id=archive_category_id,
            log_channel_id=log_channel_id,
            close_message=close_message,
        )

        embed = self.cog._panel_embed(
            "Configuracao geral salva",
            "As configuracoes globais do sistema de ticket foram atualizadas.",
            2,
            5,
            "Proximo passo: configure a mensagem de abertura.",
            discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class TicketOpenMessageModal(discord.ui.Modal, title="Mensagem de abertura"):
    open_message_input = discord.ui.TextInput(
        label="Mensagem do ticket",
        placeholder="Ola {member}, descreva seu problema para nossa equipe.",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=2000,
    )

    def __init__(self, cog: "Ticket", default_message: str | None):
        super().__init__()
        self.cog = cog
        if default_message:
            self.open_message_input.default = default_message[:2000]

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Esse comando so funciona em servidor.", ephemeral=True)
            return

        message = str(self.open_message_input.value).strip()
        if not message:
            await interaction.response.send_message("Mensagem de abertura obrigatoria.", ephemeral=True)
            return

        await self.cog._upsert_ticket_settings(
            interaction.guild.id,
            open_mode="text",
            open_message=message,
        )
        embed = self.cog._panel_embed(
            "Mensagem de abertura salva",
            "A mensagem padrao usada nos tickets foi atualizada.",
            3,
            5,
            "Proximo passo: configure os canais de ticket.",
            discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class TicketOpenEmbedModal(discord.ui.Modal, title="Embed de abertura do ticket"):
    title_input = discord.ui.TextInput(
        label="Titulo do embed",
        placeholder="Bem-vindo ao seu ticket!",
        required=True,
        max_length=256,
    )
    description_input = discord.ui.TextInput(
        label="Descricao",
        placeholder="Ola {member}, descreva o problema para a equipe.",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=2000,
    )
    color_input = discord.ui.TextInput(
        label="Cor HEX (opcional)",
        placeholder="#5865F2",
        required=False,
        max_length=7,
    )
    footer_input = discord.ui.TextInput(
        label="Footer (opcional)",
        placeholder="KRM Support",
        required=False,
        max_length=2048,
    )
    image_url_input = discord.ui.TextInput(
        label="URL da imagem (opcional)",
        placeholder="https://...",
        required=False,
        max_length=300,
    )

    def __init__(self, cog: "Ticket", defaults: dict | None = None):
        super().__init__()
        self.cog = cog
        if defaults:
            self.title_input.default = str(defaults.get("title", ""))[:256] or None
            self.description_input.default = str(defaults.get("description", ""))[:2000] or None
            raw_color = defaults.get("color")
            if isinstance(raw_color, int):
                self.color_input.default = f"#{raw_color:06X}"
            elif raw_color:
                self.color_input.default = str(raw_color)
            footer_val = defaults.get("footer")
            self.footer_input.default = str(footer_val)[:2048] if footer_val else None
            image_val = defaults.get("image_url")
            self.image_url_input.default = str(image_val)[:300] if image_val else None

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Esse comando so funciona em servidor.", ephemeral=True)
            return

        title = str(self.title_input.value).strip()
        description = str(self.description_input.value).strip()
        if not title or not description:
            await interaction.response.send_message("Titulo e descricao sao obrigatorios.", ephemeral=True)
            return

        color_raw = str(self.color_input.value).strip().lstrip("#") if self.color_input.value else ""
        color_int = None
        if color_raw:
            try:
                color_int = int(color_raw, 16)
                if not (0 <= color_int <= 0xFFFFFF):
                    raise ValueError
            except ValueError:
                await interaction.response.send_message(
                    "Cor invalida. Use HEX de 6 digitos, ex: #5865F2.", ephemeral=True
                )
                return

        embed_payload = {
            "title": title,
            "description": description,
            "color": color_int,
            "footer": str(self.footer_input.value).strip() or None,
            "image_url": str(self.image_url_input.value).strip() or None,
        }
        await self.cog._upsert_ticket_settings(interaction.guild.id, open_mode="embed", open_embed=embed_payload)

        preview = discord.Embed(
            title=title,
            description=description
                .replace("{member}", interaction.user.mention)
                .replace("{server}", interaction.guild.name),
            color=discord.Color(color_int) if color_int is not None else discord.Color.blurple(),
        )
        if embed_payload["footer"]:
            preview.set_footer(text=embed_payload["footer"])
        if embed_payload["image_url"]:
            preview.set_image(url=embed_payload["image_url"])
        await interaction.response.send_message("Embed de abertura salvo! Preview:", embed=preview, ephemeral=True)


class TicketChannelAddModal(discord.ui.Modal, title="Adicionar canal de ticket"):
    source_channel_input = discord.ui.TextInput(
        label="ID do canal onde o painel sera enviado",
        placeholder="Canal publico onde os membros vao clicar",
        required=True,
        max_length=20,
    )
    target_category_input = discord.ui.TextInput(
        label="ID da categoria dos tickets",
        placeholder="Categoria onde os canais de ticket serao criados",
        required=True,
        max_length=20,
    )
    custom_message_input = discord.ui.TextInput(
        label="Mensagem personalizada (opcional)",
        placeholder="Usada apenas se a configuracao global estiver em 'nao'",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=2000,
    )

    def __init__(self, cog: "Ticket"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Esse comando so funciona em servidor.", ephemeral=True)
            return

        try:
            source_channel_id = int(str(self.source_channel_input.value).strip())
            target_category_id = int(str(self.target_category_input.value).strip())
        except ValueError:
            await interaction.response.send_message("IDs invalidos. Use apenas numeros.", ephemeral=True)
            return

        source_channel = interaction.guild.get_channel(source_channel_id)
        target_category = interaction.guild.get_channel(target_category_id)
        if not isinstance(source_channel, discord.TextChannel):
            await interaction.response.send_message("Canal de painel nao encontrado.", ephemeral=True)
            return
        if not isinstance(target_category, discord.CategoryChannel):
            await interaction.response.send_message("Categoria de ticket nao encontrada.", ephemeral=True)
            return

        custom_message = str(self.custom_message_input.value).strip() or None
        await self.cog._upsert_ticket_channel(
            guild_id=interaction.guild.id,
            source_channel_id=source_channel.id,
            target_category_id=target_category.id,
            custom_open_message=custom_message,
        )

        embed = self.cog._panel_embed(
            "Canal adicionado",
            f"Painel: {source_channel.mention}\nCategoria: {target_category.mention}",
            4,
            5,
            "Publique ou atualize os paineis para este canal.",
            discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class TicketChannelRemoveModal(discord.ui.Modal, title="Remover canal de ticket"):
    source_channel_input = discord.ui.TextInput(
        label="ID do canal de painel",
        placeholder="Canal configurado anteriormente",
        required=True,
        max_length=20,
    )

    def __init__(self, cog: "Ticket"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Esse comando so funciona em servidor.", ephemeral=True)
            return

        try:
            source_channel_id = int(str(self.source_channel_input.value).strip())
        except ValueError:
            await interaction.response.send_message("ID do canal invalido.", ephemeral=True)
            return

        removed = await self.cog._remove_ticket_channel(interaction.guild.id, source_channel_id)
        if not removed:
            await interaction.response.send_message("Canal nao estava configurado.", ephemeral=True)
            return

        embed = self.cog._panel_embed(
            "Canal removido",
            "A configuracao desse canal de ticket foi excluida.",
            4,
            5,
            "Verifique a lista atual de canais no painel.",
            discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class TicketButtonAddModal(discord.ui.Modal, title="Adicionar botao de ticket"):
    source_channel_input = discord.ui.TextInput(
        label="ID do canal de painel",
        placeholder="Canal onde o painel sera publicado",
        required=True,
        max_length=20,
    )
    button_label_input = discord.ui.TextInput(
        label="Texto do botao",
        placeholder="Suporte",
        required=True,
        max_length=80,
    )
    prefix_input = discord.ui.TextInput(
        label="Prefixo do ticket",
        placeholder="suporte",
        required=True,
        max_length=20,
    )
    target_category_input = discord.ui.TextInput(
        label="ID da categoria do tipo",
        placeholder="Categoria onde esse tipo abre ticket",
        required=True,
        max_length=20,
    )
    custom_message_input = discord.ui.TextInput(
        label="Mensagem para este botao (opcional)",
        placeholder="Usada no modo texto quando global = nao",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=2000,
    )

    def __init__(self, cog: "Ticket"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Esse comando so funciona em servidor.", ephemeral=True)
            return

        try:
            source_channel_id = int(str(self.source_channel_input.value).strip())
            target_category_id = int(str(self.target_category_input.value).strip())
        except ValueError:
            await interaction.response.send_message("IDs invalidos. Use apenas numeros.", ephemeral=True)
            return

        source_channel = interaction.guild.get_channel(source_channel_id)
        target_category = interaction.guild.get_channel(target_category_id)
        if not isinstance(source_channel, discord.TextChannel):
            await interaction.response.send_message("Canal de painel nao encontrado.", ephemeral=True)
            return
        if not isinstance(target_category, discord.CategoryChannel):
            await interaction.response.send_message("Categoria nao encontrada.", ephemeral=True)
            return

        prefix = _sanitize_channel_name(str(self.prefix_input.value).strip().lower())
        button_key = prefix[:20]
        button_label = str(self.button_label_input.value).strip()
        if not button_label:
            await interaction.response.send_message("Texto do botao obrigatorio.", ephemeral=True)
            return

        custom_message = str(self.custom_message_input.value).strip() or None
        await self.cog._upsert_ticket_panel_button(
            guild_id=interaction.guild.id,
            source_channel_id=source_channel.id,
            button_key=button_key,
            button_label=button_label,
            prefix=prefix,
            target_category_id=target_category.id,
            custom_open_message=custom_message,
            style="primary",
            emoji=None,
        )
        await interaction.response.send_message(
            f"Botao '{button_label}' adicionado para {source_channel.mention}.",
            ephemeral=True,
        )


class TicketButtonRemoveModal(discord.ui.Modal, title="Remover botao de ticket"):
    source_channel_input = discord.ui.TextInput(
        label="ID do canal de painel",
        placeholder="Canal onde o botao foi criado",
        required=True,
        max_length=20,
    )
    button_key_input = discord.ui.TextInput(
        label="Chave do botao",
        placeholder="Ex: suporte, member",
        required=True,
        max_length=20,
    )

    def __init__(self, cog: "Ticket"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Esse comando so funciona em servidor.", ephemeral=True)
            return

        try:
            source_channel_id = int(str(self.source_channel_input.value).strip())
        except ValueError:
            await interaction.response.send_message("ID do canal invalido.", ephemeral=True)
            return

        button_key = _sanitize_channel_name(str(self.button_key_input.value).strip())[:20]
        removed = await self.cog._remove_ticket_panel_button(interaction.guild.id, source_channel_id, button_key)
        if not removed:
            await interaction.response.send_message("Botao nao encontrado para esse canal.", ephemeral=True)
            return

        await interaction.response.send_message(f"Botao '{button_key}' removido.", ephemeral=True)


class TicketRoleAddModal(discord.ui.Modal, title="Adicionar cargo de suporte"):
    role_id_input = discord.ui.TextInput(
        label="ID do cargo",
        placeholder="Cargo com acesso aos tickets",
        required=True,
        max_length=20,
    )

    def __init__(self, cog: "Ticket"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Esse comando so funciona em servidor.", ephemeral=True)
            return

        try:
            role_id = int(str(self.role_id_input.value).strip())
        except ValueError:
            await interaction.response.send_message("ID do cargo invalido.", ephemeral=True)
            return

        role = interaction.guild.get_role(role_id)
        if role is None:
            await interaction.response.send_message("Cargo nao encontrado.", ephemeral=True)
            return

        await self.cog._add_ticket_role(interaction.guild.id, role.id)
        await interaction.response.send_message(f"Cargo {role.mention} adicionado ao ticket.", ephemeral=True)


class TicketRoleRemoveModal(discord.ui.Modal, title="Remover cargo de suporte"):
    role_id_input = discord.ui.TextInput(
        label="ID do cargo",
        placeholder="Cargo que nao deve mais acessar tickets",
        required=True,
        max_length=20,
    )

    def __init__(self, cog: "Ticket"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Esse comando so funciona em servidor.", ephemeral=True)
            return

        try:
            role_id = int(str(self.role_id_input.value).strip())
        except ValueError:
            await interaction.response.send_message("ID do cargo invalido.", ephemeral=True)
            return

        removed = await self.cog._remove_ticket_role(interaction.guild.id, role_id)
        if not removed:
            await interaction.response.send_message("Cargo nao estava configurado no sistema.", ephemeral=True)
            return

        await interaction.response.send_message("Cargo removido do sistema de ticket.", ephemeral=True)


class TicketCloseModal(discord.ui.Modal, title="Fechar ticket"):
    reason_input = discord.ui.TextInput(
        label="Motivo do fechamento",
        style=discord.TextStyle.paragraph,
        placeholder="Descreva porque este ticket esta sendo encerrado",
        required=True,
        max_length=1000,
    )

    def __init__(self, cog: "Ticket"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog._close_ticket(interaction, str(self.reason_input.value).strip())


class TicketMainSelect(discord.ui.Select):
    def __init__(self, cog: "Ticket", owner_id: int):
        self.cog = cog
        self.owner_id = owner_id
        options = [
            discord.SelectOption(label="Configuracao geral", value="general", description="Mensagem global, logs e arquivamento"),
            discord.SelectOption(label="Mensagem de abertura", value="open_message", description="Texto enviado ao abrir ticket"),
            discord.SelectOption(label="Canais de ticket", value="channels", description="Um ou mais canais com painel de ticket"),
            discord.SelectOption(label="Cargos de suporte", value="roles", description="Quem pode ver e responder tickets"),
            discord.SelectOption(label="Publicar paineis", value="publish", description="Envia/atualiza botoes de abrir ticket"),
            discord.SelectOption(label="Resumo da configuracao", value="summary", description="Resumo completo do sistema"),
        ]
        super().__init__(placeholder="Escolha uma etapa do sistema de ticket", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        if selected == "general":
            defaults = await self.cog._get_ticket_settings(interaction.guild.id) if interaction.guild else {}
            await interaction.response.send_modal(TicketGeneralModal(self.cog, defaults or {}))
            return
        if selected == "open_message":
            settings = await self.cog._get_ticket_settings(interaction.guild.id) if interaction.guild else {}
            open_mode = str((settings or {}).get("open_mode", "text"))
            if open_mode == "embed":
                defaults = _normalize_open_embed((settings or {}).get("open_embed"))
                await interaction.response.send_modal(TicketOpenEmbedModal(self.cog, defaults))
                return
            await interaction.response.send_modal(TicketOpenMessageModal(self.cog, (settings or {}).get("open_message")))
            return
        if selected == "channels":
            await interaction.response.edit_message(
                embed=self.cog._ticket_channels_embed(),
                view=TicketChannelsView(self.cog, self.owner_id),
            )
            return
        if selected == "roles":
            await interaction.response.edit_message(
                embed=self.cog._ticket_roles_embed(),
                view=TicketRolesView(self.cog, self.owner_id),
            )
            return
        if selected == "publish":
            await self.cog._publish_ticket_panels(interaction)
            return
        await self.cog._send_ticket_summary(interaction)


class TicketMainView(PanelBaseView):
    def __init__(self, cog: "Ticket", owner_id: int):
        super().__init__(cog, owner_id)
        self.add_item(TicketMainSelect(cog, owner_id))


class TicketChannelsSelect(discord.ui.Select):
    def __init__(self, cog: "Ticket"):
        self.cog = cog
        options = [
            discord.SelectOption(label="Adicionar canal", value="add", description="Vincular canal de painel + categoria de ticket"),
            discord.SelectOption(label="Remover canal", value="remove", description="Excluir canal da configuracao"),
            discord.SelectOption(label="Listar canais", value="list", description="Ver canais configurados"),
            discord.SelectOption(label="Adicionar botao", value="add_button", description="Criar novo tipo de ticket no painel"),
            discord.SelectOption(label="Remover botao", value="remove_button", description="Excluir tipo de ticket do painel"),
            discord.SelectOption(label="Listar botoes", value="list_buttons", description="Ver botoes por canal"),
        ]
        super().__init__(placeholder="Acoes para canais de ticket", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        if selected == "add":
            await interaction.response.send_modal(TicketChannelAddModal(self.cog))
            return
        if selected == "remove":
            await interaction.response.send_modal(TicketChannelRemoveModal(self.cog))
            return
        if selected == "add_button":
            await interaction.response.send_modal(TicketButtonAddModal(self.cog))
            return
        if selected == "remove_button":
            await interaction.response.send_modal(TicketButtonRemoveModal(self.cog))
            return
        if selected == "list_buttons":
            await self.cog._list_ticket_buttons(interaction)
            return
        await self.cog._list_ticket_channels(interaction)


class TicketChannelsView(PanelBaseView):
    def __init__(self, cog: "Ticket", owner_id: int):
        super().__init__(cog, owner_id)
        self.add_item(TicketChannelsSelect(cog))

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.danger, row=2)
    async def back(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.edit_message(embed=self.cog._main_embed(), view=TicketMainView(self.cog, self.owner_id))


class TicketRolesSelect(discord.ui.Select):
    def __init__(self, cog: "Ticket"):
        self.cog = cog
        options = [
            discord.SelectOption(label="Adicionar cargo", value="add", description="Cargo com acesso aos tickets"),
            discord.SelectOption(label="Remover cargo", value="remove", description="Remover acesso de cargo"),
            discord.SelectOption(label="Listar cargos", value="list", description="Ver cargos permitidos"),
        ]
        super().__init__(placeholder="Acoes para cargos", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        if selected == "add":
            await interaction.response.send_modal(TicketRoleAddModal(self.cog))
            return
        if selected == "remove":
            await interaction.response.send_modal(TicketRoleRemoveModal(self.cog))
            return
        await self.cog._list_ticket_roles(interaction)


class TicketRolesView(PanelBaseView):
    def __init__(self, cog: "Ticket", owner_id: int):
        super().__init__(cog, owner_id)
        self.add_item(TicketRolesSelect(cog))

    @discord.ui.button(label="Voltar", style=discord.ButtonStyle.danger, row=2)
    async def back(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.edit_message(embed=self.cog._main_embed(), view=TicketMainView(self.cog, self.owner_id))


class Ticket(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        pool = self._get_pool()
        if pool is None:
            return

        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_settings (
                guild_id BIGINT PRIMARY KEY,
                open_message TEXT,
                open_mode TEXT NOT NULL DEFAULT 'text',
                close_message TEXT,
                use_same_message BOOLEAN NOT NULL DEFAULT TRUE,
                archive_category_id BIGINT,
                log_channel_id BIGINT,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_channels (
                guild_id BIGINT NOT NULL,
                source_channel_id BIGINT NOT NULL,
                target_category_id BIGINT NOT NULL,
                panel_message_id BIGINT,
                custom_open_message TEXT,
                PRIMARY KEY (guild_id, source_channel_id)
            )
            """
        )
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_roles (
                guild_id BIGINT NOT NULL,
                role_id BIGINT NOT NULL,
                PRIMARY KEY (guild_id, role_id)
            )
            """
        )
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                ticket_channel_id BIGINT NOT NULL UNIQUE,
                source_channel_id BIGINT NOT NULL,
                opener_id BIGINT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                close_reason TEXT,
                closed_by BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                closed_at TIMESTAMPTZ
            )
            """
        )
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_panel_buttons (
                guild_id BIGINT NOT NULL,
                source_channel_id BIGINT NOT NULL,
                button_key TEXT NOT NULL,
                button_label TEXT NOT NULL,
                prefix TEXT NOT NULL,
                target_category_id BIGINT NOT NULL,
                custom_open_message TEXT,
                style TEXT NOT NULL DEFAULT 'primary',
                emoji TEXT,
                PRIMARY KEY (guild_id, source_channel_id, button_key)
            )
            """
        )
        await pool.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_counters (
                guild_id BIGINT NOT NULL,
                prefix TEXT NOT NULL,
                last_number BIGINT NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, prefix)
            )
            """
        )
        await pool.execute(
            "ALTER TABLE ticket_settings ADD COLUMN IF NOT EXISTS open_embed JSONB"
        )
        await pool.execute(
            "ALTER TABLE ticket_settings ADD COLUMN IF NOT EXISTS open_mode TEXT NOT NULL DEFAULT 'text'"
        )
        await pool.execute(
            "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS ticket_type TEXT"
        )
        await pool.execute(
            "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS ticket_prefix TEXT"
        )

        self.bot.add_view(TicketCloseView())
        await self._restore_ticket_panel_views()

    async def _restore_ticket_panel_views(self):
        pool = self._get_pool()
        if pool is None:
            return

        rows = await pool.fetch(
            """
            SELECT guild_id, source_channel_id, panel_message_id
            FROM ticket_channels
            WHERE panel_message_id IS NOT NULL
            """
        )
        for row in rows:
            buttons = await self._get_ticket_panel_buttons(int(row["guild_id"]), int(row["source_channel_id"]))
            if not buttons:
                continue
            self.bot.add_view(
                TicketPanelPostView(self, int(row["source_channel_id"]), buttons),
                message_id=int(row["panel_message_id"]),
            )

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
            "Painel de Ticket",
            "Configure sistema completo de ticket: geral, mensagem, canais, cargos e fechamento.",
            1,
            5,
            "Selecione a proxima etapa para configurar.",
        )

    def _ticket_channels_embed(self) -> discord.Embed:
        return self._panel_embed(
            "Canais de Ticket",
            "Gerencie um ou mais canais de painel e seus tipos de ticket com botoes.",
            4,
            5,
            "Adicione/remova canais e botoes, depois publique os paineis.",
        )

    def _ticket_roles_embed(self) -> discord.Embed:
        return self._panel_embed(
            "Cargos de Ticket",
            "Defina quais cargos de equipe terao acesso automatico aos canais de ticket.\n\n"
            "**Como pegar o ID de um cargo:** Ative o Modo Desenvolvedor no Discord "
            "([saiba como](https://www.howtogeek.com/714348/how-to-enable-or-disable-developer-mode-on-discord/)), "
            "clique com o botao direito no cargo e selecione **Copiar ID**.",
            4,
            5,
            "Adicione, remova ou liste cargos de suporte.",
        )

    async def _get_ticket_settings(self, guild_id: int) -> dict | None:
        pool = self._get_pool()
        if pool is None:
            return None
        row = await pool.fetchrow(
            """
            SELECT guild_id, open_message, open_mode, close_message, use_same_message, archive_category_id, log_channel_id, open_embed
            FROM ticket_settings
            WHERE guild_id = $1
            """,
            guild_id,
        )
        if not row:
            return None
        payload = dict(row)
        payload["open_embed"] = _normalize_open_embed(payload.get("open_embed"))
        return payload

    async def _upsert_ticket_settings(
        self,
        guild_id: int,
        *,
        open_message: str | None = None,
        open_mode: str | None = None,
        close_message: str | None = None,
        use_same_message: bool | None = None,
        archive_category_id: int | None = None,
        log_channel_id: int | None = None,
        open_embed: dict | None = None,
    ) -> None:
        pool = self._get_pool()
        if pool is None:
            return

        current = await self._get_ticket_settings(guild_id) or {}
        next_open = open_message if open_message is not None else current.get("open_message")
        next_mode = open_mode if open_mode is not None else current.get("open_mode", "text")
        next_close = close_message if close_message is not None else current.get("close_message")
        next_same = use_same_message if use_same_message is not None else current.get("use_same_message", True)
        next_archive = archive_category_id if archive_category_id is not None else current.get("archive_category_id")
        next_log = log_channel_id if log_channel_id is not None else current.get("log_channel_id")
        next_embed = open_embed if open_embed is not None else current.get("open_embed")
        next_embed_db = json.dumps(next_embed) if isinstance(next_embed, dict) else next_embed

        await pool.execute(
            """
            INSERT INTO ticket_settings (
                guild_id, open_message, open_mode, close_message, use_same_message, archive_category_id, log_channel_id, open_embed, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            ON CONFLICT (guild_id)
            DO UPDATE SET
                open_message = EXCLUDED.open_message,
                open_mode = EXCLUDED.open_mode,
                close_message = EXCLUDED.close_message,
                use_same_message = EXCLUDED.use_same_message,
                archive_category_id = EXCLUDED.archive_category_id,
                log_channel_id = EXCLUDED.log_channel_id,
                open_embed = EXCLUDED.open_embed,
                updated_at = NOW()
            """,
            guild_id,
            next_open,
            next_mode,
            next_close,
            next_same,
            next_archive,
            next_log,
            next_embed_db,
        )

    async def _upsert_ticket_channel(
        self,
        *,
        guild_id: int,
        source_channel_id: int,
        target_category_id: int,
        custom_open_message: str | None,
    ) -> None:
        pool = self._get_pool()
        if pool is None:
            return
        await pool.execute(
            """
            INSERT INTO ticket_channels (guild_id, source_channel_id, target_category_id, custom_open_message)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, source_channel_id)
            DO UPDATE SET
                target_category_id = EXCLUDED.target_category_id,
                custom_open_message = EXCLUDED.custom_open_message
            """,
            guild_id,
            source_channel_id,
            target_category_id,
            custom_open_message,
        )
        await pool.execute(
            """
            INSERT INTO ticket_panel_buttons (
                guild_id, source_channel_id, button_key, button_label, prefix, target_category_id, custom_open_message, style, emoji
            )
            VALUES ($1, $2, 'support', 'Suporte', 'support', $3, $4, 'primary', '🎫')
            ON CONFLICT (guild_id, source_channel_id, button_key)
            DO UPDATE SET
                target_category_id = EXCLUDED.target_category_id,
                custom_open_message = COALESCE(ticket_panel_buttons.custom_open_message, EXCLUDED.custom_open_message)
            """,
            guild_id,
            source_channel_id,
            target_category_id,
            custom_open_message,
        )

    async def _remove_ticket_channel(self, guild_id: int, source_channel_id: int) -> bool:
        pool = self._get_pool()
        if pool is None:
            return False
        result = await pool.execute(
            "DELETE FROM ticket_channels WHERE guild_id = $1 AND source_channel_id = $2",
            guild_id,
            source_channel_id,
        )
        return result.endswith("1")

    async def _get_ticket_channels(self, guild_id: int) -> list[dict]:
        pool = self._get_pool()
        if pool is None:
            return []
        rows = await pool.fetch(
            """
            SELECT source_channel_id, target_category_id, panel_message_id, custom_open_message
            FROM ticket_channels
            WHERE guild_id = $1
            ORDER BY source_channel_id ASC
            """,
            guild_id,
        )
        return [dict(row) for row in rows]

    async def _upsert_ticket_panel_button(
        self,
        *,
        guild_id: int,
        source_channel_id: int,
        button_key: str,
        button_label: str,
        prefix: str,
        target_category_id: int,
        custom_open_message: str | None,
        style: str,
        emoji: str | None,
    ) -> None:
        pool = self._get_pool()
        if pool is None:
            return
        await pool.execute(
            """
            INSERT INTO ticket_panel_buttons (
                guild_id, source_channel_id, button_key, button_label, prefix, target_category_id, custom_open_message, style, emoji
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (guild_id, source_channel_id, button_key)
            DO UPDATE SET
                button_label = EXCLUDED.button_label,
                prefix = EXCLUDED.prefix,
                target_category_id = EXCLUDED.target_category_id,
                custom_open_message = EXCLUDED.custom_open_message,
                style = EXCLUDED.style,
                emoji = EXCLUDED.emoji
            """,
            guild_id,
            source_channel_id,
            button_key,
            button_label,
            prefix,
            target_category_id,
            custom_open_message,
            style,
            emoji,
        )

    async def _remove_ticket_panel_button(self, guild_id: int, source_channel_id: int, button_key: str) -> bool:
        pool = self._get_pool()
        if pool is None:
            return False
        result = await pool.execute(
            """
            DELETE FROM ticket_panel_buttons
            WHERE guild_id = $1 AND source_channel_id = $2 AND button_key = $3
            """,
            guild_id,
            source_channel_id,
            button_key,
        )
        return result.endswith("1")

    async def _get_ticket_panel_buttons(self, guild_id: int, source_channel_id: int) -> list[dict]:
        pool = self._get_pool()
        if pool is None:
            return []
        rows = await pool.fetch(
            """
            SELECT button_key, button_label, prefix, target_category_id, custom_open_message, style, emoji
            FROM ticket_panel_buttons
            WHERE guild_id = $1 AND source_channel_id = $2
            ORDER BY button_key ASC
            """,
            guild_id,
            source_channel_id,
        )
        return [dict(row) for row in rows]

    async def _next_ticket_number(self, guild_id: int, prefix: str) -> int:
        pool = self._get_pool()
        if pool is None:
            return 1
        row = await pool.fetchrow(
            """
            INSERT INTO ticket_counters (guild_id, prefix, last_number)
            VALUES ($1, $2, 1)
            ON CONFLICT (guild_id, prefix)
            DO UPDATE SET last_number = ticket_counters.last_number + 1
            RETURNING last_number
            """,
            guild_id,
            prefix,
        )
        return int(row["last_number"]) if row else 1

    async def _add_ticket_role(self, guild_id: int, role_id: int) -> None:
        pool = self._get_pool()
        if pool is None:
            return
        await pool.execute(
            """
            INSERT INTO ticket_roles (guild_id, role_id)
            VALUES ($1, $2)
            ON CONFLICT (guild_id, role_id) DO NOTHING
            """,
            guild_id,
            role_id,
        )

    async def _remove_ticket_role(self, guild_id: int, role_id: int) -> bool:
        pool = self._get_pool()
        if pool is None:
            return False
        result = await pool.execute(
            "DELETE FROM ticket_roles WHERE guild_id = $1 AND role_id = $2",
            guild_id,
            role_id,
        )
        return result.endswith("1")

    async def _get_ticket_roles(self, guild_id: int) -> list[int]:
        pool = self._get_pool()
        if pool is None:
            return []
        rows = await pool.fetch(
            "SELECT role_id FROM ticket_roles WHERE guild_id = $1 ORDER BY role_id ASC",
            guild_id,
        )
        return [int(row["role_id"]) for row in rows]

    async def _publish_ticket_panels(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Esse comando so funciona em servidor.", ephemeral=True)
            return

        channels = await self._get_ticket_channels(interaction.guild.id)
        settings = await self._get_ticket_settings(interaction.guild.id) or {}
        open_message = settings.get("open_message")
        open_embed = settings.get("open_embed")
        if not channels:
            await interaction.response.send_message("Nenhum canal de ticket configurado ainda.", ephemeral=True)
            return
        if settings.get("open_mode", "text") == "embed" and not open_embed:
            await interaction.response.send_message("Defina o embed de abertura antes de publicar os paineis.", ephemeral=True)
            return
        if settings.get("open_mode", "text") != "embed" and not open_message:
            await interaction.response.send_message("Defina a mensagem de abertura antes de publicar os paineis.", ephemeral=True)
            return

        use_same_message = bool(settings.get("use_same_message", True))
        sent_count = 0
        pool = self._get_pool()
        if pool is None:
            await interaction.response.send_message("Banco de dados indisponivel no momento.", ephemeral=True)
            return

        for channel_cfg in channels:
            source_channel = interaction.guild.get_channel(channel_cfg["source_channel_id"])
            if not isinstance(source_channel, discord.TextChannel):
                continue

            button_rows = await self._get_ticket_panel_buttons(interaction.guild.id, source_channel.id)
            if not button_rows:
                continue

            panel_view = TicketPanelPostView(self, source_channel.id, button_rows)

            panel_text = (
                open_message
                if use_same_message
                else (channel_cfg.get("custom_open_message") or open_message)
            )
            panel_embed = discord.Embed(
                title="Central de Tickets",
                description=_short_text(panel_text, "Clique em um dos botoes abaixo para abrir seu ticket."),
                color=discord.Color.blurple(),
                timestamp=datetime.utcnow(),
            )
            panel_embed.set_footer(text="Ticket System")

            message = await source_channel.send(embed=panel_embed, view=panel_view)
            sent_count += 1
            await pool.execute(
                """
                UPDATE ticket_channels
                SET panel_message_id = $3
                WHERE guild_id = $1 AND source_channel_id = $2
                """,
                interaction.guild.id,
                source_channel.id,
                message.id,
            )
            self.bot.add_view(panel_view, message_id=message.id)

        embed = self._panel_embed(
            "Paineis publicados",
            f"{sent_count} painel(is) enviado(s) nos canais configurados.",
            5,
            5,
            "Sistema pronto para uso pelos membros.",
            discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _list_ticket_channels(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Esse comando so funciona em servidor.", ephemeral=True)
            return
        channels = await self._get_ticket_channels(interaction.guild.id)
        if not channels:
            await interaction.response.send_message("Nenhum canal de ticket configurado.", ephemeral=True)
            return

        lines = []
        for cfg in channels:
            source = f"<#{cfg['source_channel_id']}>"
            category = f"<#{cfg['target_category_id']}>"
            custom = "sim" if cfg.get("custom_open_message") else "nao"
            button_count = len(await self._get_ticket_panel_buttons(interaction.guild.id, int(cfg["source_channel_id"])))
            lines.append(
                f"• Painel: {source} | Categoria padrao: {category} | Msg personalizada: {custom} | Botoes: {button_count}"
            )

        embed = self._panel_embed(
            "Canais configurados",
            "\n".join(lines)[:4000],
            4,
            5,
            "Se necessario, ajuste canais e publique os paineis novamente.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _list_ticket_buttons(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Esse comando so funciona em servidor.", ephemeral=True)
            return

        channels = await self._get_ticket_channels(interaction.guild.id)
        if not channels:
            await interaction.response.send_message("Nenhum canal de ticket configurado.", ephemeral=True)
            return

        sections = []
        for cfg in channels:
            source_channel_id = int(cfg["source_channel_id"])
            buttons = await self._get_ticket_panel_buttons(interaction.guild.id, source_channel_id)
            if not buttons:
                sections.append(f"Canal <#{source_channel_id}>: nenhum botao")
                continue
            lines = [
                f"- {b['button_label']} | chave: {b['button_key']} | prefixo: {b['prefix']} | categoria: <#{b['target_category_id']}>"
                for b in buttons
            ]
            sections.append(f"Canal <#{source_channel_id}>:\n" + "\n".join(lines))

        embed = self._panel_embed(
            "Botoes configurados",
            _short_text("\n\n".join(sections), "Nenhum botao configurado."),
            4,
            5,
            "Use adicionar/remover botao para ajustar os tipos de ticket.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _list_ticket_roles(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Esse comando so funciona em servidor.", ephemeral=True)
            return

        role_ids = await self._get_ticket_roles(interaction.guild.id)
        if not role_ids:
            await interaction.response.send_message("Nenhum cargo de suporte configurado.", ephemeral=True)
            return

        mentions = [f"<@&{role_id}>" for role_id in role_ids]
        embed = self._panel_embed(
            "Cargos de suporte",
            "\n".join(mentions)[:4000],
            4,
            5,
            "Esses cargos recebem acesso automatico aos tickets.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _send_ticket_summary(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Esse comando so funciona em servidor.", ephemeral=True)
            return

        settings = await self._get_ticket_settings(interaction.guild.id) or {}
        channels = await self._get_ticket_channels(interaction.guild.id)
        roles = await self._get_ticket_roles(interaction.guild.id)

        embed = self._panel_embed(
            "Resumo do Ticket",
            "Visao geral da configuracao atual.",
            5,
            5,
            "Revise tudo antes de publicar os paineis.",
        )
        embed.add_field(
            name="Tipo de abertura",
            value=("Embed" if settings.get("open_mode", "text") == "embed" else "Texto"),
            inline=True,
        )
        embed.add_field(
            name="Mensagem de abertura (texto)",
            value=_short_text(settings.get("open_message")),
            inline=False,
        )
        embed.add_field(
            name="Embed de abertura",
            value=("Configurado" if settings.get("open_embed") else "Nao configurado"),
            inline=True,
        )
        embed.add_field(
            name="Mensagem de fechamento",
            value=_short_text(settings.get("close_message")),
            inline=False,
        )
        embed.add_field(
            name="Mesma mensagem em todos os paineis",
            value="Sim" if settings.get("use_same_message", True) else "Nao",
            inline=True,
        )
        embed.add_field(
            name="Categoria de arquivamento",
            value=(f"<#{settings['archive_category_id']}>" if settings.get("archive_category_id") else "Nao configurado"),
            inline=True,
        )
        embed.add_field(
            name="Canal de logs",
            value=(f"<#{settings['log_channel_id']}>" if settings.get("log_channel_id") else "Nao configurado"),
            inline=True,
        )

        channels_text = "\n".join(
            [f"• <#{c['source_channel_id']}> -> <#{c['target_category_id']}>" for c in channels]
        ) or "Nenhum canal configurado"
        embed.add_field(name="Canais de painel/categoria", value=_short_text(channels_text), inline=False)

        role_text = "\n".join([f"<@&{r}>" for r in roles]) or "Nenhum cargo configurado"
        embed.add_field(name="Cargos de suporte", value=_short_text(role_text), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _open_ticket_from_panel(
        self,
        interaction: discord.Interaction,
        source_channel_id: int | None = None,
        button_key: str | None = None,
    ):
        guild = interaction.guild
        if guild is None or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("Esse botao so funciona em canal de servidor.", ephemeral=True)
            return

        pool = self._get_pool()
        if pool is None:
            await interaction.response.send_message("Banco de dados indisponivel no momento.", ephemeral=True)
            return

        source_channel_id = source_channel_id or interaction.channel.id
        button_key = button_key or "support"

        cfg = await pool.fetchrow(
            """
            SELECT button_key, button_label, prefix, target_category_id, custom_open_message
            FROM ticket_panel_buttons
            WHERE guild_id = $1 AND source_channel_id = $2 AND button_key = $3
            """,
            guild.id,
            source_channel_id,
            button_key,
        )
        if not cfg:
            legacy = await pool.fetchrow(
                """
                SELECT target_category_id, custom_open_message
                FROM ticket_channels
                WHERE guild_id = $1 AND source_channel_id = $2
                """,
                guild.id,
                source_channel_id,
            )
            if not legacy:
                await interaction.response.send_message("Este canal nao esta configurado para abrir ticket.", ephemeral=True)
                return
            cfg = {
                "button_key": "support",
                "button_label": "Suporte",
                "prefix": "support",
                "target_category_id": legacy["target_category_id"],
                "custom_open_message": legacy["custom_open_message"],
            }

        settings = await self._get_ticket_settings(guild.id) or {}
        target_category = guild.get_channel(cfg["target_category_id"])
        if not isinstance(target_category, discord.CategoryChannel):
            await interaction.response.send_message("Categoria de ticket nao encontrada. Avise a administracao.", ephemeral=True)
            return

        # Evita tickets duplicados por usuario na mesma origem.
        existing = await pool.fetchrow(
            """
            SELECT ticket_channel_id
            FROM tickets
            WHERE guild_id = $1 AND source_channel_id = $2 AND opener_id = $3 AND status = 'open'
            LIMIT 1
            """,
            guild.id,
            source_channel_id,
            interaction.user.id,
        )
        if existing:
            existing_channel = guild.get_channel(existing["ticket_channel_id"])
            if existing_channel:
                await interaction.response.send_message(
                    f"Voce ja tem um ticket aberto: {existing_channel.mention}",
                    ephemeral=True,
                )
                return

        support_role_ids = await self._get_ticket_roles(guild.id)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True,
                read_message_history=True,
            ),
        }
        for role_id in support_role_ids:
            role = guild.get_role(role_id)
            if role is not None:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True,
                )

        ticket_prefix = _sanitize_channel_name(str(cfg["prefix"]))
        next_number = await self._next_ticket_number(guild.id, ticket_prefix)
        ticket_name = f"{ticket_prefix}-{next_number:04d}"
        ticket_channel = await guild.create_text_channel(
            name=ticket_name,
            category=target_category,
            overwrites=overwrites,
            reason=f"Ticket aberto por {interaction.user} ({interaction.user.id})",
        )

        await pool.execute(
            """
            INSERT INTO tickets (guild_id, ticket_channel_id, source_channel_id, opener_id, status, ticket_type, ticket_prefix)
            VALUES ($1, $2, $3, $4, 'open', $5, $6)
            """,
            guild.id,
            ticket_channel.id,
            source_channel_id,
            interaction.user.id,
            str(cfg["button_key"]),
            ticket_prefix,
        )

        use_same = bool(settings.get("use_same_message", True))
        base_message = settings.get("open_message") or "Ticket aberto com sucesso."
        open_embed_payload = settings.get("open_embed")
        if not use_same and cfg.get("custom_open_message"):
            base_message = cfg["custom_open_message"]
            open_embed_payload = None

        open_mode = str(settings.get("open_mode", "text"))

        support_mentions = " ".join([f"<@&{r}>" for r in support_role_ids])
        if open_mode == "embed" and open_embed_payload and isinstance(open_embed_payload, dict):
            raw_color = open_embed_payload.get("color")
            embed_color = discord.Color(raw_color) if isinstance(raw_color, int) else discord.Color.green()
            desc = (
                str(open_embed_payload.get("description", ""))
                .replace("{member}", interaction.user.mention)
                .replace("{user}", interaction.user.mention)
                .replace("{server}", guild.name)
                .replace("{type}", str(cfg["button_label"]))
            )
            open_embed = discord.Embed(
                title=str(open_embed_payload.get("title", "Ticket Aberto")),
                description=desc,
                color=embed_color,
                timestamp=datetime.utcnow(),
            )
            if open_embed_payload.get("footer"):
                open_embed.set_footer(text=str(open_embed_payload["footer"]))
            else:
                open_embed.set_footer(text="Use o botao abaixo para fechar o ticket")
            if open_embed_payload.get("image_url"):
                open_embed.set_image(url=str(open_embed_payload["image_url"]))
        else:
            content = (
                base_message
                .replace("{member}", interaction.user.mention)
                .replace("{user}", interaction.user.mention)
                .replace("{server}", guild.name)
                .replace("{type}", str(cfg["button_label"]))
            )
            open_embed = discord.Embed(
                title="Ticket Aberto",
                description=content,
                color=discord.Color.green(),
                timestamp=datetime.utcnow(),
            )
            open_embed.set_footer(text="Use o botao abaixo para fechar o ticket")

        open_embed.add_field(name="Criado por", value=interaction.user.mention, inline=True)
        open_embed.add_field(name="Canal de origem", value=interaction.channel.mention, inline=True)
        await ticket_channel.send(content=support_mentions or None, embed=open_embed, view=TicketCloseView())
        await interaction.response.send_message(f"Ticket criado em {ticket_channel.mention}", ephemeral=True)

    async def _close_ticket(self, interaction: discord.Interaction, reason: str):
        guild = interaction.guild
        if guild is None or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("Esse botao so funciona em ticket de servidor.", ephemeral=True)
            return

        pool = self._get_pool()
        if pool is None:
            await interaction.response.send_message("Banco de dados indisponivel no momento.", ephemeral=True)
            return

        ticket_row = await pool.fetchrow(
            """
            SELECT id, opener_id, status
            FROM tickets
            WHERE guild_id = $1 AND ticket_channel_id = $2
            """,
            guild.id,
            interaction.channel.id,
        )
        if not ticket_row:
            await interaction.response.send_message("Este canal nao esta registrado como ticket.", ephemeral=True)
            return
        if ticket_row["status"] != "open":
            await interaction.response.send_message("Esse ticket ja foi fechado.", ephemeral=True)
            return

        opener_id = int(ticket_row["opener_id"])
        can_manage = interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.administrator
        if interaction.user.id != opener_id and not can_manage:
            await interaction.response.send_message("Apenas o criador ou staff pode fechar este ticket.", ephemeral=True)
            return

        settings = await self._get_ticket_settings(guild.id) or {}
        close_template = settings.get("close_message") or "Ticket fechado por {staff}.\nMotivo: {reason}"
        close_text = (
            close_template
            .replace("{staff}", interaction.user.mention)
            .replace("{member}", f"<@{opener_id}>")
            .replace("{reason}", reason or "Nao informado")
            .replace("{server}", guild.name)
        )

        await pool.execute(
            """
            UPDATE tickets
            SET status = 'closed', close_reason = $3, closed_by = $4, closed_at = NOW()
            WHERE guild_id = $1 AND ticket_channel_id = $2
            """,
            guild.id,
            interaction.channel.id,
            reason,
            interaction.user.id,
        )

        archive_category_id = settings.get("archive_category_id")
        archive_category = guild.get_channel(archive_category_id) if archive_category_id else None
        opener_member = guild.get_member(opener_id)

        if opener_member is not None:
            await interaction.channel.set_permissions(
                opener_member,
                view_channel=False,
                send_messages=False,
                reason=f"Ticket fechado por {interaction.user} ({interaction.user.id})",
            )

        if isinstance(archive_category, discord.CategoryChannel):
            try:
                await interaction.channel.edit(category=archive_category, name=f"closed-{interaction.channel.name}")
            except discord.HTTPException:
                pass

        close_embed = discord.Embed(
            title="Ticket Fechado",
            description=close_text,
            color=discord.Color.orange(),
            timestamp=datetime.utcnow(),
        )
        close_embed.add_field(name="Fechado por", value=interaction.user.mention, inline=True)
        close_embed.add_field(name="Motivo", value=_short_text(reason, "Nao informado"), inline=False)
        await interaction.response.send_message(embed=close_embed)

        log_channel_id = settings.get("log_channel_id")
        log_channel = guild.get_channel(log_channel_id) if log_channel_id else None
        if isinstance(log_channel, discord.TextChannel):
            log_embed = discord.Embed(
                title="Log de Ticket Fechado",
                color=discord.Color.red(),
                timestamp=datetime.utcnow(),
            )
            log_embed.add_field(name="Canal", value=interaction.channel.mention, inline=True)
            log_embed.add_field(name="Criador", value=f"<@{opener_id}>", inline=True)
            log_embed.add_field(name="Staff", value=interaction.user.mention, inline=True)
            log_embed.add_field(name="Motivo", value=_short_text(reason, "Nao informado"), inline=False)
            await log_channel.send(embed=log_embed)

    @app_commands.command(name="ticketpanel", description="Abre o painel completo de configuracao de ticket.")
    @app_commands.check(check_manage_or_admin)
    async def ticketpanel(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=self._main_embed(),
            view=TicketMainView(self, interaction.user.id),
            ephemeral=True,
        )

    @ticketpanel.error
    async def ticketpanel_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
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
    await bot.add_cog(Ticket(bot))