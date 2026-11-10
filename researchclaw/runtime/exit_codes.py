"""Exit-code contract between worker and supervisor (G1b / A1-7, R-1).

Mapping (DESIGN §2): 0 ok, 65 data, 75 retryable, 77 revoked, 78 config,
85 paused-normal. Only 75 is retryable.
"""
from __future__ import annotations

from enum import Enum

OK = 0
DATA = 65
RETRYABLE = 75
REVOKED = 77
CONFIG = 78
PAUSED = 85

RETRYABLE_CODE = RETRYABLE

REVOKED_HINTS = ("401", "403", "unauthorized", "forbidden", "revoked",
                 "invalid api key", "authentication")
CONFIG_HINTS = ("config", "configuration", "version incompatible",
                "schema", "invalid argument", "not found: config")
PAUSED_STATUSES = ("paused", "blocked_approval", "rejected")


class ExitClass(str, Enum):
    OK = "ok"
    DATA = "data"
    RETRYABLE = "retryable"
    REVOKED = "revoked"
    CONFIG = "config"
    PAUSED = "paused"


_CODE_BY_CLASS = {
    ExitClass.OK: OK,
    ExitClass.DATA: DATA,
    ExitClass.RETRYABLE: RETRYABLE,
    ExitClass.REVOKED: REVOKED,
    ExitClass.CONFIG: CONFIG,
    ExitClass.PAUSED: PAUSED,
}


def _status_value(result) -> str:
    status = getattr(result, "status", "")
    return str(getattr(status, "value", status)).lower()


def classify_error(error: str | None) -> ExitClass:
    text = (error or "").lower()
    if any(h in text for h in REVOKED_HINTS):
        return ExitClass.REVOKED
    if any(h in text for h in CONFIG_HINTS):
        return ExitClass.CONFIG
    return ExitClass.RETRYABLE


def classify_results(results) -> int:
    """Map a stage-result list to the worker exit code (DESIGN §2)."""
    results = list(results or [])
    if not results:
        return DATA
    failed = [r for r in results if _status_value(r) == "failed"]
    if failed:
        return _CODE_BY_CLASS[classify_error(getattr(failed[-1], "error", ""))]
    if any(_status_value(r) in PAUSED_STATUSES for r in results):
        return PAUSED
    return OK


def is_retryable(code: int) -> bool:
    return code == RETRYABLE_CODE


def class_name(code: int) -> str:
    for cls, value in _CODE_BY_CLASS.items():
        if value == code:
            return cls.value
    return "unknown"
