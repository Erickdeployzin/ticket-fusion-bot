"""Interface administrativa completa de gerenciamento de painéis de tickets (/painel)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from src.bot.modals.ticket_modals import (
    TicketAddDepartmentModal,
    TicketAddFormFieldModal,
    TicketPanelAppearanceModal,
    TicketPanelButtonModal,
    TicketPanelCreateModal,
    TicketPanelRulesModal,
    TicketPanelWelcomeModal,
)
from src.bot.ui.components import BaseOwnerView, ConfirmationView
from src.bot.ui.embeds import create_panel_embed, error_embed, success_embed, warning_embed
from src.bot.ui.theme import Theme
from src.bot.views.admin.navigation import open_admin_section
from src.bot.views.tickets.ticket_runtime_views import TicketPanelLauncherView
from src.database.schemas import GuildSettingsSchema, TicketPanelSchema

if TYPE_CHECKING:
    from src.bot.client import FusionBot


async def open_ticket_panel_manager(
    bot: FusionBot,
    interaction: discord.Interaction,
) -> None:
    """Abre a listagem central de painéis de tickets do servidor."""
    assert interaction.guild is not None
    assert isinstance(interaction.user, discord.Member)

    settings = await bot.guild_service.get_settings(interaction.guild.id)
    bot.permissions.ensure_module_access(interaction.user, settings, "tickets")

    panels = await bot.ctx.db.tickets.list_panels(interaction.guild.id)
    view = TicketPanelListView(bot, interaction.user.id, settings, panels)
    embed = view.build_embed()

    if interaction.response.is_done():
        await interaction.edit_original_response(embed=embed, view=view)
    else:
        await interaction.response.edit_message(embed=embed, view=view)


async def open_ticket_panel_editor(
    bot: FusionBot,
    interaction: discord.Interaction,
    panel: TicketPanelSchema,
) -> None:
    """Abre o editor completo de um painel específico."""
    assert interaction.guild is not None
    settings = await bot.guild_service.get_settings(interaction.guild.id)
    view = TicketPanelEditorView(bot, interaction.user.id, settings, panel)
    embed = view.build_embed()

    if interaction.response.is_done():
        await interaction.edit_original_response(embed=embed, view=view)
    else:
        await interaction.response.edit_message(embed=embed, view=view)


class _PanelPickSelect(discord.ui.Select["TicketPanelListView"]):
    """Dropdown para selecionar um painel existente para edição."""

    def __init__(self, panels: list[TicketPanelSchema]) -> None:
        options = [
            discord.SelectOption(
                label=p.name[:100],
                value=p.id,
                description=(
                    f"{'Ativo' if p.enabled else 'Desativado'} • "
                    f"Modo: {p.open_mode} • Deptos: {len(p.departments)}"
                )[:100],
                emoji="🟢" if p.enabled else "🔴",
            )
            for p in panels[:25]
        ]
        super().__init__(
            placeholder="Selecione um painel para editar, publicar ou duplicar...",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None and interaction.guild is not None
        panel = await self.view.bot.ctx.db.tickets.get_panel(
            interaction.guild.id, self.values[0]
        )
        if panel is None:
            await interaction.response.send_message(
                embed=error_embed("Painel Não Encontrado", "Atualize a lista de painéis."),
                ephemeral=True,
            )
            return
        await open_ticket_panel_editor(self.view.bot, interaction, panel)


class TicketPanelListView(BaseOwnerView):
    """Lista todos os painéis de tickets configurados e estatísticas da equipe."""

    def __init__(
        self,
        bot: FusionBot,
        owner_id: int,
        settings: GuildSettingsSchema,
        panels: list[TicketPanelSchema],
    ) -> None:
        super().__init__(owner_id=owner_id)
        self.bot = bot
        self._settings = settings
        self._panels = panels

        if panels:
            self.add_item(_PanelPickSelect(panels))

    def build_embed(self) -> discord.Embed:
        embed = create_panel_embed(
            title=f"{Theme.ICON_TICKETS} Gerenciador de Painéis de Tickets",
            description=(
                "Crie múltiplos painéis independentes (Suporte, Financeiro, Denúncias, VIP, etc.) "
                "e publique-os em qualquer canal do servidor."
            ),
            settings=self._settings,
        )

        if not self._panels:
            embed.add_field(
                name="Nenhum Painel Configurado",
                value="Clique em **Criar Novo Painel** abaixo para configurar o primeiro.",
                inline=False,
            )
        else:
            for panel in self._panels[:12]:
                status = Theme.status_badge(panel.enabled)
                dest = Theme.mention_channel(panel.channel_id)
                embed.add_field(
                    name=f"{panel.name}",
                    value=(
                        f"**Estado:** {status}\n"
                        f"**Canal:** {dest}\n"
                        f"**Modo:** `{panel.open_mode}` • **Limite:** `{panel.max_tickets_per_user}`"
                    ),
                    inline=True,
                )
        return embed

    @discord.ui.button(
        label="Criar Novo Painel",
        emoji="➕",
        style=discord.ButtonStyle.success,
        row=1,
    )
    async def create_panel_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[TicketPanelListView],
    ) -> None:
        modal = TicketPanelCreateModal(
            self.bot,
            on_created=lambda inter, panel: open_ticket_panel_editor(self.bot, inter, panel),
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Ranking e Avaliações da Equipe",
        emoji="⭐",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def staff_stats_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[TicketPanelListView],
    ) -> None:
        assert interaction.guild is not None
        stats = await self.bot.ticket_service.get_staff_statistics(interaction.guild.id)
        stats.sort(key=lambda item: (item["average"], item["total"]), reverse=True)

        if not stats:
            desc = "*Nenhuma avaliação de atendimento registrada até o momento.*"
        else:
            lines = [
                f"**{idx}.** <@{int(row['staff_id'])}> — ⭐ **{row['average']:.2f}/5.00** "
                f"(`{int(row['total'])}` avaliações)"
                for idx, row in enumerate(stats[:15], start=1)
            ]
            desc = "\n".join(lines)

        embed = create_panel_embed(
            title="⭐ Desempenho e Avaliações por Atendente",
            description=desc,
            settings=self._settings,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="Voltar ao Módulo Tickets",
        emoji=Theme.ICON_BACK,
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def back_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[TicketPanelListView],
    ) -> None:
        await open_admin_section(self.bot, interaction, "tickets")


# ==============================================================================
# EDITOR COMPLETO DE PAINEL INDIVIDUAL
# ==============================================================================


class _PanelCategorySelect(discord.ui.ChannelSelect["TicketPanelEditorView"]):
    """Seletor nativo da categoria Discord onde os tickets deste painel serão criados."""

    def __init__(self) -> None:
        super().__init__(
            placeholder="Selecionar categoria de destino dos tickets...",
            channel_types=[discord.ChannelType.category],
            min_values=0,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        self.view.panel.category_id = self.values[0].id if self.values else None
        self.view.panel = await self.view.bot.ticket_service.save_panel(
            self.view.panel,
            interaction.user.id,
            f"Categoria do painel **{self.view.panel.name}** atualizada.",
        )
        await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)


class _PanelPublishChannelSelect(discord.ui.ChannelSelect["TicketPanelEditorView"]):
    """Seletor nativo do canal onde o painel será publicado."""

    def __init__(self) -> None:
        super().__init__(
            placeholder="Selecionar canal onde este painel será publicado...",
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            min_values=1,
            max_values=1,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        self.view.panel.channel_id = self.values[0].id
        self.view.panel = await self.view.bot.ticket_service.save_panel(
            self.view.panel,
            interaction.user.id,
            f"Canal de publicação do painel **{self.view.panel.name}** definido para <#{self.values[0].id}>.",
        )
        await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)


class _PanelStaffRoleSelect(discord.ui.RoleSelect["TicketPanelEditorView"]):
    """Seletor nativo dos cargos da equipe de atendimento deste painel."""

    def __init__(self) -> None:
        super().__init__(
            placeholder="Selecionar cargos de atendimento responsáveis...",
            min_values=0,
            max_values=10,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        self.view.panel.staff_role_ids = [r.id for r in self.values]
        for dept in self.view.panel.departments:
            if not dept.staff_role_ids:
                dept.staff_role_ids = list(self.view.panel.staff_role_ids)
        self.view.panel = await self.view.bot.ticket_service.save_panel(
            self.view.panel,
            interaction.user.id,
            f"Cargos de atendimento do painel **{self.view.panel.name}** atualizados.",
        )
        await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)


class TicketPanelEditorView(BaseOwnerView):
    """Editor visual completo de um painel de tickets (100% pelo Discord)."""

    def __init__(
        self,
        bot: FusionBot,
        owner_id: int,
        settings: GuildSettingsSchema,
        panel: TicketPanelSchema,
    ) -> None:
        super().__init__(owner_id=owner_id)
        self.bot = bot
        self._settings = settings
        self.panel = panel

        self.add_item(_PanelCategorySelect())
        self.add_item(_PanelPublishChannelSelect())
        self.add_item(_PanelStaffRoleSelect())

        self.toggle_enabled_btn.label = "Desativar" if panel.enabled else "Ativar"
        self.toggle_enabled_btn.style = (
            discord.ButtonStyle.secondary if panel.enabled else discord.ButtonStyle.success
        )

    def build_embed(self) -> discord.Embed:
        p = self.panel
        bh_text = (
            f"`{p.business_hours.start_hour:02d}h às {p.business_hours.end_hour:02d}h`"
            if p.business_hours.enabled
            else "`24 horas (sem restrição)`"
        )
        dept_names = (
            ", ".join(f"`{d.label}`" for d in p.departments[:8])
            if p.departments
            else "`Padrão único`"
        )
        form_names = (
            ", ".join(f"`{f.label}`" for f in p.form_fields)
            if p.form_fields
            else "`Nenhuma pergunta`"
        )

        embed = create_panel_embed(
            title=f"{Theme.ICON_TICKETS} Editor de Painel • {p.name}",
            description=(
                "Configure todos os detalhes abaixo e clique em **Visualizar** ou **Publicar / Atualizar**."
            ),
            settings=self._settings,
        )
        embed.add_field(
            name="Status e Destinos",
            value=(
                f"**Estado:** {Theme.status_badge(p.enabled)}\n"
                f"**Canal Publicação:** {Theme.mention_channel(p.channel_id)}\n"
                f"**Categoria Tickets:** {Theme.mention_channel(p.category_id)}\n"
                f"**Cargos Atendimento:** {Theme.mention_roles(p.staff_role_ids)}"
            ),
            inline=False,
        )
        embed.add_field(
            name="Interface e Abertura",
            value=(
                f"**Modo:** `{p.open_mode}`\n"
                f"**Botão:** `{p.button_emoji or ''} {p.button_label}` (`{p.button_style}`)\n"
                f"**Banner:** {'`Configurado`' if p.embed.image_url else '`Sem banner`'}\n"
                f"**Departamentos ({len(p.departments)}):** {dept_names}"
            ),
            inline=True,
        )
        embed.add_field(
            name="Regras e Formulário",
            value=(
                f"**Limite/Usuário:** `{p.max_tickets_per_user}` | **Cooldown:** `{p.cooldown_seconds}s`\n"
                f"**Expediente:** {bh_text}\n"
                f"**Reabertura:** {'`Sim`' if p.allow_reopen else '`Não`'} | **Avaliação:** {'`Sim`' if p.enable_rating else '`Não`'}\n"
                f"**Formulário ({len(p.form_fields)}/5):** {form_names}"
            ),
            inline=True,
        )
        return embed

    # --- Linha 3: Edição de Conteúdo, Controles e Departamentos ---

    @discord.ui.button(label="Aparência", emoji="🎨", style=discord.ButtonStyle.secondary, row=3)
    async def edit_appearance_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[TicketPanelEditorView],
    ) -> None:
        modal = TicketPanelAppearanceModal(
            self.bot,
            self.panel,
            on_saved=lambda inter, updated: open_ticket_panel_editor(self.bot, inter, updated),
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Botão/Dropdown", emoji="🔘", style=discord.ButtonStyle.secondary, row=3)
    async def edit_button_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[TicketPanelEditorView],
    ) -> None:
        modal = TicketPanelButtonModal(
            self.bot,
            self.panel,
            on_saved=lambda inter, updated: open_ticket_panel_editor(self.bot, inter, updated),
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="+ Depto", emoji="🗂️", style=discord.ButtonStyle.secondary, row=3)
    async def add_dept_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[TicketPanelEditorView],
    ) -> None:
        modal = TicketAddDepartmentModal(
            self.bot,
            self.panel,
            on_saved=lambda inter, updated: open_ticket_panel_editor(self.bot, inter, updated),
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="+ Pergunta", emoji="📝", style=discord.ButtonStyle.secondary, row=3)
    async def add_form_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[TicketPanelEditorView],
    ) -> None:
        modal = TicketAddFormFieldModal(
            self.bot,
            self.panel,
            on_saved=lambda inter, updated: open_ticket_panel_editor(self.bot, inter, updated),
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Regras/Msg Inicial", emoji="⚙️", style=discord.ButtonStyle.secondary, row=3)
    async def edit_rules_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[TicketPanelEditorView],
    ) -> None:
        # Sub-menu rápido para escolher entre Regras/Expediente, Msg Inicial ou Limpar Listas
        sub_view = _TicketPanelAdvancedOptionsView(self.bot, self.owner_id, self.panel)
        await interaction.response.send_message(
            embed=create_panel_embed(
                title=f"Configurações Avançadas • {self.panel.name}",
                description="Escolha qual configuração avançada deseja ajustar:",
                settings=self._settings,
            ),
            view=sub_view,
            ephemeral=True,
        )

    # --- Linha 4: Pré-visualizar, Publicar, Duplicar, Ativar/Desativar, Excluir, Voltar ---

    @discord.ui.button(
        label="Visualizar",
        emoji=Theme.ICON_PREVIEW,
        style=discord.ButtonStyle.secondary,
        row=4,
    )
    async def preview_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[TicketPanelEditorView],
    ) -> None:
        assert interaction.guild is not None
        preview_embed = self.bot.ticket_service.build_panel_public_embed(
            interaction.guild, self.panel, self._settings
        )
        preview_view = TicketPanelLauncherView(self.bot, self.panel)
        for child in preview_view.children:
            if isinstance(child, (discord.ui.Button, discord.ui.Select)):
                child.disabled = True

        await interaction.response.send_message(
            content="**Pré-visualização do Painel** *(os controles estão desativados apenas nesta prévia)*:",
            embed=preview_embed,
            view=preview_view,
            ephemeral=True,
        )

    @discord.ui.button(
        label="Publicar / Atualizar",
        emoji=Theme.ICON_PUBLISH,
        style=discord.ButtonStyle.primary,
        row=4,
    )
    async def publish_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[TicketPanelEditorView],
    ) -> None:
        assert interaction.guild is not None
        self.panel = await self.bot.ticket_service.publish_or_update_panel(
            interaction.guild,
            self.panel,
            interaction.user.id,
        )
        await interaction.response.edit_message(embed=self.build_embed(), view=self)
        await interaction.followup.send(
            embed=success_embed(
                "Painel Publicado",
                f"O painel **{self.panel.name}** foi publicado/atualizado em <#{self.panel.channel_id}>.",
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="Duplicar", emoji="📑", style=discord.ButtonStyle.secondary, row=4)
    async def duplicate_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[TicketPanelEditorView],
    ) -> None:
        assert interaction.guild is not None
        cloned = await self.bot.ticket_service.duplicate_panel(
            interaction.guild.id,
            interaction.user.id,
            self.panel.id,
        )
        await open_ticket_panel_editor(self.bot, interaction, cloned)

    @discord.ui.button(label="Ativar/Desativar", style=discord.ButtonStyle.secondary, row=4)
    async def toggle_enabled_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[TicketPanelEditorView],
    ) -> None:
        self.panel.enabled = not self.panel.enabled
        state_str = "ativado" if self.panel.enabled else "desativado"
        self.panel = await self.bot.ticket_service.save_panel(
            self.panel,
            interaction.user.id,
            f"Painel **{self.panel.name}** foi **{state_str}**.",
        )
        await open_ticket_panel_editor(self.bot, interaction, self.panel)

    @discord.ui.button(label="Excluir / Voltar", emoji="🗑️", style=discord.ButtonStyle.danger, row=4)
    async def delete_or_back_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[TicketPanelEditorView],
    ) -> None:
        assert interaction.guild is not None
        guild_id = interaction.guild.id
        panel_id = self.panel.id
        panel_name = self.panel.name

        async def _confirm_delete(confirm_inter: discord.Interaction) -> None:
            await self.bot.ticket_service.delete_panel(guild_id, confirm_inter.user.id, panel_id)
            await open_ticket_panel_manager(self.bot, confirm_inter)

        confirm_view = ConfirmationView(
            owner_id=self.owner_id,
            on_confirm=_confirm_delete,
            on_cancel=lambda cancel_inter: open_ticket_panel_manager(self.bot, cancel_inter),
            confirm_label=f"Excluir '{panel_name[:25]}'",
            cancel_label="Voltar à Lista",
        )
        await interaction.response.edit_message(
            embed=warning_embed(
                f"Gerenciar Saída • {panel_name}",
                "Clique em **Voltar à Lista** para retornar aos painéis ou confirme a exclusão permanente deste painel.",
            ),
            view=confirm_view,
        )


class _TicketPanelAdvancedOptionsView(BaseOwnerView):
    """Sub-menu efêmero para configurações complementares do painel."""

    def __init__(self, bot: FusionBot, owner_id: int, panel: TicketPanelSchema) -> None:
        super().__init__(owner_id=owner_id, timeout=120.0)
        self._bot = bot
        self._panel = panel

    @discord.ui.button(label="Regras e Expediente", emoji="⏰", style=discord.ButtonStyle.primary, row=0)
    async def rules_modal_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[_TicketPanelAdvancedOptionsView],
    ) -> None:
        await interaction.response.send_modal(
            TicketPanelRulesModal(
                self._bot,
                self._panel,
                on_saved=lambda inter, _p: inter.response.send_message(
                    embed=success_embed("Regras Salvas", "Regras e horário atualizados!"),
                    ephemeral=True,
                ),
            )
        )

    @discord.ui.button(label="Mensagem Inicial", emoji="💬", style=discord.ButtonStyle.primary, row=0)
    async def welcome_modal_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[_TicketPanelAdvancedOptionsView],
    ) -> None:
        await interaction.response.send_modal(
            TicketPanelWelcomeModal(
                self._bot,
                self._panel,
                on_saved=lambda inter, _p: inter.response.send_message(
                    embed=success_embed("Mensagem Salva", "Mensagem inicial do ticket atualizada!"),
                    ephemeral=True,
                ),
            )
        )

    @discord.ui.button(label="Alternar Reabertura", emoji="🔓", style=discord.ButtonStyle.secondary, row=1)
    async def toggle_reopen_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[_TicketPanelAdvancedOptionsView],
    ) -> None:
        self._panel.allow_reopen = not self._panel.allow_reopen
        await self._bot.ticket_service.save_panel(
            self._panel,
            interaction.user.id,
            f"Reabertura do painel **{self._panel.name}** definida para `{self._panel.allow_reopen}`.",
        )
        await interaction.response.send_message(
            embed=success_embed(
                "Configuração Atualizada",
                f"Permitir reabertura: **{'Ativado' if self._panel.allow_reopen else 'Desativado'}**.",
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="Alternar Avaliação", emoji="⭐", style=discord.ButtonStyle.secondary, row=1)
    async def toggle_rating_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[_TicketPanelAdvancedOptionsView],
    ) -> None:
        self._panel.enable_rating = not self._panel.enable_rating
        await self._bot.ticket_service.save_panel(
            self._panel,
            interaction.user.id,
            f"Avaliação pós-atendimento do painel **{self._panel.name}** definida para `{self._panel.enable_rating}`.",
        )
        await interaction.response.send_message(
            embed=success_embed(
                "Configuração Atualizada",
                f"Avaliação 1-5 estrelas: **{'Ativada' if self._panel.enable_rating else 'Desativada'}**.",
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="Limpar Deptos/Perguntas", emoji="🧹", style=discord.ButtonStyle.danger, row=1)
    async def clear_lists_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[_TicketPanelAdvancedOptionsView],
    ) -> None:
        self._panel.departments.clear()
        self._panel.form_fields.clear()
        self._panel.open_mode = "button"
        await self._bot.ticket_service.save_panel(
            self._panel,
            interaction.user.id,
            f"Departamentos e formulário do painel **{self._panel.name}** resetados.",
        )
        await interaction.response.send_message(
            embed=success_embed(
                "Listas Limpas",
                "Departamentos e perguntas pré-abertura foram removidos deste painel.",
            ),
            ephemeral=True,
        )