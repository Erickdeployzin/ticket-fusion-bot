"""Modals interativos do editor visual de mensagens, componentes e agendamentos."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord

from src.bot.ui.embeds import error_embed
from src.core.exceptions import FusionBotError, ValidationError
from src.database.schemas import (
    AutomationRuleSchema,
    AutomationType,
    ButtonActionType,
    ButtonStyleType,
    CustomButtonSchema,
    CustomDropdownSchema,
    DropdownOptionSchema,
    EmbedFieldSchema,
    ScheduleFrequency,
)

if TYPE_CHECKING:
    from src.bot.client import FusionBot

_DAY_ALIASES: dict[str, int] = {
    "seg": 0,
    "segunda": 0,
    "mon": 0,
    "0": 0,
    "ter": 1,
    "terca": 1,
    "terça": 1,
    "tue": 1,
    "1": 1,
    "qua": 2,
    "quarta": 2,
    "wed": 2,
    "2": 2,
    "qui": 3,
    "quinta": 3,
    "thu": 3,
    "3": 3,
    "sex": 4,
    "sexta": 4,
    "fri": 4,
    "4": 4,
    "sab": 5,
    "sabado": 5,
    "sábado": 5,
    "sat": 5,
    "5": 5,
    "dom": 6,
    "domingo": 6,
    "sun": 6,
    "6": 6,
}


class AutomationCreateModal(discord.ui.Modal, title="Nova Mensagem ou Automação"):
    """Modal inicial para criação de regra de mensagem personalizada ou automática."""

    rule_name = discord.ui.TextInput(
        label="Nome Interno",
        placeholder="Ex: Boas-vindas VIP, Regras Gerais, Aviso Diário...",
        min_length=2,
        max_length=80,
        required=True,
    )
    rule_type = discord.ui.TextInput(
        label="Tipo (welcome, goodbye, scheduled, periodi...",
        placeholder="custom, welcome, goodbye, scheduled, periodic ou announcement",
        min_length=6,
        max_length=20,
        required=True,
    )
    plain_content = discord.ui.TextInput(
        label="Texto Fora da Embed (opcional)",
        placeholder="Suporta {user}, {username}, {server}, {member_count}, {date}, {time}",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1800,
    )
    embed_title = discord.ui.TextInput(
        label="Título da Embed (opcional)",
        placeholder="Ex: Bem-vindo(a) ao {server}!",
        required=False,
        max_length=256,
    )
    embed_description = discord.ui.TextInput(
        label="Descrição da Embed (opcional)",
        style=discord.TextStyle.paragraph,
        placeholder="Escreva a mensagem principal...",
        required=False,
        max_length=3500,
    )

    def __init__(
        self,
        bot: FusionBot,
        on_created: Callable[[discord.Interaction, AutomationRuleSchema], Awaitable[None]],
    ) -> None:
        super().__init__()
        self._bot = bot
        self._on_created = on_created
        self.rule_type.default = "custom"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        allowed_types: set[str] = {
            "welcome",
            "goodbye",
            "scheduled",
            "periodic",
            "announcement",
            "custom",
        }
        raw_type = self.rule_type.value.strip().lower()
        if raw_type not in allowed_types:
            await interaction.response.send_message(
                embed=error_embed(
                    "Tipo Inválido",
                    "Informe um dos tipos: `welcome`, `goodbye`, `scheduled`, `periodic`, `announcement` ou `custom`.",
                ),
                ephemeral=True,
            )
            return

        try:
            rule = await self._bot.automation_service.create_rule(
                interaction.guild.id,
                interaction.user.id,
                name=self.rule_name.value,
                automation_type=cast(AutomationType, raw_type),
                content=self.plain_content.value,
                embed_title=self.embed_title.value,
                embed_description=self.embed_description.value,
            )
            await self._on_created(interaction, rule)
        except FusionBotError as exc:
            await interaction.response.send_message(
                embed=error_embed("Falha ao Criar Mensagem", exc.user_message),
                ephemeral=True,
            )


class AutomationContentAndEmbedModal(discord.ui.Modal, title="Editar Conteúdo e Embed"):
    """Edita nome interno, conteúdo externo, título, descrição e cor HEX."""

    rule_name = discord.ui.TextInput(
        label="Nome Interno",
        min_length=2,
        max_length=80,
        required=True,
    )
    plain_content = discord.ui.TextInput(
        label="Conteúdo de Texto (fora da embed)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1800,
    )
    embed_title = discord.ui.TextInput(
        label="Título da Embed",
        required=False,
        max_length=256,
    )
    embed_description = discord.ui.TextInput(
        label="Descrição da Embed",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=3800,
    )
    embed_color = discord.ui.TextInput(
        label="Cor Lateral da Embed (HEX)",
        placeholder="Ex: #5865F2",
        min_length=6,
        max_length=7,
        required=True,
    )

    def __init__(
        self,
        bot: FusionBot,
        rule: AutomationRuleSchema,
        on_saved: Callable[[discord.Interaction, AutomationRuleSchema], Awaitable[None]],
    ) -> None:
        super().__init__()
        self._bot = bot
        self._rule = rule
        self._on_saved = on_saved

        self.rule_name.default = rule.name
        self.plain_content.default = rule.content or ""
        self.embed_title.default = rule.embed.title or ""
        self.embed_description.default = rule.embed.description or ""
        self.embed_color.default = f"#{rule.embed.color:06X}"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            hex_clean = self.embed_color.value.strip().lstrip("#")
            try:
                color_int = int(hex_clean, 16)
                if not (0 <= color_int <= 0xFFFFFF):
                    raise ValueError
            except ValueError as exc:
                raise ValidationError(
                    "Cor HEX inválida.",
                    user_message="Informe uma cor hexadecimal válida (ex: `#5865F2` ou `10B981`).",
                ) from exc

            self._rule.name = self.rule_name.value.strip()[:100]
            self._rule.content = self.plain_content.value.strip()[:2000] or None
            self._rule.embed.title = self.embed_title.value.strip()[:256] or None
            self._rule.embed.description = self.embed_description.value.strip()[:4096] or None
            self._rule.embed.color = color_int

            updated = await self._bot.automation_service.save_rule(
                self._rule,
                interaction.user.id,
                f"Conteúdo e embed da mensagem **{self._rule.name}** atualizados.",
            )
            await self._on_saved(interaction, updated)
        except FusionBotError as exc:
            await interaction.response.send_message(
                embed=error_embed("Erro de Validação", exc.user_message),
                ephemeral=True,
            )


class AutomationMediaAndAuthorModal(discord.ui.Modal, title="Mídia, Autor e Rodapé da Embed"):
    """Configura banner, thumbnail, autor e rodapé da embed."""

    banner_url = discord.ui.TextInput(
        label="URL do Banner / Imagem Grande (opcional)",
        placeholder="https://...",
        required=False,
        max_length=512,
    )
    thumbnail_url = discord.ui.TextInput(
        label="URL da Thumbnail / Miniatura (opcional)",
        placeholder="https://...",
        required=False,
        max_length=512,
    )
    author_name = discord.ui.TextInput(
        label="Nome do Autor no Topo (opcional)",
        placeholder="Ex: Comunicado Oficial • {server}",
        required=False,
        max_length=256,
    )
    author_icon = discord.ui.TextInput(
        label="URL do Ícone do Autor (opcional)",
        placeholder="https://...",
        required=False,
        max_length=512,
    )
    footer_text = discord.ui.TextInput(
        label="Texto do Rodapé (opcional)",
        placeholder="Ex: Enviado em {date} às {time}",
        required=False,
        max_length=1000,
    )

    def __init__(
        self,
        bot: FusionBot,
        rule: AutomationRuleSchema,
        on_saved: Callable[[discord.Interaction, AutomationRuleSchema], Awaitable[None]],
    ) -> None:
        super().__init__()
        self._bot = bot
        self._rule = rule
        self._on_saved = on_saved

        self.banner_url.default = rule.embed.image_url or ""
        self.thumbnail_url.default = rule.embed.thumbnail_url or ""
        self.author_name.default = rule.embed.author_name or ""
        self.author_icon.default = rule.embed.author_icon_url or ""
        self.footer_text.default = rule.embed.footer_text or ""

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            urls = {
                "Banner": self.banner_url.value.strip() or None,
                "Thumbnail": self.thumbnail_url.value.strip() or None,
                "Ícone do Autor": self.author_icon.value.strip() or None,
            }
            for label, val in urls.items():
                if val and not val.startswith(("http://", "https://")):
                    raise ValidationError(
                        f"URL inválida em {label}.",
                        user_message=f"A URL de **{label}** deve começar com `http://` ou `https://`.",
                    )

            self._rule.embed.image_url = urls["Banner"]
            self._rule.embed.thumbnail_url = urls["Thumbnail"]
            self._rule.embed.author_icon_url = urls["Ícone do Autor"]
            self._rule.embed.author_name = self.author_name.value.strip()[:256] or None
            self._rule.embed.footer_text = self.footer_text.value.strip()[:2048] or None

            updated = await self._bot.automation_service.save_rule(
                self._rule,
                interaction.user.id,
                f"Mídia e rodapé da mensagem **{self._rule.name}** atualizados.",
            )
            await self._on_saved(interaction, updated)
        except FusionBotError as exc:
            await interaction.response.send_message(
                embed=error_embed("URL Inválida", exc.user_message),
                ephemeral=True,
            )


class AutomationAddFieldModal(discord.ui.Modal, title="Adicionar Campo à Embed"):
    """Adiciona um campo personalizado (Name / Value / Inline) à embed."""

    field_name = discord.ui.TextInput(
        label="Título do Campo",
        placeholder="Ex: Horário de Manutenção",
        min_length=1,
        max_length=256,
        required=True,
    )
    field_value = discord.ui.TextInput(
        label="Conteúdo do Campo",
        style=discord.TextStyle.paragraph,
        placeholder="Ex: Todos os domingos às 03:00",
        min_length=1,
        max_length=1024,
        required=True,
    )
    field_inline = discord.ui.TextInput(
        label="Exibir lado a lado / Inline? (sim ou nao)",
        placeholder="nao",
        min_length=3,
        max_length=4,
        required=True,
    )

    def __init__(
        self,
        bot: FusionBot,
        rule: AutomationRuleSchema,
        on_saved: Callable[[discord.Interaction, AutomationRuleSchema], Awaitable[None]],
    ) -> None:
        super().__init__()
        self._bot = bot
        self._rule = rule
        self._on_saved = on_saved
        self.field_inline.default = "nao"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if len(self._rule.embed.fields) >= 25:
            await interaction.response.send_message(
                embed=error_embed("Limite Atingido", "Embeds suportam no máximo 25 campos."),
                ephemeral=True,
            )
            return

        inline_bool = self.field_inline.value.strip().lower() in {"sim", "s", "yes", "true", "1"}
        self._rule.embed.fields.append(
            EmbedFieldSchema(
                name=self.field_name.value.strip()[:256],
                value=self.field_value.value.strip()[:1024],
                inline=inline_bool,
            )
        )
        updated = await self._bot.automation_service.save_rule(
            self._rule,
            interaction.user.id,
            f"Campo `{self.field_name.value.strip()}` adicionado à mensagem **{self._rule.name}**.",
        )
        await self._on_saved(interaction, updated)


class AutomationAddButtonModal(discord.ui.Modal, title="Adicionar Botão Personalizado"):
    """Adiciona um botão interativo ou de link à mensagem."""

    btn_label = discord.ui.TextInput(
        label="Texto do Botão",
        placeholder="Ex: Acessar Site, Receber Cargo, Abrir Suporte...",
        min_length=1,
        max_length=80,
        required=True,
    )
    btn_emoji = discord.ui.TextInput(
        label="Emoji (opcional)",
        placeholder="Ex: 🔗 ou 🎁",
        required=False,
        max_length=64,
    )
    btn_style = discord.ui.TextInput(
        label="Cor (primary, secondary, success, danger,...",
        placeholder="primary",
        min_length=4,
        max_length=12,
        required=True,
    )
    btn_action_type = discord.ui.TextInput(
        label="Ação (link, toggle_role, send_ephemeral, o...",
        placeholder="link | toggle_role | add_role | remove_role | send_ephemeral | open_ticket_panel",
        min_length=4,
        max_length=25,
        required=True,
    )
    btn_action_value = discord.ui.TextInput(
        label="Valor (URL, ID do Cargo, Texto ou ID do Pa...",
        placeholder="https://... ou ID numérico do cargo ou texto da resposta privada",
        min_length=1,
        max_length=1000,
        required=True,
    )

    def __init__(
        self,
        bot: FusionBot,
        rule: AutomationRuleSchema,
        on_saved: Callable[[discord.Interaction, AutomationRuleSchema], Awaitable[None]],
    ) -> None:
        super().__init__()
        self._bot = bot
        self._rule = rule
        self._on_saved = on_saved
        self.btn_style.default = "primary"
        self.btn_action_type.default = "send_ephemeral"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if len(self._rule.buttons) >= 20:
            await interaction.response.send_message(
                embed=error_embed("Limite Atingido", "Máximo de 20 botões por mensagem."),
                ephemeral=True,
            )
            return

        style_raw = self.btn_style.value.strip().lower()
        action_raw = self.btn_action_type.value.strip().lower()
        val_raw = self.btn_action_value.value.strip()

        valid_styles: set[str] = {"primary", "secondary", "success", "danger", "link"}
        valid_actions: set[str] = {
            "link",
            "toggle_role",
            "add_role",
            "remove_role",
            "send_ephemeral",
            "open_ticket_panel",
        }

        try:
            if style_raw not in valid_styles:
                raise ValidationError(
                    "Estilo inválido.",
                    user_message="Cor do botão deve ser: `primary`, `secondary`, `success`, `danger` ou `link`.",
                )
            if action_raw not in valid_actions:
                raise ValidationError(
                    "Ação inválida.",
                    user_message=(
                        "Ação deve ser: `link`, `toggle_role`, `add_role`, `remove_role`, "
                        "`send_ephemeral` ou `open_ticket_panel`."
                    ),
                )

            if action_raw == "link" or style_raw == "link":
                style_raw = "link"
                action_raw = "link"
                val_raw = self._bot.automation_service.validate_safe_url(val_raw)
            elif action_raw in {"toggle_role", "add_role", "remove_role"}:
                try:
                    int(val_raw)
                except ValueError as exc:
                    raise ValidationError(
                        "ID de cargo inválido.",
                        user_message="Para ações de cargo, informe o **ID numérico do cargo**.",
                    ) from exc

            target_row = min(len(self._rule.buttons) // 5, 3)
            self._rule.buttons.append(
                CustomButtonSchema(
                    label=self.btn_label.value.strip()[:80],
                    emoji=self.btn_emoji.value.strip() or None,
                    style=cast(ButtonStyleType, style_raw),
                    action_type=cast(ButtonActionType, action_raw),
                    action_value=val_raw[:1024],
                    row=target_row,
                )
            )
            updated = await self._bot.automation_service.save_rule(
                self._rule,
                interaction.user.id,
                f"Botão **{self.btn_label.value.strip()}** adicionado à mensagem **{self._rule.name}**.",
            )
            await self._on_saved(interaction, updated)
        except FusionBotError as exc:
            await interaction.response.send_message(
                embed=error_embed("Configuração de Botão Inválida", exc.user_message),
                ephemeral=True,
            )


class AutomationAddDropdownOptionModal(discord.ui.Modal, title="Configurar Dropdown e Opção"):
    """Cria o menu dropdown (se não existir) e adiciona uma nova opção interativa."""

    dropdown_placeholder = discord.ui.TextInput(
        label="Placeholder do Menu Dropdown",
        placeholder="Ex: Selecione um cargo ou tópico...",
        min_length=2,
        max_length=150,
        required=True,
    )
    option_label = discord.ui.TextInput(
        label="Nome da Opção",
        placeholder="Ex: Notificações de Eventos",
        min_length=1,
        max_length=100,
        required=True,
    )
    option_description = discord.ui.TextInput(
        label="Descrição da Opção (opcional)",
        placeholder="Ex: Receba avisos quando houver sorteios",
        required=False,
        max_length=100,
    )
    option_action_type = discord.ui.TextInput(
        label="Ação (toggle_role, send_ephemeral, open_ti...",
        placeholder="toggle_role | add_role | remove_role | send_ephemeral | open_ticket_panel",
        min_length=4,
        max_length=25,
        required=True,
    )
    option_action_value = discord.ui.TextInput(
        label="Valor (ID do Cargo, Texto ou ID do Painel)",
        placeholder="ID do cargo ou texto da mensagem privada",
        min_length=1,
        max_length=1000,
        required=True,
    )

    def __init__(
        self,
        bot: FusionBot,
        rule: AutomationRuleSchema,
        on_saved: Callable[[discord.Interaction, AutomationRuleSchema], Awaitable[None]],
    ) -> None:
        super().__init__()
        self._bot = bot
        self._rule = rule
        self._on_saved = on_saved

        if rule.dropdowns:
            self.dropdown_placeholder.default = rule.dropdowns[0].placeholder
        else:
            self.dropdown_placeholder.default = "Selecione uma opção..."
        self.option_action_type.default = "send_ephemeral"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        valid_actions: set[str] = {
            "toggle_role",
            "add_role",
            "remove_role",
            "send_ephemeral",
            "open_ticket_panel",
        }
        action_raw = self.option_action_type.value.strip().lower()
        val_raw = self.option_action_value.value.strip()

        if action_raw not in valid_actions:
            await interaction.response.send_message(
                embed=error_embed(
                    "Ação Inválida",
                    "Use `toggle_role`, `add_role`, `remove_role`, `send_ephemeral` ou `open_ticket_panel`.",
                ),
                ephemeral=True,
            )
            return

        if action_raw in {"toggle_role", "add_role", "remove_role"}:
            try:
                int(val_raw)
            except ValueError:
                await interaction.response.send_message(
                    embed=error_embed(
                        "ID Inválido",
                        "Informe o **ID numérico do cargo** para ações de atribuição de cargo.",
                    ),
                    ephemeral=True,
                )
                return

        if not self._rule.dropdowns:
            self._rule.dropdowns.append(
                CustomDropdownSchema(
                    placeholder=self.dropdown_placeholder.value.strip()[:150],
                    row=4,
                )
            )
        else:
            self._rule.dropdowns[0].placeholder = self.dropdown_placeholder.value.strip()[:150]

        dropdown = self._rule.dropdowns[0]
        if len(dropdown.options) >= 25:
            await interaction.response.send_message(
                embed=error_embed("Limite Atingido", "Um menu dropdown suporta até 25 opções."),
                ephemeral=True,
            )
            return

        opt_index = len(dropdown.options) + 1
        dropdown.options.append(
            DropdownOptionSchema(
                label=self.option_label.value.strip()[:100],
                value=f"opt_{opt_index}_{int(datetime.now(UTC).timestamp())}"[:100],
                description=self.option_description.value.strip()[:100] or None,
                action_type=cast(ButtonActionType, action_raw),
                action_value=val_raw[:1024],
            )
        )

        updated = await self._bot.automation_service.save_rule(
            self._rule,
            interaction.user.id,
            f"Opção **{self.option_label.value.strip()}** adicionada ao dropdown de **{self._rule.name}**.",
        )
        await self._on_saved(interaction, updated)


class AutomationScheduleModal(discord.ui.Modal, title="Configurar Agendamento Automático"):
    """Configura disparos programados (data única) ou periódicos (diário, semanal, intervalo)."""

    frequency_input = discord.ui.TextInput(
        label="Frequência (off, once, daily, weekly, inte...",
        placeholder="off (desativar) | once | daily | weekly | interval",
        min_length=3,
        max_length=12,
        required=True,
    )
    time_or_date_input = discord.ui.TextInput(
        label="Horário HH:MM (daily/weekly) ou DD/MM/AAAA...",
        placeholder="Ex: 12:00 ou 25/12/2026 18:30",
        required=False,
        max_length=20,
    )
    days_or_interval_input = discord.ui.TextInput(
        label="Dias (seg,qua,sex) ou Intervalo em Minutos...",
        placeholder="Para weekly: seg,qua,sex | Para interval: 60 (mín. 5 min)",
        required=False,
        max_length=60,
    )
    max_runs_input = discord.ui.TextInput(
        label="Limite Máximo de Repetições (opcional, vaz...",
        placeholder="Ex: 10 (ou deixe em branco)",
        required=False,
        max_length=6,
    )

    def __init__(
        self,
        bot: FusionBot,
        rule: AutomationRuleSchema,
        on_saved: Callable[[discord.Interaction, AutomationRuleSchema], Awaitable[None]],
    ) -> None:
        super().__init__()
        self._bot = bot
        self._rule = rule
        self._on_saved = on_saved

        sched = rule.schedule
        self.frequency_input.default = sched.frequency if sched.enabled else "off"
        if sched.frequency == "once" and sched.run_at:
            try:
                tz = ZoneInfo(sched.timezone)
            except ZoneInfoNotFoundError:
                tz = ZoneInfo("UTC")
            self.time_or_date_input.default = sched.run_at.astimezone(tz).strftime("%d/%m/%Y %H:%M")
        elif sched.time_of_day:
            self.time_or_date_input.default = sched.time_of_day

        if sched.frequency == "interval" and sched.interval_minutes:
            self.days_or_interval_input.default = str(sched.interval_minutes)
        elif sched.days_of_week:
            inv = {0: "seg", 1: "ter", 2: "qua", 3: "qui", 4: "sex", 5: "sab", 6: "dom"}
            self.days_or_interval_input.default = ",".join(inv[d] for d in sched.days_of_week if d in inv)

        if sched.max_runs is not None:
            self.max_runs_input.default = str(sched.max_runs)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        freq_raw = self.frequency_input.value.strip().lower()
        sched = self._rule.schedule

        try:
            if freq_raw == "off":
                sched.enabled = False
                sched.next_run_at = None
                updated = await self._bot.automation_service.save_rule(
                    self._rule,
                    interaction.user.id,
                    f"Agendamento da mensagem **{self._rule.name}** desativado.",
                )
                await self._on_saved(interaction, updated)
                return

            if freq_raw not in {"once", "daily", "weekly", "interval"}:
                raise ValidationError(
                    "Frequência inválida.",
                    user_message="Use `off`, `once`, `daily`, `weekly` ou `interval`.",
                )

            try:
                tz = ZoneInfo(sched.timezone)
            except ZoneInfoNotFoundError:
                tz = ZoneInfo("UTC")

            time_str = self.time_or_date_input.value.strip()
            extra_str = self.days_or_interval_input.value.strip().lower()
            max_runs_str = self.max_runs_input.value.strip()

            if max_runs_str:
                try:
                    mr = int(max_runs_str)
                    if mr < 1:
                        raise ValueError
                    sched.max_runs = mr
                except ValueError as exc:
                    raise ValidationError(
                        "Repetições inválidas.",
                        user_message="O limite de repetições deve ser um número inteiro maior ou igual a `1`.",
                    ) from exc
            else:
                sched.max_runs = None

            if freq_raw == "once":
                try:
                    naive_dt = datetime.strptime(time_str, "%d/%m/%Y %H:%M")
                    aware_local = naive_dt.replace(tzinfo=tz)
                    if aware_local.astimezone(UTC) <= datetime.now(UTC):
                        raise ValidationError(
                            "Data no passado.",
                            user_message="A data e horário programados devem estar no futuro.",
                        )
                    sched.run_at = aware_local.astimezone(UTC)
                    sched.run_count = 0
                except ValueError as exc:
                    raise ValidationError(
                        "Data inválida.",
                        user_message="Para disparo único (`once`), informe a data no formato `DD/MM/AAAA HH:MM`.",
                    ) from exc

            elif freq_raw in {"daily", "weekly"}:
                try:
                    parts = time_str.split(":", maxsplit=1)
                    hh, mm = int(parts[0]), int(parts[1])
                    if not (0 <= hh <= 23 and 0 <= mm <= 59):
                        raise ValueError
                    sched.time_of_day = f"{hh:02d}:{mm:02d}"
                except (ValueError, IndexError) as exc:
                    raise ValidationError(
                        "Horário inválido.",
                        user_message="Informe o horário no formato `HH:MM` (ex: `12:00` ou `18:30`).",
                    ) from exc

                if freq_raw == "weekly":
                    raw_days = [d.strip() for d in extra_str.split(",") if d.strip()]
                    parsed_days = [_DAY_ALIASES[d] for d in raw_days if d in _DAY_ALIASES]
                    if not parsed_days:
                        raise ValidationError(
                            "Dias da semana inválidos.",
                            user_message="Informe os dias separados por vírgula (ex: `seg,qua,sex` ou `sab,dom`).",
                        )
                    sched.days_of_week = sorted(set(parsed_days))

            elif freq_raw == "interval":
                try:
                    mins = int(extra_str)
                    if not (5 <= mins <= 43200):
                        raise ValueError
                    sched.interval_minutes = mins
                except ValueError as exc:
                    raise ValidationError(
                        "Intervalo inválido.",
                        user_message="Informe o intervalo em minutos entre `5` e `43200` (30 dias).",
                    ) from exc

            sched.frequency = cast(ScheduleFrequency, freq_raw)
            sched.enabled = True
            if self._rule.automation_type == "custom":
                self._rule.automation_type = "once" == freq_raw and "scheduled" or "periodic"  # type: ignore[assignment]

            updated = await self._bot.automation_service.save_rule(
                self._rule,
                interaction.user.id,
                f"Agendamento (`{freq_raw}`) configurado para **{self._rule.name}**.",
            )
            await self._on_saved(interaction, updated)
        except FusionBotError as exc:
            await interaction.response.send_message(
                embed=error_embed("Configuração de Agenda Inválida", exc.user_message),
                ephemeral=True,
            )