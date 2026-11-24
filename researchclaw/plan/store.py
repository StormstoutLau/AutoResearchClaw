"""ResearchPlan storage: plan/plan.v1.json, index.json, plan_events.jsonl (G8a / P-152).

The plan directory is the authority for "what is intended"; ``stage-XX/`` stays
the authority for "what happened" (design §8). Writes are atomic and every
change appends one event line.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from researchclaw.runtime.event_log import canonical_json
from researchclaw.plan.schema import seal_plan

PLAN_DIR = "plan"
PLAN_NAME = "plan.v1.json"
INDEX_NAME = "index.json"
EVENTS_NAME = "plan_events.jsonl"


def plan_filename(version: int) -> str:
    return f"plan.v{int(version)}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def plan_dir(run_dir: str | Path) -> Path:
    return Path(run_dir) / PLAN_DIR


def read_index(run_dir: str | Path) -> dict | None:
    path = plan_dir(run_dir) / INDEX_NAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def plan_path(run_dir: str | Path, version: int | None = None) -> Path:
    """Path of the requested version; ``None`` follows ``index.json``."""
    if version is not None:
        return plan_dir(run_dir) / plan_filename(version)
    index = read_index(run_dir)
    if index and index.get("file"):
        return plan_dir(run_dir) / str(index["file"])
    return plan_dir(run_dir) / PLAN_NAME


def load_plan(run_dir: str | Path) -> dict | None:
    path = plan_path(run_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def append_event(
    run_dir: str | Path,
    event_type: str,
    payload: Mapping[str, Any],
) -> None:
    line = canonical_json({
        "ts": _now_iso(),
        "type": str(event_type),
        "payload": dict(payload),
    })
    path = plan_dir(run_dir) / EVENTS_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_events(run_dir: str | Path) -> list[dict]:
    path = plan_dir(run_dir) / EVENTS_NAME
    if not path.is_file():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            break
        if isinstance(item, dict):
            out.append(item)
    return out


def _write(run_dir: str | Path, plan: Mapping[str, Any], *, stage: int, event: str) -> dict:
    sealed = seal_plan(plan)
    version = int(sealed.get("version", 1))
    filename = plan_filename(version)
    _atomic_write(
        plan_dir(run_dir) / filename,
        json.dumps(sealed, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
    )
    index = {
        "version": version,
        "digest": sealed.get("plan_digest", ""),
        "file": filename,
    }
    _atomic_write(
        plan_dir(run_dir) / INDEX_NAME,
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
    )
    append_event(
        run_dir,
        event,
        {
            "stage": int(stage),
            "version": version,
            "digest": sealed.get("plan_digest", ""),
        },
    )
    return sealed


def write_replan(
    run_dir: str | Path,
    plan: Mapping[str, Any],
    *,
    stage: int,
    diff: Mapping[str, Any],
    reason: str,
) -> dict:
    """Persist a new plan version with its diff and a ``plan.replanned`` event."""
    sealed = seal_plan(plan)
    version = int(sealed.get("version", 1))
    filename = plan_filename(version)
    _atomic_write(
        plan_dir(run_dir) / filename,
        json.dumps(sealed, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
    )
    _atomic_write(
        plan_dir(run_dir) / INDEX_NAME,
        json.dumps(
            {"version": version, "digest": sealed.get("plan_digest", ""), "file": filename},
            indent=2,
            ensure_ascii=False,
        ) + "\n",
    )
    append_event(
        run_dir,
        "plan.replanned",
        {
            "stage": int(stage),
            "version": version,
            "parent_version": sealed.get("parent_version"),
            "reason": str(reason),
            "diff": dict(diff),
            "digest": sealed.get("plan_digest", ""),
        },
    )
    return sealed


def write_plan(run_dir: str | Path, plan: Mapping[str, Any], *, stage: int = 2) -> dict:
    return _write(run_dir, plan, stage=stage, event="plan.created")


def update_plan(run_dir: str | Path, plan: Mapping[str, Any], *, stage: int) -> dict:
    return _write(run_dir, plan, stage=stage, event="plan.updated")


def update_from_stage(run_dir: str | Path, stage: int, transform) -> dict | None:
    """Apply ``transform(plan)`` when a plan exists; no-op otherwise.

    Stage hooks use this so a missing plan (for example a resumed run that
    started after Stage 2) never breaks the pipeline.
    """
    plan = load_plan(run_dir)
    if plan is None:
        return None
    return update_plan(run_dir, transform(plan), stage=stage)
