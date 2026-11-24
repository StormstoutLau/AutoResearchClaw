"""Soak driver: process restarts, progress-gated injection, convergence (P-160).

Design authority: ``spec/arc-g7-soak/DESIGN.md`` §4.1.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from researchclaw.runtime.lease import (
    is_expired,
    is_pid_alive,
    read_lease,
    release,
)
from researchclaw.runtime.supervisor import full_jitter
from researchclaw.soak.verifier import RunVerification, verify_run

FIELD_WALL_SECONDS = 72 * 3600
MIN_FIELD_RESTARTS = 3
_SIGKILL = getattr(signal, "SIGKILL", 9)


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class SoakConfig:
    run_dir: Path
    worker_cmd: tuple[str, ...]
    duration_seconds: float = 72 * 3600
    max_restarts: int = 3
    inject_at_stages: tuple[int, ...] = ()
    poll_seconds: float = 5.0
    min_restart_interval_seconds: float = 10.0
    worker_exit_timeout_seconds: float = 30.0
    lease_clear_timeout_seconds: float = 10.0
    worker_cwd: Path | None = None
    reference_run_dir: Path | None = None
    config_path: str | None = None


@dataclass(frozen=True)
class RestartRecord:
    reason: str
    at: str
    exit_code: int | None
    stage_before: int
    stage_after: int | None
    recovery_seconds: float | None


@dataclass
class SoakResult:
    status: str
    restarts: list[RestartRecord]
    verification: RunVerification
    wall_seconds: float
    field_run_satisfied: bool
    session: list[dict] = field(default_factory=list)


def _spawn_kwargs(os_name: str | None = None) -> dict[str, bool]:
    """POSIX children start their own session so their whole tree is killable."""
    return {} if (os_name or os.name) == "nt" else {"start_new_session": True}


def _posix_kill_tree(proc, *, getpgid=None, killpg=None, kill=None) -> str:
    """Kill a POSIX child's process group only when it is the group leader.

    A custom ``spawn`` may not have created a new session; in that case the
    child's pgid equals the driver's and ``killpg`` would kill the driver, so
    we fall back to a single-process kill.
    """
    getpgid = getpgid or os.getpgid
    killpg = killpg or os.killpg
    kill = kill or proc.kill
    try:
        pgid = getpgid(proc.pid)
    except OSError:
        kill()
        return "process"
    if pgid == proc.pid:
        try:
            killpg(pgid, _SIGKILL)
            return "group"
        except OSError:
            pass
    kill()
    return "process"


def _default_spawn(cmd, **kwargs):
    return subprocess.Popen(cmd, **{**_spawn_kwargs(), **kwargs})


def _default_kill(proc) -> None:
    """Hard kill; never a graceful shutdown (Windows terminate == TerminateProcess)."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True, check=False,
        )
    else:
        _posix_kill_tree(proc)


