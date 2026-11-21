"""Serviço completo de regras de negócio do sistema profissional de tickets."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord

from src.bot.ui.embeds import create_panel_embed
from src.bot.ui.theme import Theme
from src.core.exceptions import (
    EntityNotFoundError,
    PermissionDeniedError,
    TicketOperationError,
    ValidationError,
)
from src.core.lifecycle import LockManager
from src.core.logger import get_logger
from src.core.permissions import PermissionService
from src.database.interfaces.provider import IDatabaseProvider
from src.database.schemas import (
    GuildSettingsSchema,
    TicketDepartmentOption,
    TicketPanelSchema,
    TicketPriority,
    TicketRatingSchema,
    TicketSchema,
    new_uuid,
    utc_now,
)
from src.services.log_service import LogService
from src.services.placeholder_service import PlaceholderContext, PlaceholderService
from src.services.transcript_service import TranscriptService

if TYPE_CHECKING:
    from src.bot.client import FusionBot

logger = get_logger(__name__)

PRIORITY_LABELS: dict[TicketPriority, str] = {
    "low": "🟢 Baixa",
    "normal": "🔵 Normal",
    "high": "🟠 Alta",
    "urgent": "🔴 Urgente",
}


class TicketService:
    """Orquestra painéis, abertura, atendimento, transcripts, fechamento e avaliações."""

    def __init__(
        self,
        bot: FusionBot,
        db: IDatabaseProvider,
        locks: LockManager,
        permissions: PermissionService,
        log_service: LogService,
        placeholders: PlaceholderService,
        transcripts: TranscriptService,
    ) -> None:
        self._bot = bot
        self._db = db
        self._locks = locks
        self._permissions = permissions
        self._logs = log_service
        self._placeholders = placeholders
        self._transcripts = transcripts
        self._notify_cooldowns: dict[str, datetime] = {}

    # ==========================================================================
    # GESTÃO DE PAINÉIS DE TICKETS
    # ==========================================================================

    async def create_panel(
        self,
        guild_id: int,
        actor_id: int,
        name: str,
        *,
        title: str | None = None,
        description: str | None = None,
    ) -> TicketPanelSchema:
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError("Nome do painel vazio.", user_message="Informe um nome para o painel.")

        settings = await self._db.guilds.get_or_create(guild_id)
        panel = TicketPanelSchema(
            guild_id=guild_id,
            name=clean_name[:100],
            category_id=settings.default_ticket_category_id,
        )
        panel.embed.color = settings.brand_color
        panel.embed.footer_text = settings.brand_footer
        if title:
            panel.embed.title = title[:256]
        if description:
            panel.embed.description = description[:4096]

        panel.welcome_embed.color = settings.brand_color
        panel.welcome_embed.footer_text = settings.brand_footer

        created = await self._db.tickets.create_panel(panel)
        await self._logs.record(
            guild_id=guild_id,
            category="tickets",
            action="panel.created",
            actor_id=actor_id,
            target_id=created.id,
            details=f"Painel de tickets **{created.name}** criado por <@{actor_id}>.",
        )
        return created

    async def duplicate_panel(
        self,
        guild_id: int,
        actor_id: int,
        panel_id: str,
    ) -> TicketPanelSchema:
        source = await self._db.tickets.get_panel(guild_id, panel_id)
        if source is None:
            raise EntityNotFoundError("Painel não encontrado.")

        clone_data = source.model_dump(mode="python")
        clone_data["id"] = new_uuid()
        clone_data["name"] = f"{source.name[:88]} (Cópia)"
        clone_data["channel_id"] = None
        clone_data["message_id"] = None
        clone_data["created_at"] = utc_now()
        clone_data["updated_at"] = utc_now()

        cloned = await self._db.tickets.create_panel(TicketPanelSchema.model_validate(clone_data))
        await self._logs.record(
            guild_id=guild_id,
            category="tickets",
            action="panel.duplicated",
            actor_id=actor_id,
            target_id=cloned.id,
            details=f"Painel **{source.name}** duplicado como **{cloned.name}**.",
        )
        return cloned

    async def save_panel(
        self,
        panel: TicketPanelSchema,
        actor_id: int,
        audit_detail: str,
    ) -> TicketPanelSchema:
        updated = await self._db.tickets.update_panel(panel)
        await self._logs.record(
            guild_id=panel.guild_id,
            category="tickets",
            action="panel.updated",
            actor_id=actor_id,
            target_id=panel.id,
            details=audit_detail,
        )
        return updated

    async def delete_panel(self, guild_id: int, actor_id: int, panel_id: str) -> None:
        panel = await self._db.tickets.get_panel(guild_id, panel_id)
        if panel is None:
            raise EntityNotFoundError("Painel não encontrado.")
        await self._db.tickets.delete_panel(guild_id, panel_id)
        await self._logs.record(
            guild_id=guild_id,
            category="tickets",
            action="panel.deleted",
            actor_id=actor_id,
            target_id=panel_id,
            details=f"Painel de tickets **{panel.name}** excluído por <@{actor_id}>.",
        )

    def build_panel_public_embed(
        self,
        guild: discord.Guild,
        panel: TicketPanelSchema,
        settings: GuildSettingsSchema,
    ) -> discord.Embed:
        ctx = PlaceholderContext(guild=guild, timezone=settings.timezone)
        return self._placeholders.build_embed(
            panel.embed,
            ctx,
            fallback_footer=settings.brand_footer,
        )

    async def publish_or_update_panel(
        self,
        guild: discord.Guild,
        panel: TicketPanelSchema,
        actor_id: int,
        target_channel: discord.TextChannel | None = None,
    ) -> TicketPanelSchema:
        """Publica o painel no canal escolhido ou atualiza a mensagem já publicada."""
        from src.bot.views.tickets.ticket_runtime_views import TicketPanelLauncherView

        settings = await self._db.guilds.get_or_create(guild.id)
        channel = target_channel
        if channel is None and panel.channel_id:
            resolved = guild.get_channel(panel.channel_id)
            if isinstance(resolved, discord.TextChannel):
                channel = resolved

        if channel is None:
            raise ValidationError(
                "Canal de destino não definido.",
                user_message="Selecione primeiro o **Canal de Publicação** deste painel.",
            )

        perms = channel.permissions_for(guild.me)
        if not (perms.send_messages and perms.embed_links):
            raise TicketOperationError(
                "Sem permissão no canal de destino.",
                user_message=f"Não possuo permissão de enviar mensagens/embeds em {channel.mention}.",
            )

        embed = self.build_panel_public_embed(guild, panel, settings)
        view = TicketPanelLauncherView(self._bot, panel)

        edited_existing = False
        if (
            panel.channel_id == channel.id
            and panel.message_id is not None
        ):
            try:
                existing_msg = await channel.fetch_message(panel.message_id)
                await existing_msg.edit(embed=embed, view=view)
                edited_existing = True
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                edited_existing = False

        if not edited_existing:
            sent_msg = await channel.send(embed=embed, view=view)
            panel.channel_id = channel.id
            panel.message_id = sent_msg.id

        saved = await self._db.tickets.update_panel(panel)
        action_verb = "atualizado" if edited_existing else "publicado"
        await self._logs.record(
            guild_id=guild.id,
            category="tickets",
            action="panel.published",
            actor_id=actor_id,
            target_id=panel.id,
            details=f"Painel **{panel.name}** {action_verb} em {channel.mention}.",
        )
        return saved

    # ==========================================================================
    # VALIDAÇÕES E ABERTURA DE TICKETS
    # ==========================================================================

    def is_within_business_hours(self, panel: TicketPanelSchema) -> bool:
        """Verifica se o momento atual está dentro do expediente configurado do painel."""
        bh = panel.business_hours
        if not bh.enabled:
            return True
        try:
            now_local = datetime.now(ZoneInfo(bh.timezone))
        except ZoneInfoNotFoundError:
            now_local = datetime.now(UTC)

        if now_local.weekday() not in bh.days_of_week:
            return False

        if bh.start_hour <= bh.end_hour:
            return bh.start_hour <= now_local.hour < bh.end_hour
        # Suporte a turno noturno (ex: 22h às 06h)
        return now_local.hour >= bh.start_hour or now_local.hour < bh.end_hour

    async def validate_can_open(
        self,
        guild: discord.Guild,
        member: discord.Member,
        panel: TicketPanelSchema,
    ) -> GuildSettingsSchema:
        """Executa todas as pré-validações antes de abrir modal ou criar canal."""
        settings = await self._db.guilds.get_or_create(guild.id)

        if not settings.tickets_enabled:
            raise TicketOperationError(
                "Módulo de tickets desativado.",
                user_message="O sistema de tickets está temporariamente desativado neste servidor.",
            )

        if not panel.enabled:
            raise TicketOperationError(
                "Painel desativado.",
                user_message="Este painel de atendimento está desativado no momento.",
            )

        active_count = await self._db.tickets.count_active_user_tickets(
            guild.id, panel.id, member.id
        )
        if active_count >= panel.max_tickets_per_user:
            raise TicketOperationError(
                "Limite de tickets atingido.",
                user_message=(
                    f"Você já atingiu o limite de **{panel.max_tickets_per_user}** ticket(s) "
                    f"simultâneo(s) neste departamento."
                ),
            )

        if panel.cooldown_seconds > 0:
            last_ticket = await self._db.tickets.get_last_user_ticket(
                guild.id, panel.id, member.id
            )
            if last_ticket is not None:
                elapsed = (utc_now() - last_ticket.created_at).total_seconds()
                if elapsed < panel.cooldown_seconds:
                    remaining = int(panel.cooldown_seconds - elapsed) + 1
                    raise TicketOperationError(
                        "Cooldown ativo.",
                        user_message=f"Aguarde `{remaining}s` antes de abrir um novo ticket neste painel.",
                    )

        return settings

    async def open_ticket(
        self,
        guild: discord.Guild,
        member: discord.Member,
        panel: TicketPanelSchema,
        *,
        department: TicketDepartmentOption | None = None,
        form_answers: dict[str, str] | None = None,
    ) -> tuple[TicketSchema, discord.TextChannel]:
        """Cria canal privado de atendimento com trava anti-duplicação."""
        from src.bot.views.tickets.ticket_runtime_views import TicketInsideControlView

        lock_key = f"ticket_open:{guild.id}:{panel.id}:{member.id}"
        async with self._locks.acquire(lock_key, ttl_seconds=15):
            settings = await self.validate_can_open(guild, member, panel)

            category_id = (
                (department.category_id if department and department.category_id else None)
                or panel.category_id
                or settings.default_ticket_category_id
            )
            category = guild.get_channel(category_id) if category_id else None
            if category is not None and not isinstance(category, discord.CategoryChannel):
                category = None

            staff_role_ids = list(
                dict.fromkeys(
                    (department.staff_role_ids if department and department.staff_role_ids else [])
                    or panel.staff_role_ids
                )
            )

            ticket_number = await self._db.tickets.next_ticket_number(guild.id)
            safe_user = "".join(c for c in member.name.lower() if c.isalnum())[:12] or "membro"
            channel_name = f"ticket-{ticket_number:04d}-{safe_user}"

            overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                member: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True,
                ),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_channels=True,
                    manage_permissions=True,
                    manage_messages=True,
                    read_message_history=True,
                    attach_files=True,
                ),
            }

            for role_id in staff_role_ids:
                role = guild.get_role(role_id)
                if role is not None:
                    overwrites[role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                        attach_files=True,
                        manage_messages=True,
                    )

            dept_label = department.label if department else panel.name
            try:
                channel = await guild.create_text_channel(
                    name=channel_name,
                    category=category,
                    overwrites=overwrites,
                    topic=f"Ticket #{ticket_number:04d} | Departamento: {dept_label} | Autor: {member.id}",
                    reason=f"Abertura de ticket #{ticket_number:04d} por {member} ({member.id})",
                )
            except discord.Forbidden as exc:
                raise TicketOperationError(
                    "Permissão insuficiente para criar canal.",
                    user_message="Não tenho permissão para criar canais privados nesta categoria.",
                ) from exc
            except discord.HTTPException as exc:
                raise TicketOperationError(
                    f"Erro da API do Discord ao criar canal: {exc}",
                    user_message="Não foi possível criar o canal do ticket no momento. Tente novamente.",
                ) from exc

            ticket = TicketSchema(
                guild_id=guild.id,
                panel_id=panel.id,
                ticket_number=ticket_number,
                channel_id=channel.id,
                opener_id=member.id,
                department=dept_label,
                priority="normal",
                status="open",
                participant_ids=[member.id],
                form_answers=form_answers or {},
            )
            saved_ticket = await self._db.tickets.create_ticket(ticket)

            ctx = PlaceholderContext(
                guild=guild,
                user=member,
                timezone=settings.timezone,
                extra={
                    "ticket_number": f"{ticket_number:04d}",
                    "department": dept_label,
                },
            )
            welcome_embed = self._placeholders.build_embed(
                panel.welcome_embed,
                ctx,
                fallback_footer=settings.brand_footer,
            )
            welcome_embed.add_field(name="Departamento", value=f"`{dept_label}`", inline=True)
            welcome_embed.add_field(
                name="Prioridade",
                value=PRIORITY_LABELS[saved_ticket.priority],
                inline=True,
            )
            welcome_embed.add_field(name="Responsável", value="`Aguardando equipe`", inline=True)

            if saved_ticket.form_answers:
                answers_block = "\n".join(
                    f"**{q}:** {a}" for q, a in saved_ticket.form_answers.items()
                )
                welcome_embed.add_field(
                    name="Informações Enviadas",
                    value=answers_block[:1024],
                    inline=False,
                )

            if not self.is_within_business_hours(panel):
                welcome_embed.add_field(
                    name="⏰ Horário de Atendimento",
                    value=panel.business_hours.offline_message[:1024],
                    inline=False,
                )

            mentions = [member.mention] + [
                f"<@&{rid}>" for rid in staff_role_ids if guild.get_role(rid) is not None
            ]
            control_view = TicketInsideControlView(self._bot, closed=False)

            await channel.send(
                content=" ".join(mentions),
                embed=welcome_embed,
                view=control_view,
            )

            await self._logs.record(
                guild_id=guild.id,
                category="tickets",
                action="ticket.opened",
                actor_id=member.id,
                target_id=f"#{ticket_number:04d}",
                details=(
                    f"Ticket **#{ticket_number:04d}** ({channel.mention}) aberto por "
                    f"{member.mention} no departamento **{dept_label}**."
                ),
            )
            return saved_ticket, channel

    # ==========================================================================
    # CONTROLES INTERNOS DO TICKET E PERMISSÕES DE EQUIPE
    # ==========================================================================

    async def get_ticket_context(
        self,
        channel_id: int,
    ) -> tuple[TicketSchema, TicketPanelSchema, GuildSettingsSchema]:
        ticket = await self._db.tickets.get_ticket_by_channel(channel_id)
        if ticket is None:
            raise EntityNotFoundError(
                "Canal não vinculado a nenhum ticket.",
                user_message="Este canal não corresponde a um ticket ativo no banco de dados.",
            )
        panel = await self._db.tickets.get_panel(ticket.guild_id, ticket.panel_id)
        if panel is None:
            panel = TicketPanelSchema(id=ticket.panel_id, guild_id=ticket.guild_id, name=ticket.department)
        settings = await self._db.guilds.get_or_create(ticket.guild_id)
        return ticket, panel, settings

    def is_ticket_staff(
        self,
        member: discord.Member,
        panel: TicketPanelSchema,
        settings: GuildSettingsSchema,
    ) -> bool:
        """Verifica se o membro faz parte da equipe de atendimento ou administração."""
        if self._permissions.has_module_access(member, settings, "tickets"):
            return True
        member_roles = {r.id for r in member.roles}
        if member_roles.intersection(panel.staff_role_ids):
            return True
        for dept in panel.departments:
            if member_roles.intersection(dept.staff_role_ids):
                return True
        return False

    def ensure_ticket_staff(
        self,
        member: discord.Member,
        panel: TicketPanelSchema,
        settings: GuildSettingsSchema,
    ) -> None:
        if not self.is_ticket_staff(member, panel, settings):
            raise PermissionDeniedError(
                f"Usuário {member.id} não é atendente do ticket.",
                user_message="Apenas membros da equipe de atendimento podem executar esta ação.",
            )

    async def claim_ticket(
        self,
        channel: discord.TextChannel,
        staff: discord.Member,
    ) -> TicketSchema:
        ticket, panel, settings = await self.get_ticket_context(channel.id)
        self.ensure_ticket_staff(staff, panel, settings)

        if ticket.status == "closed":
            raise TicketOperationError("Ticket fechado.", user_message="Reabra o ticket antes de assumi-lo.")

        ticket.claimed_by_id = staff.id
        ticket.status = "claimed"
        if ticket.first_response_at is None:
            ticket.first_response_at = utc_now()

        updated = await self._db.tickets.update_ticket(ticket)
        await self._logs.record(
            guild_id=ticket.guild_id,
            category="tickets",
            action="ticket.claimed",
            actor_id=staff.id,
            target_id=f"#{ticket.ticket_number:04d}",
            details=f"Atendimento **#{ticket.ticket_number:04d}** ({channel.mention}) assumido por {staff.mention}.",
        )
        return updated

    async def add_participant(
        self,
        channel: discord.TextChannel,
        actor: discord.Member,
        target_member: discord.Member,
    ) -> TicketSchema:
        ticket, panel, settings = await self.get_ticket_context(channel.id)
        self.ensure_ticket_staff(actor, panel, settings)

        await channel.set_permissions(
            target_member,
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
        )
        if target_member.id not in ticket.participant_ids:
            ticket.participant_ids.append(target_member.id)
        updated = await self._db.tickets.update_ticket(ticket)

        await self._logs.record(
            guild_id=ticket.guild_id,
            category="tickets",
            action="ticket.member_added",
            actor_id=actor.id,
            target_id=f"#{ticket.ticket_number:04d}",
            details=f"{target_member.mention} adicionado ao ticket **#{ticket.ticket_number:04d}** por {actor.mention}.",
        )
        return updated

    async def remove_participant(
        self,
        channel: discord.TextChannel,
        actor: discord.Member,
        target_member: discord.Member,
    ) -> TicketSchema:
        ticket, panel, settings = await self.get_ticket_context(channel.id)
        self.ensure_ticket_staff(actor, panel, settings)

        if target_member.id == ticket.opener_id:
            raise ValidationError(
                "Não é possível remover o autor do ticket.",
                user_message="O autor original do ticket não pode ser removido do canal.",
            )

        await channel.set_permissions(target_member, overwrite=None)
        ticket.participant_ids = [uid for uid in ticket.participant_ids if uid != target_member.id]
        updated = await self._db.tickets.update_ticket(ticket)

        await self._logs.record(
            guild_id=ticket.guild_id,
            category="tickets",
            action="ticket.member_removed",
            actor_id=actor.id,
            target_id=f"#{ticket.ticket_number:04d}",
            details=f"{target_member.mention} removido do ticket **#{ticket.ticket_number:04d}** por {actor.mention}.",
        )
        return updated

    async def transfer_assignee(
        self,
        channel: discord.TextChannel,
        actor: discord.Member,
        new_staff: discord.Member,
    ) -> TicketSchema:
        ticket, panel, settings = await self.get_ticket_context(channel.id)
        self.ensure_ticket_staff(actor, panel, settings)

        await channel.set_permissions(
            new_staff,
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            manage_messages=True,
        )
        ticket.claimed_by_id = new_staff.id
        ticket.status = "claimed"
        updated = await self._db.tickets.update_ticket(ticket)

        await self._logs.record(
            guild_id=ticket.guild_id,
            category="tickets",
            action="ticket.transferred",
            actor_id=actor.id,
            target_id=f"#{ticket.ticket_number:04d}",
            details=(
                f"Responsável pelo ticket **#{ticket.ticket_number:04d}** alterado para "
                f"{new_staff.mention} por {actor.mention}."
            ),
        )
        return updated

    async def change_department(
        self,
        channel: discord.TextChannel,
        actor: discord.Member,
        department: TicketDepartmentOption,
    ) -> TicketSchema:
        ticket, panel, settings = await self.get_ticket_context(channel.id)
        self.ensure_ticket_staff(actor, panel, settings)

        ticket.department = department.label
        if department.category_id:
            cat = channel.guild.get_channel(department.category_id)
            if isinstance(cat, discord.CategoryChannel):
                await channel.edit(category=cat, reason=f"Transferência de departamento por {actor}")

        for role_id in department.staff_role_ids:
            role = channel.guild.get_role(role_id)
            if role is not None:
                await channel.set_permissions(
                    role,
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    manage_messages=True,
                )

        updated = await self._db.tickets.update_ticket(ticket)
        await self._logs.record(
            guild_id=ticket.guild_id,
            category="tickets",
            action="ticket.department_changed",
            actor_id=actor.id,
            target_id=f"#{ticket.ticket_number:04d}",
            details=f"Departamento do ticket **#{ticket.ticket_number:04d}** alterado para **{department.label}**.",
        )
        return updated

    async def set_priority(
        self,
        channel: discord.TextChannel,
        actor: discord.Member,
        priority: TicketPriority,
    ) -> TicketSchema:
        ticket, panel, settings = await self.get_ticket_context(channel.id)
        self.ensure_ticket_staff(actor, panel, settings)

        ticket.priority = priority
        updated = await self._db.tickets.update_ticket(ticket)
        await self._logs.record(
            guild_id=ticket.guild_id,
            category="tickets",
            action="ticket.priority_changed",
            actor_id=actor.id,
            target_id=f"#{ticket.ticket_number:04d}",
            details=f"Prioridade do ticket **#{ticket.ticket_number:04d}** definida para **{PRIORITY_LABELS[priority]}**.",
        )
        return updated

    async def rename_ticket_channel(
        self,
        channel: discord.TextChannel,
        actor: discord.Member,
        new_name: str,
    ) -> str:
        ticket, panel, settings = await self.get_ticket_context(channel.id)
        self.ensure_ticket_staff(actor, panel, settings)

        sanitized = "-".join(new_name.strip().lower().split())[:90]
        if not sanitized:
            raise ValidationError("Nome inválido.", user_message="Informe um nome válido para o canal.")

        await channel.edit(name=sanitized, reason=f"Ticket renomeado por {actor}")
        await self._logs.record(
            guild_id=ticket.guild_id,
            category="tickets",
            action="ticket.renamed",
            actor_id=actor.id,
            target_id=f"#{ticket.ticket_number:04d}",
            details=f"Ticket **#{ticket.ticket_number:04d}** renomeado para `{sanitized}` por {actor.mention}.",
        )
        return sanitized

    async def notify_staff_team(
        self,
        channel: discord.TextChannel,
        actor: discord.Member,
    ) -> str:
        """Menciona os cargos responsáveis pelo atendimento com proteção anti-spam."""
        ticket, panel, _settings = await self.get_ticket_context(channel.id)

        if actor.id != ticket.opener_id and not self.is_ticket_staff(actor, panel, _settings):
            raise PermissionDeniedError("Sem permissão para notificar equipe.")

        last_ping = self._notify_cooldowns.get(ticket.id)
        if last_ping is not None:
            elapsed = (utc_now() - last_ping).total_seconds()
            if elapsed < 300:
                rem = int(300 - elapsed)
                raise TicketOperationError(
                    "Cooldown de notificação.",
                    user_message=f"A equipe já foi notificada recentemente. Aguarde `{rem}s`.",
                )

        self._notify_cooldowns[ticket.id] = utc_now()
        role_mentions = [
            f"<@&{rid}>" for rid in panel.staff_role_ids if channel.guild.get_role(rid) is not None
        ]
        if ticket.claimed_by_id:
            role_mentions.append(f"<@{ticket.claimed_by_id}>")

        return " ".join(dict.fromkeys(role_mentions)) or "@here"

    async def close_ticket(
        self,
        channel: discord.TextChannel,
        actor: discord.Member,
    ) -> tuple[TicketSchema, TicketPanelSchema, GuildSettingsSchema]:
        """Encerra o ticket, bloqueia envio de mensagens do autor, gera transcript e envia avaliação."""
        from src.bot.views.tickets.ticket_runtime_views import (
            TicketInsideControlView,
            TicketRatingView,
        )

        ticket, panel, settings = await self.get_ticket_context(channel.id)
        if actor.id != ticket.opener_id:
            self.ensure_ticket_staff(actor, panel, settings)

        if ticket.status == "closed":
            raise TicketOperationError("Ticket já fechado.", user_message="Este ticket já está fechado.")

        ticket.status = "closed"
        ticket.closed_by_id = actor.id
        ticket.closed_at = utc_now()

        # Bloqueia envio de mensagens para participantes comuns mantendo leitura
        for uid in ticket.participant_ids:
            member = channel.guild.get_member(uid)
            if member is not None and not self.is_ticket_staff(member, panel, settings):
                await channel.set_permissions(
                    member,
                    view_channel=True,
                    send_messages=False,
                    read_message_history=True,
                )

        # Gera e envia transcript HTML ao canal configurado
        transcript_file = await self._transcripts.generate_html_file(channel, ticket, settings)
        transcript_channel_id = settings.default_transcript_channel_id
        if transcript_channel_id:
            t_chan = channel.guild.get_channel(transcript_channel_id)
            if isinstance(t_chan, discord.TextChannel):
                t_embed = create_panel_embed(
                    title=f"📄 Transcript • Ticket #{ticket.ticket_number:04d}",
                    description=(
                        f"**Autor:** <@{ticket.opener_id}>\n"
                        f"**Atendente:** {f'<@{ticket.claimed_by_id}>' if ticket.claimed_by_id else '`Não assumido`'}\n"
                        f"**Fechado por:** {actor.mention}\n"
                        f"**Departamento:** `{ticket.department}`"
                    ),
                    settings=settings,
                )
                sent_transcript = await t_chan.send(embed=t_embed, file=transcript_file)
                if sent_transcript.attachments:
                    ticket.transcript_url = sent_transcript.attachments[0].url

        updated = await self._db.tickets.update_ticket(ticket)

        closed_embed = create_panel_embed(
            title=f"🔒 Ticket #{ticket.ticket_number:04d} Encerrado",
            description=(
                f"Atendimento finalizado por {actor.mention}.\n"
                "Utilize os controles abaixo para reabrir, baixar o transcript ou excluir este canal."
            ),
            settings=settings,
            color=Theme.WARNING,
        )
        await channel.send(
            embed=closed_embed,
            view=TicketInsideControlView(
                self._bot,
                closed=True,
                allow_reopen=panel.allow_reopen,
            ),
        )

        # Solicita avaliação de 1 a 5 estrelas se habilitado
        if panel.enable_rating:
            opener = channel.guild.get_member(ticket.opener_id)
            if opener is not None:
                rating_embed = create_panel_embed(
                    title=f"⭐ Avalie seu Atendimento • #{ticket.ticket_number:04d}",
                    description=(
                        f"Olá {opener.mention}, como você avalia o suporte recebido no servidor "
                        f"**{channel.guild.name}**?"
                    ),
                    settings=settings,
                )
                rating_view = TicketRatingView(self._bot, ticket.id)
                try:
                    await opener.send(embed=rating_embed, view=rating_view)
                except discord.Forbidden:
                    await channel.send(content=opener.mention, embed=rating_embed, view=rating_view)

        await self._logs.record(
            guild_id=ticket.guild_id,
            category="tickets",
            action="ticket.closed",
            actor_id=actor.id,
            target_id=f"#{ticket.ticket_number:04d}",
            details=f"Ticket **#{ticket.ticket_number:04d}** fechado por {actor.mention}.",
        )
        return updated, panel, settings

    async def reopen_ticket(
        self,
        channel: discord.TextChannel,
        actor: discord.Member,
    ) -> TicketSchema:
        from src.bot.views.tickets.ticket_runtime_views import TicketInsideControlView

        ticket, panel, settings = await self.get_ticket_context(channel.id)
        self.ensure_ticket_staff(actor, panel, settings)

        if not panel.allow_reopen:
            raise TicketOperationError(
                "Reabertura desativada.",
                user_message="A reabertura de tickets está desativada nas configurações deste painel.",
            )

        ticket.status = "claimed" if ticket.claimed_by_id else "open"
        ticket.closed_by_id = None
        ticket.closed_at = None

        for uid in ticket.participant_ids:
            member = channel.guild.get_member(uid)
            if member is not None:
                await channel.set_permissions(
                    member,
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                )

        updated = await self._db.tickets.update_ticket(ticket)
        reopen_embed = create_panel_embed(
            title=f"🔓 Ticket #{ticket.ticket_number:04d} Reaberto",
            description=f"Atendimento reaberto por {actor.mention}.",
            settings=settings,
            color=Theme.SUCCESS,
        )
        await channel.send(
            embed=reopen_embed,
            view=TicketInsideControlView(self._bot, closed=False),
        )
        await self._logs.record(
            guild_id=ticket.guild_id,
            category="tickets",
            action="ticket.reopened",
            actor_id=actor.id,
            target_id=f"#{ticket.ticket_number:04d}",
            details=f"Ticket **#{ticket.ticket_number:04d}** reaberto por {actor.mention}.",
        )
        return updated

    async def delete_ticket_channel(
        self,
        channel: discord.TextChannel,
        actor: discord.Member,
    ) -> None:
        ticket, panel, settings = await self.get_ticket_context(channel.id)
        self.ensure_ticket_staff(actor, panel, settings)

        ticket.status = "archived"
        if ticket.closed_at is None:
            ticket.closed_at = utc_now()
            ticket.closed_by_id = actor.id
        await self._db.tickets.update_ticket(ticket)

        await self._logs.record(
            guild_id=ticket.guild_id,
            category="tickets",
            action="ticket.deleted",
            actor_id=actor.id,
            target_id=f"#{ticket.ticket_number:04d}",
            details=f"Canal do ticket **#{ticket.ticket_number:04d}** excluído por {actor.mention}.",
        )
        await asyncio.sleep(3)
        await channel.delete(reason=f"Ticket #{ticket.ticket_number:04d} excluído por {actor}")

    # ==========================================================================
    # AVALIAÇÕES E ESTATÍSTICAS POR ATENDENTE
    # ==========================================================================

    async def submit_rating(
        self,
        ticket_id: str,
        user_id: int,
        stars: int,
        comment: str | None = None,
    ) -> TicketRatingSchema:
        existing = await self._db.tickets.get_rating_by_ticket(ticket_id)
        if existing is not None:
            raise ValidationError(
                "Ticket já avaliado.",
                user_message="Você já enviou uma avaliação para este atendimento.",
            )

        # Localiza o ticket em todas as guilds pelo ID interno
        # (via busca direta no canal ou lista do servidor)
        target_ticket: TicketSchema | None = None
        for guild in self._bot.guilds:
            found = await self._db.tickets.get_ticket_by_id(guild.id, ticket_id)
            if found is not None:
                target_ticket = found
                break

        if target_ticket is None:
            raise EntityNotFoundError("Ticket não encontrado para avaliação.")

        if target_ticket.opener_id != user_id:
            raise PermissionDeniedError("Somente o autor do ticket pode avaliá-lo.")

        rating = TicketRatingSchema(
            guild_id=target_ticket.guild_id,
            ticket_id=target_ticket.id,
            panel_id=target_ticket.panel_id,
            user_id=user_id,
            staff_id=target_ticket.claimed_by_id,
            stars=stars,
            comment=comment.strip()[:1000] if comment and comment.strip() else None,
        )
        saved = await self._db.tickets.create_rating(rating)

        settings = await self._db.guilds.get_or_create(target_ticket.guild_id)
        stars_visual = "⭐" * stars
        await self._logs.record(
            guild_id=target_ticket.guild_id,
            category="tickets",
            action="ticket.rated",
            actor_id=user_id,
            target_id=f"#{target_ticket.ticket_number:04d}",
            details=(
                f"Avaliação **{stars_visual} ({stars}/5)** recebida no ticket "
                f"**#{target_ticket.ticket_number:04d}**"
                f"{f' (Atendente: <@{target_ticket.claimed_by_id}>)' if target_ticket.claimed_by_id else ''}."
            ),
        )

        if settings.default_rating_channel_id:
            guild_obj = self._bot.get_guild(target_ticket.guild_id)
            if guild_obj:
                r_chan = guild_obj.get_channel(settings.default_rating_channel_id)
                if isinstance(r_chan, discord.TextChannel):
                    r_embed = create_panel_embed(
                        title=f"Nova Avaliação • Ticket #{target_ticket.ticket_number:04d}",
                        description=(
                            f"**Nota:** {stars_visual} (`{stars}/5`)\n"
                            f"**Membro:** <@{user_id}>\n"
                            f"**Atendente:** {f'<@{target_ticket.claimed_by_id}>' if target_ticket.claimed_by_id else '`Equipe Geral`'}\n"
                            f"**Comentário:** {saved.comment or '*Sem comentário adicional.*'}"
                        ),
                        settings=settings,
                        color=Theme.SUCCESS,
                    )
                    await r_chan.send(embed=r_embed)

        return saved

    async def get_staff_statistics(self, guild_id: int) -> list[dict[str, float | int]]:
        return await self._db.tickets.get_staff_rating_stats(guild_id)