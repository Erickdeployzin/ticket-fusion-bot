"""Gerenciamento e validação de configurações via variáveis de ambiente."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core.exceptions import ConfigurationError

DatabaseType = Literal["sqlite", "mysql", "mariadb", "postgresql", "mongodb"]
EnvironmentType = Literal["development", "staging", "production"]
LogFormatType = Literal["console", "json"]


class Settings(BaseSettings):
    """Configurações tipadas e validadas carregadas a partir do ambiente / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Discord
    discord_token: SecretStr = Field(..., description="Token de autenticação do bot Discord.")
    discord_application_id: int = Field(..., gt=0, description="Application ID do bot.")
    dev_guild_id: int | None = Field(
        default=None,
        description="ID opcional de guild para sync rápido de comandos em desenvolvimento.",
    )

    # Escalabilidade / Sharding
    auto_sharding: bool = Field(default=True, description="Habilita AutoShardedBot.")
    shard_count: int | None = Field(default=None, ge=1, description="Quantidade fixa de shards.")

    # Banco de Dados Multi-Provider
    database_type: DatabaseType = Field(default="sqlite")
    database_url: str = Field(default="sqlite+aiosqlite:///./data/fusion_bot.db")
    mongo_database_name: str = Field(default="fusion_bot", min_length=1)
    db_pool_size: int = Field(default=10, ge=1, le=100)
    db_max_overflow: int = Field(default=20, ge=0, le=200)
    db_echo: bool = Field(default=False)

    # Redis Opcional
    redis_url: str | None = Field(default=None)

    # Ambiente e Logs
    environment: EnvironmentType = Field(default="production")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(default="INFO")
    log_format: LogFormatType = Field(default="console")
    temp_dir: Path = Field(default=Path("./data/tmp"))

    @field_validator("dev_guild_id", "shard_count", mode="before")
    @classmethod
    def _empty_str_to_none(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator("redis_url", mode="before")
    @classmethod
    def _empty_redis_to_none(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @model_validator(mode="after")
    def _validate_database_compatibility(self) -> Settings:
        """Garante coerência entre DATABASE_TYPE e o driver informado em DATABASE_URL."""
        url = self.database_url.strip()
        expected_prefixes: dict[DatabaseType, tuple[str, ...]] = {
            "sqlite": ("sqlite+aiosqlite://",),
            "mysql": ("mysql+asyncmy://", "mysql+aiomysql://"),
            "mariadb": ("mariadb+asyncmy://", "mysql+asyncmy://"),
            "postgresql": ("postgresql+asyncpg://",),
            "mongodb": ("mongodb://", "mongodb+srv://"),
        }

        allowed = expected_prefixes[self.database_type]
        if not url.startswith(allowed):
            raise ConfigurationError(
                f"DATABASE_URL incompatível com DATABASE_TYPE='{self.database_type}'. "
                f"Prefixos assíncronos aceitos: {', '.join(allowed)}"
            )

        # Garante criação automática do diretório local para SQLite e arquivos temporários
        if self.database_type == "sqlite" and ":///" in url and ":memory:" not in url:
            raw_path = url.split(":///", maxsplit=1)[1]
            db_file = Path(raw_path)
            db_file.parent.mkdir(parents=True, exist_ok=True)

        self.temp_dir.mkdir(parents=True, exist_ok=True)
        return self

    @property
    def is_sql(self) -> bool:
        """Indica se o provider configurado é relacional (SQLAlchemy)."""
        return self.database_type in {"sqlite", "mysql", "mariadb", "postgresql"}

    @property
    def is_mongo(self) -> bool:
        """Indica se o provider configurado é MongoDB."""
        return self.database_type == "mongodb"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna a instância singleton validada das configurações."""
    return Settings()  # type: ignore[call-arg]