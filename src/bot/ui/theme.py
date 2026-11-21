"""Identidade visual centralizada do Fusion Bot.

Define paleta de cores consistente, indicadores de status minimalistas e
formatações padronizadas para evitar interfaces poluídas ou genéricas.
"""

from __future__ import annotations


class Theme:
    """Tokens visuais da interface administrativa e operacional."""

    # Paleta semântica
    PRIMARY = 0x5865F2      # Blurple institucional
    SUCCESS = 0x10B981      # Esmeralda (ativo, concluído)
    WARNING = 0xF59E0B      # Âmbar (atenção, confirmação)
    DANGER = 0xEF4444       # Coral/Vermelho (erro, exclusão)
    NEUTRAL = 0x2B2D31      # Grafite escuro minimalista

    # Indicadores de estado
    STATUS_ON = "🟢 Ativo"
    STATUS_OFF = "🔴 Desativado"
    STATUS_WARN = "🟡 Pendente"

    # Ícones funcionais moderados
    ICON_DASHBOARD = "🧭"
    ICON_TICKETS = "🎫"
    ICON_AUTOMATIONS = "⚡"
    ICON_PERMISSIONS = "🛡️"
    ICON_CHANNELS = "📁"
    ICON_LOGS = "📜"
    ICON_BRANDING = "🎨"
    ICON_SETTINGS = "⚙️"
    ICON_DIAGNOSTICS = "🩺"
    ICON_BACK = "◀️"
    ICON_CANCEL = "✖️"
    ICON_CONFIRM = "✔️"
    ICON_PREVIEW = "👁️"
    ICON_PUBLISH = "🚀"

    @staticmethod
    def status_badge(enabled: bool) -> str:
        return Theme.STATUS_ON if enabled else Theme.STATUS_OFF

    @staticmethod
    def format_uptime(seconds: int) -> str:
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, secs = divmod(rem, 60)
        parts: list[str] = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        parts.append(f"{secs}s")
        return " ".join(parts)

    @staticmethod
    def mention_channel(channel_id: int | None) -> str:
        return f"<#{channel_id}>" if channel_id else "`Não definido`"

    @staticmethod
    def mention_roles(role_ids: list[int]) -> str:
        if not role_ids:
            return "`Nenhum cargo`"
        return ", ".join(f"<@&{rid}>" for rid in role_ids)

    @staticmethod
    def mention_users(user_ids: list[int]) -> str:
        if not user_ids:
            return "`Nenhum usuário`"
        return ", ".join(f"<@{uid}>" for uid in user_ids)