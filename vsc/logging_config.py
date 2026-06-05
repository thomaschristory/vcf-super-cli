"""Logging configuration.

Logs go to **stderr** so stdout stays clean for machine-readable output, and the
default level is ``WARNING`` (override with ``VSC_LOG_LEVEL``). This keeps the
agent-friendly contract: stdout is data, stderr is diagnostics.
"""

from __future__ import annotations

import logging
import os
import sys

import structlog

_DEFAULT_LEVEL = "WARNING"


def _level() -> int:
    name = os.environ.get("VSC_LOG_LEVEL", _DEFAULT_LEVEL).upper()
    return logging.getLevelNamesMapping().get(name, logging.WARNING)


def configure_logging() -> None:
    """Send structlog output to stderr at the configured level (idempotent)."""
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(_level()),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=False,
    )
