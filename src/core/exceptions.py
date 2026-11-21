"""Hierarquia centralizada de exceções do Fusion Bot.

Permite separar erros esperados de domínio/permissão (que geram feedback limpo
ao usuário no Discord) de falhas internas críticas (que acionam logs e alertas).
"""

from __future__ import annotations


class FusionBotError(Exception):
    """Exceção base para todos os erros controlados da aplicação."""

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.user_message = user_message or message


class ConfigurationError(FusionBotError):
    """Erro de configuração de infraestrutura ou variáveis de ambiente inválidas."""


class DatabaseError(FusionBotError):
    """Erro na camada de persistência, conexão ou integridade de dados."""


class EntityNotFoundError(DatabaseError):
    """Registro solicitado não encontrado ou não pertence ao servidor (guild_id)."""


class DuplicateEntityError(DatabaseError):
    """Tentativa de criar um registro duplicado violando restrições de unicidade."""


class PermissionDeniedError(FusionBotError):
    """O usuário não possui permissão granular para executar a ação no módulo."""


class ValidationError(FusionBotError):
    """Dados fornecidos pelo usuário ou administrador falharam na validação."""


class TicketOperationError(FusionBotError):
    """Falha controlada durante operações do ciclo de vida de um ticket."""


class AutomationOperationError(FusionBotError):
    """Falha controlada na criação, validação ou disparo de uma automação."""


class ExternalServiceError(FusionBotError):
    """Falha de comunicação com serviços externos (API do Discord, Redis, etc.)."""