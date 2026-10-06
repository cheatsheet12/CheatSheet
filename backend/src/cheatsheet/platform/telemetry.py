"""Structured logging. `print()` is forbidden and ruff (T20) blocks it.

Logs are JSON in every deployed environment because they are read by a machine
before they are read by a person, and a regex over free-form text is not a query.
Locally they are rendered for humans, which is the only difference.

**What never enters a log**: passwords, tokens, integration secrets, certificates,
full CUITs of third parties, WhatsApp message bodies. CLAUDE.md §5 states it and
there is no logging level that makes it acceptable — a log shipped to a third-party
aggregator is data leaving the system.
"""

from __future__ import annotations

import logging
import sys

import structlog

from cheatsheet.platform.settings import Entorno, Settings


def configurar_logging(settings: Settings) -> None:
    """Install the structured logging pipeline. Idempotent: safe to call per worker."""
    nivel = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=nivel)

    procesadores: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    legible = settings.entorno in (Entorno.LOCAL, Entorno.TEST)
    procesadores.append(
        structlog.dev.ConsoleRenderer() if legible else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=procesadores,
        wrapper_class=structlog.make_filtering_bound_logger(nivel),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def obtener_logger(nombre: str) -> structlog.stdlib.BoundLogger:
    """The logger a module should use: `logger = obtener_logger(__name__)`."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(nombre)
    return logger
