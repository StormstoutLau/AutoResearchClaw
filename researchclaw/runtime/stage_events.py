"""Stage progress ledger and loop guard (G3 M2, P-078).

Design authority: ``spec/arc-g3-m2-stage-events/DESIGN.md`` §3.

Invariants
----------
I-1  ``stage_events.jsonl`` is append-only; ``seq`` is strictly monotonic.
I-2  ``evaluate_loop`` is a pure function over the event list (no IO).
I-3  Callers treat failures as non-fatal; this module raises for the caller
     to log, never to abort a run.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from researchclaw.runtime.filelock import LOCK_DIR_NAME, exclusive_lock

STAGE_EVENTS_NAME = "stage_events.jsonl"
E_LOOP_DETECTED = "E_LOOP_DETECTED"

LOOP_WINDOW = 3
LOOP_WARN = 2
DEFAULT_QUALITY_THRESHOLD = 0.6
MIN_SHORTLIST = 15
ID_KEYS = ("id", "paper_id", "doi", "title")


class StageEventError(ValueError):
    """Corrupt ``stage_events.jsonl`` line (a torn tail is tolerated)."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class StageEvent:
    seq: int
    ts: str
    stage: int
    stage_name: str
    attempt: int
    plan_sig: str
    new_rows: int
    row_ids_digest: str
    network_error: bool
    status: str

    def as_dict(self) -> dict:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "stage": self.stage,
            "stage_name": self.stage_name,
            "attempt": self.attempt,
            "plan_sig": self.plan_sig,
            "new_rows": self.new_rows,
            "row_ids_digest": self.row_ids_digest,
            "network_error": self.network_error,
            "status": self.status,
        }


def plan_signature(payload: Mapping[str, Any]) -> str:
    """Deterministic signature of a search/screen plan payload."""
    return _sha256_text(_canonical_json(dict(payload)))


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_yaml_mapping(path: Path) -> dict:
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - missing/broken plan degrades to no filters
        return {}
    return data if isinstance(data, dict) else {}


def plan_payload(
    run_dir: Path,
    stage: int,
    *,
    quality_threshold: float = DEFAULT_QUALITY_THRESHOLD,
    min_shortlist: int = MIN_SHORTLIST,
) -> dict | None:
    """Build the signed plan payload for stage 4/5, or ``None`` if inputs are absent."""
    run_dir = Path(run_dir)
    meta = _read_json(run_dir / "stage-03" / "queries.json")
    if not isinstance(meta, dict):
        return None
    queries = sorted(
        {str(item).strip() for item in (meta.get("queries") or []) if str(item).strip()}
    )
    raw_sources = _read_json(run_dir / "stage-03" / "sources.json")
    source_ids = sorted(
        {
            str(item.get("id"))
            for item in raw_sources or []
            if isinstance(item, dict) and item.get("id")
        }
    ) if isinstance(raw_sources, list) else []
    plan = _read_yaml_mapping(run_dir / "stage-03" / "search_plan.yaml")
    filters = plan.get("filters") if isinstance(plan.get("filters"), dict) else {}
    year_min = int(meta.get("year_min") or 0)
    if int(stage) == 4:
        return {
            "stage": 4,
            "queries": queries,
            "year_min": year_min,
            "sources": source_ids,
            "filters": filters,
        }
    if int(stage) == 5:
        return {
            "stage": 5,
            "queries": queries,
            "year_min": year_min,
            "sources": source_ids,
            "filters": {
                "quality_threshold": float(quality_threshold),
                "min_shortlist": int(min_shortlist),
                "prefilter": "keyword_overlap>=1",
            },
        }
    return None


def count_rows(path: Path) -> int:
    path = Path(path)
    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _rows(path: Path) -> list[dict]:
    path = Path(path)
    if not path.is_file():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _row_id(row: Mapping[str, Any]) -> str:
    for key in ID_KEYS:
        value = row.get(key)
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value)
    return ""


def row_ids_digest(path: Path) -> str:
    """Identity of a round's result set (sorted, deduplicated ids)."""
    ids = sorted({rid for rid in (_row_id(row) for row in _rows(path)) if rid})
    return _sha256_text(_canonical_json(ids))


def collect_progress(
    run_dir: Path,
    stage: int,
    *,
    quality_threshold: float = DEFAULT_QUALITY_THRESHOLD,
    min_shortlist: int = MIN_SHORTLIST,
) -> dict:
    """Read the progress signals for one literature round from existing artifacts."""
    run_dir = Path(run_dir)
    payload = plan_payload(
        run_dir,
        stage,
        quality_threshold=quality_threshold,
        min_shortlist=min_shortlist,
    )
    artifact = run_dir / f"stage-{int(stage):02d}" / (
        "candidates.jsonl" if int(stage) == 4 else "shortlist.jsonl"
    )
    status = _read_json(run_dir / "stage-04" / "retrieval_status.json")
    degraded = bool(status.get("retrieval_degraded")) if isinstance(status, dict) else False
    return {
        "plan_sig": plan_signature(payload) if payload is not None else None,
        "new_rows": count_rows(artifact),
        "row_ids_digest": row_ids_digest(artifact),
        "network_error": degraded,
    }


