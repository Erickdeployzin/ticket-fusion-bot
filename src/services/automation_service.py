"""Serviço de gestão de mensagens personalizadas, componentes interativos e automações."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord

from src.bot.ui.embeds import create_panel_embed, error_embed, success_embed
from src.core.exceptions import (
    AutomationOperationError,
    EntityNotFoundError,
    ValidationError,
)
from src.core.logger import get_logger
from src.database.interfaces.provider import IDatabaseProvider
from src.database.schemas import (
    AutomationRuleSchema,
    AutomationType,
    ButtonActionType,
    CustomButtonSchema,
    CustomDropdownSchema,
    GuildSettingsSchema,
    ScheduleConfigSchema,
    utc_now,
)
from src.services.log_service import LogService
from src.services.placeholder_service import PlaceholderContext, PlaceholderService

if TYPE_CHECKING:
    from src.bot.client import FusionBot

logger = get_logger(__name__)

AUTOMATION_TYPE_LABELS: dict[AutomationType, str] = {
    "welcome": "Boas-vindas (Entrada)",
    "goodbye": "Despedida (Saída)",
    "scheduled": "Mensagem Programada",
    "periodic": "Mensagem Periódica",
    "announcement": "Anúncio / Divulgação",
    "custom": "Mensagem Personalizada",
}


class AutomationService:
    """Orquestra criação, edição, pré-visualização, publicação e execução de automações."""

    def __init__(
        self,
        bot: FusionBot,
        db: IDatabaseProvider,
        log_service: LogService,
        placeholders: PlaceholderService,
    ) -> None:
        self._bot = bot
        self._db = db
        self._logs = log_service
        self._placeholders = placeholders

    # ==========================================================================
    # CRUD DE AUTOMAÇÕES E MENSAGENS PERSONALIZADAS
    # ==========================================================================

    async def create_rule(
        self,
        guild_id: int,
        actor_id: int,
        *,
        name: str,
        automation_type: AutomationType,
        content: str | None = None,
        embed_title: str | None = None,
        embed_description: str | None = None,
    ) -> AutomationRuleSchema:
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError(
                "Nome vazio.",
                user_message="Informe um nome identificador para a mensagem/automação.",
            )

        settings = await self._db.guilds.get_or_create(guild_id)
        use_embed = bool(embed_title or embed_description or not content)

        rule = AutomationRuleSchema(
            guild_id=guild_id,
            name=clean_name[:100],
            automation_type=automation_type,
            content=content.strip()[:2000] if content and content.strip() else None,
            use_embed=use_embed,
        )
        rule.embed.color = settings.brand_color
        rule.embed.footer_text = settings.brand_footer
        rule.schedule.timezone = settings.timezone

        if embed_title:
            rule.embed.title = embed_title.strip()[:256]
        if embed_description:
            rule.embed.description = embed_description.strip()[:4096]
        elif use_embed and not embed_title:
            rule.embed.title = clean_name[:256]
            rule.embed.description = "Edite o conteúdo desta mensagem diretamente pelo painel."

        created = await self._db.automations.create_automation(rule)
        await self._logs.record(
            guild_id=guild_id,
            category="automations",
            action="automation.created",
            actor_id=actor_id,
            target_id=created.id,
            details=f"Automação **{created.name}** (`{created.automation_type}`) criada por <@{actor_id}>.",
        )
        return created

    async def save_rule(
        self,
        rule: AutomationRuleSchema,
        actor_id: int,
        audit_detail: str,
    ) -> AutomationRuleSchema:
        rule.schedule.next_run_at = self.compute_next_run(rule.schedule)
        updated = await self._db.automations.update_automation(rule)
        await self._logs.record(
            guild_id=rule.guild_id,
            category="automations",
            action="automation.updated",
            actor_id=actor_id,
            target_id=rule.id,
            details=audit_detail,
        )
        return updated

    async def delete_rule(self, guild_id: int, actor_id: int, rule_id: str) -> None:
        rule = await self._db.automations.get_automation(guild_id, rule_id)
        if rule is None:
            raise EntityNotFoundError("Automação não encontrada.")
        await self._db.automations.delete_automation(guild_id, rule_id)
        await self._logs.record(
            guild_id=guild_id,
            category="automations",
            action="automation.deleted",
            actor_id=actor_id,
            target_id=rule_id,
            details=f"Automação **{rule.name}** excluída por <@{actor_id}>.",
        )

    # ==========================================================================
    # CÁLCULO DE AGENDAMENTO E PERIODICIDADE
    # ==========================================================================

    @staticmethod
    def compute_next_run(
        schedule: ScheduleConfigSchema,
        reference_utc: datetime | None = None,
    ) -> datetime | None:
        """Calcula o próximo timestamp UTC de execução de forma determinística."""
        if not schedule.enabled:
            return None

        if schedule.max_runs is not None and schedule.run_count >= schedule.max_runs:
            return None

        now = reference_utc or utc_now()

        if schedule.frequency == "once":
            if schedule.run_count > 0 or schedule.run_at is None:
                return None
            return schedule.run_at.astimezone(UTC)

        if schedule.frequency == "interval":
            if not schedule.interval_minutes or schedule.interval_minutes < 5:
                return None
            base = schedule.last_run_at.astimezone(UTC) if schedule.last_run_at else now
            candidate = base + timedelta(minutes=schedule.interval_minutes)
            while candidate <= now:
                candidate += timedelta(minutes=schedule.interval_minutes)
            return candidate

        try:
            tz = ZoneInfo(schedule.timezone)
        except ZoneInfoNotFoundError:
            tz = ZoneInfo("UTC")

        now_local = now.astimezone(tz)
        hour, minute = 12, 0
        if schedule.time_of_day:
            h_str, m_str = schedule.time_of_day.split(":", maxsplit=1)
            hour, minute = int(h_str), int(m_str)

        if schedule.frequency == "daily":
            candidate_local = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate_local <= now_local:
                candidate_local += timedelta(days=1)
            return candidate_local.astimezone(UTC)

        if schedule.frequency == "weekly":
            valid_days = set(schedule.days_of_week or [0])
            for offset in range(0, 8):
                day_dt = now_local + timedelta(days=offset)
                if day_dt.weekday() in valid_days:
                    candidate_local = day_dt.replace(
                        hour=hour, minute=minute, second=0, microsecond=0
                    )
                    if candidate_local > now_local:
                        return candidate_local.astimezone(UTC)

        return None

    # ==========================================================================
    # CONSTRUÇÃO DE PAYLOAD DISCORD, PRÉ-VISUALIZAÇÃO E PUBLICAÇÃO
    # ==========================================================================

    def build_message_payload(
        self,
        guild: discord.Guild,
        rule: AutomationRuleSchema,
        settings: GuildSettingsSchema,
        *,
        member: discord.abc.User | None = None,
        disable_components: bool = False,
    ) -> tuple[str | None, discord.Embed | None, discord.ui.View | None, discord.AllowedMentions]:
        """Monta content, embed, view interativa e allowed_mentions prontos para envio."""
        from src.bot.views.automations.automation_runtime_views import AutomationMessageView

        ctx = PlaceholderContext(
            guild=guild,
            user=member,
            timezone=settings.timezone,
        )

        mention_parts: list[str] = []
        if rule.mention_everyone:
            mention_parts.append("@everyone")
        for role_id in rule.mention_role_ids:
            if guild.get_role(role_id) is not None:
                mention_parts.append(f"<@&{role_id}>")

        rendered_content = self._placeholders.render(rule.content, ctx)
        full_content_parts = [p for p in (" ".join(mention_parts), rendered_content) if p]
        final_content = "\n".join(full_content_parts)[:2000] if full_content_parts else None

        final_embed: discord.Embed | None = None
        if rule.use_embed:
            final_embed = self._placeholders.build_embed(
                rule.embed,
                ctx,
                fallback_footer=settings.brand_footer,
            )

        if not final_content and final_embed is None:
            final_content = "*(Mensagem configurada sem conteúdo de texto ou embed)*"

        view: discord.ui.View | None = None
        if rule.buttons or rule.dropdowns:
            view = AutomationMessageView(
                self._bot,
                rule,
                disable_all=disable_components,
            )

        allowed_mentions = discord.AllowedMentions(
            everyone=rule.mention_everyone,
            users=True,
            roles=True,
        )
        return final_content, final_embed, view, allowed_mentions

    async def publish_or_update_message(
        self,
        guild: discord.Guild,
        rule: AutomationRuleSchema,
        actor_id: int,
        *,
        target_channel: discord.TextChannel | None = None,
        is_scheduled_trigger: bool = False,
    ) -> tuple[AutomationRuleSchema, discord.Message]:
        """Publica a mensagem no canal de destino ou edita a mensagem já publicada."""
        settings = await self._db.guilds.get_or_create(guild.id)
        if not settings.automations_enabled and is_scheduled_trigger:
            raise AutomationOperationError("Módulo de automações desativado na guild.")

        channel = target_channel
        if channel is None and rule.target_channel_id:
            resolved = guild.get_channel(rule.target_channel_id)
            if isinstance(resolved, discord.TextChannel):
                channel = resolved

        if channel is None:
            raise ValidationError(
                "Canal de destino não configurado.",
                user_message="Selecione primeiro o **Canal de Destino** desta mensagem.",
            )

        perms = channel.permissions_for(guild.me)
        if not perms.send_messages:
            raise AutomationOperationError(
                "Sem permissão de envio no canal.",
                user_message=f"Não possuo permissão de enviar mensagens em {channel.mention}.",
            )
        if rule.use_embed and not perms.embed_links:
            raise AutomationOperationError(
                "Sem permissão de embed no canal.",
                user_message=f"Não possuo permissão de **Inserir Links (Embeds)** em {channel.mention}.",
            )

        content, embed, view, allowed_mentions = self.build_message_payload(
            guild, rule, settings
        )

        # Mensagens agendadas/periódicas criam nova postagem a cada disparo;
        # mensagens estáticas/anúncios atualizam a mensagem existente quando no mesmo canal.
        should_try_edit = (
            not is_scheduled_trigger
            and rule.automation_type not in {"scheduled", "periodic"}
            and rule.published_channel_id == channel.id
            and rule.published_message_id is not None
        )

        sent_message: discord.Message | None = None
        was_edited = False

        if should_try_edit and rule.published_message_id is not None:
            try:
                existing = await channel.fetch_message(rule.published_message_id)
                sent_message = await existing.edit(
                    content=content,
                    embed=embed,
                    view=view,
                    allowed_mentions=allowed_mentions,
                )
                was_edited = True
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                sent_message = None

        if sent_message is None:
            sent_message = await channel.send(
                content=content,
                embed=embed,
                view=view,
                allowed_mentions=allowed_mentions,
            )

        rule.target_channel_id = channel.id
        rule.published_channel_id = channel.id
        rule.published_message_id = sent_message.id
        updated = await self._db.automations.update_automation(rule)

        action_name = "automation.edited_published" if was_edited else "automation.published"
        verb = "atualizada" if was_edited else "publicada"
        await self._logs.record(
            guild_id=guild.id,
            category="automations",
            action=action_name,
            actor_id=actor_id if actor_id > 0 else None,
            target_id=rule.id,
            details=f"Mensagem **{rule.name}** {verb} em {channel.mention}.",
        )
        return updated, sent_message

    async def dispatch_member_event(
        self,
        member: discord.Member,
        event_type: AutomationType,
    ) -> None:
        """Dispara automações ativas de boas-vindas ou despedida para um membro."""
        guild = member.guild
        settings = await self._db.guilds.get_or_create(guild.id)
        if not settings.automations_enabled:
            return

        rules = await self._db.automations.list_automations(
            guild.id,
            automation_type=event_type,
            enabled_only=True,
        )
        for rule in rules:
            if not rule.target_channel_id:
                continue
            channel = guild.get_channel(rule.target_channel_id)
            if not isinstance(channel, discord.TextChannel):
                continue

            perms = channel.permissions_for(guild.me)
            if not perms.send_messages:
                continue

            try:
                content, embed, view, allowed_mentions = self.build_message_payload(
                    guild,
                    rule,
                    settings,
                    member=member,
                )
                await channel.send(
                    content=content,
                    embed=embed,
                    view=view,
                    allowed_mentions=allowed_mentions,
                )
            except Exception:
                logger.exception(
                    "Falha ao enviar automação '%s' (guild=%s, user=%s)",
                    rule.id,
                    guild.id,
                    member.id,
                )

    # ==========================================================================
    # EXECUÇÃO SEGURA DE AÇÕES DE BOTÕES E DROPDOWNS PERSONALIZADOS
    # ==========================================================================

    @staticmethod
    def validate_safe_url(url: str) -> str:
        clean = url.strip()
        if not clean.startswith(("http://", "https://")) or len(clean) > 512:
            raise ValidationError(
                "URL inválida.",
                user_message="A URL deve começar com `http://` ou `https://` e ter até 512 caracteres.",
            )
        return clean

    async def execute_component_action(
        self,
        interaction: discord.Interaction,
        rule: AutomationRuleSchema,
        *,
        action_type: ButtonActionType,
        action_value: str,
        required_role_ids: list[int] | None = None,
    ) -> None:
        """Executa a ação configurada em um botão ou opção de dropdown com validações de segurança."""
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return

        if required_role_ids:
            user_roles = {r.id for r in interaction.user.roles}
            if not user_roles.intersection(required_role_ids):
                await interaction.response.send_message(
                    embed=error_embed(
                        "Acesso Restrito",
                        "Você não possui o cargo necessário para utilizar este componente.",
                    ),
                    ephemeral=True,
                )
                return

        if action_type == "open_ticket_panel":
            from src.bot.views.tickets.ticket_runtime_views import _handle_ticket_open_request

            panel_id = action_value.strip()
            await _handle_ticket_open_request(self._bot, interaction, panel_id)
            return

        if action_type == "send_ephemeral":
            settings = await self._db.guilds.get_or_create(interaction.guild.id)
            ctx = PlaceholderContext(
                guild=interaction.guild,
                user=interaction.user,
                timezone=settings.timezone,
            )
            rendered = self._placeholders.render(action_value, ctx) or "Ação executada."
            embed = create_panel_embed(
                title=rule.name,
                description=rendered[:4000],
                settings=settings,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if action_type in {"toggle_role", "add_role", "remove_role"}:
            try:
                role_id = int(action_value.strip())
            except ValueError:
                await interaction.response.send_message(
                    embed=error_embed("Configuração Inválida", "ID de cargo inválido neste botão."),
                    ephemeral=True,
                )
                return

            role = interaction.guild.get_role(role_id)
            if (
                role is None
                or role.is_default()
                or role.managed
                or role >= interaction.guild.me.top_role
            ):
                await interaction.response.send_message(
                    embed=error_embed(
                        "Cargo Indisponível",
                        "O cargo configurado não existe ou está acima da hierarquia do bot.",
                    ),
                    ephemeral=True,
                )
                return

            has_role = role in interaction.user.roles
            try:
                if action_type == "toggle_role":
                    if has_role:
                        await interaction.user.remove_roles(role, reason=f"Automação: {rule.name}")
                        msg = f"O cargo {role.mention} foi **removido** do seu perfil."
                    else:
                        await interaction.user.add_roles(role, reason=f"Automação: {rule.name}")
                        msg = f"O cargo {role.mention} foi **adicionado** ao seu perfil."
                elif action_type == "add_role":
                    if has_role:
                        msg = f"Você já possui o cargo {role.mention}."
                    else:
                        await interaction.user.add_roles(role, reason=f"Automação: {rule.name}")
                        msg = f"O cargo {role.mention} foi **adicionado** ao seu perfil."
                else:
                    if not has_role:
                        msg = f"Você não possui o cargo {role.mention}."
                    else:
                        await interaction.user.remove_roles(role, reason=f"Automação: {rule.name}")
                        msg = f"O cargo {role.mention} foi **removido** do seu perfil."

                await interaction.response.send_message(
                    embed=success_embed("Cargo Atualizado", msg),
                    ephemeral=True,
                )
            except discord.Forbidden:
                await interaction.response.send_message(
                    embed=error_embed(
                        "Permissão Insuficiente",
                        "O bot não tem permissão para gerenciar este cargo.",
                    ),
                    ephemeral=True,
                )
            return

        # Fallback seguro caso action_type seja 'link' acionado indevidamente
        await interaction.response.send_message(
            embed=success_embed("Link", f"Acesse: {cast(str, action_value)}"),
            ephemeral=True,
        )