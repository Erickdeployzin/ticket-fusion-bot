"""Views de Visão Geral, Hubs dos Módulos (Tickets/Automações) e Diagnóstico."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

import discord

from src.bot.ui.components import BaseOwnerView
from src.bot.ui.embeds import create_panel_embed, warning_embed
from src.bot.ui.theme import Theme
from src.bot.views.admin.navigation import (
    AdminSectionSelect,
    BackToOverviewButton,
    open_admin_section,
)
from src.database.schemas import GuildSettingsSchema
from src.services.guild_service import GuildDashboardSnapshot, SystemDiagnosticsReport

if TYPE_CHECKING:
    from src.bot.client import FusionBot


class OverviewDashboardView(BaseOwnerView):
    """1. Visão Geral — Painel inicial com métricas reais do servidor."""

    def __init__(
        self,
        bot: FusionBot,
        owner_id: int,
        snapshot: GuildDashboardSnapshot,
    ) -> None:
        super().__init__(owner_id=owner_id)
        self._bot = bot
        self._dashboard_snapshot = snapshot
        self.add_item(AdminSectionSelect(bot, "overview"))

    def build_embed(self) -> discord.Embed:
        snap = self._dashboard_snapshot
        embed = create_panel_embed(
            title=f"{Theme.ICON_DASHBOARD} Painel Administrativo • {snap.guild_name}",
            description=(
                "Central de gerenciamento unificada do servidor. "
                "Selecione uma categoria no menu abaixo para configurar qualquer recurso."
            ),
            settings=snap.settings,
        )

        embed.add_field(
            name="Comunidade",
            value=(
                f"**Membros:** `{snap.member_count:,}`\n"
                f"**ID:** `{snap.guild_id}`"
            ),
            inline=True,
        )
        embed.add_field(
            name="Estado dos Módulos",
            value=(
                f"**Tickets:** {Theme.status_badge(snap.tickets_enabled)}\n"
                f"**Automações:** {Theme.status_badge(snap.automations_enabled)}"
            ),
            inline=True,
        )
        embed.add_field(
            name="Indicadores Operacionais",
            value=(
                f"**Tickets Abertos:** `{snap.open_tickets_count}`\n"
                f"**Painéis Criados:** `{snap.total_panels_count}`\n"
                f"**Automações Ativas:** `{snap.active_automations_count}/{snap.total_automations_count}`"
            ),
            inline=True,
        )

        if snap.recent_logs:
            lines: list[str] = []
            for entry in snap.recent_logs[:4]:
                ts = int(entry.created_at.timestamp())
                lines.append(f"• <t:{ts}:R> — {entry.details}")
            activity_text = "\n".join(lines)
        else:
            activity_text = "*Nenhuma atividade administrativa registrada até o momento.*"

        embed.add_field(
            name="Últimas Atividades Administrativas",
            value=activity_text[:1024],
            inline=False,
        )
        return embed

    @discord.ui.button(
        label="Tickets",
        emoji=Theme.ICON_TICKETS,
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def quick_tickets(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[OverviewDashboardView],
    ) -> None:
        await open_admin_section(self._bot, interaction, "tickets")

    @discord.ui.button(
        label="Automações",
        emoji=Theme.ICON_AUTOMATIONS,
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def quick_automations(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[OverviewDashboardView],
    ) -> None:
        await open_admin_section(self._bot, interaction, "automations")

    @discord.ui.button(
        label="Permissões",
        emoji=Theme.ICON_PERMISSIONS,
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def quick_permissions(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[OverviewDashboardView],
    ) -> None:
        await open_admin_section(self._bot, interaction, "permissions")

    @discord.ui.button(
        label="Atualizar Dados",
        emoji="🔄",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def refresh_overview(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[OverviewDashboardView],
    ) -> None:
        await open_admin_section(self._bot, interaction, "overview")


class TicketsHubView(BaseOwnerView):
    """2. Sistema de Tickets — Controle do módulo e acesso ao gerenciador de painéis."""

    def __init__(
        self,
        bot: FusionBot,
        owner_id: int,
        settings: GuildSettingsSchema,
    ) -> None:
        super().__init__(owner_id=owner_id)
        self._bot = bot
        self._settings = settings
        self.add_item(AdminSectionSelect(bot, "tickets"))
        self.add_item(BackToOverviewButton(bot, row=2))

        self.toggle_btn.label = (
            "Desativar Módulo" if settings.tickets_enabled else "Ativar Módulo"
        )
        self.toggle_btn.style = (
            discord.ButtonStyle.danger
            if settings.tickets_enabled
            else discord.ButtonStyle.success
        )

    async def build_embed(self, guild: discord.Guild) -> discord.Embed:
        panels = await self._bot.ctx.db.tickets.list_panels(guild.id)
        open_count = await self._bot.ctx.db.tickets.count_open_guild_tickets(guild.id)
        active_panels = sum(1 for p in panels if p.enabled)

        embed = create_panel_embed(
            title=f"{Theme.ICON_TICKETS} Sistema Profissional de Tickets",
            description=(
                "Gerencie departamentos, formulários pré-abertura, horários de atendimento, "
                "transcripts HTML e avaliações de suporte."
            ),
            settings=self._settings,
        )
        embed.add_field(
            name="Estado do Módulo",
            value=Theme.status_badge(self._settings.tickets_enabled),
            inline=True,
        )
        embed.add_field(
            name="Painéis Configurados",
            value=f"`{active_panels}` ativos de `{len(panels)}` totais",
            inline=True,
        )
        embed.add_field(
            name="Atendimentos em Aberto",
            value=f"`{open_count}` tickets",
            inline=True,
        )
        embed.add_field(
            name="Padrões Globais",
            value=(
                f"**Categoria Padrão:** {Theme.mention_channel(self._settings.default_ticket_category_id)}\n"
                f"**Canal de Transcripts:** {Theme.mention_channel(self._settings.default_transcript_channel_id)}\n"
                f"**Canal de Avaliações:** {Theme.mention_channel(self._settings.default_rating_channel_id)}"
            ),
            inline=False,
        )
        return embed

    @discord.ui.button(
        label="Gerenciar Painéis de Tickets",
        emoji="🗂️",
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def open_panel_manager(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[TicketsHubView],
    ) -> None:
        try:
            module = importlib.import_module("src.bot.views.tickets.panel_manager_view")
            await module.open_ticket_panel_manager(self._bot, interaction)
        except ModuleNotFoundError:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Módulo em Implantação",
                    "O gerenciador detalhado de painéis será carregado na **Fase 4**.",
                ),
                ephemeral=True,
            )

    @discord.ui.button(
        label="Ativar/Desativar",
        emoji="🔌",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def toggle_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[TicketsHubView],
    ) -> None:
        assert interaction.guild is not None
        await self._bot.guild_service.toggle_module(
            interaction.guild.id,
            interaction.user.id,
            "tickets",
        )
        await open_admin_section(self._bot, interaction, "tickets")


class AutomationsHubView(BaseOwnerView):
    """3. Mensagens Automáticas — Controle do módulo e acesso ao editor visual."""

    def __init__(
        self,
        bot: FusionBot,
        owner_id: int,
        settings: GuildSettingsSchema,
    ) -> None:
        super().__init__(owner_id=owner_id)
        self._bot = bot
        self._settings = settings
        self.add_item(AdminSectionSelect(bot, "automations"))
        self.add_item(BackToOverviewButton(bot, row=2))

        self.toggle_btn.label = (
            "Desativar Módulo" if settings.automations_enabled else "Ativar Módulo"
        )
        self.toggle_btn.style = (
            discord.ButtonStyle.danger
            if settings.automations_enabled
            else discord.ButtonStyle.success
        )

    async def build_embed(self, guild: discord.Guild) -> discord.Embed:
        rules = await self._bot.ctx.db.automations.list_automations(guild.id)
        active_count = sum(1 for r in rules if r.enabled)
        scheduled_count = sum(1 for r in rules if r.schedule.enabled)

        embed = create_panel_embed(
            title=f"{Theme.ICON_AUTOMATIONS} Mensagens Automáticas e Personalizadas",
            description=(
                "Crie mensagens ricas com embeds, banners, botões interativos, select menus, "
                "boas-vindas, despedidas e agendamentos recorrentes sem tocar em código."
            ),
            settings=self._settings,
        )
        embed.add_field(
            name="Estado do Módulo",
            value=Theme.status_badge(self._settings.automations_enabled),
            inline=True,
        )
        embed.add_field(
            name="Regras Ativas",
            value=f"`{active_count}` de `{len(rules)}` configuradas",
            inline=True,
        )
        embed.add_field(
            name="Agendamentos Ativos",
            value=f"`{scheduled_count}` tarefas programadas",
            inline=True,
        )
        return embed

    @discord.ui.button(
        label="Gerenciar Mensagens e Automações",
        emoji="✨",
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def open_automation_manager(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[AutomationsHubView],
    ) -> None:
        try:
            module = importlib.import_module("src.bot.views.automations.automation_manager_view")
            await module.open_automation_manager(self._bot, interaction)
        except ModuleNotFoundError:
            await interaction.response.send_message(
                embed=warning_embed(
                    "Módulo em Implantação",
                    "O editor visual de mensagens e agendamentos será carregado nas **Fases 5 a 7**.",
                ),
                ephemeral=True,
            )

    @discord.ui.button(
        label="Ativar/Desativar",
        emoji="🔌",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def toggle_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[AutomationsHubView],
    ) -> None:
        assert interaction.guild is not None
        await self._bot.guild_service.toggle_module(
            interaction.guild.id,
            interaction.user.id,
            "automations",
        )
        await open_admin_section(self._bot, interaction, "automations")


class DiagnosticsView(BaseOwnerView):
    """9. Diagnóstico do Sistema — Métricas técnicas em tempo real."""

    def __init__(
        self,
        bot: FusionBot,
        owner_id: int,
        settings: GuildSettingsSchema,
        report: SystemDiagnosticsReport,
    ) -> None:
        super().__init__(owner_id=owner_id)
        self._bot = bot
        self._settings = settings
        self._report = report
        self.add_item(AdminSectionSelect(bot, "diagnostics"))
        self.add_item(BackToOverviewButton(bot, row=2))

    def build_embed(self) -> discord.Embed:
        rep = self._report
        db_status = (
            f"{Theme.STATUS_ON} (`{rep.database_latency_ms} ms`)"
            if rep.database_healthy
            else f"{Theme.STATUS_OFF} (Falha de conexão)"
        )
        redis_status = Theme.STATUS_ON if self._bot.ctx.redis is not None else "`Standalone (Memória)`"

        embed = create_panel_embed(
            title=f"{Theme.ICON_DIAGNOSTICS} Diagnóstico do Sistema",
            description="Telemetria em tempo real de infraestrutura, banco de dados e Gateway Discord.",
            settings=self._settings,
        )
        embed.add_field(
            name="Persistência",
            value=(
                f"**Provider:** `{rep.database_provider}`\n"
                f"**Saúde:** {db_status}\n"
                f"**Cache/Locks:** {redis_status}"
            ),
            inline=True,
        )
        embed.add_field(
            name="Gateway & Sharding",
            value=(
                f"**Latência API:** `{rep.gateway_latency_ms} ms`\n"
                f"**Shard Atual:** `{rep.shard_id + 1}/{rep.shard_count}`\n"
                f"**Servidores:** `{rep.guild_count}`"
            ),
            inline=True,
        )
        embed.add_field(
            name="Ambiente & Runtime",
            value=(
                f"**Uptime:** `{Theme.format_uptime(rep.uptime_seconds)}`\n"
                f"**Python:** `{rep.python_version}`\n"
                f"**discord.py:** `{rep.discord_py_version}`"
            ),
            inline=True,
        )
        return embed

    @discord.ui.button(
        label="Executar Novo Teste",
        emoji="🔄",
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def refresh_diagnostics(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[DiagnosticsView],
    ) -> None:
        await open_admin_section(self._bot, interaction, "diagnostics")