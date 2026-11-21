"""Testes de integração dos repositórios multi-banco (guilds, tickets, automations, logs)."""

from __future__ import annotations

from datetime import timedelta

from src.database.interfaces.provider import IDatabaseProvider
from src.database.schemas import (
    AuditLogSchema,
    AutomationRuleSchema,
    TicketPanelSchema,
    TicketRatingSchema,
    TicketSchema,
    utc_now,
)


async def test_guild_settings_crud(db: IDatabaseProvider) -> None:
    guild_id = 100200300400500600
    created = await db.guilds.get_or_create(guild_id)
    assert created.guild_id == guild_id
    assert created.tickets_enabled is True
    assert created.timezone == "America/Sao_Paulo"

    created.brand_color = 0x10B981
    created.permissions["administration"].role_ids = [111, 222]
    updated = await db.guilds.update(created)

    fetched = await db.guilds.get_or_create(guild_id)
    assert updated.brand_color == 0x10B981
    assert fetched.permissions["administration"].role_ids == [111, 222]


async def test_ticket_panels_tickets_and_rating_stats(db: IDatabaseProvider) -> None:
    guild_id = 200300400500600700
    panel = TicketPanelSchema(
        guild_id=guild_id,
        name="Suporte Geral",
        staff_role_ids=[999],
    )
    saved_panel = await db.tickets.create_panel(panel)
    panels = await db.tickets.list_panels(guild_id)
    assert len(panels) == 1
    assert panels[0].id == saved_panel.id

    num1 = await db.tickets.next_ticket_number(guild_id)
    assert num1 == 1

    ticket = TicketSchema(
        guild_id=guild_id,
        panel_id=saved_panel.id,
        ticket_number=num1,
        channel_id=777888999,
        opener_id=12345,
        claimed_by_id=67890,
        department="Suporte Geral",
    )
    saved_ticket = await db.tickets.create_ticket(ticket)
    assert await db.tickets.count_active_user_tickets(guild_id, saved_panel.id, 12345) == 1

    num2 = await db.tickets.next_ticket_number(guild_id)
    assert num2 == 2

    by_chan = await db.tickets.get_ticket_by_channel(777888999)
    assert by_chan is not None
    assert by_chan.id == saved_ticket.id

    await db.tickets.create_rating(
        TicketRatingSchema(
            guild_id=guild_id,
            ticket_id=saved_ticket.id,
            panel_id=saved_panel.id,
            user_id=12345,
            staff_id=67890,
            stars=5,
            comment="Atendimento impecável!",
        )
    )
    stats = await db.tickets.get_staff_rating_stats(guild_id)
    assert len(stats) == 1
    assert stats[0]["staff_id"] == 67890
    assert stats[0]["average"] == 5.0
    assert stats[0]["total"] == 1


async def test_automations_due_schedule_query_and_audit_logs(db: IDatabaseProvider) -> None:
    guild_id = 300400500600700800
    now = utc_now()

    due_rule = AutomationRuleSchema(
        guild_id=guild_id,
        name="Aviso Imediato",
        automation_type="scheduled",
        target_channel_id=555444333,
    )
    due_rule.schedule.enabled = True
    due_rule.schedule.frequency = "once"
    due_rule.schedule.next_run_at = now - timedelta(seconds=10)
    await db.automations.create_automation(due_rule)

    future_rule = AutomationRuleSchema(
        guild_id=guild_id,
        name="Aviso Futuro",
        automation_type="periodic",
        target_channel_id=555444333,
    )
    future_rule.schedule.enabled = True
    future_rule.schedule.frequency = "daily"
    future_rule.schedule.next_run_at = now + timedelta(hours=3)
    await db.automations.create_automation(future_rule)

    due_list = await db.automations.get_due_scheduled_automations(now)
    assert len(due_list) == 1
    assert due_list[0].id == due_rule.id

    await db.logs.append_log(
        AuditLogSchema(
            guild_id=guild_id,
            category="tickets",
            action="ticket.opened",
            actor_id=12345,
            target_id="#0001",
            details="Ticket aberto em teste automatizado.",
        )
    )
    recent_logs = await db.logs.list_recent_logs(guild_id, category="tickets", limit=10)
    assert len(recent_logs) == 1
    assert recent_logs[0].action == "ticket.opened"