"""Motor assíncrono persistente para execução de mensagens agendadas e periódicas.

Garante:
- Recuperação automática de tarefas pendentes após reinicialização do bot;
- Trava exclusiva por regra (`LockManager`) evitando disparos duplicados em sharding;
- Atualização atômica de `run_count`, `last_run_at` e `next_run_at`.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from src.core.logger import get_logger
from src.database.schemas import AutomationRuleSchema, utc_now

if TYPE_CHECKING:
    from src.bot.client import FusionBot

logger = get_logger(__name__)


class SchedulerEngine:
    """Loop de verificação contínua de automações agendadas no banco de dados."""

    def __init__(self, bot: FusionBot, *, poll_interval_seconds: float = 15.0) -> None:
        self._bot = bot
        self._poll_interval = poll_interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()

    def start(self) -> None:
        """Inicia a tarefa em background caso ainda não esteja em execução."""
        if self._task is not None and not self._task.done():
            return
        self._stopped.clear()
        self._task = asyncio.create_task(self._run_loop(), name="fusion-scheduler-engine")
        logger.info("SchedulerEngine iniciado (intervalo=%.1fs).", self._poll_interval)

    async def stop(self) -> None:
        """Encerra o agendador de forma limpa."""
        self._stopped.set()
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("SchedulerEngine encerrado.")

    async def _run_loop(self) -> None:
        await self._bot.wait_until_ready()
        while not self._stopped.is_set():
            try:
                await self.process_due_automations()
            except Exception:
                logger.exception("Erro inesperado no ciclo do SchedulerEngine.")

            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self._poll_interval)
            except TimeoutError:
                continue

    async def process_due_automations(self) -> int:
        """Consulta automações vencidas e dispara apenas as que pertencem aos shards locais."""
        now = utc_now()
        due_rules = await self._bot.ctx.db.automations.get_due_scheduled_automations(now)
        executed = 0

        for rule in due_rules:
            guild = self._bot.get_guild(rule.guild_id)
            if guild is None:
                # Guild não está neste shard ou bot foi removido
                continue

            async with self._bot.ctx.locks.acquire(f"sched:{rule.id}", ttl_seconds=30):
                # Revalida no banco dentro da trava para impedir duplicação pós-restart
                fresh = await self._bot.ctx.db.automations.get_automation(rule.guild_id, rule.id)
                if (
                    fresh is None
                    or not fresh.enabled
                    or not fresh.schedule.enabled
                    or fresh.schedule.next_run_at is None
                    or fresh.schedule.next_run_at > utc_now()
                ):
                    continue

                await self._execute_single_rule(fresh)
                executed += 1

        return executed

    async def _execute_single_rule(self, rule: AutomationRuleSchema) -> None:
        """Atualiza agenda antes do envio (at-most-once) e publica a mensagem."""
        now = utc_now()
        rule.schedule.last_run_at = now
        rule.schedule.run_count += 1
        next_dt = self._bot.automation_service.compute_next_run(rule.schedule, reference_utc=now)
        rule.schedule.next_run_at = next_dt
        if next_dt is None:
            rule.schedule.enabled = False

        await self._bot.ctx.db.automations.update_automation(rule)

        guild = self._bot.get_guild(rule.guild_id)
        if guild is None:
            return

        try:
            await self._bot.automation_service.publish_or_update_message(
                guild,
                rule,
                actor_id=0,
                is_scheduled_trigger=True,
            )
            logger.info(
                "Automação agendada '%s' (ID: %s) executada na guild %s.",
                rule.name,
                rule.id,
                guild.id,
            )
        except Exception as exc:
            logger.exception(
                "Falha ao publicar automação agendada '%s' (guild=%s)",
                rule.id,
                guild.id,
            )
            await self._bot.log_service.record(
                guild_id=guild.id,
                category="errors",
                action="scheduler.execution_failed",
                target_id=rule.id,
                details=f"Falha ao executar agendamento **{rule.name}**: `{exc}`",
            )