class SoakDriver:
    def __init__(
        self,
        config: SoakConfig,
        *,
        spawn: Callable | None = None,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
        kill: Callable[[object], None] | None = None,
    ) -> None:
        self.config = config
        self._spawn = spawn or _default_spawn
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._kill = kill or _default_kill
        self.session: list[dict] = []

    # ------------------------------------------------------------ logging

    def _record(self, event: str, **fields) -> None:
        row = {"ts": _iso(), "event": event, **fields}
        self.session.append(row)
        try:
            with (self.config.run_dir / "soak_session.jsonl").open(
                    "a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
        except OSError:
            pass

    # ------------------------------------------------------------ state

    def _progress(self) -> int:
        """Return the checkpoint stage; never raises."""
        path = self.config.run_dir / "checkpoint.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return int(data.get("last_completed_stage") or 0)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return 0

    def _reclaim_stale_lease(self) -> bool:
        """Release only a lease whose owner is provably dead or expired."""
        deadline = self._clock() + self.config.lease_clear_timeout_seconds
        while True:
            lease = read_lease(self.config.run_dir)
            if lease is None or lease.released:
                return True
            if is_expired(lease) or not is_pid_alive(lease.pid):
                release(self.config.run_dir, lease)
                self._record("stale_lease_released", pid=lease.pid,
                             fencing=lease.fencing)
                return True
            if self._clock() >= deadline:
                self._record("lease_held", pid=lease.pid, owner=lease.owner)
                return False
            self._sleep(0.05)

    # ------------------------------------------------------------ process

    def _spawn_worker(self):
        run_dir = self.config.run_dir
        out_path = run_dir / "soak_worker.out.log"
        err_path = run_dir / "soak_worker.err.log"
        with out_path.open("ab") as out, err_path.open("ab") as err:
            return self._spawn(
                list(self.config.worker_cmd),
                cwd=str(self.config.worker_cwd or Path.cwd()),
                stdout=out,
                stderr=err,
            )

    def _terminate(self, proc) -> int | None:
        try:
            self._kill(proc)
        except Exception:  # noqa: BLE001 - kill is best effort, wait is the proof
            pass
        try:
            return int(proc.wait(timeout=self.config.worker_exit_timeout_seconds))
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass
            try:
                return int(proc.wait(timeout=1.0))
            except Exception:  # noqa: BLE001
                return None

    # ------------------------------------------------------------ loop

    def run(self) -> SoakResult:
        cfg = self.config
        started = self._clock()
        if not cfg.run_dir.is_dir():
            self._record("driver_finished", status="failed",
                         reason="no_resumable_run")
            return self._finish(started, "failed", [])
        self._record(
            "driver_started",
            run_id=cfg.run_dir.name,
            config={
                "duration_seconds": cfg.duration_seconds,
                "max_restarts": cfg.max_restarts,
                "inject_at_stages": list(cfg.inject_at_stages),
                "poll_seconds": cfg.poll_seconds,
                "reference_run_dir": str(cfg.reference_run_dir)
                if cfg.reference_run_dir else None,
            },
        )

        if not self._reclaim_stale_lease():
            self._record("driver_finished", status="failed", reason="lease_held")
            return self._finish(started, "failed", [])

        restart_rows: list[dict] = []
        pending_recovery: int | None = None
        injected_targets: set[int] = set()
        last_injection_stage = -1
        last_restart_at = -1e9
        capped = False
        status = "failed"
        attempt = 0

        def note_progress(stage: int) -> None:
            nonlocal pending_recovery
            if pending_recovery is None:
                return
            row = restart_rows[pending_recovery]
            if stage > int(row["stage_before"]):
                row["stage_after"] = stage
                row["recovery_seconds"] = max(0.0, self._clock() - row["killed_at"])
                pending_recovery = None

        while True:
            wall = self._clock() - started
            if wall >= cfg.duration_seconds:
                status = "timed_out"
                self._record("duration_reached", wall_seconds=round(wall, 3))
                break

            attempt += 1
            if not self._reclaim_stale_lease():
                status = "failed"
                break
            try:
                proc = self._spawn_worker()
            except OSError as exc:
                self._record("worker_spawn_failed", error=str(exc))
                status = "failed"
                break
            stage = self._progress()
            self._record("worker_started", pid=getattr(proc, "pid", None),
                         attempt=attempt, stage=stage)

            action = "exit"
            while True:
                wall = self._clock() - started
                if wall >= cfg.duration_seconds:
                    rc = self._terminate(proc)
                    self._record("worker_exited", rc=rc, reason="duration")
                    status = "timed_out"
                    action = "duration"
                    break

                rc = proc.poll()
                if rc is not None:
                    self._record("worker_exited", rc=int(rc),
                                 reason="exit", stage=stage)
                    if int(rc) == 0:
                        status = "passed"
                    elif int(rc) == 75 and len(restart_rows) < cfg.max_restarts:
                        delay = full_jitter(len(restart_rows) + 1)
                        self._record("restart_scheduled", rc=int(rc),
                                     delay=round(delay, 3))
                        self._sleep(delay)
                        restart_rows.append({
                            "reason": "retryable_exit",
                            "at": _iso(),
                            "exit_code": int(rc),
                            "stage_before": stage,
                            "stage_after": None,
                            "recovery_seconds": None,
                            "killed_at": self._clock(),
                        })
                        pending_recovery = len(restart_rows) - 1
                        last_restart_at = self._clock()
                        action = "retryable"
                    elif int(rc) == 75:
                        status = "restarts_exhausted"
                        action = "exit"
                    else:
                        status = "failed"
                        action = "exit"
                    break

                stage = self._progress()
                note_progress(stage)

                pending = sorted(s for s in cfg.inject_at_stages
                                 if s not in injected_targets and s <= stage)
                if pending and stage > last_injection_stage:
                    target = pending[0]
                    if len(restart_rows) >= cfg.max_restarts:
                        if not capped:
                            capped = True
                            self._record("restart_capped",
                                         pending=list(pending),
                                         observed=len(restart_rows))
                    elif (self._clock() - last_restart_at
                          >= cfg.min_restart_interval_seconds):
                        injected_targets.add(target)
                        last_injection_stage = stage
                        killed_at = self._clock()
                        self._record("restart_injected", target_stage=target,
                                     stage_before=stage)
                        rc = self._terminate(proc)
                        if rc is None:
                            self._record("kill_failed", pid=getattr(proc, "pid", None))
                            status = "failed"
                            action = "exit"
                            break
                        self._record("worker_exited", rc=rc, reason="injected",
                                     stage=stage)
                        restart_rows.append({
                            "reason": "injected",
                            "at": _iso(),
                            "exit_code": rc,
                            "stage_before": stage,
                            "stage_after": None,
                            "recovery_seconds": None,
                            "killed_at": killed_at,
                        })
                        pending_recovery = len(restart_rows) - 1
                        last_restart_at = self._clock()
                        if not self._reclaim_stale_lease():
                            status = "failed"
                            action = "exit"
                            break
                        action = "injected"
                        break

                self._sleep(cfg.poll_seconds)

            if action in {"injected", "retryable"}:
                continue
            if action == "duration":
                status = "timed_out"
            break

        wall = self._clock() - started
        return self._finish(started, status, restart_rows)

    def _finish(self, started: float, status: str,
                restart_rows: list[dict]) -> SoakResult:
        cfg = self.config
        verification = verify_run(
            cfg.run_dir,
            reference_run_dir=cfg.reference_run_dir,
        )
        if status == "passed" and not (verification.ok and verification.converged):
            status = "failed"
            self._record("verification_failed", problems=list(verification.problems),
                         converged=verification.converged)

        wall = self._clock() - started
        restarts = [
            RestartRecord(
                reason=str(row["reason"]),
                at=str(row["at"]),
                exit_code=row.get("exit_code"),
                stage_before=int(row["stage_before"]),
                stage_after=row.get("stage_after"),
                recovery_seconds=row.get("recovery_seconds"),
            )
            for row in restart_rows
        ]
        field_satisfied = bool(
            wall >= FIELD_WALL_SECONDS and len(restarts) >= MIN_FIELD_RESTARTS)
        self._record("driver_finished", status=status,
                     wall_seconds=round(wall, 3),
                     restarts=len(restarts))
        return SoakResult(
            status=status,
            restarts=restarts,
            verification=verification,
            wall_seconds=wall,
            field_run_satisfied=field_satisfied,
            session=list(self.session),
        )
