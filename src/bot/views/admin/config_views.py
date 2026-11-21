"""Views administrativas de configuração (Permissões, Canais, Logs, Branding e Geral)."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import discord

from src.bot.modals.admin_modals import BrandingModal, GeneralSettingsModal
from src.bot.ui.components import BaseOwnerView, EmbedPaginatorView
from src.bot.ui.embeds import create_panel_embed
from src.bot.ui.theme import Theme
from src.bot.views.admin.navigation import (
    AdminSectionSelect,
    BackToOverviewButton,
    open_admin_section,
)
from src.core.permissions import MODULE_LABELS
from src.database.schemas import (
    BotModule,
    GuildSettingsSchema,
    LogCategory,
    ModulePermissionRule,
)

if TYPE_CHECKING:
    from src.bot.client import FusionBot


# ==============================================================================
# 4. CARGOS E PERMISSÕES
# ==============================================================================


class PermissionModuleSelect(discord.ui.Select["PermissionsConfigView"]):
    """Seleciona qual módulo terá seus cargos e usuários configurados."""

    def __init__(self, current_module: BotModule) -> None:
        options = [
            discord.SelectOption(
                label=label,
                value=mod,
                default=(mod == current_module),
            )
            for mod, label in MODULE_LABELS.items()
        ]
        super().__init__(
            placeholder="Selecione o módulo para configurar permissões...",
            min_values=1,
            max_values=1,
            options=options,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        self.view.selected_module = cast(BotModule, self.values[0])
        await interaction.response.edit_message(
            embed=self.view.build_embed(),
            view=self.view,
        )


class PermissionRoleSelect(discord.ui.RoleSelect["PermissionsConfigView"]):
    """Seletor nativo de cargos autorizados para o módulo atual."""

    def __init__(self) -> None:
        super().__init__(
            placeholder="Selecionar cargos autorizados para este módulo...",
            min_values=0,
            max_values=10,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None and interaction.guild is not None
        role_ids = [role.id for role in self.values]
        updated = await self.view.bot.guild_service.update_module_permissions(
            interaction.guild.id,
            interaction.user.id,
            self.view.selected_module,
            role_ids=role_ids,
        )
        self.view.settings = updated
        await interaction.response.edit_message(
            embed=self.view.build_embed(),
            view=self.view,
        )


class PermissionUserSelect(discord.ui.UserSelect["PermissionsConfigView"]):
    """Seletor nativo de usuários individuais autorizados para o módulo atual."""

    def __init__(self) -> None:
        super().__init__(
            placeholder="Selecionar usuários autorizados individualmente...",
            min_values=0,
            max_values=10,
            row=3,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None and interaction.guild is not None
        user_ids = [user.id for user in self.values]
        updated = await self.view.bot.guild_service.update_module_permissions(
            interaction.guild.id,
            interaction.user.id,
            self.view.selected_module,
            user_ids=user_ids,
        )
        self.view.settings = updated
        await interaction.response.edit_message(
            embed=self.view.build_embed(),
            view=self.view,
        )


class PermissionsConfigView(BaseOwnerView):
    """4. Cargos e Permissões — Controle granular por módulo usando seletores nativos."""

    def __init__(
        self,
        bot: FusionBot,
        owner_id: int,
        settings: GuildSettingsSchema,
        selected_module: BotModule = "tickets",
    ) -> None:
        super().__init__(owner_id=owner_id)
        self.bot = bot
        self.settings = settings
        self.selected_module: BotModule = selected_module

        self.add_item(AdminSectionSelect(bot, "permissions"))
        self.add_item(PermissionModuleSelect(selected_module))
        self.add_item(PermissionRoleSelect())
        self.add_item(PermissionUserSelect())
        self.add_item(BackToOverviewButton(bot, row=4))

    def build_embed(self) -> discord.Embed:
        embed = create_panel_embed(
            title=f"{Theme.ICON_PERMISSIONS} Cargos e Permissões por Módulo",
            description=(
                "Defina exatamente quais cargos e usuários podem administrar cada módulo.\n"
                "*Membros com permissão **Administrador** no Discord possuem acesso total automático.*"
            ),
            settings=self.settings,
        )

        for mod, label in MODULE_LABELS.items():
            rule = self.settings.permissions.get(mod, ModulePermissionRule())
            active_marker = "▶ " if mod == self.selected_module else ""
            embed.add_field(
                name=f"{active_marker}{label}",
                value=(
                    f"**Cargos:** {Theme.mention_roles(rule.role_ids)}\n"
                    f"**Usuários:** {Theme.mention_users(rule.user_ids)}"
                ),
                inline=False,
            )
        return embed


# ==============================================================================
# 5. CANAIS E CATEGORIAS PADRÃO
# ==============================================================================


class DefaultCategorySelect(discord.ui.ChannelSelect["ChannelsConfigView"]):
    """Seletor nativo de categoria padrão para criação de tickets."""

    def __init__(self) -> None:
        super().__init__(
            placeholder="Definir categoria padrão para novos tickets...",
            channel_types=[discord.ChannelType.category],
            min_values=0,
            max_values=1,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None and interaction.guild is not None
        cat_id = self.values[0].id if self.values else None
        self.view.settings = await self.view.bot.guild_service.update_default_channels(
            interaction.guild.id,
            interaction.user.id,
            ticket_category_id=cat_id,
        )
        await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)


class DefaultTranscriptChannelSelect(discord.ui.ChannelSelect["ChannelsConfigView"]):
    """Seletor nativo de canal padrão para envio de transcripts HTML."""

    def __init__(self) -> None:
        super().__init__(
            placeholder="Definir canal padrão de transcripts HTML...",
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            min_values=0,
            max_values=1,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None and interaction.guild is not None
        chan_id = self.values[0].id if self.values else None
        self.view.settings = await self.view.bot.guild_service.update_default_channels(
            interaction.guild.id,
            interaction.user.id,
            transcript_channel_id=chan_id,
        )
        await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)


class DefaultRatingChannelSelect(discord.ui.ChannelSelect["ChannelsConfigView"]):
    """Seletor nativo de canal padrão para registro público/interno de avaliações."""

    def __init__(self) -> None:
        super().__init__(
            placeholder="Definir canal padrão de avaliações de atendimento...",
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            min_values=0,
            max_values=1,
            row=3,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None and interaction.guild is not None
        chan_id = self.values[0].id if self.values else None
        self.view.settings = await self.view.bot.guild_service.update_default_channels(
            interaction.guild.id,
            interaction.user.id,
            rating_channel_id=chan_id,
        )
        await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)


class ChannelsConfigView(BaseOwnerView):
    """5. Canais — Configuração visual das categorias e canais padrão."""

    def __init__(
        self,
        bot: FusionBot,
        owner_id: int,
        settings: GuildSettingsSchema,
    ) -> None:
        super().__init__(owner_id=owner_id)
        self.bot = bot
        self.settings = settings

        self.add_item(AdminSectionSelect(bot, "channels"))
        self.add_item(DefaultCategorySelect())
        self.add_item(DefaultTranscriptChannelSelect())
        self.add_item(DefaultRatingChannelSelect())
        self.add_item(BackToOverviewButton(bot, row=4))

    def build_embed(self) -> discord.Embed:
        embed = create_panel_embed(
            title=f"{Theme.ICON_CHANNELS} Canais e Categorias Padrão",
            description=(
                "Selecione diretamente nos menus abaixo os destinos padrão utilizados pelo sistema. "
                "Para limpar uma seleção, abra o menu e desmarque o item."
            ),
            settings=self.settings,
        )
        embed.add_field(
            name="Categoria Padrão de Tickets",
            value=Theme.mention_channel(self.settings.default_ticket_category_id),
            inline=False,
        )
        embed.add_field(
            name="Canal de Transcripts HTML",
            value=Theme.mention_channel(self.settings.default_transcript_channel_id),
            inline=True,
        )
        embed.add_field(
            name="Canal de Avaliações",
            value=Theme.mention_channel(self.settings.default_rating_channel_id),
            inline=True,
        )
        return embed


# ==============================================================================
# 6. SISTEMA DE LOGS POR CATEGORIA
# ==============================================================================

LOG_CATEGORY_LABELS: dict[LogCategory, str] = {
    "tickets": "Tickets (Abertura, Fechamento, Transcripts, Avaliações)",
    "automations": "Automações (Publicações, Edições, Agendamentos)",
    "administration": "Administração (Alterações no Painel e Permissões)",
    "errors": "Erros Internos e Alertas",
}


class LogCategorySelect(discord.ui.Select["LogsConfigView"]):
    """Seleciona qual categoria de log será vinculada a um canal."""

    def __init__(self, selected: LogCategory) -> None:
        options = [
            discord.SelectOption(
                label=cat.capitalize(),
                value=cat,
                description=desc[:100],
                default=(cat == selected),
            )
            for cat, desc in LOG_CATEGORY_LABELS.items()
        ]
        super().__init__(
            placeholder="Escolha a categoria de log...",
            min_values=1,
            max_values=1,
            options=options,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        self.view.selected_category = cast(LogCategory, self.values[0])
        await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)


class LogTargetChannelSelect(discord.ui.ChannelSelect["LogsConfigView"]):
    """Seletor nativo de canal de texto para destino da categoria de log selecionada."""

    def __init__(self) -> None:
        super().__init__(
            placeholder="Selecionar canal de destino para esta categoria de log...",
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            min_values=0,
            max_values=1,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None and interaction.guild is not None
        chan_id = self.values[0].id if self.values else None
        self.view.settings = await self.view.bot.guild_service.update_log_channel(
            interaction.guild.id,
            interaction.user.id,
            self.view.selected_category,
            chan_id,
        )
        await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)


class LogsConfigView(BaseOwnerView):
    """6. Logs — Roteamento de auditoria por categoria e consulta de histórico."""

    def __init__(
        self,
        bot: FusionBot,
        owner_id: int,
        settings: GuildSettingsSchema,
        selected_category: LogCategory = "tickets",
    ) -> None:
        super().__init__(owner_id=owner_id)
        self.bot = bot
        self.settings = settings
        self.selected_category: LogCategory = selected_category

        self.add_item(AdminSectionSelect(bot, "logs"))
        self.add_item(LogCategorySelect(selected_category))
        self.add_item(LogTargetChannelSelect())
        self.add_item(BackToOverviewButton(bot, row=4))

    def build_embed(self) -> discord.Embed:
        embed = create_panel_embed(
            title=f"{Theme.ICON_LOGS} Sistema de Logs e Auditoria",
            description=(
                "Configure canais independentes para cada categoria de evento. "
                "Todos os registros também ficam armazenados com segurança no banco de dados."
            ),
            settings=self.settings,
        )
        for cat, desc in LOG_CATEGORY_LABELS.items():
            marker = "▶ " if cat == self.selected_category else ""
            chan_id = self.settings.log_channels.get(cat)
            embed.add_field(
                name=f"{marker}{desc.split(' (')[0]}",
                value=Theme.mention_channel(chan_id),
                inline=True,
            )
        return embed

    @discord.ui.button(
        label="Ver Histórico Recente",
        emoji="📋",
        style=discord.ButtonStyle.primary,
        row=3,
    )
    async def view_audit_history(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[LogsConfigView],
    ) -> None:
        assert interaction.guild is not None
        entries = await self.bot.log_service.get_recent(interaction.guild.id, limit=25)

        if not entries:
            pages = [
                create_panel_embed(
                    title=f"{Theme.ICON_LOGS} Histórico de Auditoria",
                    description="Nenhum registro encontrado para este servidor.",
                    settings=self.settings,
                )
            ]
        else:
            pages = []
            chunk_size = 5
            for idx in range(0, len(entries), chunk_size):
                chunk = entries[idx : idx + chunk_size]
                lines = [
                    f"• `<t:{int(item.created_at.timestamp())}:g>` **[{item.category}]** {item.details}"
                    for item in chunk
                ]
                pages.append(
                    create_panel_embed(
                        title=f"{Theme.ICON_LOGS} Histórico de Auditoria ({len(entries)} recentes)",
                        description="\n".join(lines),
                        settings=self.settings,
                    )
                )

        paginator = EmbedPaginatorView(
            owner_id=self.owner_id,
            pages=pages,
            on_back=lambda inter: open_admin_section(self.bot, inter, "logs"),
        )
        await interaction.response.edit_message(embed=paginator.current_embed, view=paginator)

    @discord.ui.button(
        label="Desativar Canal Selecionado",
        emoji="🔕",
        style=discord.ButtonStyle.secondary,
        row=3,
    )
    async def clear_selected_log(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[LogsConfigView],
    ) -> None:
        assert interaction.guild is not None
        self.settings = await self.bot.guild_service.update_log_channel(
            interaction.guild.id,
            interaction.user.id,
            self.selected_category,
            None,
        )
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


# ==============================================================================
# 7. PERSONALIZAÇÃO (IDENTIDADE VISUAL DO SERVIDOR)
# ==============================================================================


class BrandingConfigView(BaseOwnerView):
    """7. Personalização — Edição da identidade visual padrão do servidor."""

    def __init__(
        self,
        bot: FusionBot,
        owner_id: int,
        settings: GuildSettingsSchema,
    ) -> None:
        super().__init__(owner_id=owner_id)
        self.bot = bot
        self.settings = settings
        self.add_item(AdminSectionSelect(bot, "branding"))
        self.add_item(BackToOverviewButton(bot, row=2))

    def build_embed(self) -> discord.Embed:
        embed = create_panel_embed(
            title=f"{Theme.ICON_BRANDING} Identidade Visual do Servidor",
            description=(
                "A cor lateral desta mensagem e o rodapé abaixo refletem em tempo real "
                "a identidade visual aplicada nos painéis e embeds padrão."
            ),
            settings=self.settings,
        )
        embed.add_field(
            name="Cor Institucional (HEX)",
            value=f"`#{self.settings.brand_color:06X}`",
            inline=True,
        )
        embed.add_field(
            name="Rodapé Padrão",
            value=f"`{self.settings.brand_footer}`",
            inline=True,
        )
        return embed

    @discord.ui.button(
        label="Editar Cor e Rodapé",
        emoji="✏️",
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def open_branding_modal(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[BrandingConfigView],
    ) -> None:
        modal = BrandingModal(
            self.bot,
            self.settings,
            on_success=lambda inter: open_admin_section(self.bot, inter, "branding"),
        )
        await interaction.response.send_modal(modal)


# ==============================================================================
# 8. CONFIGURAÇÕES GERAIS
# ==============================================================================


class GeneralConfigView(BaseOwnerView):
    """8. Configurações Gerais — Timezone, idioma e ativação global dos módulos."""

    def __init__(
        self,
        bot: FusionBot,
        owner_id: int,
        settings: GuildSettingsSchema,
    ) -> None:
        super().__init__(owner_id=owner_id)
        self.bot = bot
        self.settings = settings
        self.add_item(AdminSectionSelect(bot, "general"))
        self.add_item(BackToOverviewButton(bot, row=2))

    def build_embed(self) -> discord.Embed:
        embed = create_panel_embed(
            title=f"{Theme.ICON_SETTINGS} Configurações Gerais",
            description="Parâmetros globais de operação, fuso horário dos agendamentos e módulos.",
            settings=self.settings,
        )
        embed.add_field(
            name="Fuso Horário",
            value=f"`{self.settings.timezone}`",
            inline=True,
        )
        embed.add_field(
            name="Idioma",
            value=f"`{self.settings.language}`",
            inline=True,
        )
        embed.add_field(
            name="Módulos",
            value=(
                f"**Tickets:** {Theme.status_badge(self.settings.tickets_enabled)}\n"
                f"**Automações:** {Theme.status_badge(self.settings.automations_enabled)}"
            ),
            inline=False,
        )
        return embed

    @discord.ui.button(
        label="Editar Fuso Horário e Idioma",
        emoji="🌐",
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def edit_general_modal(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[GeneralConfigView],
    ) -> None:
        modal = GeneralSettingsModal(
            self.bot,
            self.settings,
            on_success=lambda inter: open_admin_section(self.bot, inter, "general"),
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Alternar Tickets",
        emoji=Theme.ICON_TICKETS,
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def toggle_tickets_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[GeneralConfigView],
    ) -> None:
        assert interaction.guild is not None
        await self.bot.guild_service.toggle_module(
            interaction.guild.id,
            interaction.user.id,
            "tickets",
        )
        await open_admin_section(self.bot, interaction, "general")

    @discord.ui.button(
        label="Alternar Automações",
        emoji=Theme.ICON_AUTOMATIONS,
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def toggle_automations_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[GeneralConfigView],
    ) -> None:
        assert interaction.guild is not None
        await self.bot.guild_service.toggle_module(
            interaction.guild.id,
            interaction.user.id,
            "automations",
        )
        await open_admin_section(self.bot, interaction, "general")