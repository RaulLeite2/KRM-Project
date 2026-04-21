import discord
from discord.ext import commands
from discord import app_commands
import json
from datetime import datetime, timezone
import time
import io


WELCOME_EMBED_DRAFT_TTL_SECONDS = 1800
WELCOME_EMBED_DRAFTS: dict[tuple[int, int], dict] = {}


def _draft_key(guild_id: int, user_id: int) -> tuple[int, int]:
    return guild_id, user_id


def _clean_welcome_embed_drafts() -> None:
    now = time.time()
    expired = [
        key
        for key, value in WELCOME_EMBED_DRAFTS.items()
        if now - value.get("updated_at", 0) > WELCOME_EMBED_DRAFT_TTL_SECONDS
    ]
    for key in expired:
        WELCOME_EMBED_DRAFTS.pop(key, None)


def set_welcome_embed_draft(guild_id: int, user_id: int, channel_id: int, payload: dict) -> None:
    _clean_welcome_embed_drafts()
    WELCOME_EMBED_DRAFTS[_draft_key(guild_id, user_id)] = {
        "guild_id": guild_id,
        "user_id": user_id,
        "channel_id": channel_id,
        "payload": payload,
        "updated_at": time.time(),
    }


def get_welcome_embed_draft(guild_id: int, user_id: int) -> dict | None:
    _clean_welcome_embed_drafts()
    return WELCOME_EMBED_DRAFTS.get(_draft_key(guild_id, user_id))


def clear_welcome_embed_draft(guild_id: int, user_id: int) -> None:
    WELCOME_EMBED_DRAFTS.pop(_draft_key(guild_id, user_id), None)


def list_embed_fields_text(fields: list) -> str:
    if not isinstance(fields, list) or not fields:
        return "Nenhum field configurado."

    lines = []
    for i, field in enumerate(fields, start=1):
        if not isinstance(field, dict):
            continue
        name = str(field.get("name", "Sem nome"))
        inline = "inline" if field.get("inline", True) else "bloco"
        lines.append(f"{i}. {name} ({inline})")
    return "\n".join(lines) if lines else "Nenhum field configurado."


def apply_step_footer(embed: discord.Embed, step: int, total_steps: int, hint: str | None = None) -> discord.Embed:
    text = f"Step {step}/{total_steps}"
    if hint:
        text = f"{text} • {hint}"
    embed.set_footer(text=text)
    return embed


def render_template_text(text: str | None, member: discord.Member) -> str | None:
    if text is None:
        return None
    guild = member.guild
    values = {
        "{member}": member.mention,
        "{user}": member.mention,
        "{user_name}": member.display_name,
        "{server}": guild.name,
        "{member_count}": str(guild.member_count or 0),
    }
    rendered = str(text)
    for key, value in values.items():
        rendered = rendered.replace(key, value)
    return rendered


def validate_welcome_embed_payload(payload: dict) -> str | None:
    if not isinstance(payload, dict):
        return "Payload invalido para o embed."

    title = str(payload.get("title", "") or "").strip()
    description = str(payload.get("description", "") or "").strip()
    color = payload.get("color")
    fields = payload.get("fields", [])
    author_name = str(payload.get("author_name", "") or "")

    if not title:
        return "Titulo obrigatorio."
    if not description:
        return "Descricao obrigatoria."
    if len(title) > 256:
        return "Titulo excede 256 caracteres."
    if len(description) > 4096:
        return "Descricao excede 4096 caracteres."

    parsed_color = color
    if isinstance(color, str):
        cleaned = color.strip().lower().replace("#", "")
        if cleaned.startswith("0x"):
            cleaned = cleaned[2:]
        if len(cleaned) != 6:
            return "Cor invalida. Use hexadecimal com 6 digitos, ex: #FFAA00."
        try:
            parsed_color = int(cleaned, 16)
        except ValueError:
            return "Cor invalida. Use hexadecimal com 6 digitos, ex: #FFAA00."
    elif not isinstance(parsed_color, int):
        return "Cor invalida. Informe HEX ou inteiro."

    if not isinstance(fields, list):
        return "Fields precisam estar em lista."
    if len(fields) > 25:
        return "Limite de fields atingido. Maximo: 25."

    total_chars = len(title) + len(description) + len(author_name)
    for index, field in enumerate(fields, start=1):
        if not isinstance(field, dict):
            return f"Field #{index} invalido."
        name = str(field.get("name", "") or "")
        value = str(field.get("value", "") or "")
        if not name or not value:
            return f"Field #{index} precisa de nome e valor."
        if len(name) > 256:
            return f"Nome do field #{index} excede 256 caracteres."
        if len(value) > 1024:
            return f"Valor do field #{index} excede 1024 caracteres."
        total_chars += len(name) + len(value)

    if total_chars > 6000:
        return "Embed excede 6000 caracteres totais."

    return None


async def check_manage_or_admin(interaction: discord.Interaction) -> bool:
    """Verifica se o usuário tem permissão de Gerenciar Servidor ou é Administrador"""
    if interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild:
        return True
    await interaction.response.send_message(
        "Você precisa de permissão de **Gerenciar Servidor** ou ser **Administrador** para usar este comando.",
        ephemeral=True
    )
    return False


