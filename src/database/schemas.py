"""Schemas de domínio (DTOs) agnósticos ao banco de dados.

Todas as camadas acima de `src/database/` manipulam exclusivamente estas
estruturas tipadas, garantindo que SQLite, MySQL, MariaDB, PostgreSQL e
MongoDB sejam 100% intercambiáveis.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

BotModule = Literal["tickets", "automations", "administration", "logs"]
TicketStatus = Literal["open", "claimed", "closed", "archived"]
TicketPriority = Literal["low", "normal", "high", "urgent"]
AutomationType = Literal[
    "welcome",
    "goodbye",
    "scheduled",
    "periodic",
    "announcement",
    "custom",
]
ScheduleFrequency = Literal["once", "daily", "weekly", "interval"]
ButtonStyleType = Literal["primary", "secondary", "success", "danger", "link"]
ButtonActionType = Literal[
    "link",
    "toggle_role",
    "add_role",
    "remove_role",
    "send_ephemeral",
    "open_ticket_panel",
]
LogCategory = Literal["tickets", "automations", "administration", "errors"]


def utc_now() -> datetime:
    """Retorna o timestamp atual timezone-aware em UTC."""
    return datetime.now(UTC)


def new_uuid() -> str:
    """Gera um identificador único UUID4 em string."""
    return str(uuid4())


class EmbedFieldSchema(BaseModel):
    """Campo individual de uma embed do Discord."""

    name: str = Field(..., min_length=1, max_length=256)
    value: str = Field(..., min_length=1, max_length=1024)
    inline: bool = Field(default=False)


class EmbedConfigSchema(BaseModel):
    """Configuração visual completa e serializável de uma embed."""

    title: str | None = Field(default=None, max_length=256)
    description: str | None = Field(default=None, max_length=4096)
    color: int = Field(default=0x5865F2, ge=0, le=0xFFFFFF)
    url: str | None = Field(default=None, max_length=512)
    author_name: str | None = Field(default=None, max_length=256)
    author_icon_url: str | None = Field(default=None, max_length=512)
    thumbnail_url: str | None = Field(default=None, max_length=512)
    image_url: str | None = Field(default=None, max_length=512)
    footer_text: str | None = Field(default=None, max_length=2048)
    footer_icon_url: str | None = Field(default=None, max_length=512)
    timestamp: bool = Field(default=False)
    fields: list[EmbedFieldSchema] = Field(default_factory=list, max_length=25)


class CustomButtonSchema(BaseModel):
    """Configuração de botão interativo ou de link anexado a uma mensagem."""

    id: str = Field(default_factory=new_uuid)
    label: str = Field(..., min_length=1, max_length=80)
    emoji: str | None = Field(default=None, max_length=64)
    style: ButtonStyleType = Field(default="secondary")
    action_type: ButtonActionType = Field(default="send_ephemeral")
    action_value: str = Field(default="", max_length=1024)
    required_role_ids: list[int] = Field(default_factory=list)
    row: int = Field(default=0, ge=0, le=4)


class DropdownOptionSchema(BaseModel):
    """Opção individual de um Select Menu personalizado."""

    label: str = Field(..., min_length=1, max_length=100)
    value: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=100)
    emoji: str | None = Field(default=None, max_length=64)
    action_type: ButtonActionType = Field(default="send_ephemeral")
    action_value: str = Field(default="", max_length=1024)


class CustomDropdownSchema(BaseModel):
    """Configuração de Select Menu (Dropdown) personalizado."""

    id: str = Field(default_factory=new_uuid)
    placeholder: str = Field(default="Selecione uma opção...", max_length=150)
    min_values: int = Field(default=1, ge=1, le=25)
    max_values: int = Field(default=1, ge=1, le=25)
    options: list[DropdownOptionSchema] = Field(default_factory=list, max_length=25)
    row: int = Field(default=1, ge=0, le=4)


class TicketFormFieldSchema(BaseModel):
    """Pergunta exibida via Modal antes da abertura do ticket."""

    id: str = Field(default_factory=new_uuid)
    label: str = Field(..., min_length=1, max_length=45)
    placeholder: str | None = Field(default=None, max_length=100)
    style: Literal["short", "paragraph"] = Field(default="short")
    required: bool = Field(default=True)
    min_length: int = Field(default=1, ge=0, le=4000)
    max_length: int = Field(default=500, ge=1, le=4000)


class TicketDepartmentOption(BaseModel):
    """Subdepartamento disponível quando o painel utiliza dropdown de seleção."""

    id: str = Field(default_factory=new_uuid)
    label: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=100)
    emoji: str | None = Field(default=None, max_length=64)
    category_id: int | None = Field(default=None)
    staff_role_ids: list[int] = Field(default_factory=list)


class BusinessHoursSchema(BaseModel):
    """Configuração de horário de atendimento e mensagem de ausência."""

    enabled: bool = Field(default=False)
    timezone: str = Field(default="America/Sao_Paulo")
    start_hour: int = Field(default=9, ge=0, le=23)
    end_hour: int = Field(default=18, ge=0, le=23)
    days_of_week: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    offline_message: str = Field(
        default=(
            "Nossa equipe está fora do horário de atendimento no momento. "
            "Sua solicitação foi registrada e responderemos assim que possível."
        ),
        max_length=1000,
    )


class ModulePermissionRule(BaseModel):
    """Lista de cargos e usuários autorizados para um módulo específico."""

    role_ids: list[int] = Field(default_factory=list)
    user_ids: list[int] = Field(default_factory=list)


class GuildSettingsSchema(BaseModel):
    """Configurações globais e isolamento por servidor (guild_id)."""

    guild_id: int = Field(..., gt=0)
    tickets_enabled: bool = Field(default=True)
    automations_enabled: bool = Field(default=True)
    language: str = Field(default="pt-BR")
    timezone: str = Field(default="America/Sao_Paulo")
    brand_color: int = Field(default=0x5865F2, ge=0, le=0xFFFFFF)
    brand_footer: str = Field(default="Fusion • Gestão Profissional", max_length=256)
    log_channels: dict[LogCategory, int | None] = Field(
        default_factory=lambda: {
            "tickets": None,
            "automations": None,
            "administration": None,
            "errors": None,
        }
    )
    default_ticket_category_id: int | None = Field(default=None)
    default_transcript_channel_id: int | None = Field(default=None)
    default_rating_channel_id: int | None = Field(default=None)
    permissions: dict[BotModule, ModulePermissionRule] = Field(
        default_factory=lambda: {
            "administration": ModulePermissionRule(),
            "tickets": ModulePermissionRule(),
            "automations": ModulePermissionRule(),
            "logs": ModulePermissionRule(),
        }
    )
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TicketPanelSchema(BaseModel):
    """Configuração completa de um painel de tickets independente."""

    id: str = Field(default_factory=new_uuid)
    guild_id: int = Field(..., gt=0)
    name: str = Field(..., min_length=1, max_length=100)
    enabled: bool = Field(default=True)
    embed: EmbedConfigSchema = Field(
        default_factory=lambda: EmbedConfigSchema(
            title="Central de Atendimento",
            description="Clique no botão abaixo para iniciar um atendimento privado com nossa equipe.",
        )
    )
    open_mode: Literal["button", "dropdown"] = Field(default="button")
    button_label: str = Field(default="Abrir Ticket", max_length=80)
    button_emoji: str | None = Field(default="🎫", max_length=64)
    button_style: Literal["primary", "secondary", "success", "danger"] = Field(default="primary")
    dropdown_placeholder: str = Field(default="Escolha o departamento...", max_length=150)
    departments: list[TicketDepartmentOption] = Field(default_factory=list, max_length=25)
    category_id: int | None = Field(default=None)
    staff_role_ids: list[int] = Field(default_factory=list)
    channel_id: int | None = Field(default=None)
    message_id: int | None = Field(default=None)
    welcome_embed: EmbedConfigSchema = Field(
        default_factory=lambda: EmbedConfigSchema(
            title="Atendimento Iniciado",
            description=(
                "Olá {user}, descreva detalhadamente sua solicitação. "
                "Um membro da equipe assumirá seu atendimento em breve."
            ),
        )
    )
    max_tickets_per_user: int = Field(default=1, ge=1, le=10)
    cooldown_seconds: int = Field(default=30, ge=0, le=86400)
    allow_reopen: bool = Field(default=True)
    enable_rating: bool = Field(default=True)
    form_fields: list[TicketFormFieldSchema] = Field(default_factory=list, max_length=5)
    business_hours: BusinessHoursSchema = Field(default_factory=BusinessHoursSchema)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TicketSchema(BaseModel):
    """Registro persistente de um ticket individual."""

    id: str = Field(default_factory=new_uuid)
    guild_id: int = Field(..., gt=0)
    panel_id: str
    ticket_number: int = Field(..., ge=1)
    channel_id: int = Field(..., gt=0)
    opener_id: int = Field(..., gt=0)
    claimed_by_id: int | None = Field(default=None)
    closed_by_id: int | None = Field(default=None)
    department: str = Field(default="Geral", max_length=100)
    priority: TicketPriority = Field(default="normal")
    status: TicketStatus = Field(default="open")
    participant_ids: list[int] = Field(default_factory=list)
    form_answers: dict[str, str] = Field(default_factory=dict)
    transcript_url: str | None = Field(default=None)
    first_response_at: datetime | None = Field(default=None)
    closed_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TicketRatingSchema(BaseModel):
    """Avaliação enviada pelo usuário após o encerramento de um ticket."""

    id: str = Field(default_factory=new_uuid)
    guild_id: int = Field(..., gt=0)
    ticket_id: str
    panel_id: str
    user_id: int = Field(..., gt=0)
    staff_id: int | None = Field(default=None)
    stars: int = Field(..., ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)
    created_at: datetime = Field(default_factory=utc_now)


class ScheduleConfigSchema(BaseModel):
    """Configuração de agendamento e periodicidade de mensagens."""

    enabled: bool = Field(default=False)
    frequency: ScheduleFrequency = Field(default="once")
    timezone: str = Field(default="America/Sao_Paulo")
    run_at: datetime | None = Field(default=None)
    time_of_day: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    days_of_week: list[int] = Field(default_factory=list)
    interval_minutes: int | None = Field(default=None, ge=5, le=43200)
    max_runs: int | None = Field(default=None, ge=1)
    run_count: int = Field(default=0, ge=0)
    last_run_at: datetime | None = Field(default=None)
    next_run_at: datetime | None = Field(default=None)


class AutomationRuleSchema(BaseModel):
    """Automação de mensagem personalizada, evento de membro ou agendamento."""

    id: str = Field(default_factory=new_uuid)
    guild_id: int = Field(..., gt=0)
    name: str = Field(..., min_length=1, max_length=100)
    automation_type: AutomationType = Field(default="custom")
    enabled: bool = Field(default=True)
    target_channel_id: int | None = Field(default=None)
    published_channel_id: int | None = Field(default=None)
    published_message_id: int | None = Field(default=None)
    content: str | None = Field(default=None, max_length=2000)
    mention_role_ids: list[int] = Field(default_factory=list)
    mention_everyone: bool = Field(default=False)
    use_embed: bool = Field(default=True)
    embed: EmbedConfigSchema = Field(default_factory=EmbedConfigSchema)
    buttons: list[CustomButtonSchema] = Field(default_factory=list, max_length=20)
    dropdowns: list[CustomDropdownSchema] = Field(default_factory=list, max_length=4)
    schedule: ScheduleConfigSchema = Field(default_factory=ScheduleConfigSchema)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AuditLogSchema(BaseModel):
    """Registro de auditoria administrativa e operacional."""

    id: str = Field(default_factory=new_uuid)
    guild_id: int = Field(..., gt=0)
    category: LogCategory
    action: str = Field(..., min_length=1, max_length=100)
    actor_id: int | None = Field(default=None)
    target_id: str | None = Field(default=None, max_length=128)
    details: str = Field(..., max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)