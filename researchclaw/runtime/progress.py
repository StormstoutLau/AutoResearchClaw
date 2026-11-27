"""In-stage progress heartbeat (B-31b).

``heartbeat.json`` used to be written only after a stage finished, so a run
inside a long stage looked identical to a dead one.  :class:`ProgressKeeper`
writes the same file on a fixed cadence while the stage is running and adds
the last completed sub-step from ``steps.jsonl`` (the B-33 ledger), so readers
can tell *where* the stage is without parsing logs.

Invariants
----------
I-1  The heartbeat is a projection: ``steps.jsonl`` / artifacts stay the truth.
I-2  Writes are atomic (temp file + replace) and best-effort; a failed write
     must never break the stage.
I-3  Payloads carry no prompts or generated code.
I-4  ``timestamp`` is kept for old readers; ``updated_at`` is the new name.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

HEARTBEAT_NAME = "heartbeat.json"
DEFAULT_INTERVAL_SEC = 30.0
MIN_STALE_AFTER_SEC = 300.0

# Progress-only view: step_id -> phase shown in the heartbeat.
_PHASE_BY_STEP = {
    "blueprint": "blueprint",
    "generate_file": "generate",
    "entrypoint": "entrypoint",
    "hard_validation": "validate",
    "alignment": "alignment",
    "review": "review",
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _replace_with_retry(tmp: Path, target: Path, attempts: int = 5) -> None:
    """``os.replace`` with a short retry for Windows sharing violations."""
    for index in range(attempts):
        try:
            os.replace(tmp, target)
            return
        except PermissionError:
            if index == attempts - 1:
                raise
            time.sleep(0.05 * (index + 1))


def _atomic_write_json(target: Path, payload: dict[str, Any]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=target.parent, suffix=".tmp", prefix="heartbeat_",
    )
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        tmp.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        _replace_with_retry(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def read_last_step(stage_dir: str | Path) -> dict[str, Any]:
    """Return the last parseable ``steps.jsonl`` row (``{}`` when absent)."""
    path = Path(stage_dir) / "steps.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        return row if isinstance(row, dict) else {}
    return {}


def count_steps(stage_dir: str | Path) -> int:
    """Number of parseable journal rows (progress counter only)."""
    path = Path(stage_dir) / "steps.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    return sum(1 for line in lines if line.strip())


class ProgressKeeper:
    """Write ``heartbeat.json`` while a stage runs.

    Parameters
    ----------
    run_dir:
        Run directory that owns ``heartbeat.json``.
    run_id / stage / stage_name:
        Identity of the run and the stage being executed.
    stage_dir:
        Stage directory whose ``steps.jsonl`` is projected into the heartbeat.
        Defaults to ``run_dir / stage-<NN>``.
    interval:
        Seconds between writes.  The first write happens in :meth:`start`.
    stale_after:
        Hint stored in the payload; readers compute their own threshold.
    """

    def __init__(
        self,
        run_dir: str | Path,
        run_id: str,
        stage: Any,
        stage_name: str,
        *,
        stage_dir: str | Path | None = None,
        interval: float = DEFAULT_INTERVAL_SEC,
        stale_after: float | None = None,
    ) -> None:
        self.run_dir = Path(run_dir)
        self.run_id = run_id
        self.stage = int(stage)
        self.stage_name = stage_name
        self.stage_dir = (
            Path(stage_dir) if stage_dir is not None
            else self.run_dir / f"stage-{self.stage:02d}"
        )
        self.interval = float(interval) if interval else DEFAULT_INTERVAL_SEC
        self.stale_after = float(
            stale_after if stale_after is not None
            else max(3.0 * self.interval, MIN_STALE_AFTER_SEC)
        )
        self.started_at = _utcnow_iso()
        self._state_lock = threading.Lock()
        self._state: dict[str, Any] = {}
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="progress-keeper",
        )
        self._journal_signature: tuple[int, int] | None = None
        self._last_step: dict[str, Any] = {}
        self._steps_done = 0

    # ── public API ───────────────────────────────────────────────────────

    def start(self) -> "ProgressKeeper":
        self._write()
        self._thread.start()
        return self

    def update(self, **fields: Any) -> None:
        """Merge extra fields (``phase`` / ``step_id`` / …) into the payload."""
        with self._state_lock:
            self._state.update(fields)

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)

    # ── internals ────────────────────────────────────────────────────────

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            self._write()

    def _refresh_journal(self) -> None:
        path = self.stage_dir / "steps.jsonl"
        try:
            stat = path.stat()
        except OSError:
            return
        signature = (stat.st_mtime_ns, stat.st_size)
        if signature == self._journal_signature:
            return
        self._journal_signature = signature
        self._last_step = read_last_step(self.stage_dir)
        self._steps_done = count_steps(self.stage_dir)

    def _write(self) -> None:
        try:
            self._refresh_journal()
            with self._state_lock:
                state = dict(self._state)
            last_step = self._last_step
            step_id = str(last_step.get("step_id") or "")
            variant = str(last_step.get("variant") or "")
            phase = (
                str(state.get("phase") or "")
                or _PHASE_BY_STEP.get(step_id, "")
            )
            now = _utcnow_iso()
            payload: dict[str, Any] = {
                "pid": os.getpid(),
                "run_id": self.run_id,
                "stage": self.stage,
                "stage_name": self.stage_name,
                "status": str(state.get("status") or "running"),
                "stage_started_at": self.started_at,
                "phase": phase,
                "last_step": f"{step_id}:{variant}" if step_id else "",
                "last_step_status": str(last_step.get("status") or ""),
                "last_step_ts": str(last_step.get("ts") or ""),
                "steps_done": self._steps_done,
                "updated_at": now,
                "timestamp": now,
                "interval_sec": self.interval,
                "stale_after_sec": self.stale_after,
                # Older readers use these two fields for the stage label.
                "last_stage": self.stage,
                "last_stage_name": self.stage_name,
            }
            payload.update(state)
            _atomic_write_json(self.run_dir / HEARTBEAT_NAME, payload)
        except Exception as exc:  # noqa: BLE001 - observability must not break a run
            logger.debug("progress heartbeat write failed: %s", exc)
