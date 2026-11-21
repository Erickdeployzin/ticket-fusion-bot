"""Cog responsável pelo comando principal /painel."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from src.bot.ui.embeds import error_embed
from src.bot.views.admin.navigation import open_admin_section

if TYPE_CHECKING:
    from src.bot.client import FusionBot


class AdminCog(commands.Cog):
    """Comandos administrativos principais do servidor."""

    def __init__(self, bot: FusionBot) -> None:
        self.bot = bot

    @app_commands.command(
        name="painel",
        description="Abre o painel administrativo completo do servidor.",
    )
    @app_commands.guild_only()
    async def painel_command(self, interaction: discord.Interaction) -> None:
        """Ponto de entrada único para 100% das configurações do bot via Discord."""
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                embed=error_embed(
                    "Contexto Inválido",
                    "Este comando só pode ser utilizado dentro de um servidor Discord.",
                ),
                ephemeral=True,
            )
            return

        settings = await self.bot.guild_service.get_settings(interaction.guild.id)
        accessible = self.bot.permissions.get_accessible_modules(interaction.user, settings)

        if not accessible:
            await interaction.response.send_message(
                embed=error_embed(
                    "Acesso Restrito",
                    "Você não possui permissão para acessar nenhum módulo administrativo deste bot.\n"
                    "Solicite autorização a um administrador do servidor.",
                ),
                ephemeral=True,
            )
            return

        await open_admin_section(self.bot, interaction, "overview", send_new=True)


async def setup(bot: FusionBot) -> None:
    await bot.add_cog(AdminCog(bot))