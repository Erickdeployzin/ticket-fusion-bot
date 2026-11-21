"""Modelos declarativos SQLAlchemy 2.x para persistência relacional."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.database.schemas import utc_now


class Base(DeclarativeBase):
    """Classe base declarativa para todos os modelos SQL."""


class GuildSettingsModel(Base):
    """Tabela de configurações isoladas por servidor Discord."""

    __tablename__ = "guild_settings"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    tickets_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    automations_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="pt-BR", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="America/Sao_Paulo", nullable=False)
    brand_color: Mapped[int] = mapped_column(Integer, default=0x5865F2, nullable=False)
    brand_footer: Mapped[str] = mapped_column(String(256), nullable=False)
    log_channels: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    default_ticket_category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    default_transcript_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    default_rating_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    permissions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class TicketPanelModel(Base):
    """Tabela de painéis configuráveis de atendimento."""

    __tablename__ = "ticket_panels"
    __table_args__ = (
        Index("ix_ticket_panels_guild_id", "guild_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    embed: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    open_mode: Mapped[str] = mapped_column(String(20), default="button", nullable=False)
    button_label: Mapped[str] = mapped_column(String(80), nullable=False)
    button_emoji: Mapped[str | None] = mapped_column(String(64), nullable=True)
    button_style: Mapped[str] = mapped_column(String(20), default="primary", nullable=False)
    dropdown_placeholder: Mapped[str] = mapped_column(String(150), nullable=False)
    departments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    staff_role_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    welcome_embed: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    max_tickets_per_user: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    allow_reopen: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enable_rating: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    form_fields: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    business_hours: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class TicketModel(Base):
    """Tabela de tickets individuais abertos pelos membros."""

    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("guild_id", "ticket_number", name="uq_tickets_guild_number"),
        Index("ix_tickets_guild_status", "guild_id", "status"),
        Index("ix_tickets_channel_id", "channel_id", unique=True),
        Index("ix_tickets_opener", "guild_id", "panel_id", "opener_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    panel_id: Mapped[str] = mapped_column(String(36), nullable=False)
    ticket_number: Mapped[int] = mapped_column(Integer, nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    opener_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    claimed_by_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    closed_by_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    department: Mapped[str] = mapped_column(String(100), default="Geral", nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    participant_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    form_answers: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    transcript_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    first_response_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class TicketRatingModel(Base):
    """Tabela de avaliações de atendimento."""

    __tablename__ = "ticket_ratings"
    __table_args__ = (
        UniqueConstraint("ticket_id", name="uq_ticket_ratings_ticket_id"),
        Index("ix_ticket_ratings_guild_staff", "guild_id", "staff_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ticket_id: Mapped[str] = mapped_column(String(36), nullable=False)
    panel_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    staff_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    stars: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class AutomationRuleModel(Base):
    """Tabela de mensagens automáticas, personalizadas e agendamentos."""

    __tablename__ = "automation_rules"
    __table_args__ = (
        Index("ix_automations_guild_type", "guild_id", "automation_type"),
        Index("ix_automations_enabled", "enabled"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    automation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    target_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    published_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    published_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    mention_role_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    mention_everyone: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    use_embed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    embed: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    buttons: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    dropdowns: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    schedule: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class AuditLogModel(Base):
    """Tabela de histórico de logs administrativos e operacionais."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_guild_created", "guild_id", "created_at"),
        Index("ix_audit_logs_guild_category", "guild_id", "category"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )