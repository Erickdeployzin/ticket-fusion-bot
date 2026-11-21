"""Fixtures compartilhadas para testes unitários e de integração assíncronos."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import MagicMock

import discord
import pytest
from cryptography.fernet import Fernet

from src.core.config import Settings
from src.core.lifecycle import LockManager
from src.core.permissions import PermissionService
from src.database.factory import DatabaseFactory
from src.database.interfaces.provider import IDatabaseProvider
from src.services.placeholder_service import PlaceholderService


@pytest.fixture
def test_settings() -> Settings:
    """Configuração isolada em memória para execução rápida da suíte."""
    return Settings(
        discord_token="test-token-placeholder",
        discord_application_id=123456789012345678,
        db_backend="sqlite",
        sqlite_path=":memory:",
        fernet_key=Fernet.generate_key().decode("utf-8"),
        log_level="WARNING",
    )


@pytest.fixture
async def db(test_settings: Settings) -> AsyncGenerator[IDatabaseProvider, None]:
    """Provedor de banco de dados inicializado em memória e encerrado após cada teste."""
    provider = DatabaseFactory.create(test_settings)
    await provider.connect()
    try:
        yield provider
    finally:
        await provider.disconnect()


@pytest.fixture
def lock_manager() -> LockManager:
    return LockManager()


@pytest.fixture
def permission_service() -> PermissionService:
    return PermissionService()


@pytest.fixture
def placeholder_service() -> PlaceholderService:
    return PlaceholderService()


@pytest.fixture
def mock_guild() -> MagicMock:
    guild = MagicMock(spec=discord.Guild)
    guild.id = 987654321098765432
    guild.name = "Servidor Teste Fusion"
    guild.member_count = 142
    guild.members = []
    return guild


@pytest.fixture
def mock_member(mock_guild: MagicMock) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.id = 111222333444555666
    member.name = "erikdev"
    member.display_name = "Erik"
    member.mention = "<@111222333444555666>"
    member.guild = mock_guild
    member.created_at = datetime(2022, 5, 10, 14, 30, tzinfo=UTC)
    member.guild_permissions = discord.Permissions.none()

    default_role = MagicMock(spec=discord.Role)
    default_role.id = mock_guild.id
    member.roles = [default_role]
    return member