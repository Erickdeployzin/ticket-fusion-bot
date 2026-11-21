"""Fábrica responsável por instanciar o provedor de banco de dados configurado."""

from __future__ import annotations

from src.core.config import Settings
from src.core.exceptions import ConfigurationError
from src.database.interfaces.provider import IDatabaseProvider
from src.database.providers.mongo.provider import MongoDatabaseProvider
from src.database.providers.sql.provider import SQLDatabaseProvider


def create_database_provider(
    settings: Settings,
    *,
    auto_create_tables: bool = True,
) -> IDatabaseProvider:
    """Instancia o provider apropriado conforme DATABASE_TYPE no ambiente."""
    if settings.is_sql:
        return SQLDatabaseProvider(settings, auto_create_tables=auto_create_tables)
    if settings.is_mongo:
        return MongoDatabaseProvider(settings)

    raise ConfigurationError(f"Tipo de banco de dados não suportado: {settings.database_type}")


class DatabaseFactory:
    """Wrapper estático para criação do provedor de banco de dados."""

    @staticmethod
    def create(
        settings: Settings,
        *,
        auto_create_tables: bool = True,
    ) -> IDatabaseProvider:
        return create_database_provider(
            settings,
            auto_create_tables=auto_create_tables,
        )