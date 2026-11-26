"""Runtime logging configuration (B-31a).

``researchclaw`` never configured the root logger, so the default WARNING
level dropped every ``logger.info`` progress line and a long stage looked
dead on disk.  This module is the single place that turns the ``run`` command
line flags into a configured logger.  It follows the standard recipe from the
Python logging HOWTO: ``getattr(logging, level.upper())`` plus
``logging.basicConfig(level=..., handlers=...)``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

DEFAULT_LEVEL = "INFO"
DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
VALID_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def resolve_log_level(name: str | int | None) -> int:
    """Map a CLI level name (``info`` / ``INFO``) to a logging level int."""
    if name is None:
        name = DEFAULT_LEVEL
    if isinstance(name, int):
        return name
    level = getattr(logging, str(name).strip().upper(), None)
    if not isinstance(level, int):
        raise ValueError(
            f"Invalid log level: {name!r} (expected one of {VALID_LEVELS})"
        )
    return level


def configure_logging(
    level: str | int | None = DEFAULT_LEVEL,
    log_file: str | Path | None = None,
    *,
    stream: Any | None = None,
) -> int:
    """Configure the root logger once and return the numeric level.

    ``force=True`` replaces handlers a previous call installed, so a second
    invocation in the same process is idempotent instead of duplicating
    output.
    """
    numeric = resolve_log_level(level)
    formatter = logging.Formatter(DEFAULT_FORMAT)
    handlers: list[logging.Handler] = []

    stream_handler = logging.StreamHandler(sys.stderr if stream is None else stream)
    stream_handler.setFormatter(formatter)
    handlers.append(stream_handler)

    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    logging.basicConfig(level=numeric, handlers=handlers, force=True)
    return numeric


def force_line_buffering(stream: Any | None = None) -> bool:
    """Flush redirected stdout/stderr per line so logs grow during a stage.

    ``print`` to a redirected stdout is block-buffered.  ``reconfigure`` is
    available on ``io.TextIOWrapper`` since Python 3.7; other stream types
    (pytest capture, StringIO) are left untouched.
    """
    targets = [stream] if stream is not None else [sys.stdout, sys.stderr]
    changed = False
    for target in targets:
        reconfigure = getattr(target, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(line_buffering=True)
        except (ValueError, OSError):
            continue
        changed = True
    return changed
