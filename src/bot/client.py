"""Cliente principal do Fusion Bot com suporte a AutoShardedBot e Views persistentes."""

from __future__ import annotations

import discord
from discord.ext import commands

from src.core.lifecycle import AppContext
from src.core.logger import get_logger
from src.core.permissions import PermissionService
from src.services.automation_service import AutomationService
from src.services.guild_service import GuildService
from src.services.log_service import LogService
from src.services.placeholder_service import PlaceholderService
from src.services.ticket_service import TicketService
from src.services.transcript_service import TranscriptService
from src.tasks.scheduler import SchedulerEngine

logger = get_logger(__name__)


class FusionBot(commands.AutoShardedBot):
    """Subclasse de AutoShardedBot preparada para alta escala e persistência de estado."""

    EXTENSIONS: tuple[str, ...] = (
        "src.bot.cogs.system_cog",
        "src.bot.cogs.admin_cog",
        "src.bot.cogs.tickets_cog",
        "src.bot.cogs.automations_cog",
    )

    def __init__(self, context: AppContext) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.messages = True
        intents.message_content = True

        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            application_id=context.settings.discord_application_id,
            shard_count=context.settings.shard_count,
            chunk_guilds_at_startup=False,
            max_messages=2000,
        )
        self.ctx = context
        self.permissions = PermissionService()
        self.placeholders = PlaceholderService()
        self.transcripts = TranscriptService()
        self.log_service = LogService(self, context.db)
        self.guild_service = GuildService(context.db, self.log_service)
        self.ticket_service = TicketService(
            bot=self,
            db=context.db,
            locks=context.locks,
            permissions=self.permissions,
            log_service=self.log_service,
            placeholders=self.placeholders,
            transcripts=self.transcripts,
        )
        self.automation_service = AutomationService(
            bot=self,
            db=context.db,
            log_service=self.log_service,
            placeholders=self.placeholders,
        )
        self.scheduler = SchedulerEngine(self)

    async def setup_hook(self) -> None:
        """Executa antes da conexão ao Gateway: carrega cogs, views persistentes e comandos."""
        logger.info("Executando setup_hook do Fusion Bot...")

        for extension in self.EXTENSIONS:
            await self.load_extension(extension)
            logger.info("Extensão carregada: %s", extension)

        if self.ctx.settings.dev_guild_id:
            guild_obj = discord.Object(id=self.ctx.settings.dev_guild_id)
            self.tree.copy_global_to(guild=guild_obj)
            synced = await self.tree.sync(guild=guild_obj)
            logger.info(
                "Comandos slash sincronizados na guild de desenvolvimento (%s): %d comandos.",
                self.ctx.settings.dev_guild_id,
                len(synced),
            )
        else:
            synced = await self.tree.sync()
            logger.info("Comandos slash sincronizados globalmente: %d comandos.", len(synced))

    async def on_ready(self) -> None:
        """Evento disparado quando o cliente e shards estão prontos."""
        assert self.user is not None
        logger.info(
            "Bot online como %s (ID: %s) | Servidores: %d | Shards: %s",
            self.user,
            self.user.id,
            len(self.guilds),
            self.shard_count or 1,
        )
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="/painel • Gestão Profissional",
            ),
            status=discord.Status.online,
        )

    async def close(self) -> None:
        """Garante encerramento ordenado do agendador antes de fechar o Gateway."""
        await self.scheduler.stop()
        await super().close()