"""Ponto de entrada principal do Fusion Bot."""

from __future__ import annotations

import asyncio
import contextlib
import signal
import subprocess
import sys
from pathlib import Path


def _prepare_environment() -> None:
    """Atualiza o pip e instala as dependências declaradas em requirements.txt."""
    project_dir = Path(__file__).resolve().parent
    requirements_file = project_dir / "requirements.txt"

    if not requirements_file.is_file():
        raise FileNotFoundError(
            f"Arquivo requirements.txt não encontrado em: {requirements_file}"
        )

    python = sys.executable

    print("[PIP] Atualizando o pip...")
    subprocess.run(
        [python, "-m", "pip", "install", "--upgrade", "pip"],
        cwd=project_dir,
        check=True,
    )

    print("[PIP] Instalando dependências do requirements.txt...")
    subprocess.run(
        [python, "-m", "pip", "install", "-r", str(requirements_file)],
        cwd=project_dir,
        check=True,
    )

    print("[Fusion] Ambiente preparado com sucesso.")


# Executa antes dos imports do projeto, pois eles podem depender
# dos pacotes declarados em requirements.txt.
_prepare_environment()

from src.bot.client import FusionBot
from src.core.config import get_settings
from src.core.lifecycle import AppContext
from src.core.logger import get_logger, setup_logging


def _install_uvloop_if_available() -> None:
    """Ativa uvloop em sistemas Unix/Linux para máxima performance de I/O assíncrono."""
    if sys.platform != "win32":
        with contextlib.suppress(ImportError):
            import uvloop

            uvloop.install()


async def _async_main() -> None:
    settings = get_settings()
    setup_logging(level=settings.log_level, log_format=settings.log_format)
    logger = get_logger("fusion.main")

    logger.info(
        "Iniciando Fusion Bot (env=%s, db=%s)",
        settings.environment,
        settings.database_type,
    )

    app_context = AppContext(settings)
    await app_context.startup()

    bot = FusionBot(app_context)
    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)

    async def _runner() -> None:
        async with bot:
            await bot.start(settings.discord_token.get_secret_value(), reconnect=True)

    bot_task = asyncio.create_task(_runner(), name="fusion-bot-gateway")

    try:
        if sys.platform == "win32":
            await bot_task
        else:
            done, _pending = await asyncio.wait(
                [bot_task, asyncio.create_task(stop_event.wait())],
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not bot.is_closed():
                logger.info("Sinal de encerramento recebido. Desconectando bot...")
                await bot.close()
            for task in done:
                if task is bot_task and task.exception():
                    raise task.exception()  # type: ignore[misc]
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Interrupção solicitada pelo usuário.")
    finally:
        if not bot.is_closed():
            await bot.close()
        await app_context.shutdown()
        logger.info("Fusion Bot finalizado com segurança.")


def run() -> None:
    """Entrypoint síncrono utilizado via CLI ou `python main.py`."""
    _install_uvloop_if_available()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_async_main())


if __name__ == "__main__":
    run()
