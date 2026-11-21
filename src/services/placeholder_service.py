"""Motor extensível de variáveis dinâmicas e construção de Embeds do Discord."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord

from src.database.schemas import EmbedConfigSchema


@dataclass(frozen=True)
class PlaceholderContext:
    """Contexto de dados reais para resolução de placeholders em textos e embeds."""

    guild: discord.Guild
    user: discord.abc.User | None = None
    timezone: str = "America/Sao_Paulo"
    extra: dict[str, str] | None = None


PlaceholderResolver = Callable[[PlaceholderContext], str]


class PlaceholderService:
    """Resolve variáveis dinâmicas ({user}, {server}, etc.) e constrói Embeds."""

    _TOKEN_PATTERN = re.compile(r"\{([a-zA-Z0-9_]+)\}")

    def __init__(self) -> None:
        self._resolvers: dict[str, PlaceholderResolver] = {}
        self._register_defaults()

    def register(self, key: str, resolver: PlaceholderResolver) -> None:
        """Registra uma nova variável dinâmica personalizada."""
        self._resolvers[key.strip().lower()] = resolver

    def _get_local_now(self, tz_name: str) -> datetime:
        try:
            return datetime.now(ZoneInfo(tz_name))
        except ZoneInfoNotFoundError:
            return datetime.now(UTC)

    def _register_defaults(self) -> None:
        self.register("user", lambda ctx: ctx.user.mention if ctx.user else "@usuário")
        self.register("username", lambda ctx: ctx.user.display_name if ctx.user else "Usuário")
        self.register("user_id", lambda ctx: str(ctx.user.id) if ctx.user else "0")
        self.register("server", lambda ctx: ctx.guild.name)
        self.register("server_name", lambda ctx: ctx.guild.name)
        self.register(
            "member_count",
            lambda ctx: f"{ctx.guild.member_count or len(ctx.guild.members):,}",
        )
        self.register(
            "date",
            lambda ctx: self._get_local_now(ctx.timezone).strftime("%d/%m/%Y"),
        )
        self.register(
            "time",
            lambda ctx: self._get_local_now(ctx.timezone).strftime("%H:%M"),
        )
        self.register(
            "created_at",
            lambda ctx: (
                ctx.user.created_at.strftime("%d/%m/%Y")
                if ctx.user is not None
                else self._get_local_now(ctx.timezone).strftime("%d/%m/%Y")
            ),
        )

    def render(self, text: str | None, ctx: PlaceholderContext) -> str | None:
        """Substitui placeholders conhecidos mantendo tokens desconhecidos intactos."""
        if text is None:
            return None

        extra_lower = {k.lower(): v for k, v in (ctx.extra or {}).items()}

        def _replace(match: re.Match[str]) -> str:
            token = match.group(1).lower()
            if token in extra_lower:
                return extra_lower[token]
            resolver = self._resolvers.get(token)
            if resolver is not None:
                return resolver(ctx)
            return match.group(0)

        return self._TOKEN_PATTERN.sub(_replace, text)

    def build_embed(
        self,
        config: EmbedConfigSchema,
        ctx: PlaceholderContext,
        *,
        fallback_footer: str | None = None,
    ) -> discord.Embed:
        """Constrói uma discord.Embed validada com placeholders resolvidos."""
        title = self.render(config.title, ctx)
        description = self.render(config.description, ctx)

        embed = discord.Embed(
            title=title[:256] if title else None,
            description=description[:4096] if description else None,
            color=config.color,
            url=config.url or None,
            timestamp=datetime.now(UTC) if config.timestamp else None,
        )

        if config.author_name:
            author_name = self.render(config.author_name, ctx) or config.author_name
            embed.set_author(
                name=author_name[:256],
                icon_url=config.author_icon_url or None,
            )

        if config.thumbnail_url:
            embed.set_thumbnail(url=config.thumbnail_url)

        if config.image_url:
            embed.set_image(url=config.image_url)

        footer_raw = config.footer_text or fallback_footer
        if footer_raw:
            footer_rendered = self.render(footer_raw, ctx) or footer_raw
            embed.set_footer(
                text=footer_rendered[:2048],
                icon_url=config.footer_icon_url or None,
            )

        for field in config.fields[:25]:
            f_name = self.render(field.name, ctx) or field.name
            f_val = self.render(field.value, ctx) or field.value
            embed.add_field(
                name=f_name[:256],
                value=f_val[:1024],
                inline=field.inline,
            )

        return embed