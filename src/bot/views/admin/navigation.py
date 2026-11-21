"""Navegação central e roteamento entre as 9 seções do painel administrativo."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

import discord

from src.bot.ui.theme import Theme
from src.database.schemas import BotModule

if TYPE_CHECKING:
    from src.bot.client import FusionBot

AdminSection = Literal[
    "overview",
    "tickets",
    "automations",
    "permissions",
    "channels",
    "logs",
    "branding",
    "general",
    "diagnostics",
]

SECTION_META: tuple[tuple[AdminSection, str, str, str], ...] = (
    ("overview", "1. Visão Geral", "Resumo em tempo real do servidor e módulos", Theme.ICON_DASHBOARD),
    ("tickets", "2. Sistema de Tickets", "Painéis de atendimento, filas e suporte", Theme.ICON_TICKETS),
    ("automations", "3. Mensagens Automáticas", "Embeds, botões, dropdowns e agendamentos", Theme.ICON_AUTOMATIONS),
    ("permissions", "4. Cargos e Permissões", "Controle de acesso granular por módulo", Theme.ICON_PERMISSIONS),
    ("channels", "5. Canais", "Categorias e canais padrão de atendimento", Theme.ICON_CHANNELS),
    ("logs", "6. Logs", "Auditoria por categoria e histórico recente", Theme.ICON_LOGS),
    ("branding", "7. Personalização", "Cor institucional e rodapé do servidor", Theme.ICON_BRANDING),
    ("general", "8. Configurações Gerais", "Fuso horário, idioma e ativação de módulos", Theme.ICON_SETTINGS),
    ("diagnostics", "9. Diagnóstico do Sistema", "Latência, banco de dados, shards e uptime", Theme.ICON_DIAGNOSTICS),
)

SECTION_REQUIRED_MODULE: dict[AdminSection, BotModule | None] = {
    "overview": None,
    "tickets": "tickets",
    "automations": "automations",
    "permissions": "administration",
    "channels": "administration",
    "logs": "logs",
    "branding": "administration",
    "general": "administration",
    "diagnostics": "administration",
}


class AdminSectionSelect(discord.ui.Select["discord.ui.View"]):
    """Dropdown principal para navegar entre as 9 categorias do /painel."""

    def __init__(self, bot: FusionBot, current_section: AdminSection) -> None:
        self._bot = bot
        options = [
            discord.SelectOption(
                label=label,
                value=key,
                description=desc,
                emoji=emoji,
                default=(key == current_section),
            )
            for key, label, desc, emoji in SECTION_META
        ]
        super().__init__(
            placeholder="Navegar entre as seções do painel...",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        selected = cast(AdminSection, self.values[0])
        await open_admin_section(self._bot, interaction, selected)


class BackToOverviewButton(discord.ui.Button["discord.ui.View"]):
    """Botão padronizado para retornar à Visão Geral do painel administrativo."""

    def __init__(self, bot: FusionBot, *, row: int = 4) -> None:
        super().__init__(
            label="Visão Geral",
            emoji=Theme.ICON_BACK,
            style=discord.ButtonStyle.secondary,
            row=row,
        )
        self._bot = bot

    async def callback(self, interaction: discord.Interaction) -> None:
        await open_admin_section(self._bot, interaction, "overview")


async def open_admin_section(
    bot: FusionBot,
    interaction: discord.Interaction,
    section: AdminSection,
    *,
    send_new: bool = False,
) -> None:
    """Valida permissões da seção escolhida e renderiza a View correspondente."""
    assert interaction.guild is not None
    assert isinstance(interaction.user, discord.Member)

    settings = await bot.guild_service.get_settings(interaction.guild.id)
    required_module = SECTION_REQUIRED_MODULE[section]
    if required_module is not None:
        bot.permissions.ensure_module_access(interaction.user, settings, required_module)

    # Importações locais evitam ciclos entre navigation, dashboard_view e config_views
    from src.bot.views.admin.config_views import (
        BrandingConfigView,
        ChannelsConfigView,
        GeneralConfigView,
        LogsConfigView,
        PermissionsConfigView,
    )
    from src.bot.views.admin.dashboard_view import (
        AutomationsHubView,
        DiagnosticsView,
        OverviewDashboardView,
        TicketsHubView,
    )

    embed: discord.Embed
    view: discord.ui.View

    if section == "overview":
        snapshot = await bot.guild_service.get_dashboard_snapshot(interaction.guild)
        overview_view = OverviewDashboardView(bot, interaction.user.id, snapshot)
        embed = overview_view.build_embed()
        view = overview_view
    elif section == "tickets":
        tickets_view = TicketsHubView(bot, interaction.user.id, settings)
        embed = await tickets_view.build_embed(interaction.guild)
        view = tickets_view
    elif section == "automations":
        auto_view = AutomationsHubView(bot, interaction.user.id, settings)
        embed = await auto_view.build_embed(interaction.guild)
        view = auto_view
    elif section == "permissions":
        perm_view = PermissionsConfigView(bot, interaction.user.id, settings)
        embed = perm_view.build_embed()
        view = perm_view
    elif section == "channels":
        chan_view = ChannelsConfigView(bot, interaction.user.id, settings)
        embed = chan_view.build_embed()
        view = chan_view
    elif section == "logs":
        logs_view = LogsConfigView(bot, interaction.user.id, settings)
        embed = logs_view.build_embed()
        view = logs_view
    elif section == "branding":
        brand_view = BrandingConfigView(bot, interaction.user.id, settings)
        embed = brand_view.build_embed()
        view = brand_view
    elif section == "general":
        gen_view = GeneralConfigView(bot, interaction.user.id, settings)
        embed = gen_view.build_embed()
        view = gen_view
    else:
        report = await bot.guild_service.build_diagnostics(
            bot, interaction.guild, bot.ctx.started_at
        )
        diag_view = DiagnosticsView(bot, interaction.user.id, settings, report)
        embed = diag_view.build_embed()
        view = diag_view

    if send_new:
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    elif interaction.response.is_done():
        await interaction.edit_original_response(embed=embed, view=view)
    else:
        await interaction.response.edit_message(embed=embed, view=view)