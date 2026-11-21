"""Serviço centralizado de auditoria no banco e despacho visual para canais de log."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord

from src.core.logger import get_logger
from src.database.interfaces.provider import IDatabaseProvider
from src.database.schemas import AuditLogSchema, LogCategory, utc_now

if TYPE_CHECKING:
    from src.bot.client import FusionBot

logger = get_logger(__name__)

CATEGORY_META: dict[LogCategory, tuple[str, int]] = {
    "tickets": ("Tickets", 0x3B82F6),
    "automations": ("Automações", 0x8B5CF6),
    "administration": ("Administração", 0x10B981),
    "errors": ("Erros do Sistema", 0xEF4444),
}


class LogService:
    """Persiste eventos de auditoria e envia embeds limpas aos canais configurados."""

    def __init__(self, bot: FusionBot, db: IDatabaseProvider) -> None:
        self._bot = bot
        self._db = db

    async def record(
        self,
        *,
        guild_id: int,
        category: LogCategory,
        action: str,
        details: str,
        actor_id: int | None = None,
        target_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditLogSchema:
        """Grava o evento no banco de dados e notifica o canal de log da categoria."""
        entry = AuditLogSchema(
            guild_id=guild_id,
            category=category,
            action=action,
            actor_id=actor_id,
            target_id=target_id,
            details=details,
            metadata=metadata or {},
            created_at=utc_now(),
        )
        saved = await self._db.logs.append_log(entry)
        await self._dispatch_to_discord(saved)
        return saved

    async def _dispatch_to_discord(self, entry: AuditLogSchema) -> None:
        """Envia o registro para o canal configurado da categoria, se existir e for acessível."""
        try:
            settings = await self._db.guilds.get_or_create(entry.guild_id)
            channel_id = settings.log_channels.get(entry.category)
            if not channel_id:
                return

            guild = self._bot.get_guild(entry.guild_id)
            if guild is None:
                return

            channel = guild.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                return

            perms = channel.permissions_for(guild.me)
            if not (perms.send_messages and perms.embed_links):
                return

            cat_label, cat_color = CATEGORY_META.get(entry.category, ("Sistema", 0x5865F2))
            embed = discord.Embed(
                title=f"Registro • {cat_label}",
                description=entry.details,
                color=cat_color,
                timestamp=entry.created_at,
            )
            embed.add_field(name="Ação", value=f"`{entry.action}`", inline=True)
            if entry.actor_id:
                embed.add_field(name="Responsável", value=f"<@{entry.actor_id}>", inline=True)
            if entry.target_id:
                embed.add_field(name="Referência", value=f"`{entry.target_id}`", inline=True)

            embed.set_footer(text=settings.brand_footer)
            await channel.send(embed=embed)
        except Exception:
            logger.exception(
                "Falha não-crítica ao enviar log para canal do Discord (guild=%s, category=%s)",
                entry.guild_id,
                entry.category,
            )

    async def get_recent(
        self,
        guild_id: int,
        *,
        category: LogCategory | None = None,
        limit: int = 10,
    ) -> list[AuditLogSchema]:
        """Recupera os registros mais recentes do banco para exibição no painel."""
        return await self._db.logs.list_recent_logs(
            guild_id,
            category=category,
            limit=limit,
        )