"""Shared run-state reader.

Single source of truth for interpreting a pipeline run directory.

The pipeline writes ``checkpoint.json`` (``last_completed_stage`` /
``last_completed_name``) and ``heartbeat.json`` (ISO-8601 ``timestamp``).
Consumers such as the dashboard, the projects API and the MCP server must not
re-implement that parsing, otherwise their views drift apart.

This module is intentionally read-only: it never mutates run artifacts.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_STALE_AFTER_SEC = 300
SCHEMA_VERSION = 1


class RunStatus(str, Enum):
    """Normalised run status shared by every consumer."""

    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RunState:
    """Point-in-time view of a run directory."""

    run_id: str
    current_stage: int = 0
    current_stage_name: str = ""
    status: RunStatus = RunStatus.UNKNOWN
    topic: str = ""
    start_time: str = ""
    last_update: str = ""
    is_active: bool = False
    schema_version: int = 0
    hitl: dict[str, Any] | None = None
    artifacts: tuple[str, ...] = field(default_factory=tuple)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "current_stage": self.current_stage,
            "current_stage_name": self.current_stage_name,
            "status": self.status.value,
            "topic": self.topic,
            "start_time": self.start_time,
            "last_update": self.last_update,
            "is_active": self.is_active,
            "schema_version": self.schema_version,
            "hitl": self.hitl,
            "artifacts": list(self.artifacts),
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        logger.debug("Unreadable JSON at %s: %s", path, exc)
        return None
    return payload if isinstance(payload, dict) else None


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse ISO-8601 strings as well as epoch seconds."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                return datetime.fromtimestamp(float(text), tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


def _iso(moment: datetime | None) -> str:
    return moment.isoformat() if moment is not None else ""


def _map_status(value: Any) -> RunStatus | None:
    text = str(value or "").strip().lower()
    if text in {"done", "completed", "success", "succeeded", "finished"}:
        return RunStatus.COMPLETED
    if text in {"failed", "error", "cancelled", "canceled"}:
        return RunStatus.FAILED
    if text in {
        "blocked_approval",
        "paused",
        "rejected",
        "retrying",
        "waiting_human",
        "waiting",
    }:
        return RunStatus.PAUSED
    if text in {"running", "pending", "active", "started"}:
        return RunStatus.RUNNING
    return None


def _hitl_is_paused(hitl: Any) -> bool:
    if isinstance(hitl, str):
        return "wait" in hitl.lower() or "paus" in hitl.lower()
    if isinstance(hitl, dict):
        for key in ("state", "status", "session_state"):
            mapped = _map_status(hitl.get(key))
            if mapped is RunStatus.PAUSED:
                return True
    return False


def _read_stage_number(ckpt: dict[str, Any]) -> tuple[int, str, int]:
    """Return ``(stage, stage_name, schema_version)`` from a checkpoint payload."""
    raw_schema = ckpt.get("schema_version")
    try:
        schema_version = int(raw_schema) if raw_schema is not None else 0
    except (TypeError, ValueError):
        schema_version = 0

    raw_stage = ckpt.get("last_completed_stage")
    if raw_stage is None:
        raw_stage = ckpt.get("stage")
    try:
        stage = int(raw_stage) if raw_stage is not None else 0
    except (TypeError, ValueError):
        stage = 0

    stage_name = ckpt.get("last_completed_name") or ckpt.get("stage_name") or ""
    return stage, str(stage_name), schema_version


def _read_topic(run_dir: Path) -> str:
    config_snapshot = next(iter(sorted(run_dir.glob("config*.yaml"))), None)
    if config_snapshot is not None:
        try:
            import yaml

            payload = yaml.safe_load(config_snapshot.read_text(encoding="utf-8")) or {}
            research = payload.get("research") or {}
            project = payload.get("project") or {}
            topic = str(research.get("topic") or project.get("name") or "").strip()
            if topic:
                return topic
        except Exception as exc:  # noqa: BLE001 - snapshot is best effort
            logger.debug("Could not read config snapshot %s: %s", config_snapshot, exc)

    goal = run_dir / "stage-01" / "goal.md"
    if goal.is_file():
        try:
            for line in goal.read_text(encoding="utf-8", errors="replace").splitlines():
                cleaned = line.strip().lstrip("#").strip()
                if cleaned:
                    return cleaned
        except OSError as exc:
            logger.debug("Could not read %s: %s", goal, exc)

    return run_dir.name


def _read_start_time(run_dir: Path, checkpoint_ts: str) -> str:
    config_snapshot = next(iter(sorted(run_dir.glob("config*.yaml"))), None)
    if config_snapshot is not None:
        try:
            mtime = datetime.fromtimestamp(
                config_snapshot.stat().st_mtime, tz=timezone.utc
            )
            return mtime.isoformat()
        except OSError as exc:
            logger.debug("Could not stat %s: %s", config_snapshot, exc)
    return checkpoint_ts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def read_run_state(
    run_dir: str | Path,
    *,
    stale_after_sec: int = DEFAULT_STALE_AFTER_SEC,
    now: datetime | None = None,
) -> RunState:
    """Read a run directory into a normalised :class:`RunState`.

    Missing or corrupt files never raise; the returned state degrades to
    ``RunStatus.UNKNOWN`` with ``current_stage = 0``.
    """
    run_dir = Path(run_dir)
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)

    checkpoint = _read_json(run_dir / "checkpoint.json") or {}
    heartbeat = _read_json(run_dir / "heartbeat.json")
    summary = _read_json(run_dir / "pipeline_summary.json") or {}

    stage, stage_name, schema_version = _read_stage_number(checkpoint)
    checkpoint_ts_raw = checkpoint.get("timestamp")
    checkpoint_dt = _parse_timestamp(checkpoint_ts_raw)
    checkpoint_ts = _iso(checkpoint_dt) or (
        checkpoint_ts_raw if isinstance(checkpoint_ts_raw, str) else ""
    )

    is_active = False
    heartbeat_ts = ""
    if heartbeat:
        heartbeat_dt = _parse_timestamp(heartbeat.get("timestamp"))
        heartbeat_ts = _iso(heartbeat_dt) or str(heartbeat.get("timestamp") or "")
        if heartbeat_dt is not None:
            delta = (reference - heartbeat_dt).total_seconds()
            is_active = -stale_after_sec <= delta <= stale_after_sec

    status: RunStatus | None = _map_status(summary.get("final_status"))
    if status is None:
        status = _map_status(checkpoint.get("status"))
    if status in {RunStatus.COMPLETED, RunStatus.FAILED}:
        is_active = False
    elif is_active:
        status = RunStatus.RUNNING
    elif _hitl_is_paused(checkpoint.get("hitl")):
        status = RunStatus.PAUSED
    elif status is RunStatus.RUNNING:
        # Nothing proves the process is alive: a checkpoint alone is not enough.
        status = RunStatus.UNKNOWN
    elif status not in {RunStatus.PAUSED, RunStatus.COMPLETED, RunStatus.FAILED}:
        status = RunStatus.UNKNOWN

    try:
        artifacts = tuple(
            sorted(
                d.name for d in run_dir.iterdir() if d.is_dir() and d.name.startswith("stage-")
            )
        )
    except OSError as exc:
        logger.debug("Could not list %s: %s", run_dir, exc)
        artifacts = ()

    return RunState(
        run_id=run_dir.name,
        current_stage=stage,
        current_stage_name=stage_name,
        status=status,
        topic=_read_topic(run_dir),
        start_time=_read_start_time(run_dir, checkpoint_ts),
        last_update=heartbeat_ts or checkpoint_ts,
        is_active=is_active,
        schema_version=schema_version,
        hitl=checkpoint.get("hitl") if isinstance(checkpoint.get("hitl"), dict) else None,
        artifacts=artifacts,
    )


def read_next_stage(run_dir: str | Path) -> int | None:
    """Return the next stage number after ``current_stage`` (``None`` if done)."""
    state = read_run_state(run_dir)
    if state.current_stage <= 0:
        return None
    if state.current_stage >= 23:
        return None
    return state.current_stage + 1
