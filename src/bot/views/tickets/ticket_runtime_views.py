"""Views e DynamicItems 100% persistentes para operação de tickets no Discord.

Todos os componentes aqui sobrevivem a reinicializações do bot através de
`custom_id` determinísticos e registro no `setup_hook` / `cog_load`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal, cast

import discord

from src.bot.modals.ticket_modals import (
    TicketPreOpenFormModal,
    TicketRatingCommentModal,
    TicketRenameModal,
)
from src.bot.ui.components import ConfirmationView
from src.bot.ui.embeds import create_panel_embed, error_embed, success_embed, warning_embed
from src.core.exceptions import FusionBotError
from src.database.schemas import TicketDepartmentOption, TicketPanelSchema, TicketPriority

if TYPE_CHECKING:
    from src.bot.client import FusionBot


def _map_button_style(style_name: str) -> discord.ButtonStyle:
    mapping: dict[str, discord.ButtonStyle] = {
        "primary": discord.ButtonStyle.primary,
        "secondary": discord.ButtonStyle.secondary,
        "success": discord.ButtonStyle.success,
        "danger": discord.ButtonStyle.danger,
    }
    return mapping.get(style_name, discord.ButtonStyle.primary)


async def _handle_ticket_open_request(
    bot: FusionBot,
    interaction: discord.Interaction,
    panel_id: str,
    department_id: str | None = None,
) -> None:
    """Fluxo unificado de abertura (via botão ou dropdown) com suporte a formulário Modal."""
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        return

    panel = await bot.ctx.db.tickets.get_panel(interaction.guild.id, panel_id)
    if panel is None:
        await interaction.response.send_message(
            embed=error_embed(
                "Painel Indisponível",
                "Este painel de atendimento foi removido ou não está mais ativo.",
            ),
            ephemeral=True,
        )
        return

    try:
        await bot.ticket_service.validate_can_open(interaction.guild, interaction.user, panel)
    except FusionBotError as exc:
        await interaction.response.send_message(
            embed=error_embed("Abertura Bloqueada", exc.user_message),
            ephemeral=True,
        )
        return

    selected_dept: TicketDepartmentOption | None = None
    if department_id is not None:
        selected_dept = next(
            (d for d in panel.departments if d.id == department_id),
            None,
        )

    if panel.form_fields:
        modal = TicketPreOpenFormModal(bot, panel, department=selected_dept)
        await interaction.response.send_modal(modal)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        ticket, channel = await bot.ticket_service.open_ticket(
            interaction.guild,
            interaction.user,
            panel,
            department=selected_dept,
        )
        await interaction.followup.send(
            embed=success_embed(
                f"Ticket #{ticket.ticket_number:04d} Aberto",
                f"Seu canal privado de atendimento foi criado: {channel.mention}",
            ),
            ephemeral=True,
        )
    except FusionBotError as exc:
        await interaction.followup.send(
            embed=error_embed("Não foi possível abrir o ticket", exc.user_message),
            ephemeral=True,
        )


# ==============================================================================
# 1. DYNAMIC ITEMS PARA PAINÉIS PÚBLICOS DE TICKETS
# ==============================================================================


class TicketOpenButtonItem(
    discord.ui.DynamicItem[discord.ui.Button[discord.ui.View]],
    template=r"^fusion:ticket:open:(?P<panel_id>[a-f0-9\-]{36})$",
):
    """Botão dinâmico persistente para abertura direta de tickets."""

    def __init__(
        self,
        panel_id: str,
        *,
        label: str = "Abrir Ticket",
        emoji: str | None = "🎫",
        style: discord.ButtonStyle = discord.ButtonStyle.primary,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                label=label[:80],
                emoji=emoji,
                style=style,
                custom_id=f"fusion:ticket:open:{panel_id}",
            )
        )
        self.panel_id = panel_id

    @classmethod
    async def from_custom_id(
        cls,
        _interaction: discord.Interaction,
        item: discord.ui.Item[discord.ui.View],
        match: re.Match[str],
    ) -> TicketOpenButtonItem:
        panel_id = match.group("panel_id")
        btn = cast(discord.ui.Button[discord.ui.View], item)
        return cls(
            panel_id=panel_id,
            label=btn.label or "Abrir Ticket",
            emoji=str(btn.emoji) if btn.emoji else None,
            style=btn.style,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        bot = cast("FusionBot", interaction.client)
        await _handle_ticket_open_request(bot, interaction, self.panel_id)


class TicketDepartmentSelectItem(
    discord.ui.DynamicItem[discord.ui.Select[discord.ui.View]],
    template=r"^fusion:ticket:dept:(?P<panel_id>[a-f0-9\-]{36})$",
):
    """Dropdown dinâmico persistente para seleção de departamento."""

    def __init__(
        self,
        panel_id: str,
        *,
        placeholder: str = "Selecione o departamento...",
        options: list[discord.SelectOption] | None = None,
    ) -> None:
        super().__init__(
            discord.ui.Select(
                placeholder=placeholder[:150],
                min_values=1,
                max_values=1,
                options=options
                or [discord.SelectOption(label="Atendimento Geral", value="default")],
                custom_id=f"fusion:ticket:dept:{panel_id}",
            )
        )
        self.panel_id = panel_id

    @classmethod
    async def from_custom_id(
        cls,
        _interaction: discord.Interaction,
        item: discord.ui.Item[discord.ui.View],
        match: re.Match[str],
    ) -> TicketDepartmentSelectItem:
        panel_id = match.group("panel_id")
        sel = cast(discord.ui.Select[discord.ui.View], item)
        return cls(
            panel_id=panel_id,
            placeholder=sel.placeholder or "Selecione o departamento...",
            options=list(sel.options),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        bot = cast("FusionBot", interaction.client)
        selected_dept_id = self.item.values[0]
        await _handle_ticket_open_request(
            bot,
            interaction,
            self.panel_id,
            department_id=selected_dept_id,
        )


class TicketPanelLauncherView(discord.ui.View):
    """View pública anexada à mensagem do painel de tickets."""

    def __init__(self, _bot: FusionBot, panel: TicketPanelSchema) -> None:
        super().__init__(timeout=None)
        if panel.open_mode == "dropdown" and panel.departments:
            options = [
                discord.SelectOption(
                    label=dept.label[:100],
                    value=dept.id,
                    description=dept.description[:100] if dept.description else None,
                    emoji=dept.emoji,
                )
                for dept in panel.departments[:25]
            ]
            self.add_item(
                TicketDepartmentSelectItem(
                    panel.id,
                    placeholder=panel.dropdown_placeholder,
                    options=options,
                )
            )
        else:
            self.add_item(
                TicketOpenButtonItem(
                    panel.id,
                    label=panel.button_label,
                    emoji=panel.button_emoji,
                    style=_map_button_style(panel.button_style),
                )
            )


# ==============================================================================
# 2. CONTROLES INTERNOS DO TICKET (PERSISTENTES)
# ==============================================================================


class _TicketMemberActionView(discord.ui.View):
    """Seletor efêmero de membro para adicionar, remover ou transferir atendimento."""

    def __init__(
        self,
        bot: FusionBot,
        ticket_channel: discord.TextChannel,
        mode: Literal["add", "remove", "transfer"],
    ) -> None:
        super().__init__(timeout=60.0)
        self._bot = bot
        self._channel = ticket_channel
        self._mode = mode

        placeholders = {
            "add": "Selecione o membro para adicionar ao ticket...",
            "remove": "Selecione o membro para remover do ticket...",
            "transfer": "Selecione o novo atendente responsável...",
        }
        user_select: discord.ui.UserSelect[_TicketMemberActionView] = discord.ui.UserSelect(
            placeholder=placeholders[mode],
            min_values=1,
            max_values=1,
        )
        user_select.callback = self._on_select  # type: ignore[method-assign]
        self.add_item(user_select)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            return
        select_item = cast(discord.ui.UserSelect[_TicketMemberActionView], self.children[0])
        selected = select_item.values[0]
        target_member = (
            selected
            if isinstance(selected, discord.Member)
            else interaction.guild.get_member(selected.id)
        )
        if target_member is None:
            await interaction.response.edit_message(
                embed=error_embed("Membro Inválido", "O usuário selecionado não está no servidor."),
                view=None,
            )
            return

        try:
            if self._mode == "add":
                await self._bot.ticket_service.add_participant(
                    self._channel, interaction.user, target_member
                )
                msg = f"{target_member.mention} foi adicionado a este atendimento."
            elif self._mode == "remove":
                await self._bot.ticket_service.remove_participant(
                    self._channel, interaction.user, target_member
                )
                msg = f"{target_member.mention} foi removido deste atendimento."
            else:
                await self._bot.ticket_service.transfer_assignee(
                    self._channel, interaction.user, target_member
                )
                msg = f"Atendimento transferido para {target_member.mention}."

            await interaction.response.edit_message(
                embed=success_embed("Operação Concluída", msg),
                view=None,
            )
            await self._channel.send(embed=success_embed("Atualização do Ticket", msg))
        except FusionBotError as exc:
            await interaction.response.edit_message(
                embed=error_embed("Ação Não Permitida", exc.user_message),
                view=None,
            )


class _TicketDepartmentSwitchView(discord.ui.View):
    """Seletor efêmero para mover o ticket para outro departamento do painel."""

    def __init__(
        self,
        bot: FusionBot,
        ticket_channel: discord.TextChannel,
        departments: list[TicketDepartmentOption],
    ) -> None:
        super().__init__(timeout=60.0)
        self._bot = bot
        self._channel = ticket_channel
        self._departments = {d.id: d for d in departments}

        options = [
            discord.SelectOption(
                label=d.label[:100],
                value=d.id,
                description=d.description[:100] if d.description else None,
                emoji=d.emoji,
            )
            for d in departments[:25]
        ]
        select: discord.ui.Select[_TicketDepartmentSwitchView] = discord.ui.Select(
            placeholder="Escolha o novo departamento...",
            min_values=1,
            max_values=1,
            options=options,
        )
        select.callback = self._on_select  # type: ignore[method-assign]
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member):
            return
        select_item = cast(discord.ui.Select[_TicketDepartmentSwitchView], self.children[0])
        dept = self._departments.get(select_item.values[0])
        if dept is None:
            return
        try:
            await self._bot.ticket_service.change_department(
                self._channel, interaction.user, dept
            )
            await interaction.response.edit_message(
                embed=success_embed(
                    "Departamento Alterado",
                    f"Ticket movido para o departamento **{dept.label}**.",
                ),
                view=None,
            )
            await self._channel.send(
                embed=success_embed(
                    "Departamento Atualizado",
                    f"Este ticket foi transferido para **{dept.label}** por {interaction.user.mention}.",
                )
            )
        except FusionBotError as exc:
            await interaction.response.edit_message(
                embed=error_embed("Falha ao Transferir", exc.user_message),
                view=None,
            )


class _TicketPrioritySwitchView(discord.ui.View):
    """Seletor efêmero de nível de prioridade do ticket."""

    def __init__(self, bot: FusionBot, ticket_channel: discord.TextChannel) -> None:
        super().__init__(timeout=60.0)
        self._bot = bot
        self._channel = ticket_channel

        options = [
            discord.SelectOption(label="Baixa", value="low", emoji="🟢"),
            discord.SelectOption(label="Normal", value="normal", emoji="🔵"),
            discord.SelectOption(label="Alta", value="high", emoji="🟠"),
            discord.SelectOption(label="Urgente", value="urgent", emoji="🔴"),
        ]
        select: discord.ui.Select[_TicketPrioritySwitchView] = discord.ui.Select(
            placeholder="Selecione a prioridade do atendimento...",
            min_values=1,
            max_values=1,
            options=options,
        )
        select.callback = self._on_select  # type: ignore[method-assign]
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member):
            return
        select_item = cast(discord.ui.Select[_TicketPrioritySwitchView], self.children[0])
        prio = cast(TicketPriority, select_item.values[0])
        try:
            await self._bot.ticket_service.set_priority(self._channel, interaction.user, prio)
            await interaction.response.edit_message(
                embed=success_embed("Prioridade Atualizada", f"Prioridade definida como `{prio.upper()}`."),
                view=None,
            )
        except FusionBotError as exc:
            await interaction.response.edit_message(
                embed=error_embed("Ação Não Permitida", exc.user_message),
                view=None,
            )


class TicketInsideControlView(discord.ui.View):
    """Painel de controles internos dentro de cada canal de ticket (100% persistente)."""

    def __init__(
        self,
        bot: FusionBot,
        *,
        closed: bool = False,
        allow_reopen: bool = True,
    ) -> None:
        super().__init__(timeout=None)
        self._bot = bot

        if closed:
            self.remove_item(self.claim_btn)
            self.remove_item(self.close_btn)
            self.remove_item(self.notify_btn)
            self.remove_item(self.staff_actions_select)
            if not allow_reopen:
                self.remove_item(self.reopen_btn)
        else:
            self.remove_item(self.reopen_btn)
            self.remove_item(self.delete_btn)

    async def _handle_error(self, interaction: discord.Interaction, exc: FusionBotError) -> None:
        embed = error_embed("Operação Não Concluída", exc.user_message)
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="Assumir Atendimento",
        emoji="🙋",
        style=discord.ButtonStyle.success,
        custom_id="fusion:ticket:ctrl:claim",
        row=0,
    )
    async def claim_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[TicketInsideControlView],
    ) -> None:
        if not isinstance(interaction.channel, discord.TextChannel) or not isinstance(
            interaction.user, discord.Member
        ):
            return
        try:
            ticket = await self._bot.ticket_service.claim_ticket(
                interaction.channel, interaction.user
            )
            await interaction.response.send_message(
                embed=success_embed(
                    f"Atendimento Assumido • #{ticket.ticket_number:04d}",
                    f"{interaction.user.mention} assumiu a responsabilidade por este ticket.",
                )
            )
        except FusionBotError as exc:
            await self._handle_error(interaction, exc)

    @discord.ui.button(
        label="Notificar Equipe",
        emoji="🔔",
        style=discord.ButtonStyle.secondary,
        custom_id="fusion:ticket:ctrl:notify",
        row=0,
    )
    async def notify_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[TicketInsideControlView],
    ) -> None:
        if not isinstance(interaction.channel, discord.TextChannel) or not isinstance(
            interaction.user, discord.Member
        ):
            return
        try:
            mentions = await self._bot.ticket_service.notify_staff_team(
                interaction.channel, interaction.user
            )
            await interaction.response.send_message(
                content=f"🔔 {mentions} — Solicitação de atenção iniciada por {interaction.user.mention}.",
            )
        except FusionBotError as exc:
            await self._handle_error(interaction, exc)

    @discord.ui.button(
        label="Transcript HTML",
        emoji="📄",
        style=discord.ButtonStyle.secondary,
        custom_id="fusion:ticket:ctrl:transcript",
        row=0,
    )
    async def transcript_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[TicketInsideControlView],
    ) -> None:
        if not isinstance(interaction.channel, discord.TextChannel) or not isinstance(
            interaction.user, discord.Member
        ):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            ticket, panel, settings = await self._bot.ticket_service.get_ticket_context(
                interaction.channel.id
            )
            if interaction.user.id != ticket.opener_id:
                self._bot.ticket_service.ensure_ticket_staff(interaction.user, panel, settings)

            html_file = await self._bot.transcripts.generate_html_file(
                interaction.channel, ticket, settings
            )
            await interaction.followup.send(
                embed=success_embed(
                    f"Transcript • Ticket #{ticket.ticket_number:04d}",
                    "Arquivo HTML gerado com todo o histórico atual do atendimento.",
                ),
                file=html_file,
                ephemeral=True,
            )
        except FusionBotError as exc:
            await self._handle_error(interaction, exc)

    @discord.ui.button(
        label="Fechar Ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="fusion:ticket:ctrl:close",
        row=0,
    )
    async def close_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[TicketInsideControlView],
    ) -> None:
        if not isinstance(interaction.channel, discord.TextChannel) or not isinstance(
            interaction.user, discord.Member
        ):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await self._bot.ticket_service.close_ticket(interaction.channel, interaction.user)
            await interaction.followup.send(
                embed=success_embed("Ticket Encerrado", "O atendimento foi finalizado com sucesso."),
                ephemeral=True,
            )
        except FusionBotError as exc:
            await self._handle_error(interaction, exc)

    @discord.ui.button(
        label="Reabrir Ticket",
        emoji="🔓",
        style=discord.ButtonStyle.success,
        custom_id="fusion:ticket:ctrl:reopen",
        row=1,
    )
    async def reopen_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[TicketInsideControlView],
    ) -> None:
        if not isinstance(interaction.channel, discord.TextChannel) or not isinstance(
            interaction.user, discord.Member
        ):
            return
        try:
            await self._bot.ticket_service.reopen_ticket(interaction.channel, interaction.user)
            await interaction.response.send_message(
                embed=success_embed("Ticket Reaberto", "Canal liberado novamente para mensagens."),
                ephemeral=True,
            )
        except FusionBotError as exc:
            await self._handle_error(interaction, exc)

    @discord.ui.button(
        label="Excluir Ticket",
        emoji="🗑️",
        style=discord.ButtonStyle.danger,
        custom_id="fusion:ticket:ctrl:delete",
        row=1,
    )
    async def delete_btn(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[TicketInsideControlView],
    ) -> None:
        if not isinstance(interaction.channel, discord.TextChannel) or not isinstance(
            interaction.user, discord.Member
        ):
            return
        channel = interaction.channel
        actor = interaction.user

        async def _confirm_delete(confirm_inter: discord.Interaction) -> None:
            try:
                await confirm_inter.response.edit_message(
                    embed=warning_embed(
                        "Excluindo Ticket...",
                        "Este canal será excluído permanentemente em 3 segundos.",
                    ),
                    view=None,
                )
                await self._bot.ticket_service.delete_ticket_channel(channel, actor)
            except FusionBotError as exc:
                await self._handle_error(confirm_inter, exc)

        confirm_view = ConfirmationView(
            owner_id=actor.id,
            on_confirm=_confirm_delete,
            confirm_label="Excluir Permanentemente",
        )
        await interaction.response.send_message(
            embed=warning_embed(
                "Confirmar Exclusão do Ticket",
                "Tem certeza que deseja excluir este canal? Esta ação não pode ser desfeita.",
            ),
            view=confirm_view,
            ephemeral=True,
        )

    @discord.ui.select(
        placeholder="Mais ações da equipe (membros, responsável, departamento...)",
        min_values=1,
        max_values=1,
        custom_id="fusion:ticket:ctrl:actions",
        row=2,
        options=[
            discord.SelectOption(
                label="Adicionar Membro",
                value="add_member",
                description="Conceder acesso a outro usuário neste ticket",
                emoji="➕",
            ),
            discord.SelectOption(
                label="Remover Membro",
                value="remove_member",
                description="Revogar acesso de um participante adicional",
                emoji="➖",
            ),
            discord.SelectOption(
                label="Alterar Responsável",
                value="transfer_staff",
                description="Transferir o ticket para outro atendente",
                emoji="🔄",
            ),
            discord.SelectOption(
                label="Alterar Departamento",
                value="change_dept",
                description="Mover o atendimento para outro departamento",
                emoji="🗂️",
            ),
            discord.SelectOption(
                label="Alterar Prioridade",
                value="change_priority",
                description="Definir urgência (Baixa, Normal, Alta, Urgente)",
                emoji="🚨",
            ),
            discord.SelectOption(
                label="Renomear Canal",
                value="rename_channel",
                description="Alterar o nome deste canal de atendimento",
                emoji="✏️",
            ),
        ],
    )
    async def staff_actions_select(
        self,
        interaction: discord.Interaction,
        select: discord.ui.Select[TicketInsideControlView],
    ) -> None:
        if not isinstance(interaction.channel, discord.TextChannel) or not isinstance(
            interaction.user, discord.Member
        ):
            return

        try:
            _ticket, panel, settings = await self._bot.ticket_service.get_ticket_context(
                interaction.channel.id
            )
            self._bot.ticket_service.ensure_ticket_staff(interaction.user, panel, settings)
        except FusionBotError as exc:
            await self._handle_error(interaction, exc)
            return

        action = select.values[0]
        if action == "add_member":
            await interaction.response.send_message(
                embed=create_panel_embed(
                    title="Adicionar Membro ao Ticket",
                    description="Escolha no menu abaixo o usuário que receberá acesso ao canal.",
                    settings=settings,
                ),
                view=_TicketMemberActionView(self._bot, interaction.channel, "add"),
                ephemeral=True,
            )
        elif action == "remove_member":
            await interaction.response.send_message(
                embed=create_panel_embed(
                    title="Remover Membro do Ticket",
                    description="Escolha no menu abaixo o usuário que terá o acesso removido.",
                    settings=settings,
                ),
                view=_TicketMemberActionView(self._bot, interaction.channel, "remove"),
                ephemeral=True,
            )
        elif action == "transfer_staff":
            await interaction.response.send_message(
                embed=create_panel_embed(
                    title="Transferir Atendimento",
                    description="Selecione o novo atendente responsável por este ticket.",
                    settings=settings,
                ),
                view=_TicketMemberActionView(self._bot, interaction.channel, "transfer"),
                ephemeral=True,
            )
        elif action == "change_dept":
            if not panel.departments:
                await interaction.response.send_message(
                    embed=warning_embed(
                        "Sem Outros Departamentos",
                        "Este painel possui apenas o departamento padrão configurado.",
                    ),
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(
                embed=create_panel_embed(
                    title="Alterar Departamento",
                    description="Selecione o novo departamento para este ticket.",
                    settings=settings,
                ),
                view=_TicketDepartmentSwitchView(
                    self._bot, interaction.channel, panel.departments
                ),
                ephemeral=True,
            )
        elif action == "change_priority":
            await interaction.response.send_message(
                embed=create_panel_embed(
                    title="Alterar Prioridade",
                    description="Defina o nível de prioridade deste atendimento.",
                    settings=settings,
                ),
                view=_TicketPrioritySwitchView(self._bot, interaction.channel),
                ephemeral=True,
            )
        elif action == "rename_channel":
            await interaction.response.send_modal(
                TicketRenameModal(self._bot, interaction.channel.name)
            )


# ==============================================================================
# 3. SISTEMA DE AVALIAÇÃO PÓS-ATENDIMENTO (1 A 5 ESTRELAS PERSISTENTE)
# ==============================================================================


class TicketRatingButtonItem(
    discord.ui.DynamicItem[discord.ui.Button[discord.ui.View]],
    template=r"^fusion:ticket:rate:(?P<ticket_id>[a-f0-9\-]{36}):(?P<stars>[1-5])$",
):
    """Botão dinâmico persistente de avaliação (1 a 5 estrelas)."""

    def __init__(self, ticket_id: str, stars: int) -> None:
        super().__init__(
            discord.ui.Button(
                label=f"{stars} ⭐",
                style=(
                    discord.ButtonStyle.success
                    if stars >= 4
                    else (
                        discord.ButtonStyle.primary
                        if stars == 3
                        else discord.ButtonStyle.secondary
                    )
                ),
                custom_id=f"fusion:ticket:rate:{ticket_id}:{stars}",
            )
        )
        self.ticket_id = ticket_id
        self.stars = stars

    @classmethod
    async def from_custom_id(
        cls,
        _interaction: discord.Interaction,
        _item: discord.ui.Item[discord.ui.View],
        match: re.Match[str],
    ) -> TicketRatingButtonItem:
        return cls(
            ticket_id=match.group("ticket_id"),
            stars=int(match.group("stars")),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        bot = cast("FusionBot", interaction.client)
        existing = await bot.ctx.db.tickets.get_rating_by_ticket(self.ticket_id)
        if existing is not None:
            await interaction.response.send_message(
                embed=error_embed("Avaliação Já Enviada", "Este ticket já foi avaliado anteriormente."),
                ephemeral=True,
            )
            return

        modal = TicketRatingCommentModal(bot, self.ticket_id, self.stars)
        await interaction.response.send_modal(modal)


class TicketRatingView(discord.ui.View):
    """View com botões de 1 a 5 estrelas enviada ao usuário após fechar o ticket."""

    def __init__(self, _bot: FusionBot, ticket_id: str) -> None:
        super().__init__(timeout=None)
        for stars in range(1, 6):
            self.add_item(TicketRatingButtonItem(ticket_id, stars))