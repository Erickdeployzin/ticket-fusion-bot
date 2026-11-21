"""Testes unitários de permissões, placeholders, locks, horários e agendamento."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import discord

from src.core.lifecycle import LockManager
from src.core.permissions import PermissionService
from src.database.schemas import (
    EmbedConfigSchema,
    GuildSettingsSchema,
    ScheduleConfigSchema,
    TicketPanelSchema,
)
from src.services.automation_service import AutomationService
from src.services.placeholder_service import PlaceholderContext, PlaceholderService
from src.services.ticket_service import TicketService


def test_placeholder_rendering_and_embed_building(
    placeholder_service: PlaceholderService,
    mock_guild: MagicMock,
    mock_member: MagicMock,
) -> None:
    ctx = PlaceholderContext(
        guild=mock_guild,
        user=mock_member,
        timezone="America/Sao_Paulo",
        extra={"department": "Financeiro"},
    )
    rendered = placeholder_service.render(
        "Olá {user} ({username}), bem-vindo ao {server}! Setor: {department}. {desconhecido}",
        ctx,
    )
    assert rendered is not None
    assert "<@111222333444555666>" in rendered
    assert "Erik" in rendered
    assert "Servidor Teste Fusion" in rendered
    assert "Financeiro" in rendered
    assert "{desconhecido}" in rendered

    cfg = EmbedConfigSchema(
        title="Bem-vindo, {username}",
        description="Total de membros: {member_count}",
        color=0x5865F2,
    )
    embed = placeholder_service.build_embed(cfg, ctx, fallback_footer="Fusion Core")
    assert embed.title == "Bem-vindo, Erik"
    assert embed.description == "Total de membros: 142"
    assert embed.footer.text == "Fusion Core"


def test_permission_hierarchy_and_module_roles(
    permission_service: PermissionService,
    mock_member: MagicMock,
) -> None:
    settings = GuildSettingsSchema(guild_id=mock_member.guild.id)
    settings.permissions["administration"].role_ids = [5001]
    settings.permissions["tickets"].role_ids = [5002]
    settings.permissions["automations"].role_ids = [5003]

    # Sem cargos e sem permissão nativa -> negado
    assert permission_service.has_module_access(mock_member, settings, "tickets") is False
    assert permission_service.has_module_access(mock_member, settings, "automations") is False

    # Cargo de equipe de tickets -> acesso apenas a tickets
    staff_role = MagicMock(spec=discord.Role)
    staff_role.id = 5002
    mock_member.roles.append(staff_role)
    assert permission_service.has_module_access(mock_member, settings, "tickets") is True
    assert permission_service.has_module_access(mock_member, settings, "automations") is False

    # Cargo administrativo global -> acesso irrestrito aos módulos
    admin_role = MagicMock(spec=discord.Role)
    admin_role.id = 5001
    mock_member.roles.append(admin_role)
    assert permission_service.has_module_access(mock_member, settings, "automations") is True
    assert permission_service.has_module_access(mock_member, settings, "administration") is True


def test_scheduler_next_run_calculations() -> None:
    base_utc = datetime(2026, 11, 21, 15, 0, tzinfo=UTC)  # Sábado 12:00 America/Sao_Paulo

    # 1. Intervalo periódico
    interval_sched = ScheduleConfigSchema(
        enabled=True,
        frequency="interval",
        interval_minutes=30,
    )
    next_interval = AutomationService.compute_next_run(interval_sched, reference_utc=base_utc)
    assert next_interval == base_utc + timedelta(minutes=30)

    # 2. Diário após horário já passado no dia -> agenda para o dia seguinte
    daily_sched = ScheduleConfigSchema(
        enabled=True,
        frequency="daily",
        time_of_day="10:00",
        timezone="America/Sao_Paulo",
    )
    next_daily = AutomationService.compute_next_run(daily_sched, reference_utc=base_utc)
    assert next_daily is not None
    assert next_daily > base_utc

    # 3. Limite máximo de execuções atingido -> retorna None
    capped_sched = ScheduleConfigSchema(
        enabled=True,
        frequency="daily",
        time_of_day="14:00",
        max_runs=3,
        run_count=3,
    )
    assert AutomationService.compute_next_run(capped_sched, reference_utc=base_utc) is None


async def test_lock_manager_prevents_concurrent_race_condition(
    lock_manager: LockManager,
) -> None:
    counter = 0

    async def worker() -> None:
        nonlocal counter
        async with lock_manager.acquire("ticket_open:guild:panel:user", ttl_seconds=5):
            snapshot = counter
            await asyncio.sleep(0.02)
            counter = snapshot + 1

    await asyncio.gather(*(worker() for _ in range(5)))
    assert counter == 5


def test_business_hours_evaluation() -> None:
    service = TicketService(
        bot=MagicMock(),
        db=MagicMock(),
        locks=MagicMock(),
        permissions=MagicMock(),
        log_service=MagicMock(),
        placeholders=MagicMock(),
        transcripts=MagicMock(),
    )
    panel = TicketPanelSchema(guild_id=1, name="Suporte")
    panel.business_hours.enabled = False
    assert service.is_within_business_hours(panel) is True