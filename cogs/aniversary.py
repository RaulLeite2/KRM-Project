import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime


MONTH_OPTIONS = [
    (1, "Janeiro"),
    (2, "Fevereiro"),
    (3, "Marco"),
    (4, "Abril"),
    (5, "Maio"),
    (6, "Junho"),
    (7, "Julho"),
    (8, "Agosto"),
    (9, "Setembro"),
    (10, "Outubro"),
    (11, "Novembro"),
    (12, "Dezembro"),
]


def parse_hex_color(value: str | None) -> int | None:
    if not value:
        return None
    cleaned = value.strip().replace("#", "")
    if len(cleaned) != 6:
        return None
    try:
        return int(cleaned, 16)
    except ValueError:
        return None


def parse_day_month(text: str) -> tuple[int, int] | None:
    raw = text.strip().replace("-", "/")
    if "/" not in raw:
        return None
    parts = raw.split("/")
    if len(parts) != 2:
        return None

    try:
        day = int(parts[0])
        month = int(parts[1])
    except ValueError:
        return None

    if month < 1 or month > 12:
        return None

    try:
        datetime(2000, month, day)
    except ValueError:
        return None

    return day, month


class BirthdayRepository:
    def __init__(self, pool):
        self.pool = pool

    async def set_birthday(self, guild_id: int, user_id: int, day: int, month: int) -> None:
        await self.pool.execute(
            """
            INSERT INTO user_birthdays (guild_id, user_id, day, month)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (guild_id, user_id) DO UPDATE SET
                day = EXCLUDED.day,
                month = EXCLUDED.month,
                updated_at = NOW()
            """,
            guild_id,
            user_id,
            day,
            month,
        )

    async def get_birthday(self, guild_id: int, user_id: int):
        return await self.pool.fetchrow(
            "SELECT day, month FROM user_birthdays WHERE guild_id = $1 AND user_id = $2",
            guild_id,
            user_id,
        )

    async def remove_birthday(self, guild_id: int, user_id: int) -> str:
        return await self.pool.execute(
            "DELETE FROM user_birthdays WHERE guild_id = $1 AND user_id = $2",
            guild_id,
            user_id,
        )

    async def list_birthdays_by_month(self, guild_id: int, month: int):
        return await self.pool.fetch(
            """
            SELECT user_id, day
            FROM user_birthdays
            WHERE guild_id = $1 AND month = $2
            ORDER BY day ASC, user_id ASC
            LIMIT 50
            """,
            guild_id,
            month,
        )

    async def set_birthday_channel(self, guild_id: int, channel_id: int) -> None:
        await self.pool.execute(
            """
            INSERT INTO birthday_settings (guild_id, channel_id)
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO UPDATE SET
                channel_id = EXCLUDED.channel_id,
                updated_at = NOW()
            """,
            guild_id,
            channel_id,
        )

    async def get_birthday_channel(self, guild_id: int) -> int | None:
        row = await self.pool.fetchrow(
            "SELECT channel_id FROM birthday_settings WHERE guild_id = $1",
            guild_id,
        )
        return row["channel_id"] if row else None

    async def save_panel(self, guild_id: int, channel_id: int, message_id: int) -> None:
        await self.pool.execute(
            """
            INSERT INTO birthday_panels (guild_id, channel_id, message_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (message_id) DO NOTHING
            """,
            guild_id,
            channel_id,
            message_id,
        )

    async def get_all_panels(self):
        return await self.pool.fetch(
            "SELECT guild_id, channel_id, message_id FROM birthday_panels"
        )

    async def remove_panel(self, message_id: int) -> None:
        await self.pool.execute(
            "DELETE FROM birthday_panels WHERE message_id = $1",
            message_id,
        )