class WelcomeModal(discord.ui.Modal, title="Configurar Boas-Vindas"):
    def __init__(
        self,
        bot: commands.Bot,
        default_channel_id: int | None = None,
        default_message: str | None = None,
    ):
        super().__init__()
        self.bot = bot
        self.channel_id_input = discord.ui.TextInput(
            label="ID do Canal",
            placeholder="Cole o ID do canal de boas-vindas",
            required=True,
            max_length=20,
            default=str(default_channel_id) if default_channel_id else None,
        )
        self.message_input = discord.ui.TextInput(
            label="Mensagem",
            placeholder="Use {member} para mencionar o novo membro",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=2000,
            default=(default_message or "")[:2000] or None,
        )
        self.add_item(self.channel_id_input)
        self.add_item(self.message_input)

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
        if not channel:
            await interaction.response.send_message("Canal nao encontrado.", ephemeral=True)
            return

        await self.bot.pool.execute(
            """
            INSERT INTO guild_settings (guild_id, welcome_channel_id, welcome_message)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE SET
                welcome_channel_id = EXCLUDED.welcome_channel_id,
                welcome_message = EXCLUDED.welcome_message
            """,
            interaction.guild.id,
            channel_id,
            str(self.message_input.value),
        )
        embed = discord.Embed(
            title="Boas-vindas em texto configuradas",
            description=f"Canal definido: {channel.mention}",
            color=discord.Color.green(),
        )
        apply_step_footer(embed, 2, 4, "Opcional: migre para embed no proximo passo")
        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

class ExitModal(discord.ui.Modal, title="Configurar Saida"):
    def __init__(
        self,
        bot: commands.Bot,
        default_channel_id: int | None = None,
        default_message: str | None = None,
    ):
        super().__init__()
        self.bot = bot
        self.channel_id_input = discord.ui.TextInput(
            label="ID do Canal",
            placeholder="Cole o ID do canal de saida",
            required=True,
            max_length=20,
            default=str(default_channel_id) if default_channel_id else None,
        )
        self.message_input = discord.ui.TextInput(
            label="Mensagem",
            placeholder="Use {member} para o nome do membro que saiu",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=2000,
            default=(default_message or "")[:2000] or None,
        )
        self.add_item(self.channel_id_input)
        self.add_item(self.message_input)

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
        if not channel:
            await interaction.response.send_message("Canal nao encontrado.", ephemeral=True)
            return

        await self.bot.pool.execute(
            """
            INSERT INTO guild_settings (guild_id, exit_channel_id, exit_message)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id) DO UPDATE SET
                exit_channel_id = EXCLUDED.exit_channel_id,
                exit_message = EXCLUDED.exit_message
            """,
            interaction.guild.id,
            channel_id,
            str(self.message_input.value),
        )
        await interaction.response.send_message(
            f"Saida configurada! Canal: {channel.mention}",
            ephemeral=True,
        )


def build_welcome_embed_from_payload(payload: dict, member: discord.Member) -> discord.Embed | None:
    if not isinstance(payload, dict):
        return None

    validation_error = validate_welcome_embed_payload(payload)
    if validation_error:
        return None

    rendered_fields = []
    for field in payload.get("fields", []):
        if not isinstance(field, dict):
            continue
        rendered_fields.append(
            {
                "name": render_template_text(field.get("name"), member),
                "value": render_template_text(field.get("value"), member),
                "inline": bool(field.get("inline", True)),
            }
        )

    custom = CustomEmbed(
        title=render_template_text(payload.get("title", ""), member),
        description=render_template_text(payload.get("description", ""), member),
        color=payload.get("color", "#5865F2"),
        url=payload.get("url"),
        timestamp=payload.get("timestamp"),
        thumbnail_url=payload.get("thumbnail_url"),
        image_url=payload.get("image_url"),
        author_name=render_template_text(payload.get("author_name"), member),
        author_icon_url=payload.get("author_icon_url"),
    )
    custom.add_fields(rendered_fields)
    embed = custom.create_embed()
    return embed if isinstance(embed, discord.Embed) else None


async def ensure_welcome_embed_draft(pool, guild_id: int, user_id: int) -> dict | None:
    draft = get_welcome_embed_draft(guild_id, user_id)
    if draft:
        return draft

    row = await pool.fetchrow(
        "SELECT welcome_channel_id, welcome_embed FROM guild_settings WHERE guild_id = $1",
        guild_id,
    )
    if not row or not row["welcome_embed"] or not isinstance(row["welcome_embed"], dict):
        return None

    payload = dict(row["welcome_embed"])
    if not isinstance(payload.get("fields"), list):
        payload["fields"] = []
    draft = {
        "guild_id": guild_id,
        "user_id": user_id,
        "channel_id": row["welcome_channel_id"],
        "payload": payload,
        "updated_at": time.time(),
    }
    set_welcome_embed_draft(guild_id, user_id, row["welcome_channel_id"], payload)
    return draft


async def get_saved_welcome_embed_state(pool, guild_id: int) -> tuple[int | None, dict | None]:
    row = await pool.fetchrow(
        "SELECT welcome_channel_id, welcome_embed FROM guild_settings WHERE guild_id = $1",
        guild_id,
    )
    if not row:
        return None, None
    return row["welcome_channel_id"], row["welcome_embed"]


async def get_previous_welcome_embed_state(pool, guild_id: int) -> tuple[int | None, dict | None]:
    row = await pool.fetchrow(
        "SELECT welcome_embed_previous_channel_id, welcome_embed_previous FROM guild_settings WHERE guild_id = $1",
        guild_id,
    )
    if not row:
        return None, None
    return row["welcome_embed_previous_channel_id"], row["welcome_embed_previous"]


def normalize_import_payload(payload: dict) -> dict:
    normalized = dict(payload)
    if "fields" not in normalized or not isinstance(normalized.get("fields"), list):
        normalized["fields"] = []
    return normalized


