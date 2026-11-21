"""Modals administrativos para edição de identidade visual e configurações gerais."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import discord

from src.bot.ui.embeds import error_embed
from src.core.exceptions import FusionBotError
from src.database.schemas import GuildSettingsSchema

if TYPE_CHECKING:
    from src.bot.client import FusionBot


class BrandingModal(discord.ui.Modal, title="Personalizar Identidade Visual"):
    """Modal para configurar cor principal (HEX) e texto de rodapé do servidor."""

    brand_color = discord.ui.TextInput(
        label="Cor Principal (Hexadecimal)",
        placeholder="Ex: #5865F2 ou 10B981",
        min_length=6,
        max_length=7,
        required=True,
    )

    brand_footer = discord.ui.TextInput(
        label="Rodapé Padrão das Embeds",
        placeholder="Ex: Minha Comunidade • Suporte Oficial",
        min_length=2,
        max_length=120,
        required=True,
    )

    def __init__(
        self,
        bot: FusionBot,
        settings: GuildSettingsSchema,
        on_success: Callable[[discord.Interaction], Awaitable[None]],
    ) -> None:
        super().__init__()
        self._bot = bot
        self._on_success = on_success
        self.brand_color.default = f"#{settings.brand_color:06X}"
        self.brand_footer.default = settings.brand_footer

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        try:
            await self._bot.guild_service.update_branding(
                interaction.guild.id,
                interaction.user.id,
                brand_color_hex=self.brand_color.value,
                brand_footer=self.brand_footer.value,
            )
            await self._on_success(interaction)
        except FusionBotError as exc:
            await interaction.response.send_message(
                embed=error_embed("Dados Inválidos", exc.user_message),
                ephemeral=True,
            )


class GeneralSettingsModal(discord.ui.Modal, title="Configurações Gerais do Servidor"):
    """Modal para configurar fuso horário IANA e idioma padrão."""

    timezone_input = discord.ui.TextInput(
        label="Fuso Horário (Padrão IANA)",
        placeholder="Ex: America/Sao_Paulo, Europe/Lisbon, UTC",
        min_length=3,
        max_length=64,
        required=True,
    )

    language_input = discord.ui.TextInput(
        label="Idioma do Servidor",
        placeholder="Ex: pt-BR",
        min_length=2,
        max_length=16,
        required=True,
    )

    def __init__(
        self,
        bot: FusionBot,
        settings: GuildSettingsSchema,
        on_success: Callable[[discord.Interaction], Awaitable[None]],
    ) -> None:
        super().__init__()
        self._bot = bot
        self._on_success = on_success
        self.timezone_input.default = settings.timezone
        self.language_input.default = settings.language

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        try:
            await self._bot.guild_service.update_general_settings(
                interaction.guild.id,
                interaction.user.id,
                timezone=self.timezone_input.value,
                language=self.language_input.value,
            )
            await self._on_success(interaction)
        except FusionBotError as exc:
            await interaction.response.send_message(
                embed=error_embed("Configuração Inválida", exc.user_message),
                ephemeral=True,
            )