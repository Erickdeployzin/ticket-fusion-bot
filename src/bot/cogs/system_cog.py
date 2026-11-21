"""Cog de eventos globais do sistema, ciclo de vida de guilds e tratamento de erros."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from src.bot.ui.embeds import error_embed
from src.core.exceptions import FusionBotError
from src.core.logger import get_logger

if TYPE_CHECKING:
    from src.bot.client import FusionBot

logger = get_logger(__name__)


class SystemCog(commands.Cog):
    """Gerencia eventos de infraestrutura e erros globais de Slash Commands."""

    def __init__(self, bot: FusionBot) -> None:
        self.bot = bot
        self._old_tree_error = bot.tree.on_error
        bot.tree.on_error = self.on_app_command_error  # type: ignore[method-assign]

    async def cog_unload(self) -> None:
        self.bot.tree.on_error = self._old_tree_error  # type: ignore[method-assign]

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Inicializa automaticamente as configurações padrão ao entrar em um servidor."""
        await self.bot.guild_service.get_settings(guild.id)
        logger.info(
            "Bot adicionado ao servidor '%s' (ID: %s | Membros: %s)",
            guild.name,
            guild.id,
            guild.member_count,
        )

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        logger.info("Bot removido do servidor '%s' (ID: %s)", guild.name, guild.id)

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Intercepta falhas em Slash Commands e responde com feedback limpo e auditável."""
        original = getattr(error, "original", error)

        if isinstance(original, FusionBotError):
            embed = error_embed("Operação Não Permitida", original.user_message)
        elif isinstance(error, app_commands.CommandOnCooldown):
            embed = error_embed(
                "Aguarde um Instante",
                f"Você poderá executar este comando novamente em `{error.retry_after:.1f}s`.",
            )
        elif isinstance(error, app_commands.MissingPermissions):
            embed = error_embed(
                "Permissão Insuficiente",
                "Você não possui as permissões necessárias no Discord para usar este comando.",
            )
        else:
            logger.exception(
                "Erro não tratado no comando '%s' (guild=%s, user=%s)",
                interaction.command.name if interaction.command else "desconhecido",
                interaction.guild_id,
                interaction.user.id,
            )
            if interaction.guild_id:
                await self.bot.log_service.record(
                    guild_id=interaction.guild_id,
                    category="errors",
                    action="command.unhandled_error",
                    actor_id=interaction.user.id,
                    details=f"Erro interno ao executar comando: `{type(original).__name__}`",
                )
            embed = error_embed(
                "Erro Interno",
                "Ocorreu uma falha inesperada ao processar o comando. A equipe técnica foi notificada.",
            )

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: FusionBot) -> None:
    await bot.add_cog(SystemCog(bot))