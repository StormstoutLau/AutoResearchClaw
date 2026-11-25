"""Cross-process attempt admission with a reserved HITL lane (G7 A7-6/A7-7).

Design authority: ``spec/arc-g7-concurrency-dual-plane/DESIGN.md`` §2-§4.

The registry is a single JSON document guarded by the existing advisory file
lock (P-080). It is deliberately small: this repo runs a handful of runs on
one host, so a database or a distributed lock service would add a dependency
without removing a failure mode.
"""
from __future__ import annotations

import json
import os
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from researchclaw.cost_tracker import sum_cost_log
from researchclaw.runtime.filelock import exclusive_lock
from researchclaw.runtime.lease import is_pid_alive

REGISTRY_NAME = "registry.json"
REGISTRY_LOCK = "registry.lock"
DEFAULT_TTL_SECONDS = 6 * 3600
DEFAULT_LOCK_TIMEOUT = 10.0


class AdmissionTimeout(RuntimeError):
    """No slot became available within the caller's wait budget."""


class BudgetRejected(RuntimeError):
    """The run already spent its budget; refuse to spawn another attempt."""

    def __init__(self, spent_usd: float, budget_usd: float) -> None:
        super().__init__(
            "run budget exhausted: spent=%.6f >= budget=%.6f"
            % (spent_usd, budget_usd)
        )
        self.spent_usd = spent_usd
        self.budget_usd = budget_usd


@dataclass(frozen=True)
class Slot:
    slot_id: str
    run_id: str
    owner: str
    pid: int
    slot_class: str
    acquired_at: str
    expires_at: str
    fencing: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "run_id": self.run_id,
            "owner": self.owner,
            "pid": self.pid,
            "slot_class": self.slot_class,
            "acquired_at": self.acquired_at,
            "expires_at": self.expires_at,
            "fencing": self.fencing,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Slot":
        return cls(
            slot_id=str(data["slot_id"]),
            run_id=str(data["run_id"]),
            owner=str(data.get("owner", "")),
            pid=int(data.get("pid", 0)),
            slot_class=str(data.get("slot_class", "normal")),
            acquired_at=str(data.get("acquired_at", "")),
            expires_at=str(data["expires_at"]),
            fencing=int(data.get("fencing", 0)),
        )


def default_owner() -> str:
    return "%s:%d" % (socket.gethostname(), os.getpid())


def _now(now: datetime | None = None) -> datetime:
    return now or datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _empty_state() -> dict[str, Any]:
    return {"version": 1, "fencing": 0, "slots": [], "queue": []}


