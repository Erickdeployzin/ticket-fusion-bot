"""Componentes interativos reutilizáveis (Views seguras, Confirmação e Paginação)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

import discord

from src.bot.ui.embeds import error_embed, warning_embed
from src.bot.ui.theme import Theme
from src.core.exceptions import FusionBotError
from src.core.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class BaseOwnerView(discord.ui.View):
    """View base que restringe interações ao autor do painel e trata erros com elegância."""

    def __init__(self, owner_id: int, *, timeout: float = 300.0) -> None:
        super().__init__(timeout=timeout)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                embed=error_embed(
                    "Sessão Restrita",
                    "Este painel pertence a outro administrador. Execute `/painel` para abrir o seu.",
                ),
                ephemeral=True,
            )
            return False
        return True

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item[discord.ui.View],
    ) -> None:
        if isinstance(error, FusionBotError):
            embed = error_embed("Ação não concluída", error.user_message)
        else:
            logger.exception("Erro inesperado em componente UI (%s)", type(item).__name__)
            embed = error_embed(
                "Erro Interno",
                "Ocorreu uma falha inesperada ao processar sua solicitação. O incidente foi registrado.",
            )

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


class ConfirmationView(BaseOwnerView):
    """Diálogo padronizado de confirmação para ações críticas ou destrutivas."""

    def __init__(
        self,
        owner_id: int,
        *,
        on_confirm: Callable[[discord.Interaction], Awaitable[None]],
        on_cancel: Callable[[discord.Interaction], Awaitable[None]] | None = None,
        confirm_label: str = "Confirmar",
        cancel_label: str = "Cancelar",
    ) -> None:
        super().__init__(owner_id=owner_id, timeout=120.0)
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel

        confirm_btn = discord.ui.Button(
            label=confirm_label,
            emoji=Theme.ICON_CONFIRM,
            style=discord.ButtonStyle.danger,
        )
        confirm_btn.callback = self._handle_confirm  # type: ignore[method-assign]

        cancel_btn = discord.ui.Button(
            label=cancel_label,
            emoji=Theme.ICON_CANCEL,
            style=discord.ButtonStyle.secondary,
        )
        cancel_btn.callback = self._handle_cancel  # type: ignore[method-assign]

        self.add_item(confirm_btn)
        self.add_item(cancel_btn)

    async def _handle_confirm(self, interaction: discord.Interaction) -> None:
        self.stop()
        await self._on_confirm(interaction)

    async def _handle_cancel(self, interaction: discord.Interaction) -> None:
        self.stop()
        if self._on_cancel is not None:
            await self._on_cancel(interaction)
        else:
            await interaction.response.edit_message(
                embed=warning_embed("Operação Cancelada", "Nenhuma alteração foi aplicada."),
                view=None,
            )


class EmbedPaginatorView(BaseOwnerView):
    """Paginador elegante para listas extensas (logs, tickets, automações)."""

    def __init__(
        self,
        owner_id: int,
        pages: list[discord.Embed],
        *,
        on_back: Callable[[discord.Interaction], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__(owner_id=owner_id, timeout=240.0)
        self._pages = pages
        self._index = 0
        self._on_back = on_back
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        self.prev_button.disabled = self._index <= 0
        self.next_button.disabled = self._index >= len(self._pages) - 1
        self.page_indicator.label = f"Página {self._index + 1}/{max(len(self._pages), 1)}"
        if self._on_back is None and self.back_button in self.children:
            self.remove_item(self.back_button)

    @property
    def current_embed(self) -> discord.Embed:
        return self._pages[self._index]

    @discord.ui.button(label="Anterior", emoji="⬅️", style=discord.ButtonStyle.secondary)
    async def prev_button(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[EmbedPaginatorView],
    ) -> None:
        self._index = max(0, self._index - 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.current_embed, view=self)

    @discord.ui.button(label="Página 1/1", style=discord.ButtonStyle.secondary, disabled=True)
    async def page_indicator(
        self,
        _interaction: discord.Interaction,
        _button: discord.ui.Button[EmbedPaginatorView],
    ) -> None:
        pass

    @discord.ui.button(label="Próxima", emoji="➡️", style=discord.ButtonStyle.secondary)
    async def next_button(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[EmbedPaginatorView],
    ) -> None:
        self._index = min(len(self._pages) - 1, self._index + 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.current_embed, view=self)

    @discord.ui.button(label="Voltar", emoji=Theme.ICON_BACK, style=discord.ButtonStyle.primary)
    async def back_button(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[EmbedPaginatorView],
    ) -> None:
        if self._on_back is not None:
            await self._on_back(interaction)