"""Provedor completo SQLAlchemy 2.x para SQLite, MySQL, MariaDB e PostgreSQL."""

from __future__ import annotations

import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.config import Settings
from src.core.logger import get_logger
from src.database.interfaces.provider import IDatabaseProvider
from src.database.interfaces.repositories import (
    IAutomationRepository,
    IGuildRepository,
    ILogRepository,
    ITicketRepository,
)
from src.database.providers.sql.engine import build_async_engine, build_session_factory
from src.database.providers.sql.models import Base
from src.database.providers.sql.repositories import (
    SQLAutomationRepository,
    SQLGuildRepository,
    SQLLogRepository,
    SQLTicketRepository,
)

logger = get_logger(__name__)


class SQLDatabaseProvider(IDatabaseProvider):
    """Provedor unificado para todos os bancos relacionais suportados."""

    def __init__(self, settings: Settings, *, auto_create_tables: bool = True) -> None:
        self._settings = settings
        self._auto_create_tables = auto_create_tables
        self._engine: AsyncEngine = build_async_engine(settings)
        self._session_factory: async_sessionmaker[AsyncSession] = build_session_factory(
            self._engine
        )

        self._guilds = SQLGuildRepository(self._session_factory)
        self._tickets = SQLTicketRepository(self._session_factory)
        self._automations = SQLAutomationRepository(self._session_factory)
        self._logs = SQLLogRepository(self._session_factory)

    @property
    def provider_name(self) -> str:
        return self._settings.database_type

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
        """Valida a conexão SQL e garante a existência do schema quando habilitado."""
        if self._auto_create_tables:
            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        healthy, latency_ms = await self.healthcheck()
        if not healthy:
            raise RuntimeError(f"Falha no healthcheck inicial do banco ({self.provider_name}).")

        logger.info(
            "Conexão SQL estabelecida com sucesso (provider=%s, latência=%.2fms)",
            self.provider_name,
            latency_ms,
        )

    async def disconnect(self) -> None:
        """Encerra o pool de conexões SQLAlchemy."""
        await self._engine.dispose()
        logger.info("Pool de conexões SQL (%s) encerrado.", self.provider_name)

    async def healthcheck(self) -> tuple[bool, float]:
        """Executa SELECT 1 para medir disponibilidade e latência."""
        start = time.perf_counter()
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            elapsed_ms = (time.perf_counter() - start) * 1000
            return True, round(elapsed_ms, 2)
        except Exception:
            logger.exception("Falha no healthcheck do banco SQL (%s).", self.provider_name)
            return False, -1.0