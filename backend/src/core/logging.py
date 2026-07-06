"""Logging configuration helper.

Kept intentionally small §1: `core`
must avoid heavyweight logging frameworks.
"""

from __future__ import annotations

import logging
import os
from typing import Final

_LOG_FORMAT: Final[str] = "%(asctime)s %(levelname)-7s %(name)s :: %(message)s"
_DATE_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: str | int | None = None) -> None:
    """Configure the root logger for the FastAPI process.

    Safe to call more than once; subsequent calls are idempotent because we
    replace handlers explicitly. The default level is INFO, overridable via
    the ``LOG_LEVEL`` environment variable or the ``level`` argument.
    """
    if level is None:
        level = os.environ.get("LOG_LEVEL", "INFO")
    if isinstance(level, str):
        numeric_level = logging.getLevelName(level.upper())
        if not isinstance(numeric_level, int):
            numeric_level = logging.INFO
    else:
        numeric_level = int(level)

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(numeric_level)

    # Keep uvicorn's structured access logs but align level
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(numeric_level)
