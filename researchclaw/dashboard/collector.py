"""Run data collector — scans artifacts/ for pipeline state."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from researchclaw.run_state import read_run_state

logger = logging.getLogger(__name__)

# The dashboard is a live view: a run counts as active only while its
# heartbeat keeps arriving. This is stricter than the resume-oriented
# default used by ``read_run_state``.
DASHBOARD_STALE_AFTER_SEC = 60


@dataclass
class RunSnapshot:
    """Point-in-time snapshot of a pipeline run."""

    run_id: str
    path: str
    status: str = "unknown"
    current_stage: int = 0
    current_stage_name: str = ""
    total_stages: int = 23
    start_time: str = ""
    elapsed_sec: float = 0.0
    is_active: bool = False
    topic: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    stages_completed: list[str] = field(default_factory=list)
    last_log_lines: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "path": self.path,
            "status": self.status,
            "current_stage": self.current_stage,
            "current_stage_name": self.current_stage_name,
            "total_stages": self.total_stages,
            "start_time": self.start_time,
            "elapsed_sec": round(self.elapsed_sec, 1),
            "is_active": self.is_active,
            "topic": self.topic,
            "metrics": self.metrics,
            "stages_completed": self.stages_completed,
            "error": self.error,
        }


def _elapsed_seconds(start_time: str) -> float:
    if not start_time:
        return 0.0
    try:
        started = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    delta = (datetime.now(timezone.utc) - started).total_seconds()
    return delta if delta > 0 else 0.0


class DashboardCollector:
    """Collect run state from artifacts/ directory."""

    def __init__(
        self,
        artifacts_dir: str = "artifacts",
        max_log_lines: int = 200,
    ) -> None:
        self._artifacts = Path(artifacts_dir)
        self._max_log_lines = max_log_lines

    def collect_all(self) -> list[RunSnapshot]:
        """Scan all rc-* directories and return snapshots."""
        if not self._artifacts.exists():
            return []

        runs: list[RunSnapshot] = []
        for d in sorted(self._artifacts.iterdir(), reverse=True):
            if d.is_dir() and d.name.startswith("rc-"):
                try:
                    snap = self._collect_run(d)
                    runs.append(snap)
                except Exception as exc:
                    logger.debug("Failed to collect %s: %s", d, exc)
        return runs

    def collect_run(self, run_dir: str | Path) -> RunSnapshot:
        """Collect a single run."""
        return self._collect_run(Path(run_dir))

    def _collect_run(self, run_dir: Path) -> RunSnapshot:
        state = read_run_state(run_dir, stale_after_sec=DASHBOARD_STALE_AFTER_SEC)

        snap = RunSnapshot(
            run_id=state.run_id,
            path=str(run_dir),
            status=state.status.value,
            current_stage=state.current_stage,
            current_stage_name=state.current_stage_name,
            start_time=state.start_time,
            elapsed_sec=_elapsed_seconds(state.start_time),
            is_active=state.is_active,
            topic=state.topic,
            stages_completed=list(state.artifacts),
        )

        # --- experiment metrics (results.json) ---
        for results_path in run_dir.rglob("results.json"):
            try:
                with results_path.open() as f:
                    snap.metrics = json.load(f)
                break
            except Exception:
                pass

        # --- last log lines ---
        log_path = run_dir / "pipeline.log"
        if log_path.exists():
            try:
                lines = log_path.read_text(errors="replace").splitlines()
                snap.last_log_lines = lines[-self._max_log_lines:]
            except Exception:
                pass

        return snap
