"""Implementação SQLAlchemy 2.x dos repositórios de domínio."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.exceptions import EntityNotFoundError
from src.database.interfaces.repositories import (
    IAutomationRepository,
    IGuildRepository,
    ILogRepository,
    ITicketRepository,
)
from src.database.providers.sql.models import (
    AuditLogModel,
    AutomationRuleModel,
    GuildSettingsModel,
    TicketModel,
    TicketPanelModel,
    TicketRatingModel,
)
from src.database.schemas import (
    AuditLogSchema,
    AutomationRuleSchema,
    AutomationType,
    BusinessHoursSchema,
    CustomButtonSchema,
    CustomDropdownSchema,
    EmbedConfigSchema,
    GuildSettingsSchema,
    LogCategory,
    ModulePermissionRule,
    ScheduleConfigSchema,
    TicketDepartmentOption,
    TicketFormFieldSchema,
    TicketPanelSchema,
    TicketRatingSchema,
    TicketSchema,
    TicketStatus,
    utc_now,
)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    """Garante que datetimes retornados pelo SQLite tenham tzinfo=UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class SQLGuildRepository(IGuildRepository):
    """Repositório SQL para configurações por servidor."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _to_schema(model: GuildSettingsModel) -> GuildSettingsSchema:
        raw_perms = model.permissions or {}
        parsed_perms = {
            mod: ModulePermissionRule.model_validate(rule)
            for mod, rule in raw_perms.items()
        }
        return GuildSettingsSchema(
            guild_id=model.guild_id,
            tickets_enabled=model.tickets_enabled,
            automations_enabled=model.automations_enabled,
            language=model.language,
            timezone=model.timezone,
            brand_color=model.brand_color,
            brand_footer=model.brand_footer,
            log_channels=cast(dict[LogCategory, int | None], model.log_channels),
            default_ticket_category_id=model.default_ticket_category_id,
            default_transcript_channel_id=model.default_transcript_channel_id,
            default_rating_channel_id=model.default_rating_channel_id,
            permissions=cast(Any, parsed_perms),
            created_at=_ensure_utc(model.created_at) or utc_now(),
            updated_at=_ensure_utc(model.updated_at) or utc_now(),
        )

    async def get_or_create(self, guild_id: int) -> GuildSettingsSchema:
        async with self._session_factory() as session:
            result = await session.execute(
                select(GuildSettingsModel).where(GuildSettingsModel.guild_id == guild_id)
            )
            model = result.scalar_one_or_none()
            if model is not None:
                return self._to_schema(model)

            default_schema = GuildSettingsSchema(guild_id=guild_id)
            model = GuildSettingsModel(
                guild_id=default_schema.guild_id,
                tickets_enabled=default_schema.tickets_enabled,
                automations_enabled=default_schema.automations_enabled,
                language=default_schema.language,
                timezone=default_schema.timezone,
                brand_color=default_schema.brand_color,
                brand_footer=default_schema.brand_footer,
                log_channels=dict(default_schema.log_channels),
                default_ticket_category_id=default_schema.default_ticket_category_id,
                default_transcript_channel_id=default_schema.default_transcript_channel_id,
                default_rating_channel_id=default_schema.default_rating_channel_id,
                permissions={
                    k: v.model_dump() for k, v in default_schema.permissions.items()
                },
                created_at=default_schema.created_at,
                updated_at=default_schema.updated_at,
            )
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return self._to_schema(model)

    async def save(self, settings: GuildSettingsSchema) -> GuildSettingsSchema:
        settings.updated_at = utc_now()
        async with self._session_factory() as session:
            result = await session.execute(
                select(GuildSettingsModel).where(
                    GuildSettingsModel.guild_id == settings.guild_id
                )
            )
            model = result.scalar_one_or_none()
            if model is None:
                model = GuildSettingsModel(guild_id=settings.guild_id)
                session.add(model)

            model.tickets_enabled = settings.tickets_enabled
            model.automations_enabled = settings.automations_enabled
            model.language = settings.language
            model.timezone = settings.timezone
            model.brand_color = settings.brand_color
            model.brand_footer = settings.brand_footer
            model.log_channels = dict(settings.log_channels)
            model.default_ticket_category_id = settings.default_ticket_category_id
            model.default_transcript_channel_id = settings.default_transcript_channel_id
            model.default_rating_channel_id = settings.default_rating_channel_id
            model.permissions = {k: v.model_dump() for k, v in settings.permissions.items()}
            model.updated_at = settings.updated_at

            await session.commit()
            await session.refresh(model)
            return self._to_schema(model)

    async def delete_guild_data(self, guild_id: int) -> None:
        async with self._session_factory() as session:
            await session.execute(
                delete(GuildSettingsModel).where(GuildSettingsModel.guild_id == guild_id)
            )
            await session.commit()


class SQLTicketRepository(ITicketRepository):
    """Repositório SQL para painéis, tickets e avaliações."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _panel_to_schema(model: TicketPanelModel) -> TicketPanelSchema:
        return TicketPanelSchema(
            id=model.id,
            guild_id=model.guild_id,
            name=model.name,
            enabled=model.enabled,
            embed=EmbedConfigSchema.model_validate(model.embed),
            open_mode=cast(Any, model.open_mode),
            button_label=model.button_label,
            button_emoji=model.button_emoji,
            button_style=cast(Any, model.button_style),
            dropdown_placeholder=model.dropdown_placeholder,
            departments=[
                TicketDepartmentOption.model_validate(d) for d in (model.departments or [])
            ],
            category_id=model.category_id,
            staff_role_ids=list(model.staff_role_ids or []),
            channel_id=model.channel_id,
            message_id=model.message_id,
            welcome_embed=EmbedConfigSchema.model_validate(model.welcome_embed),
            max_tickets_per_user=model.max_tickets_per_user,
            cooldown_seconds=model.cooldown_seconds,
            allow_reopen=model.allow_reopen,
            enable_rating=model.enable_rating,
            form_fields=[
                TicketFormFieldSchema.model_validate(f) for f in (model.form_fields or [])
            ],
            business_hours=BusinessHoursSchema.model_validate(model.business_hours),
            created_at=_ensure_utc(model.created_at) or utc_now(),
            updated_at=_ensure_utc(model.updated_at) or utc_now(),
        )

    @staticmethod
    def _ticket_to_schema(model: TicketModel) -> TicketSchema:
        return TicketSchema(
            id=model.id,
            guild_id=model.guild_id,
            panel_id=model.panel_id,
            ticket_number=model.ticket_number,
            channel_id=model.channel_id,
            opener_id=model.opener_id,
            claimed_by_id=model.claimed_by_id,
            closed_by_id=model.closed_by_id,
            department=model.department,
            priority=cast(Any, model.priority),
            status=cast(TicketStatus, model.status),
            participant_ids=list(model.participant_ids or []),
            form_answers=dict(model.form_answers or {}),
            transcript_url=model.transcript_url,
            first_response_at=_ensure_utc(model.first_response_at),
            closed_at=_ensure_utc(model.closed_at),
            created_at=_ensure_utc(model.created_at) or utc_now(),
            updated_at=_ensure_utc(model.updated_at) or utc_now(),
        )

    @staticmethod
    def _rating_to_schema(model: TicketRatingModel) -> TicketRatingSchema:
        return TicketRatingSchema(
            id=model.id,
            guild_id=model.guild_id,
            ticket_id=model.ticket_id,
            panel_id=model.panel_id,
            user_id=model.user_id,
            staff_id=model.staff_id,
            stars=model.stars,
            comment=model.comment,
            created_at=_ensure_utc(model.created_at) or utc_now(),
        )

    async def create_panel(self, panel: TicketPanelSchema) -> TicketPanelSchema:
        async with self._session_factory() as session:
            model = TicketPanelModel(
                id=panel.id,
                guild_id=panel.guild_id,
                name=panel.name,
                enabled=panel.enabled,
                embed=panel.embed.model_dump(),
                open_mode=panel.open_mode,
                button_label=panel.button_label,
                button_emoji=panel.button_emoji,
                button_style=panel.button_style,
                dropdown_placeholder=panel.dropdown_placeholder,
                departments=[d.model_dump() for d in panel.departments],
                category_id=panel.category_id,
                staff_role_ids=list(panel.staff_role_ids),
                channel_id=panel.channel_id,
                message_id=panel.message_id,
                welcome_embed=panel.welcome_embed.model_dump(),
                max_tickets_per_user=panel.max_tickets_per_user,
                cooldown_seconds=panel.cooldown_seconds,
                allow_reopen=panel.allow_reopen,
                enable_rating=panel.enable_rating,
                form_fields=[f.model_dump() for f in panel.form_fields],
                business_hours=panel.business_hours.model_dump(),
                created_at=panel.created_at,
                updated_at=panel.updated_at,
            )
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return self._panel_to_schema(model)

    async def update_panel(self, panel: TicketPanelSchema) -> TicketPanelSchema:
        panel.updated_at = utc_now()
        async with self._session_factory() as session:
            result = await session.execute(
                select(TicketPanelModel).where(
                    TicketPanelModel.id == panel.id,
                    TicketPanelModel.guild_id == panel.guild_id,
                )
            )
            model = result.scalar_one_or_none()
            if model is None:
                raise EntityNotFoundError(f"Painel {panel.id} não encontrado na guild {panel.guild_id}.")

            model.name = panel.name
            model.enabled = panel.enabled
            model.embed = panel.embed.model_dump()
            model.open_mode = panel.open_mode
            model.button_label = panel.button_label
            model.button_emoji = panel.button_emoji
            model.button_style = panel.button_style
            model.dropdown_placeholder = panel.dropdown_placeholder
            model.departments = [d.model_dump() for d in panel.departments]
            model.category_id = panel.category_id
            model.staff_role_ids = list(panel.staff_role_ids)
            model.channel_id = panel.channel_id
            model.message_id = panel.message_id
            model.welcome_embed = panel.welcome_embed.model_dump()
            model.max_tickets_per_user = panel.max_tickets_per_user
            model.cooldown_seconds = panel.cooldown_seconds
            model.allow_reopen = panel.allow_reopen
            model.enable_rating = panel.enable_rating
            model.form_fields = [f.model_dump() for f in panel.form_fields]
            model.business_hours = panel.business_hours.model_dump()
            model.updated_at = panel.updated_at

            await session.commit()
            await session.refresh(model)
            return self._panel_to_schema(model)

    async def get_panel(self, guild_id: int, panel_id: str) -> TicketPanelSchema | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(TicketPanelModel).where(
                    TicketPanelModel.guild_id == guild_id,
                    TicketPanelModel.id == panel_id,
                )
            )
            model = result.scalar_one_or_none()
            return self._panel_to_schema(model) if model else None

    async def list_panels(self, guild_id: int) -> list[TicketPanelSchema]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(TicketPanelModel)
                .where(TicketPanelModel.guild_id == guild_id)
                .order_by(TicketPanelModel.created_at.asc())
            )
            return [self._panel_to_schema(row) for row in result.scalars().all()]

    async def delete_panel(self, guild_id: int, panel_id: str) -> bool:
        async with self._session_factory() as session:
            result = await session.execute(
                delete(TicketPanelModel).where(
                    TicketPanelModel.guild_id == guild_id,
                    TicketPanelModel.id == panel_id,
                )
            )
            await session.commit()
            return bool(result.rowcount and result.rowcount > 0)

    async def next_ticket_number(self, guild_id: int) -> int:
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.max(TicketModel.ticket_number)).where(
                    TicketModel.guild_id == guild_id
                )
            )
            current_max = result.scalar_one_or_none()
            return int(current_max or 0) + 1

    async def create_ticket(self, ticket: TicketSchema) -> TicketSchema:
        async with self._session_factory() as session:
            model = TicketModel(
                id=ticket.id,
                guild_id=ticket.guild_id,
                panel_id=ticket.panel_id,
                ticket_number=ticket.ticket_number,
                channel_id=ticket.channel_id,
                opener_id=ticket.opener_id,
                claimed_by_id=ticket.claimed_by_id,
                closed_by_id=ticket.closed_by_id,
                department=ticket.department,
                priority=ticket.priority,
                status=ticket.status,
                participant_ids=list(ticket.participant_ids),
                form_answers=dict(ticket.form_answers),
                transcript_url=ticket.transcript_url,
                first_response_at=ticket.first_response_at,
                closed_at=ticket.closed_at,
                created_at=ticket.created_at,
                updated_at=ticket.updated_at,
            )
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return self._ticket_to_schema(model)

    async def update_ticket(self, ticket: TicketSchema) -> TicketSchema:
        ticket.updated_at = utc_now()
        async with self._session_factory() as session:
            result = await session.execute(
                select(TicketModel).where(
                    TicketModel.id == ticket.id,
                    TicketModel.guild_id == ticket.guild_id,
                )
            )
            model = result.scalar_one_or_none()
            if model is None:
                raise EntityNotFoundError(f"Ticket {ticket.id} não encontrado.")

            model.claimed_by_id = ticket.claimed_by_id
            model.closed_by_id = ticket.closed_by_id
            model.department = ticket.department
            model.priority = ticket.priority
            model.status = ticket.status
            model.participant_ids = list(ticket.participant_ids)
            model.form_answers = dict(ticket.form_answers)
            model.transcript_url = ticket.transcript_url
            model.first_response_at = ticket.first_response_at
            model.closed_at = ticket.closed_at
            model.updated_at = ticket.updated_at

            await session.commit()
            await session.refresh(model)
            return self._ticket_to_schema(model)

    async def get_ticket_by_id(self, guild_id: int, ticket_id: str) -> TicketSchema | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(TicketModel).where(
                    TicketModel.guild_id == guild_id,
                    TicketModel.id == ticket_id,
                )
            )
            model = result.scalar_one_or_none()
            return self._ticket_to_schema(model) if model else None

    async def get_ticket_by_channel(self, channel_id: int) -> TicketSchema | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(TicketModel).where(TicketModel.channel_id == channel_id)
            )
            model = result.scalar_one_or_none()
            return self._ticket_to_schema(model) if model else None

    async def list_tickets(
        self,
        guild_id: int,
        *,
        status: TicketStatus | None = None,
        opener_id: int | None = None,
        panel_id: str | None = None,
        limit: int = 50,
    ) -> list[TicketSchema]:
        async with self._session_factory() as session:
            stmt = select(TicketModel).where(TicketModel.guild_id == guild_id)
            if status is not None:
                stmt = stmt.where(TicketModel.status == status)
            if opener_id is not None:
                stmt = stmt.where(TicketModel.opener_id == opener_id)
            if panel_id is not None:
                stmt = stmt.where(TicketModel.panel_id == panel_id)

            stmt = stmt.order_by(TicketModel.created_at.desc()).limit(limit)
            result = await session.execute(stmt)
            return [self._ticket_to_schema(row) for row in result.scalars().all()]

    async def count_active_user_tickets(
        self,
        guild_id: int,
        panel_id: str,
        user_id: int,
    ) -> int:
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.count(TicketModel.id)).where(
                    TicketModel.guild_id == guild_id,
                    TicketModel.panel_id == panel_id,
                    TicketModel.opener_id == user_id,
                    TicketModel.status.in_(["open", "claimed"]),
                )
            )
            return int(result.scalar_one() or 0)

    async def count_open_guild_tickets(self, guild_id: int) -> int:
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.count(TicketModel.id)).where(
                    TicketModel.guild_id == guild_id,
                    TicketModel.status.in_(["open", "claimed"]),
                )
            )
            return int(result.scalar_one() or 0)

    async def get_last_user_ticket(
        self,
        guild_id: int,
        panel_id: str,
        user_id: int,
    ) -> TicketSchema | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(TicketModel)
                .where(
                    TicketModel.guild_id == guild_id,
                    TicketModel.panel_id == panel_id,
                    TicketModel.opener_id == user_id,
                )
                .order_by(TicketModel.created_at.desc())
                .limit(1)
            )
            model = result.scalar_one_or_none()
            return self._ticket_to_schema(model) if model else None

    async def create_rating(self, rating: TicketRatingSchema) -> TicketRatingSchema:
        async with self._session_factory() as session:
            model = TicketRatingModel(
                id=rating.id,
                guild_id=rating.guild_id,
                ticket_id=rating.ticket_id,
                panel_id=rating.panel_id,
                user_id=rating.user_id,
                staff_id=rating.staff_id,
                stars=rating.stars,
                comment=rating.comment,
                created_at=rating.created_at,
            )
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return self._rating_to_schema(model)

    async def get_rating_by_ticket(self, ticket_id: str) -> TicketRatingSchema | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(TicketRatingModel).where(TicketRatingModel.ticket_id == ticket_id)
            )
            model = result.scalar_one_or_none()
            return self._rating_to_schema(model) if model else None

    async def get_staff_rating_stats(
        self,
        guild_id: int,
        staff_id: int | None = None,
    ) -> list[dict[str, float | int]]:
        async with self._session_factory() as session:
            stmt = (
                select(
                    TicketRatingModel.staff_id,
                    func.count(TicketRatingModel.id).label("total"),
                    func.avg(TicketRatingModel.stars).label("average"),
                )
                .where(
                    TicketRatingModel.guild_id == guild_id,
                    TicketRatingModel.staff_id.is_not(None),
                )
                .group_by(TicketRatingModel.staff_id)
            )
            if staff_id is not None:
                stmt = stmt.where(TicketRatingModel.staff_id == staff_id)

            result = await session.execute(stmt)
            return [
                {
                    "staff_id": int(row.staff_id),
                    "total": int(row.total),
                    "average": round(float(row.average), 2),
                }
                for row in result.all()
                if row.staff_id is not None
            ]


