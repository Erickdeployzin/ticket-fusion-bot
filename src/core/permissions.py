"""Motor de resolução de permissões granulares por módulo, cargos e usuários."""

from __future__ import annotations

import discord

from src.core.exceptions import PermissionDeniedError
from src.database.schemas import BotModule, GuildSettingsSchema, ModulePermissionRule

MODULE_LABELS: dict[BotModule, str] = {
    "administration": "Administração Geral",
    "tickets": "Sistema de Tickets",
    "automations": "Mensagens Automáticas",
    "logs": "Auditoria e Logs",
}


class PermissionService:
    """Valida permissões reais do Discord combinadas com regras internas por módulo."""

    def is_guild_super_admin(
        self,
        member: discord.Member,
        settings: GuildSettingsSchema,
    ) -> bool:
        """Verifica se o membro tem controle administrativo total no bot."""
        if member.guild.owner_id == member.id:
            return True
        if member.guild_permissions.administrator:
            return True

        admin_rule = settings.permissions.get("administration", ModulePermissionRule())
        if member.id in admin_rule.user_ids:
            return True

        member_role_ids = {role.id for role in member.roles}
        if member_role_ids.intersection(admin_rule.role_ids):
            return True

        # Fallback seguro: se nenhum cargo/usuário admin foi configurado ainda,
        # membros com 'Gerenciar Servidor' podem realizar a configuração inicial.
        if (
            not admin_rule.role_ids
            and not admin_rule.user_ids
            and member.guild_permissions.manage_guild
        ):
            return True

        return False

    def has_module_access(
        self,
        member: discord.Member,
        settings: GuildSettingsSchema,
        module: BotModule,
    ) -> bool:
        """Verifica se o membro pode gerenciar um módulo específico."""
        if self.is_guild_super_admin(member, settings):
            return True

        rule = settings.permissions.get(module)
        if rule is None:
            return False

        if member.id in rule.user_ids:
            return True

        member_role_ids = {role.id for role in member.roles}
        return bool(member_role_ids.intersection(rule.role_ids))

    def get_accessible_modules(
        self,
        member: discord.Member,
        settings: GuildSettingsSchema,
    ) -> set[BotModule]:
        """Retorna todos os módulos aos quais o membro possui acesso."""
        all_modules: tuple[BotModule, ...] = (
            "administration",
            "tickets",
            "automations",
            "logs",
        )
        return {
            module
            for module in all_modules
            if self.has_module_access(member, settings, module)
        }

    def ensure_module_access(
        self,
        member: discord.Member,
        settings: GuildSettingsSchema,
        module: BotModule,
    ) -> None:
        """Lança PermissionDeniedError caso o membro não tenha acesso ao módulo."""
        if not self.has_module_access(member, settings, module):
            label = MODULE_LABELS.get(module, module)
            raise PermissionDeniedError(
                f"Acesso negado ao módulo '{module}' para user={member.id} na guild={member.guild.id}.",
                user_message=(
                    f"Você não possui permissão para acessar o módulo **{label}**.\n"
                    "Solicite a um administrador do servidor que adicione seu cargo ou usuário "
                    "em **Cargos e Permissões** no `/painel`."
                ),
            )

    def ensure_super_admin(
        self,
        member: discord.Member,
        settings: GuildSettingsSchema,
    ) -> None:
        """Exige privilégio administrativo global sobre o bot."""
        if not self.is_guild_super_admin(member, settings):
            raise PermissionDeniedError(
                f"Acesso super_admin negado para user={member.id} na guild={member.guild.id}.",
                user_message=(
                    "Esta ação exige permissão de **Administrador do Bot** ou "
                    "**Administrador do Servidor**."
                ),
            )