def append_stage_event(
    run_dir: Path,
    *,
    stage: int,
    stage_name: str,
    attempt: int | None = None,
    plan_sig: str,
    new_rows: int,
    row_ids_digest: str,
    network_error: bool,
    status: str = "done",
    ts: str | None = None,
) -> StageEvent:
    """Append one round to ``stage_events.jsonl`` under an advisory lock.

    ``seq`` and (when omitted) ``attempt`` are computed inside the lock, so
    concurrent writers cannot duplicate either field (P-079 O-3).
    """
    run_dir = Path(run_dir)
    with exclusive_lock(run_dir / LOCK_DIR_NAME / "stage_events.lock"):
        existing = load_stage_events(run_dir)
        resolved_attempt = (
            int(attempt)
            if attempt is not None
            else sum(1 for event in existing if int(event.stage) == int(stage)) + 1
        )
        event = StageEvent(
            seq=(existing[-1].seq + 1) if existing else 1,
            ts=ts or _utcnow_iso(),
            stage=int(stage),
            stage_name=str(stage_name),
            attempt=resolved_attempt,
            plan_sig=str(plan_sig),
            new_rows=int(new_rows),
            row_ids_digest=str(row_ids_digest),
            network_error=bool(network_error),
            status=str(status),
        )
        path = run_dir / STAGE_EVENTS_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(_canonical_json(event.as_dict()) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return event


def load_stage_events(run_dir: Path) -> list[StageEvent]:
    """Read the ledger.

    A run of corrupt lines at the end of the file is dropped (crash recovery,
    matching ``EventLog.read_all``); corruption before the last parseable line
    raises :class:`StageEventError`.
    """
    path = Path(run_dir) / STAGE_EVENTS_NAME
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    last_good = -1
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError:
            continue
        last_good = index
    events: list[StageEvent] = []
    for index, line in enumerate(lines[: last_good + 1]):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise StageEventError(f"{path}:{index + 1}: {exc.msg}") from exc
        events.append(
            StageEvent(
                seq=int(raw.get("seq") or 0),
                ts=str(raw.get("ts") or ""),
                stage=int(raw.get("stage") or 0),
                stage_name=str(raw.get("stage_name") or ""),
                attempt=int(raw.get("attempt") or 0),
                plan_sig=str(raw.get("plan_sig") or ""),
                new_rows=int(raw.get("new_rows") or 0),
                row_ids_digest=str(raw.get("row_ids_digest") or ""),
                network_error=bool(raw.get("network_error")),
                status=str(raw.get("status") or ""),
            )
        )
    return events


def evaluate_loop(
    events: Iterable[StageEvent],
    *,
    stage: int,
    window: int = LOOP_WINDOW,
) -> dict:
    """Pure loop decision: continue / warn / pause (E_LOOP_DETECTED).

    ``window`` below 1 is rejected: it would make ``consecutive >= window``
    unconditionally true and pause every round (P-079 O-2).
    """
    window = int(window)
    if window < 1:
        raise ValueError(f"window must be >= 1, got {window}")
    same_stage = [
        event
        for event in events
        if int(event.stage) == int(stage) and not event.network_error
    ]
    if not same_stage:
        return {"action": "continue", "consecutive": 0, "code": None, "plan_sig": None}
    last = same_stage[-1]
    consecutive = 0
    for event in reversed(same_stage):
        if (
            event.plan_sig != last.plan_sig
            or event.row_ids_digest != last.row_ids_digest
        ):
            break
        consecutive += 1
    if consecutive >= int(window):
        return {
            "action": "pause",
            "consecutive": consecutive,
            "code": E_LOOP_DETECTED,
            "plan_sig": last.plan_sig,
        }
    if consecutive >= LOOP_WARN:
        return {
            "action": "warn",
            "consecutive": consecutive,
            "code": None,
            "plan_sig": last.plan_sig,
        }
    return {
        "action": "continue",
        "consecutive": consecutive,
        "code": None,
        "plan_sig": last.plan_sig,
    }


def record_stage_progress(
    run_dir: Path,
    stage: int,
    stage_name: str,
    *,
    config: Any | None = None,
) -> dict:
    """Collect signals, append one event, and return the loop decision."""
    run_dir = Path(run_dir)
    threshold = DEFAULT_QUALITY_THRESHOLD
    if config is not None:
        research = getattr(config, "research", None)
        value = getattr(research, "quality_threshold", None)
        if isinstance(value, (int, float)):
            threshold = float(value)
    progress = collect_progress(run_dir, stage, quality_threshold=threshold)
    if progress["plan_sig"] is None:
        return {
            "action": "skip",
            "consecutive": 0,
            "code": None,
            "plan_sig": None,
            "reason": "missing_plan",
        }
    append_stage_event(
        run_dir,
        stage=int(stage),
        stage_name=stage_name,
        plan_sig=progress["plan_sig"],
        new_rows=progress["new_rows"],
        row_ids_digest=progress["row_ids_digest"],
        network_error=progress["network_error"],
    )
    return evaluate_loop(load_stage_events(run_dir), stage=int(stage))