class SlotRegistry:
    """Bounded attempt slots with a non-preempting reservation for HITL.

    Capacity rule: at most ``max_attempts`` slots exist. Normal runs can use
    at most ``max_attempts - hitl_priority_slots``; HITL runs can use the whole
    pool. The reservation is therefore capacity, not preemption: a long batch
    run is never killed to make room.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        max_attempts: int = 2,
        hitl_priority_slots: int = 1,
        ttl: int = DEFAULT_TTL_SECONDS,
        lock_timeout: float = DEFAULT_LOCK_TIMEOUT,
    ) -> None:
        if int(max_attempts) < 1:
            raise ValueError("max_attempts must be >= 1")
        self.root = Path(root)
        self.max_attempts = int(max_attempts)
        self.hitl_priority_slots = max(0, min(int(hitl_priority_slots),
                                             self.max_attempts))
        self.ttl = max(1, int(ttl))
        self.lock_timeout = float(lock_timeout)
        self.last_error = ""

    # ------------------------------------------------------------ paths

    @property
    def registry_path(self) -> Path:
        return self.root / REGISTRY_NAME

    @property
    def lock_path(self) -> Path:
        return self.root / REGISTRY_LOCK

    @property
    def normal_capacity(self) -> int:
        return max(0, self.max_attempts - self.hitl_priority_slots)

    # ------------------------------------------------------------ state

    def _load(self) -> dict[str, Any]:
        if not self.registry_path.is_file():
            return _empty_state()
        try:
            data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.last_error = "corrupt_registry"
            return _empty_state()
        if not isinstance(data, dict):
            self.last_error = "corrupt_registry"
            return _empty_state()
        state = _empty_state()
        state["fencing"] = int(data.get("fencing", 0) or 0)
        state["slots"] = [
            row for row in data.get("slots") or [] if isinstance(row, dict)
        ]
        state["queue"] = [
            row for row in data.get("queue") or [] if isinstance(row, dict)
        ]
        return state

    def _save(self, state: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.registry_path
        tmp = target.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)

    # ------------------------------------------------------------ helpers

    def _is_stale(self, row: dict[str, Any], moment: datetime) -> bool:
        try:
            expires = _parse(str(row["expires_at"]))
        except (KeyError, TypeError, ValueError):
            return True
        if expires <= moment:
            return True
        owner = str(row.get("owner", ""))
        host = owner.rsplit(":", 1)[0] if ":" in owner else owner
        if host != socket.gethostname():
            return False  # cross-host: trust the TTL only
        return not is_pid_alive(int(row.get("pid", 0) or 0))

    @staticmethod
    def _upsert_queue(
        state: dict[str, Any], run_id: str, slot_class: str, moment: datetime
    ) -> None:
        if any(row.get("run_id") == run_id for row in state["queue"]):
            return
        state["queue"].append({
            "run_id": run_id,
            "slot_class": slot_class,
            "priority": 0 if slot_class == "hitl" else 1,
            "queued_at": _iso(moment),
        })

    # ------------------------------------------------------------ acquire

    def try_acquire(
        self,
        run_id: str,
        *,
        slot_class: str = "normal",
        owner: str | None = None,
        now: datetime | None = None,
    ) -> Slot | None:
        """One non-blocking attempt. Returns ``None`` when capacity is full."""
        if slot_class not in ("normal", "hitl"):
            raise ValueError("slot_class must be 'normal' or 'hitl'")
        moment = _now(now)
        me = owner or default_owner()
        with exclusive_lock(self.lock_path, timeout=self.lock_timeout):
            state = self._load()
            state["slots"] = [
                row for row in state["slots"]
                if not self._is_stale(row, moment)
            ]
            held = next(
                (row for row in state["slots"] if row.get("run_id") == run_id),
                None,
            )
            if held is not None:
                held["expires_at"] = _iso(moment + timedelta(seconds=self.ttl))
                self._save(state)
                return Slot.from_dict(held)

            normal = sum(1 for row in state["slots"]
                         if row.get("slot_class") != "hitl")
            hitl = sum(1 for row in state["slots"]
                       if row.get("slot_class") == "hitl")
            total = normal + hitl
            allowed = total < self.max_attempts and (
                hitl < self.max_attempts
                if slot_class == "hitl"
                else normal < self.normal_capacity
            )
            if not allowed:
                self._upsert_queue(state, run_id, slot_class, moment)
                self._save(state)
                return None

            state["fencing"] = int(state.get("fencing", 0)) + 1
            fencing = state["fencing"]
            row = Slot(
                slot_id="s%d" % fencing,
                run_id=run_id,
                owner=me,
                pid=os.getpid(),
                slot_class=slot_class,
                acquired_at=_iso(moment),
                expires_at=_iso(moment + timedelta(seconds=self.ttl)),
                fencing=fencing,
            ).to_dict()
            state["slots"].append(row)
            state["queue"] = [
                item for item in state["queue"]
                if item.get("run_id") != run_id
            ]
            self._save(state)
            return Slot.from_dict(row)

    def acquire(
        self,
        run_id: str,
        *,
        slot_class: str = "normal",
        owner: str | None = None,
        timeout: float = 0.0,
        poll: float = 0.05,
        now: datetime | None = None,
    ) -> Slot:
        """Block up to ``timeout`` seconds, then raise :class:`AdmissionTimeout`."""
        deadline = time.monotonic() + max(0.0, float(timeout))
        while True:
            slot = self.try_acquire(
                run_id, slot_class=slot_class, owner=owner, now=now
            )
            if slot is not None:
                return slot
            if now is not None:
                raise AdmissionTimeout(
                    "no %s slot available for %s" % (slot_class, run_id)
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AdmissionTimeout(
                    "no %s slot available for %s within %.2fs"
                    % (slot_class, run_id, timeout)
                )
            time.sleep(min(max(0.001, float(poll)), remaining))

    def release(self, slot: Slot) -> bool:
        """Release our own slot; a stale/taken-over token is a no-op."""
        with exclusive_lock(self.lock_path, timeout=self.lock_timeout):
            state = self._load()
            kept = [
                row for row in state["slots"]
                if not (
                    row.get("slot_id") == slot.slot_id
                    and int(row.get("fencing", -1)) == slot.fencing
                )
            ]
            if len(kept) == len(state["slots"]):
                return False
            state["slots"] = kept
            self._save(state)
            return True

    # ------------------------------------------------------------ view

    def snapshot(self, *, now: datetime | None = None) -> dict[str, Any]:
        moment = _now(now)
        state = self._load()
        slots = [
            row for row in state["slots"] if not self._is_stale(row, moment)
        ]
        by_class = {"normal": 0, "hitl": 0}
        for row in slots:
            key = "hitl" if row.get("slot_class") == "hitl" else "normal"
            by_class[key] += 1
        return {
            "max_attempts": self.max_attempts,
            "hitl_priority_slots": self.hitl_priority_slots,
            "normal_capacity": self.normal_capacity,
            "active": len(slots),
            "by_class": by_class,
            "fencing": int(state.get("fencing", 0) or 0),
            "slots": slots,
            "queue": list(state.get("queue") or []),
        }


def preflight_budget(run_dir: str | Path, budget_usd: float) -> dict[str, Any]:
    """Reject a run at admission time when its cost log is already exhausted.

    ``budget_usd <= 0`` disables the check. Spending exactly the budget counts
    as exhausted, mirroring :meth:`CostTracker.check_budget`.
    """
    budget = float(budget_usd or 0.0)
    if budget <= 0:
        return {"ok": True, "budget_usd": 0.0, "spent_usd": 0.0}
    spent, _tokens, _lines = sum_cost_log(Path(run_dir))
    if spent >= budget:
        raise BudgetRejected(spent, budget)
    return {"ok": True, "budget_usd": budget, "spent_usd": spent}
