"""Fábrica padronizada de embeds minimalistas para feedback e painéis."""

from __future__ import annotations

import discord

from src.bot.ui.theme import Theme
from src.database.schemas import GuildSettingsSchema


def create_panel_embed(
    *,
    title: str,
    description: str,
    settings: GuildSettingsSchema | None = None,
    color: int | None = None,
) -> discord.Embed:
    """Cria uma embed limpa respeitando a identidade visual do servidor."""
    resolved_color = color if color is not None else (
        settings.brand_color if settings else Theme.PRIMARY
    )
    footer = settings.brand_footer if settings else "Fusion • Gestão Profissional"

    embed = discord.Embed(
        title=title,
        description=description,
        color=resolved_color,
    )
    embed.set_footer(text=footer)
    return embed


def success_embed(title: str, description: str) -> discord.Embed:
    """Embed objetiva de confirmação de operação."""
    return discord.Embed(
        title=f"✅ {title}",
        description=description,
        color=Theme.SUCCESS,
    )


def error_embed(title: str, description: str) -> discord.Embed:
    """Embed objetiva de erro controlado ou permissão negada."""
    return discord.Embed(
        title=f"⚠️ {title}",
        description=description,
        color=Theme.DANGER,
    )


def warning_embed(title: str, description: str) -> discord.Embed:
    """Embed de alerta para confirmação de ações destrutivas."""
    return discord.Embed(
        title=f"⚡ {title}",
        description=description,
        color=Theme.WARNING,
    )