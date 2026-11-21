"""Cog responsável pelo ciclo de vida persistente do sistema de tickets."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from src.bot.views.tickets.ticket_runtime_views import (
    TicketDepartmentSelectItem,
    TicketInsideControlView,
    TicketOpenButtonItem,
    TicketRatingButtonItem,
)
from src.core.logger import get_logger
from src.database.schemas import utc_now

if TYPE_CHECKING:
    from src.bot.client import FusionBot

logger = get_logger(__name__)


class TicketsCog(commands.Cog):
    """Registra componentes persistentes e sincroniza eventos de canais de tickets."""

    def __init__(self, bot: FusionBot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Registra DynamicItems e Views persistentes antes do bot receber eventos."""
        self.bot.add_dynamic_items(
            TicketOpenButtonItem,
            TicketDepartmentSelectItem,
            TicketRatingButtonItem,
        )
        self.bot.add_view(TicketInsideControlView(self.bot, closed=False))
        self.bot.add_view(TicketInsideControlView(self.bot, closed=True, allow_reopen=True))
        self.bot.add_view(TicketInsideControlView(self.bot, closed=True, allow_reopen=False))
        logger.info("Views e DynamicItems persistentes de tickets registrados.")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        """Sincroniza o banco caso um canal de ticket seja deletado manualmente no Discord."""
        if not isinstance(channel, discord.TextChannel):
            return

        ticket = await self.bot.ctx.db.tickets.get_ticket_by_channel(channel.id)
        if ticket is not None and ticket.status != "archived":
            ticket.status = "archived"
            if ticket.closed_at is None:
                ticket.closed_at = utc_now()
            await self.bot.ctx.db.tickets.update_ticket(ticket)
            logger.info(
                "Ticket #%04d marcado como arquivado após exclusão manual do canal %s.",
                ticket.ticket_number,
                channel.id,
            )


async def setup(bot: FusionBot) -> None:
    await bot.add_cog(TicketsCog(bot))