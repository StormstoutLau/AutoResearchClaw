"""Stage 10 repair trace (B-36 P0).

The repair loop currently logs only a summary line ("Repair attempt returned
invalid Python").  When it aborts, there is no way to tell *why* the response
was rejected, what the prompt contained, or how large it was.

This module appends one digest-only record per repair event to
``stage-10/repair_trace.jsonl``.  It deliberately stores no prompt or code
bodies (same invariant as ``steps.jsonl``): digests plus short diagnostic
summaries are enough to replay the decision path without leaking content.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from researchclaw.runtime.filelock import exclusive_lock
from researchclaw.utils.paths import safe_join

TRACE_NAME = "repair_trace.jsonl"
LOCK_NAME = ".repair_trace.lock"
_MESSAGE_MAX = 300


def digest(text: str) -> str:
    """Stable digest for prompts and responses."""
    return "sha256:" + hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def _summarize_errors(errors: Iterable[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for issue in errors or ():
        message = str(getattr(issue, "message", "") or "")
        out.append({
            "severity": str(getattr(issue, "severity", "") or ""),
            "category": str(getattr(issue, "category", "") or ""),
            "line": getattr(issue, "line", None),
            "col": getattr(issue, "col", None),
            "message": message[:_MESSAGE_MAX],
        })
    return out


def record(
    stage_dir: str | Path,
    *,
    phase: str,
    file: str = "",
    attempt: int = 0,
    max_attempts: int = 0,
    reason: str = "",
    error_summary: str = "",
    errors: Iterable[Any] = (),
    prompt: str = "",
    response: str = "",
    accepted: Iterable[str] = (),
    rejected: Iterable[str] = (),
    model: str = "",
    truncated: bool | None = None,
    extra: Mapping[str, Any] | None = None,
    ts: str | None = None,
) -> dict[str, Any] | None:
    """Append one trace record under a lock; returns it, or ``None`` on failure.

    Best-effort by design: tracing must never break a stage that is already
    failing (mirrors the ``steps.jsonl`` discipline).
    """
    try:
        stage_dir = Path(stage_dir)
        stage_dir.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "ts": ts or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "stage": stage_dir.name,
            "phase": phase,
            "file": file,
            "attempt": int(attempt),
            "max_attempts": int(max_attempts),
            "reason": reason,
            "error_summary": error_summary,
            "errors": _summarize_errors(errors),
            "prompt_sha256": digest(prompt),
            "prompt_chars": len(prompt or ""),
            "response_sha256": digest(response),
            "response_chars": len(response or ""),
            "accepted": list(accepted or ()),
            "rejected": list(rejected or ()),
            "model": model,
            "truncated": truncated,
        }
        if extra:
            payload.update(dict(extra))
        line = json.dumps(payload, ensure_ascii=False)
        with exclusive_lock(stage_dir / LOCK_NAME):
            path = safe_join(stage_dir, TRACE_NAME)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        return payload
    except Exception:  # noqa: BLE001 - tracing must never raise
        return None


def load(stage_dir: str | Path) -> list[dict[str, Any]]:
    """Read the trace; malformed tail lines are skipped."""
    path = Path(stage_dir) / TRACE_NAME
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            out.append(payload)
    return out
