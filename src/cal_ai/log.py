"""Structured logging setup for cal-ai.

Provides a consistent log format across the application with ISO 8601
timestamps and pipe-separated fields.
"""

from __future__ import annotations

import logging
import sys

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

# Sentinel to detect handlers added by setup_logging so repeated calls
# are idempotent without interfering with handlers added externally.
_HANDLER_ATTR = "_cal_ai_log_handler"


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger with a structured formatter.

    Sets the root logger level and attaches a :class:`logging.StreamHandler`
    that writes to *stderr* using the project log format.

    Calling this function multiple times is safe -- it will not add
    duplicate handlers.

    Args:
        level: A standard logging level name (e.g. ``"DEBUG"``,
            ``"INFO"``, ``"WARNING"``).

    Raises:
        ValueError: If *level* is not a recognised logging level string.
    """
    numeric_level = logging.getLevelName(level.upper())
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {level!r}")

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Idempotent: skip if we already attached our handler.
    for handler in root.handlers:
        if getattr(handler, _HANDLER_ATTR, False):
            # Update the existing handler's level in case it changed.
            handler.setLevel(numeric_level)
            return

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(numeric_level)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt="%Y-%m-%dT%H:%M:%S")
    handler.setFormatter(formatter)

    setattr(handler, _HANDLER_ATTR, True)
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger.

    Convenience wrapper around :func:`logging.getLogger` to keep imports
    tidy in other modules.

    Args:
        name: Dotted logger name, typically ``__name__`` of the caller.

    Returns:
        A :class:`logging.Logger` instance.
    """
    return logging.getLogger(name)