class SQLAutomationRepository(IAutomationRepository):
    """Repositório SQL para mensagens automáticas, personalizadas e agendamentos."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _to_schema(model: AutomationRuleModel) -> AutomationRuleSchema:
        schedule = ScheduleConfigSchema.model_validate(model.schedule)
        if model.next_run_at is not None:
            schedule.next_run_at = _ensure_utc(model.next_run_at)
        if schedule.last_run_at is not None:
            schedule.last_run_at = _ensure_utc(schedule.last_run_at)
        if schedule.run_at is not None:
            schedule.run_at = _ensure_utc(schedule.run_at)

        return AutomationRuleSchema(
            id=model.id,
            guild_id=model.guild_id,
            name=model.name,
            automation_type=cast(AutomationType, model.automation_type),
            enabled=model.enabled,
            target_channel_id=model.target_channel_id,
            published_channel_id=model.published_channel_id,
            published_message_id=model.published_message_id,
            content=model.content,
            mention_role_ids=list(model.mention_role_ids or []),
            mention_everyone=model.mention_everyone,
            use_embed=model.use_embed,
            embed=EmbedConfigSchema.model_validate(model.embed),
            buttons=[CustomButtonSchema.model_validate(b) for b in (model.buttons or [])],
            dropdowns=[CustomDropdownSchema.model_validate(d) for d in (model.dropdowns or [])],
            schedule=schedule,
            created_at=_ensure_utc(model.created_at) or utc_now(),
            updated_at=_ensure_utc(model.updated_at) or utc_now(),
        )

    async def create_automation(self, rule: AutomationRuleSchema) -> AutomationRuleSchema:
        async with self._session_factory() as session:
            model = AutomationRuleModel(
                id=rule.id,
                guild_id=rule.guild_id,
                name=rule.name,
                automation_type=rule.automation_type,
                enabled=rule.enabled,
                target_channel_id=rule.target_channel_id,
                published_channel_id=rule.published_channel_id,
                published_message_id=rule.published_message_id,
                content=rule.content,
                mention_role_ids=list(rule.mention_role_ids),
                mention_everyone=rule.mention_everyone,
                use_embed=rule.use_embed,
                embed=rule.embed.model_dump(),
                buttons=[b.model_dump() for b in rule.buttons],
                dropdowns=[d.model_dump() for d in rule.dropdowns],
                schedule=rule.schedule.model_dump(mode="json"),
                next_run_at=rule.schedule.next_run_at,
                created_at=rule.created_at,
                updated_at=rule.updated_at,
            )
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return self._to_schema(model)

    async def update_automation(self, rule: AutomationRuleSchema) -> AutomationRuleSchema:
        rule.updated_at = utc_now()
        async with self._session_factory() as session:
            result = await session.execute(
                select(AutomationRuleModel).where(
                    AutomationRuleModel.id == rule.id,
                    AutomationRuleModel.guild_id == rule.guild_id,
                )
            )
            model = result.scalar_one_or_none()
            if model is None:
                raise EntityNotFoundError(f"Automação {rule.id} não encontrada.")

            model.name = rule.name
            model.automation_type = rule.automation_type
            model.enabled = rule.enabled
            model.target_channel_id = rule.target_channel_id
            model.published_channel_id = rule.published_channel_id
            model.published_message_id = rule.published_message_id
            model.content = rule.content
            model.mention_role_ids = list(rule.mention_role_ids)
            model.mention_everyone = rule.mention_everyone
            model.use_embed = rule.use_embed
            model.embed = rule.embed.model_dump()
            model.buttons = [b.model_dump() for b in rule.buttons]
            model.dropdowns = [d.model_dump() for d in rule.dropdowns]
            model.schedule = rule.schedule.model_dump(mode="json")
            model.next_run_at = rule.schedule.next_run_at
            model.updated_at = rule.updated_at

            await session.commit()
            await session.refresh(model)
            return self._to_schema(model)

    async def get_automation(self, guild_id: int, automation_id: str) -> AutomationRuleSchema | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(AutomationRuleModel).where(
                    AutomationRuleModel.guild_id == guild_id,
                    AutomationRuleModel.id == automation_id,
                )
            )
            model = result.scalar_one_or_none()
            return self._to_schema(model) if model else None

    async def get_automation_by_id_global(self, automation_id: str) -> AutomationRuleSchema | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(AutomationRuleModel).where(AutomationRuleModel.id == automation_id)
            )
            model = result.scalar_one_or_none()
            return self._to_schema(model) if model else None

    async def list_automations(
        self,
        guild_id: int,
        *,
        automation_type: AutomationType | None = None,
        enabled_only: bool = False,
    ) -> list[AutomationRuleSchema]:
        async with self._session_factory() as session:
            stmt = select(AutomationRuleModel).where(AutomationRuleModel.guild_id == guild_id)
            if automation_type is not None:
                stmt = stmt.where(AutomationRuleModel.automation_type == automation_type)
            if enabled_only:
                stmt = stmt.where(AutomationRuleModel.enabled.is_(True))

            stmt = stmt.order_by(AutomationRuleModel.created_at.asc())
            result = await session.execute(stmt)
            return [self._to_schema(row) for row in result.scalars().all()]

    async def get_due_scheduled_automations(self, now: datetime) -> list[AutomationRuleSchema]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(AutomationRuleModel).where(
                    AutomationRuleModel.enabled.is_(True),
                    AutomationRuleModel.next_run_at.is_not(None),
                    AutomationRuleModel.next_run_at <= now,
                )
            )
            return [self._to_schema(row) for row in result.scalars().all()]

    async def delete_automation(self, guild_id: int, automation_id: str) -> bool:
        async with self._session_factory() as session:
            result = await session.execute(
                delete(AutomationRuleModel).where(
                    AutomationRuleModel.guild_id == guild_id,
                    AutomationRuleModel.id == automation_id,
                )
            )
            await session.commit()
            return bool(result.rowcount and result.rowcount > 0)


class SQLLogRepository(ILogRepository):
    """Repositório SQL para registros de auditoria."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _to_schema(model: AuditLogModel) -> AuditLogSchema:
        return AuditLogSchema(
            id=model.id,
            guild_id=model.guild_id,
            category=cast(LogCategory, model.category),
            action=model.action,
            actor_id=model.actor_id,
            target_id=model.target_id,
            details=model.details,
            metadata=dict(model.metadata_json or {}),
            created_at=_ensure_utc(model.created_at) or utc_now(),
        )

    async def append_log(self, entry: AuditLogSchema) -> AuditLogSchema:
        async with self._session_factory() as session:
            model = AuditLogModel(
                id=entry.id,
                guild_id=entry.guild_id,
                category=entry.category,
                action=entry.action,
                actor_id=entry.actor_id,
                target_id=entry.target_id,
                details=entry.details,
                metadata_json=dict(entry.metadata),
                created_at=entry.created_at,
            )
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return self._to_schema(model)

    async def list_recent_logs(
        self,
        guild_id: int,
        *,
        category: LogCategory | None = None,
        limit: int = 15,
    ) -> list[AuditLogSchema]:
        async with self._session_factory() as session:
            stmt = select(AuditLogModel).where(AuditLogModel.guild_id == guild_id)
            if category is not None:
                stmt = stmt.where(AuditLogModel.category == category)

            stmt = stmt.order_by(AuditLogModel.created_at.desc()).limit(limit)
            result = await session.execute(stmt)
            return [self._to_schema(row) for row in result.scalars().all()]