class BirthdayEmbedBuilder:
    def __init__(
        self,
        *,
        title: str,
        description: str,
        color: int | None = None,
        footer: str | None = None,
        thumbnail_url: str | None = None,
        image_url: str | None = None,
        author_name: str | None = None,
        author_icon_url: str | None = None,
        url: str | None = None,
        use_timestamp: bool = False,
    ):
        self.title = title
        self.description = description
        self.color = color
        self.footer = footer
        self.thumbnail_url = thumbnail_url
        self.image_url = image_url
        self.author_name = author_name
        self.author_icon_url = author_icon_url
        self.url = url
        self.use_timestamp = use_timestamp

    def build(self) -> discord.Embed:
        embed = discord.Embed(
            title=self.title,
            description=self.description,
            color=discord.Color(self.color) if self.color is not None else discord.Color.blurple(),
            url=self.url,
            timestamp=datetime.utcnow() if self.use_timestamp else None,
        )

        if self.footer:
            embed.set_footer(text=self.footer)
        if self.thumbnail_url:
            embed.set_thumbnail(url=self.thumbnail_url)
        if self.image_url:
            embed.set_image(url=self.image_url)
        if self.author_name:
            embed.set_author(name=self.author_name, icon_url=self.author_icon_url)

        return embed


class AddBirthdayModal(discord.ui.Modal, title="Adicionar Data"):
    birthday_input = discord.ui.TextInput(
        label="Data de aniversario",
        placeholder="Use DD/MM, exemplo: 22/10",
        required=True,
        max_length=5,
    )

    def __init__(self, repo: BirthdayRepository):
        super().__init__(timeout=300)
        self.repo = repo

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Este comando so funciona em servidor.", ephemeral=True)
            return

        parsed = parse_day_month(str(self.birthday_input.value))
        if not parsed:
            await interaction.response.send_message(
                "Data invalida. Use o formato DD/MM com uma data valida.",
                ephemeral=True,
            )
            return

        day, month = parsed
        await self.repo.set_birthday(interaction.guild.id, interaction.user.id, day, month)
        await interaction.response.send_message(
            f"Sua data foi salva como {day:02d}/{month:02d}.",
            ephemeral=True,
        )


class BirthdaySelect(discord.ui.Select):
    def __init__(self, repo: BirthdayRepository):
        options = [
            discord.SelectOption(label=label, value=f"month:{month}")
            for month, label in MONTH_OPTIONS
        ]
        options.extend(
            [
                discord.SelectOption(label="Adicionar Data", value="action:add", emoji="➕"),
                discord.SelectOption(label="Remover Data", value="action:remove", emoji="🗑️"),
                discord.SelectOption(label="Ver Data", value="action:view", emoji="📅"),
            ]
        )
        super().__init__(
            custom_id="birthday_select",
            placeholder="Escolha um mes ou uma acao...",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.repo = repo

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Este menu so funciona em servidor.", ephemeral=True)
            return

        choice = self.values[0]

        if choice == "action:add":
            await interaction.response.send_modal(AddBirthdayModal(self.repo))
            return

        if choice == "action:view":
            row = await self.repo.get_birthday(interaction.guild.id, interaction.user.id)
            if not row:
                await interaction.response.send_message(
                    "Voce ainda nao cadastrou sua data de aniversario.",
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(
                f"Sua data cadastrada e {row['day']:02d}/{row['month']:02d}.",
                ephemeral=True,
            )
            return

        if choice == "action:remove":
            result = await self.repo.remove_birthday(interaction.guild.id, interaction.user.id)
            if result.endswith("0"):
                message = "Nenhuma data cadastrada para remover."
            else:
                message = "Sua data de aniversario foi removida com sucesso."
            await interaction.response.send_message(message, ephemeral=True)
            return

        month = int(choice.split(":", 1)[1])
        rows = await self.repo.list_birthdays_by_month(interaction.guild.id, month)
        month_name = MONTH_OPTIONS[month - 1][1]
        if not rows:
            await interaction.response.send_message(
                f"Nao ha aniversarios cadastrados para {month_name}.",
                ephemeral=True,
            )
            return

        lines = [f"<@{row['user_id']}> - {row['day']:02d}/{month:02d}" for row in rows]
        content = "\n".join(lines)
        await interaction.response.send_message(
            f"Aniversarios de {month_name}:\n{content}",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions(users=False),
        )


class BirthdayView(discord.ui.View):
    def __init__(self, repo: BirthdayRepository):
        super().__init__(timeout=None)
        self.add_item(BirthdaySelect(repo))

class Aniversary(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        repo = BirthdayRepository(self.bot.pool)
        panels = await repo.get_all_panels()
        for panel in panels:
            self.bot.add_view(
                BirthdayView(repo),
                message_id=panel["message_id"],
            )
        print(f"[VIEWS] {len(panels)} painel(is) de aniversario restaurado(s).")
    
async def setup(bot):
    await bot.add_cog(Aniversary(bot))