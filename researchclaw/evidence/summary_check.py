"""pipeline_summary integrity check (G3 M1/M2, P-075/P-078).

M1 scope: canonical JSON + SHA-256 sidecar, two-way comparison.
M2 scope: ``events.jsonl`` ``pipeline.summary`` anchor (``require_event``),
with one anchor per execution segment (D-2 fix).
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


def _canonical_payload(payload: dict) -> str:
    """Must match ``event_log.canonical_json`` (the writer's encoding)."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _collect_anchors(run_dir: Path) -> tuple[list[tuple[int, dict]], list[dict]]:
    """Read ``pipeline.summary`` events with their execution segment.

    Returns ``(anchors, errors)``. A segment increments at every ``run.started``;
    the writer anchors at most once per segment (M2).
    """
    errors: list[dict] = []
    has_log = any(run_dir.glob("events*.jsonl")) or any(
        run_dir.glob("events*.jsonl.gz")
    )
    events: list[dict] = []
    if has_log:
        try:
            from researchclaw.runtime.event_log import EventLog

            events = EventLog(run_dir, run_dir.name or "run").read_all()
        except Exception:  # noqa: BLE001 - corrupt log is reported, never raised
            errors.append({
                "code": E_SUMMARY_TAMPERED,
                "field": "events.jsonl:unreadable",
            })
    anchors: list[tuple[int, dict]] = []
    segment = 0
    for event in events:
        event_type = event.get("type")
        if event_type == "run.started":
            segment += 1
            continue
        if event_type != EVENT_TYPE:
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict) or not isinstance(payload.get("digest"), str):
            errors.append({
                "code": E_SUMMARY_TAMPERED,
                "field": "events.jsonl:payload",
            })
            continue
        recorded = event.get("payload_sha256")
        expected = hashlib.sha256(_canonical_payload(payload).encode("utf-8")).hexdigest()
        if not isinstance(recorded, str) or recorded != expected:
            errors.append({
                "code": E_SUMMARY_TAMPERED,
                "field": "events.jsonl:payload_sha256",
            })
            continue
        anchors.append((segment, payload))
    return anchors, errors


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
        anchors, anchor_errors = _collect_anchors(run_dir)
        errors.extend(anchor_errors)
        if not anchors:
            errors.append({"code": E_SUMMARY_EVENT_MISSING, "field": "events.jsonl"})
        else:
            segments = [segment for segment, _ in anchors]
            if len(segments) != len(set(segments)):
                # D-2: a second anchor in the same execution segment means the
                # summary was rewritten after the real anchor was recorded.
                errors.append({
                    "code": E_SUMMARY_TAMPERED,
                    "field": "events.jsonl:duplicate_anchor",
                })
            anchored = anchors[-1][1]["digest"]
            if anchored != digest:
                errors.append({
                    "code": E_SUMMARY_TAMPERED,
                    "field": "events.jsonl",
                    "expected": anchored,
                    "actual": digest,
                })
    return {"ok": not errors, "digest": digest, "errors": errors}


def append_summary_event(
    run_dir: Path, summary: dict, event_log: Any | None = None
) -> None:
    """M2 helper: append the ``pipeline.summary`` anchor to the event chain."""
    if event_log is None:
        from researchclaw.runtime.event_log import EventLog

        event_log = EventLog(Path(run_dir) / "events.jsonl")
    event_log.append(
        EVENT_TYPE,
        {"digest": summary_digest(summary), "generated": summary.get("generated")},
    )
