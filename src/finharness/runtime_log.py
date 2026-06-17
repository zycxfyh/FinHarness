"""Structlog setup for FinHarness runtime surfaces."""

from __future__ import annotations

import logging

import structlog

_CONFIGURED = False


def configure_logging(*, json_logs: bool = True, level: int = logging.INFO) -> None:
    """Configure structlog once for local runtime commands and API requests."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(level=level, format="%(message)s")
    renderer = structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str | None = None):
    configure_logging()
    return structlog.get_logger(name)
