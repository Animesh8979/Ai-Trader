"""Structured logging via loguru.

Console + daily-rotating file. `diagnose` is deliberately turned OFF so that exception
tracebacks never dump local variables (which could contain API keys) into the logs.
"""

from __future__ import annotations

import sys

from loguru import logger

from godmode.core import paths

_CONFIGURED = False

_CONSOLE_FORMAT = (
    "<green>{time:HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)


def setup_logging(level: str = "INFO", *, json_logs: bool = False):
    """Configure logging once. Safe to call multiple times."""
    global _CONFIGURED
    if _CONFIGURED:
        return logger

    paths.ensure_runtime_dirs()
    logger.remove()

    # Console (human readable). diagnose=False => no variable dumps in tracebacks.
    logger.add(
        sys.stderr,
        level=level,
        colorize=True,
        format=_CONSOLE_FORMAT,
        backtrace=False,
        diagnose=False,
    )

    # Daily-rotating file (keeps a full DEBUG record).
    logger.add(
        paths.LOGS_DIR / "godmode_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation="00:00",
        retention="30 days",
        enqueue=True,
        backtrace=False,
        diagnose=False,
        serialize=json_logs,
    )

    _CONFIGURED = True
    return logger


def get_logger(name: str | None = None):
    """Return the shared logger (optionally tagged with a component name)."""
    return logger.bind(component=name) if name else logger
