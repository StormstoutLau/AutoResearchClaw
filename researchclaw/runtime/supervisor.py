"""Process supervisor with a classified exit-code contract (G1b / A1-3, A1-7).

The supervisor never holds the run lease — the lease means "who writes
events", and that is the worker (P-030 R-2). It only spawns, waits,
classifies, backs off, and enforces a retry budget.
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from researchclaw.runtime.exit_codes import RETRYABLE, is_retryable
from researchclaw.runtime.lease import is_expired, read_lease, release

DEFAULT_MAX_RESTARTS = 5
DEFAULT_MAX_WALL_SECONDS = 1800
DEFAULT_BASE_DELAY = 2.0
DEFAULT_CAP_DELAY = 300.0
STABLE_RESET_SECONDS = 600.0


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def full_jitter(attempt: int, base: float = DEFAULT_BASE_DELAY,
                cap: float = DEFAULT_CAP_DELAY) -> float:
    """AWS full jitter: uniform(0, min(cap, base * 2**attempt))."""
    ceiling = min(cap, base * (2 ** max(0, attempt)))
    return random.uniform(0.0, ceiling)


@dataclass
class SupervisorResult:
    exit_code: int
    restarts: int
    elapsed: float
    exhausted: bool = False
    history: list[dict] = field(default_factory=list)


class Supervisor:
    def __init__(
        self,
        run_id: str,
        run_dir: str | Path,
        worker_cmd: list[str],
        *,
        max_restarts: int = DEFAULT_MAX_RESTARTS,
        max_wall_seconds: float = DEFAULT_MAX_WALL_SECONDS,
        base_delay: float = DEFAULT_BASE_DELAY,
        cap_delay: float = DEFAULT_CAP_DELAY,
        sleep=None,
        spawn=None,
    ) -> None:
        self.run_id = run_id
        self.run_dir = Path(run_dir)
        self.worker_cmd = list(worker_cmd)
        self.max_restarts = max_restarts
        self.max_wall_seconds = max_wall_seconds
        self.base_delay = base_delay
        self.cap_delay = cap_delay
        self._sleep = sleep or time.sleep
        self._spawn = spawn or subprocess.Popen
        self.history: list[dict] = []

    # ------------------------------------------------------------ helpers

    def _log(self, record: dict) -> None:
        """Supervisor log is separate from events.jsonl (no lease/fencing)."""
        try:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            with (self.run_dir / "supervisor.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": _iso(), **record}, ensure_ascii=False) + "\n")
                fh.flush()
        except OSError:
            pass
        self.history.append(record)

    def _clear_stale_lease(self) -> None:
        """Release only leases that are already expired (never a live worker)."""
        lease = read_lease(self.run_dir)
        if lease is None or lease.released:
            return
        if is_expired(lease):
            release(self.run_dir, lease)
            self._log({"event": "stale_lease_released", "fencing": lease.fencing})

    def _run_once(self) -> int:
        proc = self._spawn(self.worker_cmd, cwd=str(self.run_dir.parent)
                           if self.run_dir.parent.exists() else None)
        return int(proc.wait())

    # ------------------------------------------------------------ loop

    def run(self) -> SupervisorResult:
        started = time.monotonic()
        restarts = 0
        last_rc = 0
        while True:
            self._clear_stale_lease()
            rc = self._run_once()
            last_rc = rc
            elapsed = time.monotonic() - started
            self._log({"event": "worker_exit", "rc": rc, "restarts": restarts,
                       "elapsed": round(elapsed, 1)})
            if rc == 0:
                self._log({"event": "supervisor_done", "rc": 0})
                return SupervisorResult(0, restarts, elapsed, False, self.history)
            if not is_retryable(rc):
                # 85 = normal pause, 65/77/78 = terminal failures.
                self._log({"event": "supervisor_stop", "rc": rc})
                return SupervisorResult(rc, restarts, elapsed, False, self.history)

            restarts += 1
            if restarts > self.max_restarts or elapsed > self.max_wall_seconds:
                self._log({"event": "supervisor_exhausted", "rc": rc,
                           "restarts": restarts})
                return SupervisorResult(rc, restarts, elapsed, True, self.history)

            delay = full_jitter(restarts, self.base_delay, self.cap_delay)
            self._log({"event": "restart_scheduled", "rc": rc,
                       "attempt": restarts, "delay": round(delay, 2)})
            self._sleep(delay)


def default_worker_cmd(run_dir: str | Path, config: str | None = None,
                       extra: list[str] | None = None) -> list[str]:
    cmd = [sys.executable, "-m", "researchclaw", "run", "--resume",
           "--output", str(run_dir)]
    if config:
        cmd += ["--config", config]
    cmd += list(extra or [])
    return cmd
