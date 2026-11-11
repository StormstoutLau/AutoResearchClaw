"""pipeline_summary integrity check (G3 M1, P-075).

M1 scope: canonical JSON + SHA-256 sidecar, two-way comparison.
M2 will add the ``events.jsonl`` ``pipeline.summary`` anchor (``require_event``).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

SUMMARY_NAME = "pipeline_summary.json"
SIDECAR_NAME = "pipeline_summary.sha256"
EVENT_TYPE = "pipeline.summary"

E_SUMMARY_MISSING = "E_SUMMARY_MISSING"
E_SUMMARY_TAMPERED = "E_SUMMARY_TAMPERED"
E_SUMMARY_EVENT_MISSING = "E_SUMMARY_EVENT_MISSING"


def canonical_summary(summary: dict) -> bytes:
    """Deterministic JSON bytes (sorted keys, compact separators)."""
    return json.dumps(
        summary, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def summary_digest(summary: dict) -> str:
    return "sha256:" + hashlib.sha256(canonical_summary(summary)).hexdigest()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_summary(run_dir: Path, summary: dict) -> Path:
    run_dir = Path(run_dir)
    path = run_dir / SUMMARY_NAME
    _atomic_write(path, canonical_summary(summary) + b"\n")
    _atomic_write(
        run_dir / SIDECAR_NAME,
        (summary_digest(summary) + "\n").encode("utf-8"),
    )
    return path


def _last_event_digest(run_dir: Path) -> str | None:
    events = run_dir / "events.jsonl"
    if not events.is_file():
        return None
    digest = None
    for line in events.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if raw.get("type") != EVENT_TYPE:
            continue
        payload = raw.get("payload")
        if isinstance(payload, dict) and isinstance(payload.get("digest"), str):
            digest = payload["digest"]
    return digest


def verify_summary(run_dir: Path, *, require_event: bool = False) -> dict:
    """Return ``{ok, digest, errors}``; never raises on corrupt input."""
    run_dir = Path(run_dir)
    errors: list[dict] = []
    path = run_dir / SUMMARY_NAME
    if not path.is_file():
        return {
            "ok": False,
            "digest": None,
            "errors": [{"code": E_SUMMARY_MISSING, "field": SUMMARY_NAME}],
        }
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "ok": False,
            "digest": None,
            "errors": [{"code": E_SUMMARY_TAMPERED, "field": "json"}],
        }
    digest = summary_digest(summary)
    sidecar = run_dir / SIDECAR_NAME
    if not sidecar.is_file():
        errors.append({"code": E_SUMMARY_TAMPERED, "field": SIDECAR_NAME})
    else:
        expected = sidecar.read_text(encoding="utf-8").strip()
        if expected != digest:
            errors.append({
                "code": E_SUMMARY_TAMPERED,
                "field": SIDECAR_NAME,
                "expected": expected,
                "actual": digest,
            })
    if require_event:
        event_digest = _last_event_digest(run_dir)
        if event_digest is None:
            errors.append({"code": E_SUMMARY_EVENT_MISSING, "field": "events.jsonl"})
        elif event_digest != digest:
            errors.append({
                "code": E_SUMMARY_TAMPERED,
                "field": "events.jsonl",
                "expected": event_digest,
                "actual": digest,
            })
    return {"ok": not errors, "digest": digest, "errors": errors}


def append_summary_event(run_dir: Path, summary: dict, event_log: Any | None = None) -> None:
    """M2 helper: append the ``pipeline.summary`` anchor to the event chain."""
    if event_log is None:
        from researchclaw.runtime.event_log import EventLog

        event_log = EventLog(Path(run_dir) / "events.jsonl")
    event_log.append(EVENT_TYPE, {"digest": summary_digest(summary)})
