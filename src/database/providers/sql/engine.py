"""Gerenciamento assíncrono de Engine e Sessões SQLAlchemy 2.x."""

from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from src.core.config import Settings


@event.listens_for(Engine, "connect")
def _configure_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    """Ativa WAL mode, foreign keys e busy_timeout em conexões SQLite."""
    module_name = type(dbapi_connection).__module__
    if "sqlite" in module_name:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.close()


def build_async_engine(settings: Settings) -> AsyncEngine:
    """Constrói o AsyncEngine otimizado para o dialeto SQL configurado."""
    kwargs: dict[str, Any] = {
        "echo": settings.db_echo,
        "future": True,
    }

    if settings.database_type == "sqlite":
        # NullPool evita contenção de conexões em arquivos SQLite locais
        kwargs["poolclass"] = NullPool
        kwargs["connect_args"] = {"timeout": 15}
    else:
        kwargs["pool_size"] = settings.db_pool_size
        kwargs["max_overflow"] = settings.db_max_overflow
        kwargs["pool_pre_ping"] = True
        kwargs["pool_recycle"] = 1800

    return create_async_engine(settings.database_url, **kwargs)


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Cria a fábrica de sessões assíncronas sem expiração automática pós-commit."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )