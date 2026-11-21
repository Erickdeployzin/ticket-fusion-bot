"""Interface administrativa completa de mensagens personalizadas, componentes e agendamentos."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from src.bot.modals.automation_modals import (
    AutomationAddButtonModal,
    AutomationAddDropdownOptionModal,
    AutomationAddFieldModal,
    AutomationContentAndEmbedModal,
    AutomationCreateModal,
    AutomationMediaAndAuthorModal,
    AutomationScheduleModal,
)
from src.bot.ui.components import BaseOwnerView, ConfirmationView
from src.bot.ui.embeds import create_panel_embed, error_embed, success_embed, warning_embed
from src.bot.ui.theme import Theme
from src.bot.views.admin.navigation import open_admin_section
from src.database.schemas import AutomationRuleSchema, GuildSettingsSchema
from src.services.automation_service import AUTOMATION_TYPE_LABELS

if TYPE_CHECKING:
    from src.bot.client import FusionBot


async def open_automation_manager(
    bot: FusionBot,
    interaction: discord.Interaction,
) -> None:
    """Abre a listagem de mensagens automáticas e personalizadas no /painel."""
    assert interaction.guild is not None
    assert isinstance(interaction.user, discord.Member)

    settings = await bot.guild_service.get_settings(interaction.guild.id)
    bot.permissions.ensure_module_access(interaction.user, settings, "automations")

    rules = await bot.ctx.db.automations.list_automations(interaction.guild.id)
    view = AutomationRuleListView(bot, interaction.user.id, settings, rules)
    embed = view.build_embed()

    if interaction.response.is_done():
        await interaction.edit_original_response(embed=embed, view=view)
    else:
        await interaction.response.edit_message(embed=embed, view=view)


async def open_automation_editor(
    bot: FusionBot,
    interaction: discord.Interaction,
    rule: AutomationRuleSchema,
) -> None:
    """Abre o editor visual completo de uma regra de mensagem/automação."""
    assert interaction.guild is not None
    settings = await bot.guild_service.get_settings(interaction.guild.id)
    view = AutomationRuleEditorView(bot, interaction.user.id, settings, rule)
    embed = view.build_embed()

    if interaction.response.is_done():
        await interaction.edit_original_response(embed=embed, view=view)
    else:
        await interaction.response.edit_message(embed=embed, view=view)


class _AutomationPickSelect(discord.ui.Select["AutomationRuleListView"]):
    """Dropdown para abrir o editor de uma mensagem/automação existente."""

    def __init__(self, rules: list[AutomationRuleSchema]) -> None:
        options = [
            discord.SelectOption(
                label=r.name[:100],
                value=r.id,
                description=(
                    f"{AUTOMATION_TYPE_LABELS.get(r.automation_type, r.automation_type)} • "
                    f"{'Ativa' if r.enabled else 'Desativada'}"
                )[:100],
                emoji="🟢" if r.enabled else "🔴",
            )
            for r in rules[:25]
        ]
        super().__init__(
            placeholder="Selecione uma mensagem ou automação para editar...",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None and interaction.guild is not None
        rule = await self.view.bot.ctx.db.automations.get_automation(
            interaction.guild.id, self.values[0]
        )
        if rule is None:
            await interaction.response.send_message(
                embed=error_embed("Item Não Encontrado", "Atualize a listagem de automações."),
                ephemeral=True,
            )
            return
        await open_automation_editor(self.view.bot, interaction, rule)


class AutomationRuleListView(BaseOwnerView):
    """Listagem central de mensagens personalizadas, eventos e agendamentos."""

    def __init__(
        self,
        bot: FusionBot,
        owner_id: int,
        settings: GuildSettingsSchema,
        rules: list[AutomationRuleSchema],
    ) -> None:
        super().__init__(owner_id=owner_id)
        self.bot = bot
        self._settings = settings
        self._rules = rules

        if rules:
            self.add_item(_AutomationPickSelect(rules))

    def build_embed(self) -> discord.Embed:
        embed = create_panel_embed(
            title=f"{Theme.ICON_AUTOMATIONS} Gerenciador de Mensagens e Automações",
            description=(
                "Crie mensagens personalizadas com embeds, banners, botões e dropdowns, "
                "ou configure disparos automáticos de boas-vindas, despedida e agendamentos."
            ),
            settings=self._settings,
        )

        if not self._rules:
            embed.add_field(
                name="Nenhuma Regra Configurada",
                value="Clique em **Criar Nova Mensagem** abaixo para começar.",
                inline=False,
            )
        else:
            for rule in self._rules[:12]:
                type_label = AUTOMATION_TYPE_LABELS.get(rule.automation_type, rule.automation_type)
                sched_info = (
                    f"<t:{int(rule.schedule.next_run_at.timestamp())}:R>"
                    if rule.schedule.enabled and rule.schedule.next_run_at
                    else "`Manual / Evento`"
                )
                embed.add_field(
                    name=rule.name,
                    value=(
                        f"**Estado:** {Theme.status_badge(rule.enabled)}\n"
                        f"**Tipo:** `{type_label}`\n"
                        f"**Canal:** {Theme.mention_channel(rule.target_channel_id)}\n"
                        f"**Próximo Disparo:** {sched_info}"
                    ),
                    inline=True,
                )
        return embed

    @discord.ui.button(
        label="Criar Nova Mensagem",
        emoji="➕",
        style=discord.ButtonStyle.success,
        row=1,
    )
    async def create_rule_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[AutomationRuleListView],
    ) -> None:
        modal = AutomationCreateModal(
            self.bot,
            on_created=lambda inter, rule: open_automation_editor(self.bot, inter, rule),
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Voltar ao Módulo Automações",
        emoji=Theme.ICON_BACK,
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def back_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[AutomationRuleListView],
    ) -> None:
        await open_admin_section(self.bot, interaction, "automations")


# ==============================================================================
# EDITOR VISUAL COMPLETO DE MENSAGEM / AUTOMAÇÃO
# ==============================================================================


class _AutomationTargetChannelSelect(discord.ui.ChannelSelect["AutomationRuleEditorView"]):
    """Seletor nativo do canal de destino da mensagem ou evento automático."""

    def __init__(self) -> None:
        super().__init__(
            placeholder="Selecionar canal de destino para publicação/envio...",
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        self.view.rule.target_channel_id = self.values[0].id
        self.view.rule = await self.view.bot.automation_service.save_rule(
            self.view.rule,
            interaction.user.id,
            f"Canal de destino de **{self.view.rule.name}** definido para <#{self.values[0].id}>.",
        )
        await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)


class _AutomationMentionRoleSelect(discord.ui.RoleSelect["AutomationRuleEditorView"]):
    """Seletor nativo dos cargos mencionados ao publicar a mensagem."""

    def __init__(self) -> None:
        super().__init__(
            placeholder="Selecionar cargos mencionados junto à mensagem (opcional)...",
            min_values=0,
            max_values=10,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        self.view.rule.mention_role_ids = [r.id for r in self.values]
        self.view.rule = await self.view.bot.automation_service.save_rule(
            self.view.rule,
            interaction.user.id,
            f"Menções de cargo da mensagem **{self.view.rule.name}** atualizadas.",
        )
        await interaction.response.edit_message(embed=self.view.build_embed(), view=self.view)


class AutomationRuleEditorView(BaseOwnerView):
    """Editor visual interativo para configurar embed, botões, dropdowns e agendamento."""

    def __init__(
        self,
        bot: FusionBot,
        owner_id: int,
        settings: GuildSettingsSchema,
        rule: AutomationRuleSchema,
    ) -> None:
        super().__init__(owner_id=owner_id)
        self.bot = bot
        self._settings = settings
        self.rule = rule

        self.add_item(_AutomationTargetChannelSelect())
        self.add_item(_AutomationMentionRoleSelect())

        self.toggle_enabled_btn.label = "Desativar" if rule.enabled else "Ativar"
        self.toggle_enabled_btn.style = (
            discord.ButtonStyle.secondary if rule.enabled else discord.ButtonStyle.success
        )

    def build_embed(self) -> discord.Embed:
        r = self.rule
        type_label = AUTOMATION_TYPE_LABELS.get(r.automation_type, r.automation_type)

        if r.schedule.enabled and r.schedule.next_run_at:
            ts = int(r.schedule.next_run_at.timestamp())
            sched_desc = (
                f"**Ativo** (`{r.schedule.frequency}`) • Próximo: <t:{ts}:F> (<t:{ts}:R>)"
            )
        else:
            sched_desc = "`Desativado (publicação manual ou por evento)`"

        dd_opts_count = len(r.dropdowns[0].options) if r.dropdowns else 0
        mentions_summary = (
            f"{'@everyone • ' if r.mention_everyone else ''}"
            f"{Theme.mention_roles(r.mention_role_ids)}"
        )

        embed = create_panel_embed(
            title=f"{Theme.ICON_AUTOMATIONS} Editor Visual • {r.name}",
            description=(
                "Variáveis disponíveis: `{user}`, `{username}`, `{user_id}`, `{server}`, "
                "`{member_count}`, `{date}`, `{time}`, `{created_at}`."
            ),
            settings=self._settings,
        )
        embed.add_field(
            name="Configuração Geral",
            value=(
                f"**Estado:** {Theme.status_badge(r.enabled)} | **Tipo:** `{type_label}`\n"
                f"**Canal Destino:** {Theme.mention_channel(r.target_channel_id)}\n"
                f"**Menções:** {mentions_summary}\n"
                f"**Agendamento:** {sched_desc}"
            ),
            inline=False,
        )
        embed.add_field(
            name="Estrutura Visual",
            value=(
                f"**Modo Embed:** {'`Ativada`' if r.use_embed else '`Somente Texto`'}\n"
                f"**Campos Embed:** `{len(r.embed.fields)}/25`\n"
                f"**Banner/Thumb:** {'`Sim`' if (r.embed.image_url or r.embed.thumbnail_url) else '`Não`'}"
            ),
            inline=True,
        )
        embed.add_field(
            name="Componentes Interativos",
            value=(
                f"**Botões:** `{len(r.buttons)}/20`\n"
                f"**Dropdowns:** `{len(r.dropdowns)}` (`{dd_opts_count}` opções)\n"
                f"**Msg Publicada:** {'`Sim (editável)`' if r.published_message_id else '`Ainda não`'}"
            ),
            inline=True,
        )
        return embed

    # --- Linha 2: Conteúdo, Mídia, Campos e Modos ---

    @discord.ui.button(label="Texto & Embed", emoji="✏️", style=discord.ButtonStyle.secondary, row=2)
    async def edit_content_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[AutomationRuleEditorView],
    ) -> None:
        modal = AutomationContentAndEmbedModal(
            self.bot,
            self.rule,
            on_saved=lambda inter, updated: open_automation_editor(self.bot, inter, updated),
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Mídia & Autor", emoji="🖼️", style=discord.ButtonStyle.secondary, row=2)
    async def edit_media_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[AutomationRuleEditorView],
    ) -> None:
        modal = AutomationMediaAndAuthorModal(
            self.bot,
            self.rule,
            on_saved=lambda inter, updated: open_automation_editor(self.bot, inter, updated),
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="+ Campo", emoji="📑", style=discord.ButtonStyle.secondary, row=2)
    async def add_field_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[AutomationRuleEditorView],
    ) -> None:
        modal = AutomationAddFieldModal(
            self.bot,
            self.rule,
            on_saved=lambda inter, updated: open_automation_editor(self.bot, inter, updated),
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Alternar Embed", emoji="🧩", style=discord.ButtonStyle.secondary, row=2)
    async def toggle_embed_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[AutomationRuleEditorView],
    ) -> None:
        self.rule.use_embed = not self.rule.use_embed
        self.rule = await self.bot.automation_service.save_rule(
            self.rule,
            interaction.user.id,
            f"Modo embed de **{self.rule.name}** definido para `{self.rule.use_embed}`.",
        )
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="@everyone", emoji="📢", style=discord.ButtonStyle.secondary, row=2)
    async def toggle_everyone_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[AutomationRuleEditorView],
    ) -> None:
        self.rule.mention_everyone = not self.rule.mention_everyone
        self.rule = await self.bot.automation_service.save_rule(
            self.rule,
            interaction.user.id,
            f"Menção @everyone de **{self.rule.name}** definida para `{self.rule.mention_everyone}`.",
        )
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    # --- Linha 3: Botões, Dropdowns, Agendamento e Limpeza ---

    @discord.ui.button(label="+ Botão", emoji="🔘", style=discord.ButtonStyle.secondary, row=3)
    async def add_button_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[AutomationRuleEditorView],
    ) -> None:
        modal = AutomationAddButtonModal(
            self.bot,
            self.rule,
            on_saved=lambda inter, updated: open_automation_editor(self.bot, inter, updated),
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="+ Dropdown", emoji="📂", style=discord.ButtonStyle.secondary, row=3)
    async def add_dropdown_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[AutomationRuleEditorView],
    ) -> None:
        modal = AutomationAddDropdownOptionModal(
            self.bot,
            self.rule,
            on_saved=lambda inter, updated: open_automation_editor(self.bot, inter, updated),
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Agendamento", emoji="⏰", style=discord.ButtonStyle.secondary, row=3)
    async def schedule_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[AutomationRuleEditorView],
    ) -> None:
        modal = AutomationScheduleModal(
            self.bot,
            self.rule,
            on_saved=lambda inter, updated: open_automation_editor(self.bot, inter, updated),
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Limpar Componentes", emoji="🧹", style=discord.ButtonStyle.secondary, row=3)
    async def clear_components_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[AutomationRuleEditorView],
    ) -> None:
        self.rule.buttons.clear()
        self.rule.dropdowns.clear()
        self.rule.embed.fields.clear()
        self.rule = await self.bot.automation_service.save_rule(
            self.rule,
            interaction.user.id,
            f"Botões, dropdowns e campos de **{self.rule.name}** foram limpos.",
        )
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    # --- Linha 4: Pré-visualizar, Publicar/Atualizar, Ativar/Desativar, Excluir/Voltar ---

    @discord.ui.button(
        label="Visualizar",
        emoji=Theme.ICON_PREVIEW,
        style=discord.ButtonStyle.secondary,
        row=4,
    )
    async def preview_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[AutomationRuleEditorView],
    ) -> None:
        assert interaction.guild is not None
        content, embed, view, _mentions = self.bot.automation_service.build_message_payload(
            interaction.guild,
            self.rule,
            self._settings,
            member=interaction.user,
            disable_components=True,
        )
        prefix = "**Pré-visualização da Mensagem** *(placeholders resolvidos para você)*:\n"
        full_preview_content = f"{prefix}{content or ''}"[:2000]

        await interaction.response.send_message(
            content=full_preview_content,
            embed=embed,
            view=view or discord.utils.MISSING,
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
        _button: discord.ui.Button[AutomationRuleEditorView],
    ) -> None:
        assert interaction.guild is not None
        self.rule, sent_msg = await self.bot.automation_service.publish_or_update_message(
            interaction.guild,
            self.rule,
            interaction.user.id,
        )
        await interaction.response.edit_message(embed=self.build_embed(), view=self)
        await interaction.followup.send(
            embed=success_embed(
                "Mensagem Publicada",
                f"Publicada/atualizada com sucesso em <#{sent_msg.channel.id}> ([Ir para mensagem]({sent_msg.jump_url})).",
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="Ativar/Desativar", style=discord.ButtonStyle.secondary, row=4)
    async def toggle_enabled_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[AutomationRuleEditorView],
    ) -> None:
        self.rule.enabled = not self.rule.enabled
        state_str = "ativada" if self.rule.enabled else "desativada"
        self.rule = await self.bot.automation_service.save_rule(
            self.rule,
            interaction.user.id,
            f"Automação **{self.rule.name}** foi **{state_str}**.",
        )
        await open_automation_editor(self.bot, interaction, self.rule)

    @discord.ui.button(label="Excluir / Voltar", emoji="🗑️", style=discord.ButtonStyle.danger, row=4)
    async def delete_or_back_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[AutomationRuleEditorView],
    ) -> None:
        assert interaction.guild is not None
        guild_id = interaction.guild.id
        rule_id = self.rule.id
        rule_name = self.rule.name

        async def _confirm_delete(confirm_inter: discord.Interaction) -> None:
            await self.bot.automation_service.delete_rule(
                guild_id, confirm_inter.user.id, rule_id
            )
            await open_automation_manager(self.bot, confirm_inter)

        confirm_view = ConfirmationView(
            owner_id=self.owner_id,
            on_confirm=_confirm_delete,
            on_cancel=lambda cancel_inter: open_automation_manager(self.bot, cancel_inter),
            confirm_label=f"Excluir '{rule_name[:25]}'",
            cancel_label="Voltar à Lista",
        )
        await interaction.response.edit_message(
            embed=warning_embed(
                f"Gerenciar Saída • {rule_name}",
                "Clique em **Voltar à Lista** para retornar ou confirme a exclusão permanente desta regra.",
            ),
            view=confirm_view,
        )