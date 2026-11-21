"""Serviço de gestão de configurações do servidor, métricas reais e diagnóstico."""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

import discord

from src.core.exceptions import ValidationError
from src.database.interfaces.provider import IDatabaseProvider
from src.database.schemas import (
    AuditLogSchema,
    BotModule,
    GuildSettingsSchema,
    LogCategory,
    ModulePermissionRule,
)
from src.services.log_service import LogService


@dataclass(frozen=True)
class GuildDashboardSnapshot:
    """Resumo em tempo real dos dados reais do servidor para o /painel."""

    guild_name: str
    guild_id: int
    member_count: int
    tickets_enabled: bool
    automations_enabled: bool
    open_tickets_count: int
    total_panels_count: int
    active_automations_count: int
    total_automations_count: int
    recent_logs: list[AuditLogSchema]
    settings: GuildSettingsSchema


@dataclass(frozen=True)
class SystemDiagnosticsReport:
    """Métricas técnicas em tempo real do bot e do banco de dados."""

    database_provider: str
    database_healthy: bool
    database_latency_ms: float
    gateway_latency_ms: float
    shard_id: int
    shard_count: int
    uptime_seconds: int
    python_version: str
    discord_py_version: str
    platform_info: str
    guild_count: int


class GuildService:
    """Orquestra configurações gerais, identidade visual, canais e permissões."""

    def __init__(self, db: IDatabaseProvider, log_service: LogService) -> None:
        self._db = db
        self._logs = log_service

    async def get_settings(self, guild_id: int) -> GuildSettingsSchema:
        return await self._db.guilds.get_or_create(guild_id)

    async def get_dashboard_snapshot(self, guild: discord.Guild) -> GuildDashboardSnapshot:
        """Coleta métricas reais do servidor e do banco de dados sem dados fictícios."""
        settings = await self._db.guilds.get_or_create(guild.id)
        open_tickets = await self._db.tickets.count_open_guild_tickets(guild.id)
        panels = await self._db.tickets.list_panels(guild.id)
        automations = await self._db.automations.list_automations(guild.id)
        recent_logs = await self._db.logs.list_recent_logs(guild.id, limit=5)

        active_automations = sum(1 for item in automations if item.enabled)

        return GuildDashboardSnapshot(
            guild_name=guild.name,
            guild_id=guild.id,
            member_count=guild.member_count or len(guild.members),
            tickets_enabled=settings.tickets_enabled,
            automations_enabled=settings.automations_enabled,
            open_tickets_count=open_tickets,
            total_panels_count=len(panels),
            active_automations_count=active_automations,
            total_automations_count=len(automations),
            recent_logs=recent_logs,
            settings=settings,
        )

    async def toggle_module(
        self,
        guild_id: int,
        actor_id: int,
        module: str,
    ) -> GuildSettingsSchema:
        """Ativa ou desativa o módulo de tickets ou automações."""
        settings = await self._db.guilds.get_or_create(guild_id)
        if module == "tickets":
            settings.tickets_enabled = not settings.tickets_enabled
            state_str = "ativado" if settings.tickets_enabled else "desativado"
        elif module == "automations":
            settings.automations_enabled = not settings.automations_enabled
            state_str = "ativado" if settings.automations_enabled else "desativado"
        else:
            raise ValidationError(f"Módulo inválido para alternância: {module}")

        saved = await self._db.guilds.save(settings)
        await self._logs.record(
            guild_id=guild_id,
            category="administration",
            action="module.toggled",
            actor_id=actor_id,
            target_id=module,
            details=f"Módulo **{module}** foi **{state_str}** por <@{actor_id}>.",
        )
        return saved

    async def update_branding(
        self,
        guild_id: int,
        actor_id: int,
        *,
        brand_color_hex: str | None = None,
        brand_footer: str | None = None,
    ) -> GuildSettingsSchema:
        """Atualiza cor principal e rodapé padrão das interfaces administrativas."""
        settings = await self._db.guilds.get_or_create(guild_id)

        if brand_color_hex is not None:
            cleaned = brand_color_hex.strip().lstrip("#")
            try:
                color_int = int(cleaned, 16)
                if not (0 <= color_int <= 0xFFFFFF):
                    raise ValueError
            except ValueError as exc:
                raise ValidationError(
                    "Cor hexadecimal inválida.",
                    user_message="Informe uma cor hexadecimal válida (ex: `#5865F2` ou `10B981`).",
                ) from exc
            settings.brand_color = color_int

        if brand_footer is not None:
            footer_clean = brand_footer.strip()
            if not footer_clean:
                raise ValidationError(
                    "Rodapé vazio.",
                    user_message="O texto de rodapé não pode ficar em branco.",
                )
            settings.brand_footer = footer_clean[:256]

        saved = await self._db.guilds.save(settings)
        await self._logs.record(
            guild_id=guild_id,
            category="administration",
            action="branding.updated",
            actor_id=actor_id,
            details=f"Identidade visual atualizada por <@{actor_id}>.",
        )
        return saved

    async def update_general_settings(
        self,
        guild_id: int,
        actor_id: int,
        *,
        timezone: str,
        language: str,
    ) -> GuildSettingsSchema:
        """Atualiza fuso horário e idioma do servidor."""
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        tz_clean = timezone.strip()
        try:
            ZoneInfo(tz_clean)
        except ZoneInfoNotFoundError as exc:
            raise ValidationError(
                f"Timezone inválido: {tz_clean}",
                user_message=(
                    f"Fuso horário `{tz_clean}` inválido. "
                    "Use o padrão IANA (ex: `America/Sao_Paulo`, `UTC`, `Europe/Lisbon`)."
                ),
            ) from exc

        settings = await self._db.guilds.get_or_create(guild_id)
        settings.timezone = tz_clean
        settings.language = language.strip() or "pt-BR"
        saved = await self._db.guilds.save(settings)

        await self._logs.record(
            guild_id=guild_id,
            category="administration",
            action="general.updated",
            actor_id=actor_id,
            details=f"Configurações gerais atualizadas (`{tz_clean}`, `{settings.language}`).",
        )
        return saved

    async def update_default_channels(
        self,
        guild_id: int,
        actor_id: int,
        *,
        ticket_category_id: int | None | object = ...,
        transcript_channel_id: int | None | object = ...,
        rating_channel_id: int | None | object = ...,
    ) -> GuildSettingsSchema:
        """Atualiza canais/categorias padrão do servidor."""
        settings = await self._db.guilds.get_or_create(guild_id)

        if ticket_category_id is not ...:
            settings.default_ticket_category_id = ticket_category_id  # type: ignore[assignment]
        if transcript_channel_id is not ...:
            settings.default_transcript_channel_id = transcript_channel_id  # type: ignore[assignment]
        if rating_channel_id is not ...:
            settings.default_rating_channel_id = rating_channel_id  # type: ignore[assignment]

        saved = await self._db.guilds.save(settings)
        await self._logs.record(
            guild_id=guild_id,
            category="administration",
            action="channels.updated",
            actor_id=actor_id,
            details=f"Canais e categorias padrão atualizados por <@{actor_id}>.",
        )
        return saved

    async def update_log_channel(
        self,
        guild_id: int,
        actor_id: int,
        category: LogCategory,
        channel_id: int | None,
    ) -> GuildSettingsSchema:
        """Define ou limpa o canal de log para uma categoria específica."""
        settings = await self._db.guilds.get_or_create(guild_id)
        settings.log_channels[category] = channel_id
        saved = await self._db.guilds.save(settings)

        target_desc = f"<#{channel_id}>" if channel_id else "Desativado"
        await self._logs.record(
            guild_id=guild_id,
            category="administration",
            action="logs.channel_updated",
            actor_id=actor_id,
            target_id=category,
            details=f"Canal de logs de **{category}** definido para {target_desc}.",
        )
        return saved

    async def update_module_permissions(
        self,
        guild_id: int,
        actor_id: int,
        module: BotModule,
        *,
        role_ids: list[int] | None = None,
        user_ids: list[int] | None = None,
    ) -> GuildSettingsSchema:
        """Atualiza lista de cargos e usuários autorizados em um módulo."""
        settings = await self._db.guilds.get_or_create(guild_id)
        current = settings.permissions.get(module, ModulePermissionRule())

        if role_ids is not None:
            current.role_ids = list(dict.fromkeys(role_ids))
        if user_ids is not None:
            current.user_ids = list(dict.fromkeys(user_ids))

        settings.permissions[module] = current
        saved = await self._db.guilds.save(settings)

        await self._logs.record(
            guild_id=guild_id,
            category="administration",
            action="permissions.updated",
            actor_id=actor_id,
            target_id=module,
            details=(
                f"Permissões do módulo **{module}** atualizadas "
                f"({len(current.role_ids)} cargos, {len(current.user_ids)} usuários)."
            ),
        )
        return saved

    async def build_diagnostics(
        self,
        bot: discord.AutoShardedClient,
        guild: discord.Guild,
        started_at: datetime,
    ) -> SystemDiagnosticsReport:
        """Executa verificações reais de saúde do banco, gateway e runtime."""
        db_healthy, db_latency = await self._db.healthcheck()
        uptime = int((datetime.now(UTC) - started_at).total_seconds())
        gw_latency = round(bot.latency * 1000, 2) if bot.latency else 0.0

        return SystemDiagnosticsReport(
            database_provider=self._db.provider_name.upper(),
            database_healthy=db_healthy,
            database_latency_ms=db_latency,
            gateway_latency_ms=gw_latency,
            shard_id=guild.shard_id or 0,
            shard_count=bot.shard_count or 1,
            uptime_seconds=max(uptime, 0),
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            discord_py_version=discord.__version__,
            platform_info=f"{platform.system()} {platform.release()}",
            guild_count=len(bot.guilds),
        )