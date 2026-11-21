"""Camada de persistência multi-provider (SQL e MongoDB) do Fusion Bot."""

from src.database.factory import create_database_provider
from src.database.interfaces.provider import IDatabaseProvider

__all__ = ["IDatabaseProvider", "create_database_provider"]