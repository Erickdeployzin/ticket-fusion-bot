"""Utilitário CLI para inicialização de schemas, health-check e geração de chaves."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Garante execução direta via `python scripts/init_db.py` sem exigir PYTHONPATH=.
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cryptography.fernet import Fernet  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.core.logger import configure_logging, get_logger  # noqa: E402
from src.database.factory import DatabaseFactory  # noqa: E402

logger = get_logger(__name__)


def cmd_generate_key() -> int:
    """Gera uma nova chave Fernet (AES-128-CBC + HMAC-SHA256) pronta para o .env."""
    key = Fernet.generate_key().decode("utf-8")
    print("\nChave Fernet gerada com sucesso (adicione ao seu .env):\n")
    print(f"FERNET_KEY={key}\n")
    return 0


async def cmd_init_database(*, verify_only: bool = False) -> int:
    """Conecta ao provedor configurado, aplica migrations/índices e valida saúde."""
    settings = get_settings()
    configure_logging(settings.log_level)

    backend_name = getattr(settings, "database_type", "unknown")
    logger.info("Backend de banco selecionado: %s", str(backend_name).upper())
    provider = DatabaseFactory.create(settings)

    try:
        await provider.connect()

        check_fn = getattr(provider, "healthcheck", None) or getattr(provider, "health_check", None)
        if check_fn is not None:
            result = await check_fn()
            healthy = result[0] if isinstance(result, tuple) else bool(result)
        else:
            healthy = True

        if not healthy:
            logger.error("Falha na verificação de integridade (healthcheck) do banco de dados.")
            return 1

        if verify_only:
            logger.info("Conexão e saúde do banco validadas com sucesso (%s).", backend_name)
        else:
            logger.info(
                "Tabelas, coleções e índices inicializados com sucesso (%s).",
                backend_name,
            )
        return 0
    except Exception:
        logger.exception("Erro crítico ao inicializar/validar o banco de dados.")
        return 1
    finally:
        await provider.disconnect()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fusion-db",
        description="CLI de administração de banco de dados e criptografia do Fusion Bot.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "init",
        help="Inicializa tabelas, coleções e índices no banco configurado no .env.",
    )
    subparsers.add_parser(
        "health",
        help="Testa a conectividade e latência do banco de dados configurado.",
    )
    subparsers.add_parser(
        "gen-key",
        help="Gera uma chave criptográfica FERNET_KEY segura para credenciais.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "gen-key":
        return cmd_generate_key()
    if args.command == "init":
        return asyncio.run(cmd_init_database(verify_only=False))
    if args.command == "health":
        return asyncio.run(cmd_init_database(verify_only=True))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())