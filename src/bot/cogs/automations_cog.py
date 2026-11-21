"""Cog responsável por mensagens automáticas, componentes dinâmicos e agendamentos."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from src.bot.views.automations.automation_runtime_views import (
    CustomAutomationButtonItem,
    CustomAutomationDropdownItem,
)
from src.core.logger import get_logger

if TYPE_CHECKING:
    from src.bot.client import FusionBot

logger = get_logger(__name__)


class AutomationsCog(commands.Cog):
    """Gerencia listeners de entrada/saída de membros, DynamicItems e SchedulerEngine."""

    def __init__(self, bot: FusionBot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Registra botões/dropdowns personalizados e inicia o agendador persistente."""
        self.bot.add_dynamic_items(
            CustomAutomationButtonItem,
            CustomAutomationDropdownItem,
        )
        self.bot.scheduler.start()
        logger.info("DynamicItems de automações registrados e SchedulerEngine ativo.")

    async def cog_unload(self) -> None:
        """Interrompe o loop de agendamento ao descarregar a extensão."""
        await self.bot.scheduler.stop()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Dispara mensagens automáticas de boas-vindas configuradas no servidor."""
        if member.bot:
            return
        await self.bot.automation_service.dispatch_member_event(member, "welcome")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Dispara mensagens automáticas de despedida configuradas no servidor."""
        if member.bot:
            return
        await self.bot.automation_service.dispatch_member_event(member, "goodbye")


async def setup(bot: FusionBot) -> None:
    await bot.add_cog(AutomationsCog(bot))