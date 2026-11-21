"""Sistema de logging estruturado do Fusion Bot."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from src.core.config import LogFormatType


class JsonFormatter(logging.Formatter):
    """Formata registros de log em JSON estruturado para observabilidade em produção."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        guild_id = getattr(record, "guild_id", None)
        if guild_id is not None:
            payload["guild_id"] = guild_id

        user_id = getattr(record, "user_id", None)
        if user_id is not None:
            payload["user_id"] = user_id

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Formata registros de log com cores ANSI limpas para leitura em terminal."""

    COLORS: dict[str, str] = {
        "DEBUG": "\033[36m",     # Ciano
        "INFO": "\033[32m",      # Verde
        "WARNING": "\033[33m",   # Amarelo
        "ERROR": "\033[31m",     # Vermelho
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"
    DIM = "\033[2m"

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        color = self.COLORS.get(record.levelname, "")
        level = f"{color}{record.levelname:<8}{self.RESET}"

        context_parts: list[str] = []
        guild_id = getattr(record, "guild_id", None)
        user_id = getattr(record, "user_id", None)
        if guild_id is not None:
            context_parts.append(f"guild={guild_id}")
        if user_id is not None:
            context_parts.append(f"user={user_id}")

        context_str = f" [{', '.join(context_parts)}]" if context_parts else ""
        base = (
            f"{self.DIM}{timestamp}{self.RESET} | {level} | "
            f"{self.DIM}{record.name}{self.RESET}{context_str} — {record.getMessage()}"
        )

        if record.exc_info:
            base += f"\n{self.formatException(record.exc_info)}"
        return base


def setup_logging(level: str = "INFO", log_format: LogFormatType = "console") -> None:
    """Configura o logger raiz e silencia ruídos excessivos de bibliotecas externas."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    formatter: logging.Formatter = (
        JsonFormatter() if log_format == "json" else ConsoleFormatter()
    )
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    # Reduz verbosidade de libs de rede/gateway mantendo erros visíveis
    logging.getLogger("discord.gateway").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("pymongo").setLevel(logging.WARNING)


configure_logging = setup_logging


def get_logger(name: str) -> logging.Logger:
    """Obtém uma instância nomeada de logger."""
    return logging.getLogger(name)