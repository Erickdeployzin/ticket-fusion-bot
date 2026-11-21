"""Modals interativos do sistema de tickets (formulários pré-abertura e configuração)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Literal, cast

import discord

from src.bot.ui.embeds import error_embed, success_embed
from src.core.exceptions import FusionBotError, ValidationError
from src.database.schemas import (
    TicketDepartmentOption,
    TicketFormFieldSchema,
    TicketPanelSchema,
)

if TYPE_CHECKING:
    from src.bot.client import FusionBot


# ==============================================================================
# 1. MODALS DE USUÁRIO FINAL (PRÉ-ABERTURA E AVALIAÇÃO)
# ==============================================================================


class TicketPreOpenFormModal(discord.ui.Modal):
    """Formulário dinâmico exibido ao membro antes de abrir o canal do ticket."""

    def __init__(
        self,
        bot: FusionBot,
        panel: TicketPanelSchema,
        department: TicketDepartmentOption | None = None,
    ) -> None:
        super().__init__(title=f"Atendimento • {panel.name}"[:45])
        self._bot = bot
        self._panel = panel
        self._department = department
        self._inputs: list[tuple[str, discord.ui.TextInput[TicketPreOpenFormModal]]] = []

        for field in panel.form_fields[:5]:
            style = (
                discord.TextStyle.paragraph
                if field.style == "paragraph"
                else discord.TextStyle.short
            )
            text_input: discord.ui.TextInput[TicketPreOpenFormModal] = discord.ui.TextInput(
                label=field.label[:45],
                placeholder=field.placeholder[:100] if field.placeholder else None,
                style=style,
                required=field.required,
                min_length=field.min_length if field.required else 0,
                max_length=min(field.max_length, 4000),
            )
            self._inputs.append((field.label, text_input))
            self.add_item(text_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        answers: dict[str, str] = {}
        for label, field_input in self._inputs:
            val = field_input.value.strip()
            if val:
                answers[label] = val

        try:
            ticket, channel = await self._bot.ticket_service.open_ticket(
                interaction.guild,
                interaction.user,
                self._panel,
                department=self._department,
                form_answers=answers,
            )
            await interaction.followup.send(
                embed=success_embed(
                    f"Ticket #{ticket.ticket_number:04d} Aberto",
                    f"Seu canal exclusivo de atendimento foi criado: {channel.mention}",
                ),
                ephemeral=True,
            )
        except FusionBotError as exc:
            await interaction.followup.send(
                embed=error_embed("Não foi possível abrir o ticket", exc.user_message),
                ephemeral=True,
            )


class TicketRatingCommentModal(discord.ui.Modal, title="Avaliação de Atendimento"):
    """Modal opcional para o usuário adicionar um comentário junto à nota."""

    comment_input = discord.ui.TextInput(
        label="Comentário sobre o atendimento (opcional)",
        placeholder="Conte-nos como foi sua experiência com nossa equipe...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=800,
    )

    def __init__(self, bot: FusionBot, ticket_id: str, stars: int) -> None:
        super().__init__(title=f"Avaliar Atendimento ({stars}/5 ⭐)")
        self._bot = bot
        self._ticket_id = ticket_id
        self._stars = stars

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            await self._bot.ticket_service.submit_rating(
                ticket_id=self._ticket_id,
                user_id=interaction.user.id,
                stars=self._stars,
                comment=self.comment_input.value,
            )
            stars_str = "⭐" * self._stars
            await interaction.response.edit_message(
                embed=success_embed(
                    "Avaliação Registrada",
                    f"Obrigado pelo seu feedback! Nota registrada: **{stars_str} ({self._stars}/5)**.",
                ),
                view=None,
            )
        except FusionBotError as exc:
            await interaction.response.send_message(
                embed=error_embed("Avaliação Não Registrada", exc.user_message),
                ephemeral=True,
            )


# ==============================================================================
# 2. MODALS DE OPERAÇÃO INTERNA DO TICKET
# ==============================================================================


class TicketRenameModal(discord.ui.Modal, title="Renomear Canal do Ticket"):
    """Modal para renomear o canal privado do atendimento."""

    new_name = discord.ui.TextInput(
        label="Novo nome do canal",
        placeholder="Ex: ticket-0012-pagamento-aprovado",
        min_length=2,
        max_length=80,
        required=True,
    )

    def __init__(self, bot: FusionBot, current_name: str) -> None:
        super().__init__()
        self._bot = bot
        self.new_name.default = current_name[:80]

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.channel, discord.TextChannel) or not isinstance(
            interaction.user, discord.Member
        ):
            return
        try:
            sanitized = await self._bot.ticket_service.rename_ticket_channel(
                interaction.channel,
                interaction.user,
                self.new_name.value,
            )
            await interaction.response.send_message(
                embed=success_embed(
                    "Canal Renomeado",
                    f"O canal deste atendimento foi renomeado para `{sanitized}`.",
                ),
                ephemeral=True,
            )
        except FusionBotError as exc:
            await interaction.response.send_message(
                embed=error_embed("Falha ao Renomear", exc.user_message),
                ephemeral=True,
            )


# ==============================================================================
# 3. MODALS DE CONFIGURAÇÃO DE PAINÉIS DE TICKETS (/painel)
# ==============================================================================


class TicketPanelCreateModal(discord.ui.Modal, title="Criar Novo Painel de Tickets"):
    """Modal inicial para criação de um painel de atendimento."""

    panel_name = discord.ui.TextInput(
        label="Nome Interno do Painel",
        placeholder="Ex: Suporte Técnico, Financeiro, Denúncias, VIP...",
        min_length=2,
        max_length=80,
        required=True,
    )
    embed_title = discord.ui.TextInput(
        label="Título da Embed Pública",
        placeholder="Ex: Central de Suporte Oficial",
        min_length=2,
        max_length=200,
        required=True,
    )
    embed_description = discord.ui.TextInput(
        label="Descrição da Embed Pública",
        placeholder="Explique quando o membro deve abrir um ticket neste painel...",
        style=discord.TextStyle.paragraph,
        min_length=5,
        max_length=2000,
        required=True,
    )

    def __init__(
        self,
        bot: FusionBot,
        on_created: Callable[[discord.Interaction, TicketPanelSchema], Awaitable[None]],
    ) -> None:
        super().__init__()
        self._bot = bot
        self._on_created = on_created

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        try:
            panel = await self._bot.ticket_service.create_panel(
                interaction.guild.id,
                interaction.user.id,
                name=self.panel_name.value,
                title=self.embed_title.value,
                description=self.embed_description.value,
            )
            await self._on_created(interaction, panel)
        except FusionBotError as exc:
            await interaction.response.send_message(
                embed=error_embed("Erro ao Criar Painel", exc.user_message),
                ephemeral=True,
            )


class TicketPanelAppearanceModal(discord.ui.Modal, title="Aparência do Painel de Tickets"):
    """Edita nome, título, descrição, banner, thumbnail e cor do painel."""

    panel_name = discord.ui.TextInput(
        label="Nome Interno",
        min_length=2,
        max_length=80,
        required=True,
    )
    embed_title = discord.ui.TextInput(
        label="Título da Embed",
        min_length=1,
        max_length=256,
        required=True,
    )
    embed_description = discord.ui.TextInput(
        label="Descrição da Embed",
        style=discord.TextStyle.paragraph,
        min_length=1,
        max_length=3500,
        required=True,
    )
    banner_and_thumb = discord.ui.TextInput(
        label="Banner URL | Thumbnail URL (opcional)",
        placeholder="https://banner.png | https://thumb.png (ou apenas banner URL)",
        required=False,
        max_length=1024,
    )
    color_and_footer = discord.ui.TextInput(
        label="Cor HEX | Rodapé (opcional)",
        placeholder="Ex: #5865F2 | Atendimento 24/7",
        required=False,
        max_length=260,
    )

    def __init__(
        self,
        bot: FusionBot,
        panel: TicketPanelSchema,
        on_saved: Callable[[discord.Interaction, TicketPanelSchema], Awaitable[None]],
    ) -> None:
        super().__init__()
        self._bot = bot
        self._panel = panel
        self._on_saved = on_saved

        self.panel_name.default = panel.name
        self.embed_title.default = panel.embed.title or ""
        self.embed_description.default = panel.embed.description or ""

        media_parts = [p for p in (panel.embed.image_url, panel.embed.thumbnail_url) if p]
        self.banner_and_thumb.default = " | ".join(media_parts)
        self.color_and_footer.default = (
            f"#{panel.embed.color:06X} | {panel.embed.footer_text or ''}".strip(" |")
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            self._panel.name = self.panel_name.value.strip()[:100]
            self._panel.embed.title = self.embed_title.value.strip()[:256]
            self._panel.embed.description = self.embed_description.value.strip()[:4096]

            raw_media = self.banner_and_thumb.value.strip()
            if not raw_media:
                self._panel.embed.image_url = None
                self._panel.embed.thumbnail_url = None
            else:
                parts = [p.strip() for p in raw_media.split("|")]
                banner_url = parts[0] if parts and parts[0] else None
                thumb_url = parts[1] if len(parts) > 1 and parts[1] else None
                for url_val in (banner_url, thumb_url):
                    if url_val and not url_val.startswith(("http://", "https://")):
                        raise ValidationError(
                            "URL de mídia inválida.",
                            user_message="As URLs de banner e thumbnail devem começar com `http://` ou `https://`.",
                        )
                self._panel.embed.image_url = banner_url
                self._panel.embed.thumbnail_url = thumb_url

            raw_style = self.color_and_footer.value.strip()
            if raw_style:
                style_parts = [p.strip() for p in raw_style.split("|", maxsplit=1)]
                hex_candidate = style_parts[0].lstrip("#")
                try:
                    color_int = int(hex_candidate, 16)
                    if not (0 <= color_int <= 0xFFFFFF):
                        raise ValueError
                    self._panel.embed.color = color_int
                except ValueError as exc:
                    raise ValidationError(
                        "Cor HEX inválida.",
                        user_message="Cor hexadecimal inválida. Use o formato `#5865F2`.",
                    ) from exc

                if len(style_parts) > 1 and style_parts[1]:
                    self._panel.embed.footer_text = style_parts[1][:256]

            updated = await self._bot.ticket_service.save_panel(
                self._panel,
                interaction.user.id,
                f"Aparência do painel **{self._panel.name}** atualizada por <@{interaction.user.id}>.",
            )
            await self._on_saved(interaction, updated)
        except FusionBotError as exc:
            await interaction.response.send_message(
                embed=error_embed("Erro na Validação", exc.user_message),
                ephemeral=True,
            )


class TicketPanelButtonModal(discord.ui.Modal, title="Botão e Modo de Abertura"):
    """Configura modo (botão ou dropdown), texto, emoji, estilo e placeholder."""

    open_mode = discord.ui.TextInput(
        label="Modo de Abertura (button ou dropdown)",
        placeholder="button ou dropdown",
        min_length=6,
        max_length=10,
        required=True,
    )
    button_label = discord.ui.TextInput(
        label="Texto do Botão Principal",
        placeholder="Ex: Abrir Atendimento",
        min_length=1,
        max_length=80,
        required=True,
    )
    button_emoji = discord.ui.TextInput(
        label="Emoji do Botão (opcional)",
        placeholder="Ex: 🎫 ou <:suporte:123456789>",
        required=False,
        max_length=64,
    )
    button_style = discord.ui.TextInput(
        label="Cor do Botão (primary, secondary, success,...",
        placeholder="primary",
        min_length=6,
        max_length=12,
        required=True,
    )
    dropdown_placeholder = discord.ui.TextInput(
        label="Placeholder do Dropdown (quando modo = dro...",
        placeholder="Selecione o departamento desejado...",
        max_length=150,
        required=True,
    )

    def __init__(
        self,
        bot: FusionBot,
        panel: TicketPanelSchema,
        on_saved: Callable[[discord.Interaction, TicketPanelSchema], Awaitable[None]],
    ) -> None:
        super().__init__()
        self._bot = bot
        self._panel = panel
        self._on_saved = on_saved

        self.open_mode.default = panel.open_mode
        self.button_label.default = panel.button_label
        self.button_emoji.default = panel.button_emoji or ""
        self.button_style.default = panel.button_style
        self.dropdown_placeholder.default = panel.dropdown_placeholder

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            mode_clean = self.open_mode.value.strip().lower()
            if mode_clean not in {"button", "dropdown"}:
                raise ValidationError(
                    "Modo inválido.",
                    user_message="O modo de abertura deve ser `button` ou `dropdown`.",
                )

            style_clean = self.button_style.value.strip().lower()
            if style_clean not in {"primary", "secondary", "success", "danger"}:
                raise ValidationError(
                    "Estilo de botão inválido.",
                    user_message="Use um dos estilos: `primary`, `secondary`, `success` ou `danger`.",
                )

            if mode_clean == "dropdown" and not self._panel.departments:
                raise ValidationError(
                    "Dropdown sem departamentos.",
                    user_message=(
                        "Adicione pelo menos **1 departamento** antes de ativar o modo `dropdown`."
                    ),
                )

            self._panel.open_mode = cast(Literal["button", "dropdown"], mode_clean)
            self._panel.button_label = self.button_label.value.strip()[:80]
            self._panel.button_emoji = self.button_emoji.value.strip() or None
            self._panel.button_style = cast(
                Literal["primary", "secondary", "success", "danger"], style_clean
            )
            self._panel.dropdown_placeholder = self.dropdown_placeholder.value.strip()[:150]

            updated = await self._bot.ticket_service.save_panel(
                self._panel,
                interaction.user.id,
                f"Controles de abertura do painel **{self._panel.name}** atualizados.",
            )
            await self._on_saved(interaction, updated)
        except FusionBotError as exc:
            await interaction.response.send_message(
                embed=error_embed("Configuração Inválida", exc.user_message),
                ephemeral=True,
            )


class TicketPanelRulesModal(discord.ui.Modal, title="Regras, Limites e Horário"):
    """Configura limite por usuário, cooldown e horário de atendimento."""

    max_tickets = discord.ui.TextInput(
        label="Limite de Tickets Simultâneos por Usuário...",
        min_length=1,
        max_length=2,
        required=True,
    )
    cooldown_sec = discord.ui.TextInput(
        label="Cooldown entre Aberturas (em segundos)",
        min_length=1,
        max_length=5,
        required=True,
    )
    business_hours_cfg = discord.ui.TextInput(
        label="Horário Atendimento (off ou HH-HH, ex: 09-18)",
        placeholder="off (para 24h) ou 09-18",
        min_length=2,
        max_length=10,
        required=True,
    )
    offline_msg = discord.ui.TextInput(
        label="Mensagem de Ausência (fora do expediente)",
        style=discord.TextStyle.paragraph,
        max_length=900,
        required=True,
    )

    def __init__(
        self,
        bot: FusionBot,
        panel: TicketPanelSchema,
        on_saved: Callable[[discord.Interaction, TicketPanelSchema], Awaitable[None]],
    ) -> None:
        super().__init__()
        self._bot = bot
        self._panel = panel
        self._on_saved = on_saved

        self.max_tickets.default = str(panel.max_tickets_per_user)
        self.cooldown_sec.default = str(panel.cooldown_seconds)
        if panel.business_hours.enabled:
            self.business_hours_cfg.default = (
                f"{panel.business_hours.start_hour:02d}-{panel.business_hours.end_hour:02d}"
            )
        else:
            self.business_hours_cfg.default = "off"
        self.offline_msg.default = panel.business_hours.offline_message

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            try:
                max_t = int(self.max_tickets.value.strip())
                cd_s = int(self.cooldown_sec.value.strip())
                if not (1 <= max_t <= 10) or not (0 <= cd_s <= 86400):
                    raise ValueError
            except ValueError as exc:
                raise ValidationError(
                    "Valores numéricos inválidos.",
                    user_message="Limite deve ser entre `1` e `10` e cooldown entre `0` e `86400` segundos.",
                ) from exc

            bh_raw = self.business_hours_cfg.value.strip().lower()
            if bh_raw == "off":
                self._panel.business_hours.enabled = False
            else:
                try:
                    start_s, end_s = bh_raw.split("-", maxsplit=1)
                    start_h, end_h = int(start_s), int(end_s)
                    if not (0 <= start_h <= 23 and 0 <= end_h <= 23):
                        raise ValueError
                    self._panel.business_hours.enabled = True
                    self._panel.business_hours.start_hour = start_h
                    self._panel.business_hours.end_hour = end_h
                except ValueError as exc:
                    raise ValidationError(
                        "Formato de horário inválido.",
                        user_message="Informe `off` ou o intervalo de horas no formato `09-18`.",
                    ) from exc

            self._panel.max_tickets_per_user = max_t
            self._panel.cooldown_seconds = cd_s
            self._panel.business_hours.offline_message = self.offline_msg.value.strip()[:1000]

            updated = await self._bot.ticket_service.save_panel(
                self._panel,
                interaction.user.id,
                f"Regras e expediente do painel **{self._panel.name}** atualizados.",
            )
            await self._on_saved(interaction, updated)
        except FusionBotError as exc:
            await interaction.response.send_message(
                embed=error_embed("Configuração Inválida", exc.user_message),
                ephemeral=True,
            )


class TicketPanelWelcomeModal(discord.ui.Modal, title="Mensagem Inicial Dentro do Ticket"):
    """Configura a embed enviada automaticamente dentro do canal privado aberto."""

    welcome_title = discord.ui.TextInput(
        label="Título da Mensagem Inicial",
        min_length=1,
        max_length=256,
        required=True,
    )
    welcome_description = discord.ui.TextInput(
        label="Descrição (suporta {user}, {server}, {depa...",
        style=discord.TextStyle.paragraph,
        min_length=1,
        max_length=3500,
        required=True,
    )
    welcome_banner = discord.ui.TextInput(
        label="URL de Banner/Imagem (opcional)",
        placeholder="https://...",
        required=False,
        max_length=512,
    )

    def __init__(
        self,
        bot: FusionBot,
        panel: TicketPanelSchema,
        on_saved: Callable[[discord.Interaction, TicketPanelSchema], Awaitable[None]],
    ) -> None:
        super().__init__()
        self._bot = bot
        self._panel = panel
        self._on_saved = on_saved

        self.welcome_title.default = panel.welcome_embed.title or ""
        self.welcome_description.default = panel.welcome_embed.description or ""
        self.welcome_banner.default = panel.welcome_embed.image_url or ""

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            banner = self.welcome_banner.value.strip() or None
            if banner and not banner.startswith(("http://", "https://")):
                raise ValidationError(
                    "URL inválida.",
                    user_message="A URL do banner deve iniciar com `http://` ou `https://`.",
                )

            self._panel.welcome_embed.title = self.welcome_title.value.strip()[:256]
            self._panel.welcome_embed.description = self.welcome_description.value.strip()[:4096]
            self._panel.welcome_embed.image_url = banner

            updated = await self._bot.ticket_service.save_panel(
                self._panel,
                interaction.user.id,
                f"Mensagem inicial do painel **{self._panel.name}** atualizada.",
            )
            await self._on_saved(interaction, updated)
        except FusionBotError as exc:
            await interaction.response.send_message(
                embed=error_embed("Erro na Validação", exc.user_message),
                ephemeral=True,
            )


class TicketAddDepartmentModal(discord.ui.Modal, title="Adicionar Departamento ao Painel"):
    """Adiciona uma opção de departamento para painéis com dropdown."""

    dept_label = discord.ui.TextInput(
        label="Nome do Departamento",
        placeholder="Ex: Suporte Financeiro, Denúncias, Parcerias...",
        min_length=2,
        max_length=80,
        required=True,
    )
    dept_description = discord.ui.TextInput(
        label="Descrição Curta (opcional)",
        placeholder="Ex: Dúvidas sobre pagamentos, VIPs e reembolsos",
        required=False,
        max_length=100,
    )
    dept_emoji = discord.ui.TextInput(
        label="Emoji (opcional)",
        placeholder="Ex: 💳",
        required=False,
        max_length=64,
    )

    def __init__(
        self,
        bot: FusionBot,
        panel: TicketPanelSchema,
        on_saved: Callable[[discord.Interaction, TicketPanelSchema], Awaitable[None]],
    ) -> None:
        super().__init__()
        self._bot = bot
        self._panel = panel
        self._on_saved = on_saved

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if len(self._panel.departments) >= 25:
            await interaction.response.send_message(
                embed=error_embed("Limite Atingido", "Um painel suporta no máximo 25 departamentos."),
                ephemeral=True,
            )
            return

        dept = TicketDepartmentOption(
            label=self.dept_label.value.strip()[:100],
            description=self.dept_description.value.strip()[:100] or None,
            emoji=self.dept_emoji.value.strip() or None,
            category_id=self._panel.category_id,
            staff_role_ids=list(self._panel.staff_role_ids),
        )
        self._panel.departments.append(dept)
        updated = await self._bot.ticket_service.save_panel(
            self._panel,
            interaction.user.id,
            f"Departamento **{dept.label}** adicionado ao painel **{self._panel.name}**.",
        )
        await self._on_saved(interaction, updated)


class TicketAddFormFieldModal(discord.ui.Modal, title="Adicionar Pergunta Pré-Abertura"):
    """Adiciona uma pergunta exibida via Modal antes da criação do ticket."""

    field_label = discord.ui.TextInput(
        label="Pergunta / Título do Campo (máx. 45 chars)",
        placeholder="Ex: Qual é o seu nickname ou ID?",
        min_length=2,
        max_length=45,
        required=True,
    )
    field_placeholder = discord.ui.TextInput(
        label="Texto de Exemplo / Placeholder (opcional)",
        placeholder="Ex: Digite exatamente como aparece no jogo...",
        required=False,
        max_length=100,
    )
    field_style = discord.ui.TextInput(
        label="Formato (short = linha única | paragraph =...",
        placeholder="short ou paragraph",
        min_length=5,
        max_length=10,
        required=True,
    )
    field_required = discord.ui.TextInput(
        label="Obrigatório? (sim ou nao)",
        placeholder="sim",
        min_length=3,
        max_length=4,
        required=True,
    )

    def __init__(
        self,
        bot: FusionBot,
        panel: TicketPanelSchema,
        on_saved: Callable[[discord.Interaction, TicketPanelSchema], Awaitable[None]],
    ) -> None:
        super().__init__()
        self._bot = bot
        self._panel = panel
        self._on_saved = on_saved
        self.field_style.default = "short"
        self.field_required.default = "sim"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if len(self._panel.form_fields) >= 5:
            await interaction.response.send_message(
                embed=error_embed(
                    "Limite da API do Discord",
                    "Modals do Discord suportam no máximo **5 perguntas** por formulário.",
                ),
                ephemeral=True,
            )
            return

        style_raw = self.field_style.value.strip().lower()
        if style_raw not in {"short", "paragraph"}:
            await interaction.response.send_message(
                embed=error_embed("Formato Inválido", "Use `short` ou `paragraph`."),
                ephemeral=True,
            )
            return

        req_bool = self.field_required.value.strip().lower() in {"sim", "s", "yes", "true", "1"}
        field = TicketFormFieldSchema(
            label=self.field_label.value.strip()[:45],
            placeholder=self.field_placeholder.value.strip()[:100] or None,
            style=cast(Literal["short", "paragraph"], style_raw),
            required=req_bool,
        )
        self._panel.form_fields.append(field)
        updated = await self._bot.ticket_service.save_panel(
            self._panel,
            interaction.user.id,
            f"Pergunta `{field.label}` adicionada ao formulário do painel **{self._panel.name}**.",
        )
        await self._on_saved(interaction, updated)