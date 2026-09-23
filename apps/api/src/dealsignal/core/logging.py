"""Structured logging. Console-friendly locally, JSON everywhere else."""

from __future__ import annotations

import logging
import sys

import structlog

from dealsignal.core.config import Settings


def configure_logging(settings: Settings) -> None:
    """Send stdlib logging and structlog through one pipeline."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer: structlog.types.Processor = (
        structlog.dev.ConsoleRenderer()
        if settings.log_format == "console"
        else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Module-level logger: `log = get_logger(__name__)`."""
    return structlog.stdlib.get_logger(name)
