"""Contratos abstratos (ABCs) dos repositórios de dados."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.database.schemas import (
    AuditLogSchema,
    AutomationRuleSchema,
    AutomationType,
    GuildSettingsSchema,
    LogCategory,
    TicketPanelSchema,
    TicketRatingSchema,
    TicketSchema,
    TicketStatus,
)


class IGuildRepository(ABC):
    """Operações de persistência para configurações de servidores."""

    @abstractmethod
    async def get_or_create(self, guild_id: int) -> GuildSettingsSchema:
        """Retorna as configurações do servidor ou cria o registro padrão."""

    @abstractmethod
    async def save(self, settings: GuildSettingsSchema) -> GuildSettingsSchema:
        """Persiste alterações nas configurações do servidor."""

    @abstractmethod
    async def delete_guild_data(self, guild_id: int) -> None:
        """Remove configurações associadas a um servidor."""


class ITicketRepository(ABC):
    """Operações de persistência para painéis, tickets e avaliações."""

    # --- Painéis ---
    @abstractmethod
    async def create_panel(self, panel: TicketPanelSchema) -> TicketPanelSchema:
        """Cria um novo painel de tickets."""

    @abstractmethod
    async def update_panel(self, panel: TicketPanelSchema) -> TicketPanelSchema:
        """Atualiza um painel existente."""

    @abstractmethod
    async def get_panel(self, guild_id: int, panel_id: str) -> TicketPanelSchema | None:
        """Busca um painel específico isolado por guild_id."""

    @abstractmethod
    async def list_panels(self, guild_id: int) -> list[TicketPanelSchema]:
        """Lista todos os painéis configurados no servidor."""

    @abstractmethod
    async def delete_panel(self, guild_id: int, panel_id: str) -> bool:
        """Exclui um painel pelo ID."""

    # --- Tickets ---
    @abstractmethod
    async def next_ticket_number(self, guild_id: int) -> int:
        """Calcula de forma segura o próximo número sequencial de ticket do servidor."""

    @abstractmethod
    async def create_ticket(self, ticket: TicketSchema) -> TicketSchema:
        """Registra a abertura de um novo ticket."""

    @abstractmethod
    async def update_ticket(self, ticket: TicketSchema) -> TicketSchema:
        """Atualiza estado, responsável, prioridade ou fechamento de um ticket."""

    @abstractmethod
    async def get_ticket_by_id(self, guild_id: int, ticket_id: str) -> TicketSchema | None:
        """Busca ticket pelo UUID."""

    @abstractmethod
    async def get_ticket_by_channel(self, channel_id: int) -> TicketSchema | None:
        """Busca ticket associado a um canal de texto do Discord."""

    @abstractmethod
    async def list_tickets(
        self,
        guild_id: int,
        *,
        status: TicketStatus | None = None,
        opener_id: int | None = None,
        panel_id: str | None = None,
        limit: int = 50,
    ) -> list[TicketSchema]:
        """Lista tickets do servidor com filtros opcionais."""

    @abstractmethod
    async def count_active_user_tickets(
        self,
        guild_id: int,
        panel_id: str,
        user_id: int,
    ) -> int:
        """Conta quantos tickets abertos/assumidos o usuário possui no painel."""

    @abstractmethod
    async def count_open_guild_tickets(self, guild_id: int) -> int:
        """Conta o total de tickets ativos no servidor."""

    @abstractmethod
    async def get_last_user_ticket(
        self,
        guild_id: int,
        panel_id: str,
        user_id: int,
    ) -> TicketSchema | None:
        """Retorna o ticket mais recente do usuário no painel para checagem de cooldown."""

    # --- Avaliações ---
    @abstractmethod
    async def create_rating(self, rating: TicketRatingSchema) -> TicketRatingSchema:
        """Salva uma avaliação de atendimento."""

    @abstractmethod
    async def get_rating_by_ticket(self, ticket_id: str) -> TicketRatingSchema | None:
        """Verifica se um ticket já foi avaliado."""

    @abstractmethod
    async def get_staff_rating_stats(
        self,
        guild_id: int,
        staff_id: int | None = None,
    ) -> list[dict[str, float | int]]:
        """Retorna média de estrelas e total de atendimentos avaliados por atendente."""


class IAutomationRepository(ABC):
    """Operações de persistência para mensagens personalizadas e automações."""

    @abstractmethod
    async def create_automation(self, rule: AutomationRuleSchema) -> AutomationRuleSchema:
        """Cria uma nova regra de automação ou mensagem personalizada."""

    @abstractmethod
    async def update_automation(self, rule: AutomationRuleSchema) -> AutomationRuleSchema:
        """Atualiza uma automação existente."""

    @abstractmethod
    async def get_automation(self, guild_id: int, automation_id: str) -> AutomationRuleSchema | None:
        """Busca uma automação pelo ID isolado por guild_id."""

    @abstractmethod
    async def get_automation_by_id_global(self, automation_id: str) -> AutomationRuleSchema | None:
        """Busca automação pelo UUID para resolução de componentes persistentes."""

    @abstractmethod
    async def list_automations(
        self,
        guild_id: int,
        *,
        automation_type: AutomationType | None = None,
        enabled_only: bool = False,
    ) -> list[AutomationRuleSchema]:
        """Lista automações de um servidor."""

    @abstractmethod
    async def get_due_scheduled_automations(self, now: datetime) -> list[AutomationRuleSchema]:
        """Retorna todas as automações agendadas ativas com next_run_at <= now."""

    @abstractmethod
    async def delete_automation(self, guild_id: int, automation_id: str) -> bool:
        """Remove uma regra de automação."""


class ILogRepository(ABC):
    """Operações de persistência para histórico de auditoria."""

    @abstractmethod
    async def append_log(self, entry: AuditLogSchema) -> AuditLogSchema:
        """Grava um evento de auditoria."""

    @abstractmethod
    async def list_recent_logs(
        self,
        guild_id: int,
        *,
        category: LogCategory | None = None,
        limit: int = 15,
    ) -> list[AuditLogSchema]:
        """Retorna os eventos administrativos/operacionais mais recentes do servidor."""