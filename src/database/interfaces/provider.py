"""Contrato principal do provedor de banco de dados."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.database.interfaces.repositories import (
    IAutomationRepository,
    IGuildRepository,
    ILogRepository,
    ITicketRepository,
)


class IDatabaseProvider(ABC):
    """Abstração de conexão e acesso aos repositórios de domínio."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Nome identificador do backend ativo (sqlite, postgresql, mysql, mongodb, etc.)."""

    @property
    @abstractmethod
    def guilds(self) -> IGuildRepository:
        """Repositório de configurações por servidor."""

    @property
    @abstractmethod
    def tickets(self) -> ITicketRepository:
        """Repositório de painéis, tickets e avaliações."""

    @property
    @abstractmethod
    def automations(self) -> IAutomationRepository:
        """Repositório de mensagens personalizadas e agendamentos."""

    @property
    @abstractmethod
    def logs(self) -> ILogRepository:
        """Repositório de logs de auditoria."""

    @abstractmethod
    async def connect(self) -> None:
        """Inicializa conexões, pools, tabelas ou índices."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Encerra conexões e libera recursos de forma limpa."""

    @abstractmethod
    async def healthcheck(self) -> tuple[bool, float]:
        """Verifica saúde do banco e retorna (saudável, latência_ms)."""