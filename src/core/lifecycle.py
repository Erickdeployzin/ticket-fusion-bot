"""Gerenciamento do ciclo de vida da aplicação, locks distribuídos/locais e estado."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from src.core.config import Settings
from src.core.logger import get_logger
from src.database.factory import create_database_provider
from src.database.interfaces.provider import IDatabaseProvider

logger = get_logger(__name__)


class LockManager:
    """Gerenciador de travas assíncronas com suporte opcional a Redis distribuído."""

    def __init__(self, redis_client: Any | None = None) -> None:
        self._redis = redis_client
        self._local_locks: dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    async def _get_local_lock(self, key: str) -> asyncio.Lock:
        async with self._guard:
            lock = self._local_locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._local_locks[key] = lock
            return lock

    @asynccontextmanager
    async def acquire(self, key: str, ttl_seconds: int = 15) -> AsyncIterator[None]:
        """Adquire trava exclusiva por chave (ex: prevenção de ticket duplicado)."""
        if self._redis is not None:
            lock = self._redis.lock(f"fusion:lock:{key}", timeout=ttl_seconds, blocking_timeout=10)
            acquired = await lock.acquire()
            try:
                if not acquired:
                    raise TimeoutError(f"Timeout ao aguardar trava distribuída: {key}")
                yield
            finally:
                if acquired:
                    try:
                        await lock.release()
                    except Exception:
                        logger.debug("Trava Redis já expirada para chave %s", key)
        else:
            local_lock = await self._get_local_lock(key)
            async with local_lock:
                yield


class AppContext:
    """Contêiner de dependências compartilhadas entre Cogs, Services e Tasks."""

    def __init__(self, settings: Settings) -> None:
        self.settings: Settings = settings
        self.db: IDatabaseProvider = create_database_provider(settings)
        self.redis: Any | None = None
        self.locks: LockManager = LockManager(None)
        self.started_at: datetime = datetime.now(UTC)

    async def startup(self) -> None:
        """Inicializa banco de dados e conexões auxiliares."""
        await self.db.connect()

        if self.settings.redis_url:
            try:
                import redis.asyncio as aioredis

                self.redis = aioredis.from_url(
                    self.settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                await self.redis.ping()
                self.locks = LockManager(self.redis)
                logger.info("Conexão Redis ativada para locks e cache distribuído.")
            except Exception:
                logger.exception(
                    "Falha ao conectar no Redis; operando em modo standalone (locks em memória)."
                )
                self.redis = None
                self.locks = LockManager(None)

    async def shutdown(self) -> None:
        """Libera conexões de forma ordenada no desligamento."""
        if self.redis is not None:
            await self.redis.aclose()
            logger.info("Conexão Redis encerrada.")
        await self.db.disconnect()