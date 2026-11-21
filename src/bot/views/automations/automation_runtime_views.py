"""Componentes dinâmicos persistentes (botões e dropdowns personalizados)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, cast

import discord

from src.bot.ui.embeds import error_embed
from src.database.schemas import AutomationRuleSchema, ButtonStyleType

if TYPE_CHECKING:
    from src.bot.client import FusionBot


def map_custom_button_style(style: ButtonStyleType) -> discord.ButtonStyle:
    mapping: dict[ButtonStyleType, discord.ButtonStyle] = {
        "primary": discord.ButtonStyle.primary,
        "secondary": discord.ButtonStyle.secondary,
        "success": discord.ButtonStyle.success,
        "danger": discord.ButtonStyle.danger,
        "link": discord.ButtonStyle.link,
    }
    return mapping.get(style, discord.ButtonStyle.secondary)


class CustomAutomationButtonItem(
    discord.ui.DynamicItem[discord.ui.Button[discord.ui.View]],
    template=r"^fusion:auto:btn:(?P<rule_id>[a-f0-9\-]{36}):(?P<btn_id>[a-f0-9\-]{36})$",
):
    """Botão dinâmico persistente vinculado a uma regra de automação."""

    def __init__(
        self,
        rule_id: str,
        btn_id: str,
        *,
        label: str,
        emoji: str | None = None,
        style: discord.ButtonStyle = discord.ButtonStyle.secondary,
        row: int = 0,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                label=label[:80],
                emoji=emoji,
                style=style,
                custom_id=f"fusion:auto:btn:{rule_id}:{btn_id}",
                row=row,
                disabled=disabled,
            )
        )
        self.rule_id = rule_id
        self.btn_id = btn_id

    @classmethod
    async def from_custom_id(
        cls,
        _interaction: discord.Interaction,
        item: discord.ui.Item[discord.ui.View],
        match: re.Match[str],
    ) -> CustomAutomationButtonItem:
        btn = cast(discord.ui.Button[discord.ui.View], item)
        return cls(
            rule_id=match.group("rule_id"),
            btn_id=match.group("btn_id"),
            label=btn.label or "Botão",
            emoji=str(btn.emoji) if btn.emoji else None,
            style=btn.style,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        bot = cast("FusionBot", interaction.client)
        rule = await bot.ctx.db.automations.get_automation_by_id_global(self.rule_id)
        if rule is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "Componente Inativo",
                    "A configuração desta mensagem foi removida pelo administrador.",
                ),
                ephemeral=True,
            )
            return

        btn_cfg = next((b for b in rule.buttons if b.id == self.btn_id), None)
        if btn_cfg is None:
            await interaction.response.send_message(
                embed=error_embed("Botão Removido", "Este botão não existe mais nesta mensagem."),
                ephemeral=True,
            )
            return

        await bot.automation_service.execute_component_action(
            interaction,
            rule,
            action_type=btn_cfg.action_type,
            action_value=btn_cfg.action_value,
            required_role_ids=btn_cfg.required_role_ids,
        )


class CustomAutomationDropdownItem(
    discord.ui.DynamicItem[discord.ui.Select[discord.ui.View]],
    template=r"^fusion:auto:dd:(?P<rule_id>[a-f0-9\-]{36}):(?P<dd_id>[a-f0-9\-]{36})$",
):
    """Select Menu (Dropdown) dinâmico persistente para mensagens personalizadas."""

    def __init__(
        self,
        rule_id: str,
        dd_id: str,
        *,
        placeholder: str,
        min_values: int = 1,
        max_values: int = 1,
        options: list[discord.SelectOption] | None = None,
        row: int = 1,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Select(
                placeholder=placeholder[:150],
                min_values=min_values,
                max_values=max_values,
                options=options or [discord.SelectOption(label="Opção", value="0")],
                custom_id=f"fusion:auto:dd:{rule_id}:{dd_id}",
                row=row,
                disabled=disabled,
            )
        )
        self.rule_id = rule_id
        self.dd_id = dd_id

    @classmethod
    async def from_custom_id(
        cls,
        _interaction: discord.Interaction,
        item: discord.ui.Item[discord.ui.View],
        match: re.Match[str],
    ) -> CustomAutomationDropdownItem:
        sel = cast(discord.ui.Select[discord.ui.View], item)
        return cls(
            rule_id=match.group("rule_id"),
            dd_id=match.group("dd_id"),
            placeholder=sel.placeholder or "Selecione...",
            min_values=sel.min_values,
            max_values=sel.max_values,
            options=list(sel.options),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        bot = cast("FusionBot", interaction.client)
        rule = await bot.ctx.db.automations.get_automation_by_id_global(self.rule_id)
        if rule is None:
            await interaction.response.send_message(
                embed=error_embed("Menu Inativo", "Esta configuração não está mais disponível."),
                ephemeral=True,
            )
            return

        dd_cfg = next((d for d in rule.dropdowns if d.id == self.dd_id), None)
        if dd_cfg is None:
            await interaction.response.send_message(
                embed=error_embed("Menu Removido", "Este dropdown foi removido pelo administrador."),
                ephemeral=True,
            )
            return

        selected_val = self.item.values[0]
        opt_cfg = next((o for o in dd_cfg.options if o.value == selected_val), None)
        if opt_cfg is None:
            return

        await bot.automation_service.execute_component_action(
            interaction,
            rule,
            action_type=opt_cfg.action_type,
            action_value=opt_cfg.action_value,
        )


class AutomationMessageView(discord.ui.View):
    """View dinâmica montada a partir dos botões e dropdowns configurados na regra."""

    def __init__(
        self,
        _bot: FusionBot,
        rule: AutomationRuleSchema,
        *,
        disable_all: bool = False,
    ) -> None:
        super().__init__(timeout=None)

        for btn in rule.buttons[:20]:
            if btn.action_type == "link" or btn.style == "link":
                if btn.action_value.startswith(("http://", "https://")):
                    self.add_item(
                        discord.ui.Button(
                            label=btn.label[:80],
                            emoji=btn.emoji,
                            style=discord.ButtonStyle.link,
                            url=btn.action_value,
                            row=min(btn.row, 4),
                            disabled=disable_all,
                        )
                    )
            else:
                self.add_item(
                    CustomAutomationButtonItem(
                        rule.id,
                        btn.id,
                        label=btn.label,
                        emoji=btn.emoji,
                        style=map_custom_button_style(btn.style),
                        row=min(btn.row, 4),
                        disabled=disable_all,
                    )
                )

        for dd in rule.dropdowns[:4]:
            if not dd.options:
                continue
            select_options = [
                discord.SelectOption(
                    label=opt.label[:100],
                    value=opt.value[:100],
                    description=opt.description[:100] if opt.description else None,
                    emoji=opt.emoji,
                )
                for opt in dd.options[:25]
            ]
            max_vals = min(dd.max_values, len(select_options))
            min_vals = min(dd.min_values, max_vals)
            self.add_item(
                CustomAutomationDropdownItem(
                    rule.id,
                    dd.id,
                    placeholder=dd.placeholder,
                    min_values=min_vals,
                    max_values=max_vals,
                    options=select_options,
                    row=min(dd.row, 4),
                    disabled=disable_all,
                )
            )