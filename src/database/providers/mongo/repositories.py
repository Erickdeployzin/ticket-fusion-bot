"""Implementação MongoDB dos repositórios de domínio utilizando PyMongo Async."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from src.core.exceptions import EntityNotFoundError
from src.database.interfaces.repositories import (
    IAutomationRepository,
    IGuildRepository,
    ILogRepository,
    ITicketRepository,
)
from src.database.schemas import (
    AuditLogSchema,
    AutomationRuleSchema,
    AutomationType,
    GuildSettingsSchema,
    LogCategory,
    TicketPanelSchema,
    TicketRatingSchema,
    TicketSchema,
    TicketStatus,
    utc_now,
)


def _clean_doc(doc: dict[str, Any]) -> dict[str, Any]:
    """Remove `_id` interno do BSON antes da validação Pydantic."""
    cleaned = dict(doc)
    cleaned.pop("_id", None)
    return cleaned


def _normalize_mongo_dates(data: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    """Assegura que campos datetime vindos do BSON tenham tzinfo=UTC."""
    for field in fields:
        value = data.get(field)
        if isinstance(value, datetime) and value.tzinfo is None:
            data[field] = value.replace(tzinfo=UTC)
    return data


class MongoGuildRepository(IGuildRepository):
    """Repositório MongoDB para configurações por servidor."""

    def __init__(self, db: AsyncDatabase[dict[str, Any]]) -> None:
        self._col = db["guild_settings"]

    async def get_or_create(self, guild_id: int) -> GuildSettingsSchema:
        doc = await self._col.find_one({"guild_id": guild_id})
        if doc is not None:
            cleaned = _normalize_mongo_dates(_clean_doc(doc), ("created_at", "updated_at"))
            return GuildSettingsSchema.model_validate(cleaned)

        default_schema = GuildSettingsSchema(guild_id=guild_id)
        payload = default_schema.model_dump(mode="python")
        await self._col.update_one(
            {"guild_id": guild_id},
            {"$setOnInsert": payload},
            upsert=True,
        )
        created = await self._col.find_one({"guild_id": guild_id})
        assert created is not None
        cleaned = _normalize_mongo_dates(_clean_doc(created), ("created_at", "updated_at"))
        return GuildSettingsSchema.model_validate(cleaned)

    async def save(self, settings: GuildSettingsSchema) -> GuildSettingsSchema:
        settings.updated_at = utc_now()
        payload = settings.model_dump(mode="python")
        await self._col.replace_one(
            {"guild_id": settings.guild_id},
            payload,
            upsert=True,
        )
        return settings

    async def delete_guild_data(self, guild_id: int) -> None:
        await self._col.delete_many({"guild_id": guild_id})


class MongoTicketRepository(ITicketRepository):
    """Repositório MongoDB para painéis, tickets, contadores atômicos e avaliações."""

    def __init__(self, db: AsyncDatabase[dict[str, Any]]) -> None:
        self._panels = db["ticket_panels"]
        self._tickets = db["tickets"]
        self._ratings = db["ticket_ratings"]
        self._counters = db["guild_counters"]

    async def create_panel(self, panel: TicketPanelSchema) -> TicketPanelSchema:
        await self._panels.insert_one(panel.model_dump(mode="python"))
        return panel

    async def update_panel(self, panel: TicketPanelSchema) -> TicketPanelSchema:
        panel.updated_at = utc_now()
        result = await self._panels.replace_one(
            {"guild_id": panel.guild_id, "id": panel.id},
            panel.model_dump(mode="python"),
        )
        if result.matched_count == 0:
            raise EntityNotFoundError(f"Painel {panel.id} não encontrado na guild {panel.guild_id}.")
        return panel

    async def get_panel(self, guild_id: int, panel_id: str) -> TicketPanelSchema | None:
        doc = await self._panels.find_one({"guild_id": guild_id, "id": panel_id})
        if doc is None:
            return None
        cleaned = _normalize_mongo_dates(_clean_doc(doc), ("created_at", "updated_at"))
        return TicketPanelSchema.model_validate(cleaned)

    async def list_panels(self, guild_id: int) -> list[TicketPanelSchema]:
        cursor = self._panels.find({"guild_id": guild_id}).sort("created_at", ASCENDING)
        items: list[TicketPanelSchema] = []
        async for doc in cursor:
            cleaned = _normalize_mongo_dates(_clean_doc(doc), ("created_at", "updated_at"))
            items.append(TicketPanelSchema.model_validate(cleaned))
        return items

    async def delete_panel(self, guild_id: int, panel_id: str) -> bool:
        result = await self._panels.delete_one({"guild_id": guild_id, "id": panel_id})
        return result.deleted_count > 0

    async def next_ticket_number(self, guild_id: int) -> int:
        """Incremento atômico via find_one_and_update para evitar colisão em concorrência."""
        doc = await self._counters.find_one_and_update(
            {"guild_id": guild_id, "counter": "tickets"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return int(doc["seq"])

    async def create_ticket(self, ticket: TicketSchema) -> TicketSchema:
        await self._tickets.insert_one(ticket.model_dump(mode="python"))
        return ticket

    async def update_ticket(self, ticket: TicketSchema) -> TicketSchema:
        ticket.updated_at = utc_now()
        result = await self._tickets.replace_one(
            {"guild_id": ticket.guild_id, "id": ticket.id},
            ticket.model_dump(mode="python"),
        )
        if result.matched_count == 0:
            raise EntityNotFoundError(f"Ticket {ticket.id} não encontrado.")
        return ticket

    async def get_ticket_by_id(self, guild_id: int, ticket_id: str) -> TicketSchema | None:
        doc = await self._tickets.find_one({"guild_id": guild_id, "id": ticket_id})
        if doc is None:
            return None
        cleaned = _normalize_mongo_dates(
            _clean_doc(doc), ("created_at", "updated_at", "first_response_at", "closed_at")
        )
        return TicketSchema.model_validate(cleaned)

    async def get_ticket_by_channel(self, channel_id: int) -> TicketSchema | None:
        doc = await self._tickets.find_one({"channel_id": channel_id})
        if doc is None:
            return None
        cleaned = _normalize_mongo_dates(
            _clean_doc(doc), ("created_at", "updated_at", "first_response_at", "closed_at")
        )
        return TicketSchema.model_validate(cleaned)

    async def list_tickets(
        self,
        guild_id: int,
        *,
        status: TicketStatus | None = None,
        opener_id: int | None = None,
        panel_id: str | None = None,
        limit: int = 50,
    ) -> list[TicketSchema]:
        query: dict[str, Any] = {"guild_id": guild_id}
        if status is not None:
            query["status"] = status
        if opener_id is not None:
            query["opener_id"] = opener_id
        if panel_id is not None:
            query["panel_id"] = panel_id

        cursor = self._tickets.find(query).sort("created_at", DESCENDING).limit(limit)
        items: list[TicketSchema] = []
        async for doc in cursor:
            cleaned = _normalize_mongo_dates(
                _clean_doc(doc),
                ("created_at", "updated_at", "first_response_at", "closed_at"),
            )
            items.append(TicketSchema.model_validate(cleaned))
        return items

    async def count_active_user_tickets(
        self,
        guild_id: int,
        panel_id: str,
        user_id: int,
    ) -> int:
        return await self._tickets.count_documents(
            {
                "guild_id": guild_id,
                "panel_id": panel_id,
                "opener_id": user_id,
                "status": {"$in": ["open", "claimed"]},
            }
        )

    async def count_open_guild_tickets(self, guild_id: int) -> int:
        return await self._tickets.count_documents(
            {
                "guild_id": guild_id,
                "status": {"$in": ["open", "claimed"]},
            }
        )

    async def get_last_user_ticket(
        self,
        guild_id: int,
        panel_id: str,
        user_id: int,
    ) -> TicketSchema | None:
        cursor = (
            self._tickets.find(
                {
                    "guild_id": guild_id,
                    "panel_id": panel_id,
                    "opener_id": user_id,
                }
            )
            .sort("created_at", DESCENDING)
            .limit(1)
        )
        docs = await cursor.to_list(length=1)
        if not docs:
            return None
        cleaned = _normalize_mongo_dates(
            _clean_doc(docs[0]),
            ("created_at", "updated_at", "first_response_at", "closed_at"),
        )
        return TicketSchema.model_validate(cleaned)

    async def create_rating(self, rating: TicketRatingSchema) -> TicketRatingSchema:
        await self._ratings.insert_one(rating.model_dump(mode="python"))
        return rating

    async def get_rating_by_ticket(self, ticket_id: str) -> TicketRatingSchema | None:
        doc = await self._ratings.find_one({"ticket_id": ticket_id})
        if doc is None:
            return None
        cleaned = _normalize_mongo_dates(_clean_doc(doc), ("created_at",))
        return TicketRatingSchema.model_validate(cleaned)

    async def get_staff_rating_stats(
        self,
        guild_id: int,
        staff_id: int | None = None,
    ) -> list[dict[str, float | int]]:
        match_stage: dict[str, Any] = {
            "guild_id": guild_id,
            "staff_id": {"$ne": None},
        }
        if staff_id is not None:
            match_stage["staff_id"] = staff_id

        pipeline: list[dict[str, Any]] = [
            {"$match": match_stage},
            {
                "$group": {
                    "_id": "$staff_id",
                    "total": {"$sum": 1},
                    "average": {"$avg": "$stars"},
                }
            },
        ]
        cursor = await self._ratings.aggregate(pipeline)
        results: list[dict[str, float | int]] = []
        async for row in cursor:
            if row["_id"] is not None:
                results.append(
                    {
                        "staff_id": int(row["_id"]),
                        "total": int(row["total"]),
                        "average": round(float(row["average"]), 2),
                    }
                )
        return results


class MongoAutomationRepository(IAutomationRepository):
    """Repositório MongoDB para mensagens personalizadas e agendamentos."""

    def __init__(self, db: AsyncDatabase[dict[str, Any]]) -> None:
        self._col = db["automation_rules"]

    @staticmethod
    def _parse(doc: dict[str, Any]) -> AutomationRuleSchema:
        cleaned = _normalize_mongo_dates(_clean_doc(doc), ("created_at", "updated_at"))
        schedule = cleaned.get("schedule")
        if isinstance(schedule, dict):
            _normalize_mongo_dates(schedule, ("run_at", "last_run_at", "next_run_at"))
        return AutomationRuleSchema.model_validate(cleaned)

    async def create_automation(self, rule: AutomationRuleSchema) -> AutomationRuleSchema:
        await self._col.insert_one(rule.model_dump(mode="python"))
        return rule

    async def update_automation(self, rule: AutomationRuleSchema) -> AutomationRuleSchema:
        rule.updated_at = utc_now()
        result = await self._col.replace_one(
            {"guild_id": rule.guild_id, "id": rule.id},
            rule.model_dump(mode="python"),
        )
        if result.matched_count == 0:
            raise EntityNotFoundError(f"Automação {rule.id} não encontrada.")
        return rule

    async def get_automation(self, guild_id: int, automation_id: str) -> AutomationRuleSchema | None:
        doc = await self._col.find_one({"guild_id": guild_id, "id": automation_id})
        return self._parse(doc) if doc else None

    async def get_automation_by_id_global(self, automation_id: str) -> AutomationRuleSchema | None:
        doc = await self._col.find_one({"id": automation_id})
        return self._parse(doc) if doc else None

    async def list_automations(
        self,
        guild_id: int,
        *,
        automation_type: AutomationType | None = None,
        enabled_only: bool = False,
    ) -> list[AutomationRuleSchema]:
        query: dict[str, Any] = {"guild_id": guild_id}
        if automation_type is not None:
            query["automation_type"] = automation_type
        if enabled_only:
            query["enabled"] = True

        cursor = self._col.find(query).sort("created_at", ASCENDING)
        return [self._parse(doc) async for doc in cursor]

    async def get_due_scheduled_automations(self, now: datetime) -> list[AutomationRuleSchema]:
        cursor = self._col.find(
            {
                "enabled": True,
                "schedule.next_run_at": {"$ne": None, "$lte": now},
            }
        )
        return [self._parse(doc) async for doc in cursor]

    async def delete_automation(self, guild_id: int, automation_id: str) -> bool:
        result = await self._col.delete_one({"guild_id": guild_id, "id": automation_id})
        return result.deleted_count > 0


class MongoLogRepository(ILogRepository):
    """Repositório MongoDB para registros de auditoria."""

    def __init__(self, db: AsyncDatabase[dict[str, Any]]) -> None:
        self._col = db["audit_logs"]

    async def append_log(self, entry: AuditLogSchema) -> AuditLogSchema:
        await self._col.insert_one(entry.model_dump(mode="python"))
        return entry

    async def list_recent_logs(
        self,
        guild_id: int,
        *,
        category: LogCategory | None = None,
        limit: int = 15,
    ) -> list[AuditLogSchema]:
        query: dict[str, Any] = {"guild_id": guild_id}
        if category is not None:
            query["category"] = category

        cursor = self._col.find(query).sort("created_at", DESCENDING).limit(limit)
        items: list[AuditLogSchema] = []
        async for doc in cursor:
            cleaned = _normalize_mongo_dates(_clean_doc(doc), ("created_at",))
            items.append(AuditLogSchema.model_validate(cleaned))
        return items