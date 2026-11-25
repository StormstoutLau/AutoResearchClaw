"""Cross-run operational view and archive sweep (G7 A7-5/A7-6).

Design authority: ``spec/arc-g7-concurrency-dual-plane/DESIGN.md`` §6.

``build_ops_view`` is read-only and never mutates a run directory.
``sweep_runs`` is a maintenance action: it applies the per-run retention that
already exists in ``EventLog`` and appends a derived index row. Run
directories are never deleted, and the index is rebuildable from them.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from researchclaw.runtime.event_log import EventLog, canonical_json
from researchclaw.runtime.filelock import exclusive_lock

RUN_INDEX_NAME = "RUN_INDEX.jsonl"
RUN_INDEX_LOCK = "RUN_INDEX.lock"


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _event_files(run_dir: Path) -> list[Path]:
    files = [
        path for path in run_dir.iterdir()
        if path.is_file()
        and path.name.startswith("events")
        and (path.name.endswith(".jsonl") or path.name.endswith(".jsonl.gz"))
    ]
    return sorted(files, key=lambda path: path.name)


def _iter_event_rows(run_dir: Path) -> Iterable[dict[str, Any]]:
    for path in _event_files(run_dir):
        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        else:
            try:
                lines = path.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
            except OSError:
                continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                yield row


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _seconds_between(left: str, right: str) -> float | None:
    try:
        a = datetime.fromisoformat(str(left).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(right).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return round(max(0.0, (b - a).total_seconds()), 3)


def _recovery_seconds(
    supervisor_rows: list[dict[str, Any]], soak_rows: list[dict[str, Any]]
) -> list[float]:
    rows = [row for row in supervisor_rows + soak_rows if row.get("ts")]
    rows.sort(key=lambda row: str(row.get("ts")))
    values: list[float] = []
    pending: str | None = None
    for row in rows:
        event = row.get("event")
        if event in ("restart_scheduled", "restart_injected"):
            pending = str(row.get("ts", ""))
        elif event == "worker_started" and pending is not None:
            delta = _seconds_between(pending, str(row.get("ts", "")))
            if delta is not None:
                values.append(delta)
            pending = None
    return values


def _failure_stages(run_dir: Path, event_rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    stage_rows = _read_jsonl(run_dir / "stage_events.jsonl")
    if stage_rows:
        for row in stage_rows:
            if str(row.get("status", "")).lower() in ("failed", "error"):
                key = str(row.get("stage", "?"))
                counts[key] = counts.get(key, 0) + 1
        if counts:
            return counts
    for row in event_rows:
        if row.get("type") != "stage.failed":
            continue
        stage = row.get("stage")
        if stage is None and isinstance(row.get("payload"), dict):
            stage = row["payload"].get("stage")
        key = str(stage if stage is not None else "?")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _run_row(run_dir: Path) -> dict[str, Any]:
    supervisor_rows = _read_jsonl(run_dir / "supervisor.jsonl")
    soak_rows = _read_jsonl(run_dir / "soak_session.jsonl")
    event_rows = list(_iter_event_rows(run_dir))

    scheduled = sum(1 for row in supervisor_rows
                    if row.get("event") == "restart_scheduled")
    injected = sum(1 for row in soak_rows
                   if row.get("event") == "restart_injected")
    checkpoint = _read_json(run_dir / "checkpoint.json", {})
    if not isinstance(checkpoint, dict):
        checkpoint = {}
    return {
        "run_id": run_dir.name,
        "restarts": max(scheduled, injected),
        "recovery_seconds": _recovery_seconds(supervisor_rows, soak_rows),
        "failure_stages": _failure_stages(run_dir, event_rows),
        "last_stage": int(checkpoint.get("last_completed_stage") or 0),
        "status": str(checkpoint.get("status", "unknown")),
        "events": len(event_rows),
    }


def build_ops_view(runs_root: str | Path) -> dict[str, Any]:
    root = Path(runs_root)
    runs: list[dict[str, Any]] = []
    if root.is_dir():
        for run_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            runs.append(_run_row(run_dir))
    totals = {
        "runs": len(runs),
        "restarts": sum(row["restarts"] for row in runs),
        "failures": sum(sum(row["failure_stages"].values()) for row in runs),
        "recovery_seconds": round(
            sum(sum(row["recovery_seconds"]) for row in runs), 3
        ),
    }
    return {"runs_root": str(root), "runs": runs, "totals": totals}


def _chain_tail(run_dir: Path, event_rows: list[dict[str, Any]]) -> str:
    summary = _read_json(run_dir / "events_summary.json", {})
    if isinstance(summary, dict) and summary.get("chain_tail"):
        return str(summary["chain_tail"])
    if not event_rows:
        return "0" * 64
    return hashlib.sha256(
        canonical_json(event_rows[-1]).encode("utf-8")
    ).hexdigest()


def _append_index(root: Path, row: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    path = root / RUN_INDEX_NAME
    with exclusive_lock(root / RUN_INDEX_LOCK, timeout=10.0):
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            fh.flush()


def sweep_runs(
    runs_root: str | Path,
    *,
    retention_days: int = 30,
    archive_days: int = 365,
    now: datetime | None = None,
    write_index: bool = True,
) -> dict[str, Any]:
    """Apply per-run event retention and append one derived index row per run."""
    root = Path(runs_root)
    moment = now or datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    if not root.is_dir():
        return {"ok": True, "runs": rows}
    for run_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        log = EventLog(run_dir, run_dir.name, fsync=False)
        result = log.apply_retention(
            retention_days=retention_days, archive_days=archive_days, now=moment
        )
        event_rows = list(_iter_event_rows(run_dir))
        row = {
            "ts": moment.isoformat(),
            "run_id": run_dir.name,
            "last_seq": int(event_rows[-1].get("seq", 0)) if event_rows else 0,
            "count": len(event_rows),
            "chain_tail": _chain_tail(run_dir, event_rows),
            "archived": list(result.get("archived") or []),
            "deleted": list(result.get("deleted") or []),
        }
        if write_index:
            _append_index(root, row)
        rows.append(row)
    return {"ok": True, "runs": rows}