async def save_welcome_embed_payload(pool, guild_id: int, channel_id: int, payload: dict) -> None:
    await pool.execute(
        """
        INSERT INTO guild_settings (guild_id, welcome_channel_id, welcome_embed, welcome_message)
        VALUES ($1, $2, $3::jsonb, NULL)
        ON CONFLICT (guild_id) DO UPDATE SET
            welcome_embed_previous = guild_settings.welcome_embed,
            welcome_embed_previous_channel_id = guild_settings.welcome_channel_id,
            welcome_channel_id = EXCLUDED.welcome_channel_id,
            welcome_embed = EXCLUDED.welcome_embed,
            welcome_message = NULL
        """,
        guild_id,
        channel_id,
        json.dumps(payload),
    )


class WelcomeEmbedModal(discord.ui.Modal, title="Configurar Embed de Entrada"):
    channel_id_input = discord.ui.TextInput(
        label="ID do Canal",
        placeholder="Cole o ID do canal de boas-vindas",
        required=True,
        max_length=20,
    )
    title_input = discord.ui.TextInput(
        label="Titulo do Embed",
        placeholder="Ex: Bem-vindo, {member}!",
        required=True,
        max_length=256,
    )
    description_input = discord.ui.TextInput(
        label="Descricao",
        placeholder="Mensagem principal (use {member} para mencao)",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=2000,
    )
    color_input = discord.ui.TextInput(
        label="Cor HEX",
        placeholder="#FFAA00",
        required=True,
        max_length=7,
    )
    thumbnail_input = discord.ui.TextInput(
        label="Thumbnail URL (opcional)",
        placeholder="https://...",
        required=False,
        max_length=300,
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

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
        if not channel:
            await interaction.response.send_message("Canal nao encontrado.", ephemeral=True)
            return

        payload = {
            "title": str(self.title_input.value),
            "description": str(self.description_input.value),
            "color": str(self.color_input.value),
            "thumbnail_url": str(self.thumbnail_input.value).strip() if self.thumbnail_input.value else None,
            "fields": [],
        }

        validation_error = validate_welcome_embed_payload(payload)
        if validation_error:
            await interaction.response.send_message(validation_error, ephemeral=True)
            return

        preview_embed = build_welcome_embed_from_payload(payload, interaction.user)
        if not preview_embed:
            await interaction.response.send_message(
                "Nao foi possivel criar o embed. Verifique os campos (principalmente a cor HEX).",
                ephemeral=True,
            )
            return

        apply_step_footer(preview_embed, 2, 4, "Agora ajuste extras e fields")

        set_welcome_embed_draft(interaction.guild.id, interaction.user.id, channel_id, payload)

        await interaction.response.send_message(
            f"Rascunho do embed criado para {channel.mention}. Use 'Confirmar Embed de Boas-Vindas' para salvar.",
            embed=preview_embed,
            ephemeral=True,
        )


class WelcomeEmbedExtrasModal(discord.ui.Modal, title="Editar Extras do Embed"):
    url_input = discord.ui.TextInput(
        label="URL do titulo (opcional)",
        placeholder="https://...",
        required=False,
        max_length=300,
    )
    image_input = discord.ui.TextInput(
        label="Imagem principal URL (opcional)",
        placeholder="https://...",
        required=False,
        max_length=300,
    )
    author_name_input = discord.ui.TextInput(
        label="Autor (opcional)",
        placeholder="Ex: KRM Staff",
        required=False,
        max_length=256,
    )
    author_icon_input = discord.ui.TextInput(
        label="Icone do autor URL (opcional)",
        placeholder="https://...",
        required=False,
        max_length=300,
    )
    timestamp_input = discord.ui.TextInput(
        label="Timestamp (opcional)",
        placeholder="agora, vazio para remover, ou ISO 2026-04-16T18:30:00+00:00",
        required=False,
        max_length=60,
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Este comando so funciona em servidor.", ephemeral=True)
            return

        draft = await ensure_welcome_embed_draft(self.bot.pool, interaction.guild.id, interaction.user.id)
        if not draft:
            await interaction.response.send_message(
                "Configure o embed de boas-vindas primeiro na opcao principal.",
                ephemeral=True,
            )
            return
        payload = draft["payload"]

        payload["url"] = str(self.url_input.value).strip() if self.url_input.value else None
        payload["image_url"] = str(self.image_input.value).strip() if self.image_input.value else None
        payload["author_name"] = str(self.author_name_input.value).strip() if self.author_name_input.value else None
        payload["author_icon_url"] = str(self.author_icon_input.value).strip() if self.author_icon_input.value else None

        ts_raw = str(self.timestamp_input.value).strip() if self.timestamp_input.value else ""
        if not ts_raw:
            payload["timestamp"] = None
        elif ts_raw.lower() in {"agora", "now"}:
            payload["timestamp"] = datetime.now(timezone.utc).isoformat()
        else:
            payload["timestamp"] = ts_raw

        preview_embed = build_welcome_embed_from_payload(payload, interaction.user)
        if not preview_embed:
            await interaction.response.send_message(
                "Nao foi possivel aplicar os extras. Verifique os campos preenchidos.",
                ephemeral=True,
            )
            return

        apply_step_footer(preview_embed, 3, 4, "Ajuste fields/ordem e depois confirme")

        set_welcome_embed_draft(interaction.guild.id, interaction.user.id, draft["channel_id"], payload)
        await interaction.response.send_message(
            "Extras do embed atualizados no rascunho.",
            embed=preview_embed,
            ephemeral=True,
        )


class WelcomeEmbedFieldAddModal(discord.ui.Modal, title="Adicionar Field"):
    field_name_input = discord.ui.TextInput(
        label="Nome do field",
        placeholder="Ex: Regras",
        required=True,
        max_length=256,
    )
    field_value_input = discord.ui.TextInput(
        label="Valor do field",
        placeholder="Ex: Leia o canal #regras",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1024,
    )
    field_inline_input = discord.ui.TextInput(
        label="Inline? (sim/nao)",
        placeholder="sim",
        required=False,
        max_length=10,
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Este comando so funciona em servidor.", ephemeral=True)
            return

        draft = await ensure_welcome_embed_draft(self.bot.pool, interaction.guild.id, interaction.user.id)
        if not draft:
            await interaction.response.send_message(
                "Configure o embed de boas-vindas primeiro na opcao principal.",
                ephemeral=True,
            )
            return
        payload = draft["payload"]

        inline_raw = str(self.field_inline_input.value).strip().lower() if self.field_inline_input.value else "sim"
        inline = inline_raw not in {"nao", "não", "n", "false", "0"}

        fields = payload.get("fields", [])
        fields.append(
            {
                "name": str(self.field_name_input.value).strip(),
                "value": str(self.field_value_input.value).strip(),
                "inline": inline,
            }
        )
        payload["fields"] = fields

        validation_error = validate_welcome_embed_payload(payload)
        if validation_error:
            await interaction.response.send_message(validation_error, ephemeral=True)
            return

        preview_embed = build_welcome_embed_from_payload(payload, interaction.user)
        if not preview_embed:
            await interaction.response.send_message("Erro ao aplicar field no embed.", ephemeral=True)
            return

        apply_step_footer(preview_embed, 3, 4, "Continue editando fields ou confirme")

        set_welcome_embed_draft(interaction.guild.id, interaction.user.id, draft["channel_id"], payload)
        await interaction.response.send_message(
            f"Field adicionado no rascunho. Total de fields: {len(fields)}",
            embed=preview_embed,
            ephemeral=True,
        )


class WelcomeEmbedFieldEditModal(discord.ui.Modal, title="Editar Field"):
    index_input = discord.ui.TextInput(
        label="Numero do field (comeca em 1)",
        placeholder="1",
        required=True,
        max_length=4,
    )
    field_name_input = discord.ui.TextInput(
        label="Novo nome (opcional)",
        placeholder="Deixe vazio para manter",
        required=False,
        max_length=256,
    )
    field_value_input = discord.ui.TextInput(
        label="Novo valor (opcional)",
        placeholder="Deixe vazio para manter",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1024,
    )
    field_inline_input = discord.ui.TextInput(
        label="Inline? (sim/nao, opcional)",
        placeholder="Deixe vazio para manter",
        required=False,
        max_length=10,
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Este comando so funciona em servidor.", ephemeral=True)
            return

        draft = await ensure_welcome_embed_draft(self.bot.pool, interaction.guild.id, interaction.user.id)
        if not draft:
            await interaction.response.send_message(
                "Configure o embed de boas-vindas primeiro na opcao principal.",
                ephemeral=True,
            )
            return
        payload = draft["payload"]

        try:
            idx = int(str(self.index_input.value).strip()) - 1
        except ValueError:
            await interaction.response.send_message("Numero do field invalido.", ephemeral=True)
            return

        fields = payload.get("fields", [])
        if idx < 0 or idx >= len(fields):
            await interaction.response.send_message(
                f"Indice invalido. Atualmente existem {len(fields)} field(s).\n{list_embed_fields_text(fields)}",
                ephemeral=True,
            )
            return

        current = fields[idx]
        name_raw = str(self.field_name_input.value).strip() if self.field_name_input.value else ""
        value_raw = str(self.field_value_input.value).strip() if self.field_value_input.value else ""
        inline_raw = str(self.field_inline_input.value).strip().lower() if self.field_inline_input.value else ""

        if name_raw:
            current["name"] = name_raw
        if value_raw:
            current["value"] = value_raw
        if inline_raw:
            current["inline"] = inline_raw not in {"nao", "não", "n", "false", "0"}

        fields[idx] = current
        payload["fields"] = fields

        validation_error = validate_welcome_embed_payload(payload)
        if validation_error:
            await interaction.response.send_message(validation_error, ephemeral=True)
            return

        preview_embed = build_welcome_embed_from_payload(payload, interaction.user)
        if not preview_embed:
            await interaction.response.send_message("Erro ao editar field.", ephemeral=True)
            return

        apply_step_footer(preview_embed, 3, 4, "Continue ajustando fields ou confirme")

        set_welcome_embed_draft(interaction.guild.id, interaction.user.id, draft["channel_id"], payload)
        await interaction.response.send_message(
            f"Field #{idx + 1} atualizado no rascunho.",
            embed=preview_embed,
            ephemeral=True,
        )


class WelcomeEmbedFieldRemoveModal(discord.ui.Modal, title="Remover Field"):
    index_input = discord.ui.TextInput(
        label="Numero do field (comeca em 1)",
        placeholder="1",
        required=True,
        max_length=4,
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Este comando so funciona em servidor.", ephemeral=True)
            return

        draft = await ensure_welcome_embed_draft(self.bot.pool, interaction.guild.id, interaction.user.id)
        if not draft:
            await interaction.response.send_message(
                "Configure o embed de boas-vindas primeiro na opcao principal.",
                ephemeral=True,
            )
            return
        payload = draft["payload"]

        try:
            idx = int(str(self.index_input.value).strip()) - 1
        except ValueError:
            await interaction.response.send_message("Numero do field invalido.", ephemeral=True)
            return

        fields = payload.get("fields", [])
        if idx < 0 or idx >= len(fields):
            await interaction.response.send_message(
                f"Indice invalido. Atualmente existem {len(fields)} field(s).\n{list_embed_fields_text(fields)}",
                ephemeral=True,
            )
            return

        removed = fields.pop(idx)
        payload["fields"] = fields

        validation_error = validate_welcome_embed_payload(payload)
        if validation_error:
            await interaction.response.send_message(validation_error, ephemeral=True)
            return

        preview_embed = build_welcome_embed_from_payload(payload, interaction.user)
        if not preview_embed:
            await interaction.response.send_message("Erro ao remover field.", ephemeral=True)
            return

        apply_step_footer(preview_embed, 3, 4, "Continue ajustando fields ou confirme")

        set_welcome_embed_draft(interaction.guild.id, interaction.user.id, draft["channel_id"], payload)
        await interaction.response.send_message(
            f"Field removido no rascunho: {removed.get('name', 'sem nome')}",
            embed=preview_embed,
            ephemeral=True,
        )


class WelcomeEmbedFieldMoveModal(discord.ui.Modal, title="Mover Field"):
    index_input = discord.ui.TextInput(
        label="Numero do field (comeca em 1)",
        placeholder="1",
        required=True,
        max_length=4,
    )
    direction_input = discord.ui.TextInput(
        label="Direcao (up/down)",
        placeholder="up",
        required=True,
        max_length=6,
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Este comando so funciona em servidor.", ephemeral=True)
            return

        draft = await ensure_welcome_embed_draft(self.bot.pool, interaction.guild.id, interaction.user.id)
        if not draft:
            await interaction.response.send_message(
                "Configure o embed de boas-vindas primeiro na opcao principal.",
                ephemeral=True,
            )
            return
        payload = draft["payload"]

        fields = payload.get("fields", [])
        if not fields:
            await interaction.response.send_message("Nao ha fields para mover.", ephemeral=True)
            return

        try:
            idx = int(str(self.index_input.value).strip()) - 1
        except ValueError:
            await interaction.response.send_message("Numero do field invalido.", ephemeral=True)
            return

        if idx < 0 or idx >= len(fields):
            await interaction.response.send_message(
                f"Indice invalido. Atualmente existem {len(fields)} field(s).\n{list_embed_fields_text(fields)}",
                ephemeral=True,
            )
            return

        direction = str(self.direction_input.value).strip().lower()
        if direction not in {"up", "down", "cima", "baixo"}:
            await interaction.response.send_message("Direcao invalida. Use up/down.", ephemeral=True)
            return

        target = idx - 1 if direction in {"up", "cima"} else idx + 1
        if target < 0 or target >= len(fields):
            await interaction.response.send_message("Nao e possivel mover alem do limite.", ephemeral=True)
            return

        fields[idx], fields[target] = fields[target], fields[idx]
        payload["fields"] = fields

        preview_embed = build_welcome_embed_from_payload(payload, interaction.user)
        if not preview_embed:
            await interaction.response.send_message("Erro ao mover field.", ephemeral=True)
            return

        apply_step_footer(preview_embed, 3, 4, "Ordem atualizada, revise e confirme")

        set_welcome_embed_draft(interaction.guild.id, interaction.user.id, draft["channel_id"], payload)
        await interaction.response.send_message(
            "Field reordenado no rascunho.\n" + list_embed_fields_text(fields),
            embed=preview_embed,
            ephemeral=True,
        )


class WelcomeEmbedImportJsonModal(discord.ui.Modal, title="Importar JSON do Embed"):
    channel_id_input = discord.ui.TextInput(
        label="ID do Canal",
        placeholder="Canal para enviar boas-vindas",
        required=True,
        max_length=20,
    )
    json_input = discord.ui.TextInput(
        label="JSON do Embed",
        placeholder='{"title": "Bem-vindo", "description": "...", "color": "#5865F2", "fields": []}',
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=4000,
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

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
        if not channel:
            await interaction.response.send_message("Canal nao encontrado.", ephemeral=True)
            return

        try:
            payload = json.loads(str(self.json_input.value))
        except json.JSONDecodeError:
            await interaction.response.send_message("JSON invalido.", ephemeral=True)
            return

        validation_error = validate_welcome_embed_payload(payload)
        if validation_error:
            await interaction.response.send_message(validation_error, ephemeral=True)
            return

        preview_embed = build_welcome_embed_from_payload(payload, interaction.user)
        if not preview_embed:
            await interaction.response.send_message("Falha ao montar embed importado.", ephemeral=True)
            return

        apply_step_footer(preview_embed, 2, 4, "JSON carregado, ajuste e confirme")

        set_welcome_embed_draft(interaction.guild.id, interaction.user.id, channel_id, payload)
        await interaction.response.send_message(
            f"JSON importado para rascunho em {channel.mention}. Confirme para salvar.",
            embed=preview_embed,
            ephemeral=True,
        )

class ConfigureEmbed():
    @staticmethod
    def create(title: str, description: str) -> discord.Embed:
        embed = discord.Embed(title=title, description=description, color=discord.Color.blurple())
        embed.set_footer(text="Use o menu abaixo para configurar as mensagens de entrada e saída.")
        return embed

class CustomEmbed():
    def __init__(
        self,
        title: str,
        description: str,
        color: int,
        url: str = None,
        timestamp: str = None,
        thumbnail_url: str = None,
        image_url: str = None,
        author_name: str = None,
        author_icon_url: str = None,
        fields: list = None,
    ):
        self.title = title
        self.description = description
        self.color = color
        self.url = url
        self.timestamp = timestamp
        self.thumbnail_url = thumbnail_url
        self.image_url = image_url
        self.author_name = author_name
        self.author_icon_url = author_icon_url
        self.fields = fields if isinstance(fields, list) else []

    def add_field(self, name: str, value: str, inline: bool = True):
        if not name or not value:
            return self
        self.fields.append(
            {
                "name": str(name),
                "value": str(value),
                "inline": bool(inline),
            }
        )
        return self

    def add_fields(self, fields: list):
        if not isinstance(fields, list):
            return self
        for field in fields:
            if not isinstance(field, dict):
                continue
            self.add_field(
                field.get("name"),
                field.get("value"),
                field.get("inline", True),
            )
        return self

    def clear_fields(self):
        self.fields = []
        return self
    
    def create_embed(self):
        # Validacoes obrigatorias
        if not self.title or not str(self.title).strip():
            return "O Titulo e obrigatorio para criar o embed."
        if not self.description or not str(self.description).strip():
            return "A Descricao e obrigatoria para criar o embed."
        if self.color is None:
            return "A Cor e obrigatoria para criar o embed."

        # Aceita int direto ou string hexadecimal (#FFAA00 / FFAA00 / 0xFFAA00)
        parsed_color = self.color
        if isinstance(self.color, str):
            cleaned = self.color.strip().lower().replace("#", "")
            if cleaned.startswith("0x"):
                cleaned = cleaned[2:]
            if len(cleaned) != 6:
                return "Cor invalida. Use hexadecimal com 6 digitos, por exemplo: #FFAA00."
            try:
                parsed_color = int(cleaned, 16)
            except ValueError:
                return "Cor invalida. Use hexadecimal com 6 digitos, por exemplo: #FFAA00."

        # Timestamp pode vir como datetime, ISO string ou None
        parsed_timestamp = None
        if self.timestamp:
            if hasattr(self.timestamp, "tzinfo"):
                parsed_timestamp = self.timestamp
            elif isinstance(self.timestamp, str):
                raw_ts = self.timestamp.strip()
                if raw_ts:
                    try:
                        parsed_timestamp = discord.utils.parse_time(raw_ts)
                    except Exception:
                        parsed_timestamp = None

        embed = discord.Embed(
            title=str(self.title).strip(),
            description=str(self.description).strip(),
            color=parsed_color,
            url=self.url if self.url else None,
            timestamp=parsed_timestamp,
        )

        if self.thumbnail_url:
            embed.set_thumbnail(url=self.thumbnail_url)

        if self.image_url:
            embed.set_image(url=self.image_url)

        if self.author_name:
            embed.set_author(name=self.author_name, icon_url=self.author_icon_url)

        if isinstance(self.fields, list):
            for field in self.fields:
                if not isinstance(field, dict):
                    continue
                name = field.get("name")
                value = field.get("value")
                if name is None or value is None:
                    continue
                embed.add_field(
                    name=str(name),
                    value=str(value),
                    inline=bool(field.get("inline", True)),
                )

        return embed

class EmbedBuilder():
    # la vamos nós... 1 milhão de modais em uma função...
    pass

class SetupSelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot):
        options = [
            discord.SelectOption(
                label="Configurar Boas-Vindas",
                description="Define canal e mensagem de entrada.",
                value="welcome",
                emoji="👋",
            ),
            discord.SelectOption(
                label="Configurar Boas-Vindas (Embed)",
                description="Define canal e mensagem de entrada em embed.",
                value="welcome_embed",
                emoji="✨",
            ),
            discord.SelectOption(
                label="Editar Extras do Embed",
                description="URL, imagem, autor e timestamp.",
                value="welcome_embed_extras",
                emoji="🛠️",
            ),
            discord.SelectOption(
                label="Adicionar Field no Embed",
                description="Adiciona um field personalizado.",
                value="welcome_embed_field_add",
                emoji="➕",
            ),
            discord.SelectOption(
                label="Editar Field do Embed",
                description="Edita um field especifico por numero.",
                value="welcome_embed_field_edit",
                emoji="✏️",
            ),
            discord.SelectOption(
                label="Mover Field do Embed",
                description="Move um field para cima/baixo.",
                value="welcome_embed_field_move",
                emoji="↕️",
            ),
            discord.SelectOption(
                label="Remover Field do Embed",
                description="Remove um field especifico por numero.",
                value="welcome_embed_field_remove",
                emoji="🗑️",
            ),
            discord.SelectOption(
                label="Listar Fields do Embed",
                description="Mostra fields atuais com indice.",
                value="welcome_embed_field_list",
                emoji="📑",
            ),
            discord.SelectOption(
                label="Exportar JSON do Embed",
                description="Exporta o embed salvo/rascunho em arquivo.",
                value="welcome_embed_export_json",
                emoji="📤",
            ),
            discord.SelectOption(
                label="Importar JSON (Texto)",
                description="Importa JSON para rascunho via modal.",
                value="welcome_embed_import_json",
                emoji="📥",
            ),
            discord.SelectOption(
                label="Restaurar Versao Anterior",
                description="Restaura o ultimo embed confirmado.",
                value="welcome_embed_restore_previous",
                emoji="🕘",
            ),
            discord.SelectOption(
                label="Confirmar Embed de Boas-Vindas",
                description="Salva o rascunho atual no banco.",
                value="welcome_embed_confirm",
                emoji="✅",
            ),
            discord.SelectOption(
                label="Cancelar Edicao do Embed",
                description="Descarta o rascunho atual.",
                value="welcome_embed_cancel",
                emoji="❌",
            ),
            discord.SelectOption(
                label="Resetar Embed de Boas-Vindas",
                description="Remove embed salvo e rascunho.",
                value="welcome_embed_reset",
                emoji="♻️",
            ),
            discord.SelectOption(
                label="Simular Entrada (Embed)",
                description="Envia no canal como no evento real.",
                value="welcome_embed_simulate",
                emoji="🎭",
            ),
            discord.SelectOption(
                label="Configurar Saida",
                description="Define canal e mensagem de saida.",
                value="exit",
                emoji="🚪",
            ),
            discord.SelectOption(
                label="Testar Boas-Vindas",
                description="Envia mensagem de teste no canal configurado.",
                value="test_welcome",
                emoji="🧪",
            ),
            discord.SelectOption(
                label="Testar Saida",
                description="Envia mensagem de teste no canal configurado.",
                value="test_exit",
                emoji="🧪",
            ),
            discord.SelectOption(
                label="Ver Configuracao",
                description="Mostra as configuracoes atuais.",
                value="view",
                emoji="📋",
            ),
            discord.SelectOption(
                label="Remover Boas-Vindas",
                description="Remove a configuracao de entrada.",
                value="remove_welcome",
                emoji="🗑️",
            ),
            discord.SelectOption(
                label="Remover Saida",
                description="Remove a configuracao de saida.",
                value="remove_exit",
                emoji="🗑️",
            ),
        ]
        super().__init__(placeholder="Escolha uma opcao...", options=options)
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Este menu so funciona em servidor.", ephemeral=True)
            return

        choice = self.values[0]
        pool = self.bot.pool

        if choice == "welcome":
            await interaction.response.send_modal(WelcomeModal(self.bot)) # Mudar isso para o callback do Embed Customizavel de entrada
            return

        if choice == "welcome_embed":
            await interaction.response.send_modal(WelcomeEmbedModal(self.bot))
            return

        if choice == "welcome_embed_extras":
            await interaction.response.send_modal(WelcomeEmbedExtrasModal(self.bot))
            return

        if choice == "welcome_embed_field_add":
            await interaction.response.send_modal(WelcomeEmbedFieldAddModal(self.bot))
            return

        if choice == "welcome_embed_field_edit":
            await interaction.response.send_modal(WelcomeEmbedFieldEditModal(self.bot))
            return

        if choice == "welcome_embed_field_move":
            await interaction.response.send_modal(WelcomeEmbedFieldMoveModal(self.bot))
            return

        if choice == "welcome_embed_field_remove":
            await interaction.response.send_modal(WelcomeEmbedFieldRemoveModal(self.bot))
            return

        if choice == "welcome_embed_field_list":
            draft = await ensure_welcome_embed_draft(self.bot.pool, interaction.guild.id, interaction.user.id)
            if not draft:
                await interaction.response.send_message(
                    "Sem rascunho no momento. Configure ou importe um embed primeiro.",
                    ephemeral=True,
                )
                return
            fields_text = list_embed_fields_text(draft["payload"].get("fields", []))
            await interaction.response.send_message(
                "Fields atuais do rascunho:\n" + fields_text,
                ephemeral=True,
            )
            return

        if choice == "welcome_embed_export_json":
            draft = get_welcome_embed_draft(interaction.guild.id, interaction.user.id)
            if draft:
                channel_id = draft.get("channel_id")
                payload = draft.get("payload")
                source = "rascunho"
            else:
                channel_id, payload = await get_saved_welcome_embed_state(self.bot.pool, interaction.guild.id)
                source = "salvo"

            if not payload:
                await interaction.response.send_message("Nenhum embed para exportar.", ephemeral=True)
                return

            data = {
                "channel_id": channel_id,
                "payload": payload,
                "source": source,
            }
            content = json.dumps(data, ensure_ascii=False, indent=2)
            file = discord.File(io.BytesIO(content.encode("utf-8")), filename="welcome_embed_export.json")
            await interaction.response.send_message(
                f"Exportacao concluida ({source}).",
                ephemeral=True,
                file=file,
            )
            return

        if choice == "welcome_embed_import_json":
            await interaction.response.send_modal(WelcomeEmbedImportJsonModal(self.bot))
            return

        if choice == "welcome_embed_restore_previous":
            prev_channel_id, prev_payload = await get_previous_welcome_embed_state(self.bot.pool, interaction.guild.id)
            if not prev_payload or not prev_channel_id:
                await interaction.response.send_message(
                    "Nao existe versao anterior registrada ainda.",
                    ephemeral=True,
                )
                return

            prev_payload = normalize_import_payload(prev_payload)
            validation_error = validate_welcome_embed_payload(prev_payload)
            if validation_error:
                await interaction.response.send_message(
                    "A versao anterior esta invalida: " + validation_error,
                    ephemeral=True,
                )
                return

            set_welcome_embed_draft(
                interaction.guild.id,
                interaction.user.id,
                prev_channel_id,
                prev_payload,
            )

            preview_embed = build_welcome_embed_from_payload(prev_payload, interaction.user)
            if not preview_embed:
                await interaction.response.send_message("Falha ao carregar versao anterior.", ephemeral=True)
                return
            apply_step_footer(preview_embed, 2, 4, "Versao anterior carregada, ajuste e confirme")

            await interaction.response.send_message(
                "Versao anterior carregada no rascunho. Confirme para salvar.",
                embed=preview_embed,
                ephemeral=True,
            )
            return

        if choice == "welcome_embed_confirm":
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
                await interaction.response.send_message("Falha ao montar embed de confirmacao.", ephemeral=True)
                return
            apply_step_footer(preview_embed, 4, 4, "Concluido")

            await save_welcome_embed_payload(
                self.bot.pool,
                interaction.guild.id,
                draft["channel_id"],
                payload,
            )
            clear_welcome_embed_draft(interaction.guild.id, interaction.user.id)
            await interaction.response.send_message(
                f"Embed de boas-vindas salvo com sucesso em {channel.mention}.",
                embed=preview_embed,
                ephemeral=True,
            )
            return

        if choice == "welcome_embed_cancel":
            clear_welcome_embed_draft(interaction.guild.id, interaction.user.id)
            await interaction.response.send_message("Rascunho de embed descartado.", ephemeral=True)
            return

        if choice == "welcome_embed_reset":
            clear_welcome_embed_draft(interaction.guild.id, interaction.user.id)
            await pool.execute(
                "UPDATE guild_settings SET welcome_embed = NULL WHERE guild_id = $1",
                interaction.guild.id,
            )
            await interaction.response.send_message("Embed de boas-vindas resetado.", ephemeral=True)
            return

        if choice == "welcome_embed_simulate":
            draft = get_welcome_embed_draft(interaction.guild.id, interaction.user.id)
            if draft:
                channel = interaction.guild.get_channel(draft["channel_id"])
                payload = draft["payload"]
            else:
                row = await pool.fetchrow(
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
                await interaction.response.send_message(
                    "Nao foi possivel simular: embed invalido ou incompleto.",
                    ephemeral=True,
                )
                return

            await channel.send(embed=simulated_embed)
            await interaction.response.send_message(f"Simulacao enviada em {channel.mention}.", ephemeral=True)
            return

        if choice == "exit":
            await interaction.response.send_modal(ExitModal(self.bot))
            return

        if choice == "test_welcome":
            draft = get_welcome_embed_draft(interaction.guild.id, interaction.user.id)
            row = None
            if draft:
                channel = interaction.guild.get_channel(draft["channel_id"])
                welcome_payload = draft["payload"]
                welcome_message = None
            else:
                row = await pool.fetchrow(
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
            await interaction.response.send_message(f"Teste enviado em {channel.mention}!", ephemeral=True)
            return

        if choice == "test_exit":
            row = await pool.fetchrow(
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
            await interaction.response.send_message(f"Teste enviado em {channel.mention}!", ephemeral=True)
            return

        if choice == "view":
            draft = get_welcome_embed_draft(interaction.guild.id, interaction.user.id)
            row = await pool.fetchrow(
                "SELECT welcome_channel_id, welcome_message, welcome_embed, exit_channel_id, exit_message FROM guild_settings WHERE guild_id = $1",
                interaction.guild.id,
            )
            embed = discord.Embed(title="Configuracao Atual", color=discord.Color.blurple())
            if row:
                welcome_channel = f"<#{row['welcome_channel_id']}>" if row["welcome_channel_id"] else "Nao configurado"
                welcome_message = row["welcome_message"] if row["welcome_message"] else "Nao configurado"
                welcome_embed = "Configurado" if row["welcome_embed"] else "Nao configurado"
                welcome_embed_fields = len(row["welcome_embed"].get("fields", [])) if row["welcome_embed"] else 0
                welcome_embed_color = row["welcome_embed"].get("color", "Nao definido") if row["welcome_embed"] else "Nao definido"
                exit_channel = f"<#{row['exit_channel_id']}>" if row["exit_channel_id"] else "Nao configurado"
                exit_message = row["exit_message"] if row["exit_message"] else "Nao configurado"
            else:
                welcome_channel = "Nao configurado"
                welcome_message = "Nao configurado"
                welcome_embed = "Nao configurado"
                welcome_embed_fields = 0
                welcome_embed_color = "Nao definido"
                exit_channel = "Nao configurado"
                exit_message = "Nao configurado"

            draft_status = "Nao"
            draft_channel = "-"
            if draft:
                draft_status = "Sim"
                draft_channel = f"<#{draft['channel_id']}>" if draft.get("channel_id") else "Nao definido"

            embed.add_field(name="👋 Canal de Boas-Vindas", value=welcome_channel, inline=True)
            embed.add_field(name="Mensagem", value=welcome_message, inline=False)
            embed.add_field(name="✨ Embed de Boas-Vindas", value=welcome_embed, inline=False)
            embed.add_field(name="🎨 Cor Atual", value=str(welcome_embed_color), inline=True)
            embed.add_field(name="🧩 Fields do Embed", value=str(welcome_embed_fields), inline=True)
            embed.add_field(
                name="📑 Lista de Fields",
                value=list_embed_fields_text((draft["payload"].get("fields", []) if draft else (row["welcome_embed"].get("fields", []) if row and row["welcome_embed"] else [])))[:1024],
                inline=False,
            )
            embed.add_field(name="📝 Rascunho em Edicao", value=draft_status, inline=True)
            embed.add_field(name="📍 Canal do Rascunho", value=draft_channel, inline=True)
            embed.add_field(name="🚪 Canal de Saida", value=exit_channel, inline=True)
            embed.add_field(name="Mensagem", value=exit_message, inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if choice == "remove_welcome":
            await pool.execute(
                "UPDATE guild_settings SET welcome_channel_id = NULL, welcome_message = NULL, welcome_embed = NULL WHERE guild_id = $1",
                interaction.guild.id,
            )
            await interaction.response.send_message("Configuracao de boas-vindas removida.", ephemeral=True)
            return

        if choice == "remove_exit":
            await pool.execute(
                "UPDATE guild_settings SET exit_channel_id = NULL, exit_message = NULL WHERE guild_id = $1",
                interaction.guild.id,
            )
            await interaction.response.send_message("Configuracao de saida removida.", ephemeral=True)


class SetupView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=120)
        self.add_item(SetupSelect(bot))



class Entry(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── Eventos ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member):
        row = await self.bot.pool.fetchrow(
            "SELECT welcome_channel_id, welcome_message, welcome_embed FROM guild_settings WHERE guild_id = $1",
            member.guild.id,
        )
        if row and row["welcome_channel_id"]:
            channel = member.guild.get_channel(row["welcome_channel_id"])
            if channel:
                welcome_embed = build_welcome_embed_from_payload(row["welcome_embed"], member)
                if welcome_embed:
                    await channel.send(embed=welcome_embed)
                elif row["welcome_message"]:
                    text = render_template_text(row["welcome_message"], member)
                    await channel.send(text or "")

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

async def setup(bot):
    await bot.add_cog(Entry(bot))

