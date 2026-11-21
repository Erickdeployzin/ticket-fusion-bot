"""Provedor completo MongoDB utilizando PyMongo AsyncMongoClient."""

from __future__ import annotations

import time
from typing import Any

from pymongo import ASCENDING, DESCENDING, AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from src.core.config import Settings
from src.core.logger import get_logger
from src.database.interfaces.provider import IDatabaseProvider
from src.database.interfaces.repositories import (
    IAutomationRepository,
    IGuildRepository,
    ILogRepository,
    ITicketRepository,
)
from src.database.providers.mongo.repositories import (
    MongoAutomationRepository,
    MongoGuildRepository,
    MongoLogRepository,
    MongoTicketRepository,
)

logger = get_logger(__name__)


class MongoDatabaseProvider(IDatabaseProvider):
    """Provedor assíncrono nativo para MongoDB."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(
            settings.database_url,
            tz_aware=True,
        )
        self._db: AsyncDatabase[dict[str, Any]] = self._client[settings.mongo_database_name]

        self._guilds = MongoGuildRepository(self._db)
        self._tickets = MongoTicketRepository(self._db)
        self._automations = MongoAutomationRepository(self._db)
        self._logs = MongoLogRepository(self._db)

    @property
    def provider_name(self) -> str:
        return "mongodb"

    @property
    def guilds(self) -> IGuildRepository:
        return self._guilds

    @property
    def tickets(self) -> ITicketRepository:
        return self._tickets

    @property
    def automations(self) -> IAutomationRepository:
        return self._automations

    @property
    def logs(self) -> ILogRepository:
        return self._logs

    async def connect(self) -> None:
        """Valida conexão com MongoDB e cria índices únicos/compostos equivalentes ao SQL."""
        healthy, latency_ms = await self.healthcheck()
        if not healthy:
            raise RuntimeError("Falha no healthcheck inicial do MongoDB.")

        await self._ensure_indexes()
        logger.info(
            "Conexão MongoDB estabelecida com sucesso (db=%s, latência=%.2fms)",
            self._settings.mongo_database_name,
            latency_ms,
        )

    async def _ensure_indexes(self) -> None:
        """Cria índices para garantir performance em servidores grandes e integridade."""
        await self._db["guild_settings"].create_index([("guild_id", ASCENDING)], unique=True)
        await self._db["guild_counters"].create_index(
            [("guild_id", ASCENDING), ("counter", ASCENDING)], unique=True
        )

        await self._db["ticket_panels"].create_index(
            [("guild_id", ASCENDING), ("id", ASCENDING)], unique=True
        )
        await self._db["tickets"].create_index(
            [("guild_id", ASCENDING), ("id", ASCENDING)], unique=True
        )
        await self._db["tickets"].create_index(
            [("guild_id", ASCENDING), ("ticket_number", ASCENDING)], unique=True
        )
        await self._db["tickets"].create_index([("channel_id", ASCENDING)], unique=True)
        await self._db["tickets"].create_index(
            [("guild_id", ASCENDING), ("status", ASCENDING)]
        )
        await self._db["tickets"].create_index(
            [("guild_id", ASCENDING), ("panel_id", ASCENDING), ("opener_id", ASCENDING)]
        )

        await self._db["ticket_ratings"].create_index([("ticket_id", ASCENDING)], unique=True)
        await self._db["ticket_ratings"].create_index(
            [("guild_id", ASCENDING), ("staff_id", ASCENDING)]
        )

        await self._db["automation_rules"].create_index([("id", ASCENDING)], unique=True)
        await self._db["automation_rules"].create_index(
            [("guild_id", ASCENDING), ("automation_type", ASCENDING)]
        )
        await self._db["automation_rules"].create_index(
            [("enabled", ASCENDING), ("schedule.next_run_at", ASCENDING)]
        )

        await self._db["audit_logs"].create_index(
            [("guild_id", ASCENDING), ("created_at", DESCENDING)]
        )

    async def disconnect(self) -> None:
        """Fecha o cliente assíncrono do MongoDB."""
        await self._client.close()
        logger.info("Conexão MongoDB encerrada.")

    async def healthcheck(self) -> tuple[bool, float]:
        """Executa comando ping no MongoDB e mede latência."""
        start = time.perf_counter()
        try:
            await self._db.command("ping")
            elapsed_ms = (time.perf_counter() - start) * 1000
            return True, round(elapsed_ms, 2)
        except Exception:
            logger.exception("Falha no healthcheck do MongoDB.")
            return False, -1.0