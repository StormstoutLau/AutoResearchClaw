"""Single-run lease with fencing tokens (G1a / A1-4).

Design authority: ``spec/arc-g1-readiness-research/DESIGN.md`` §4 and
``spec/arc-q5-decision-method/RESEARCH.md`` §8 (K-2).

Rules
-----
- One writer per run: ``acquire`` fails with :class:`LeaseBusy` when a live
  lease is held by another owner.
- The same owner may re-acquire (idempotent resume) without bumping fencing.
- Every acquisition by a *different* owner increments ``fencing``; writers
  reject events whose token is lower than the highest one seen.
- An expired lease may be taken over, but only with a higher fencing token.
"""
from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

LEASE_NAME = "lease.json"
LOCK_NAME = "lease.lock"
DEFAULT_TTL_SECONDS = 300


class LeaseBusy(RuntimeError):
    """Another live owner holds the lease."""


class LeaseLost(RuntimeError):
    """The lease is missing, expired, or owned by somebody else."""


@dataclass(frozen=True)
class Lease:
    owner: str
    pid: int
    acquired_at: str
    expires_at: str
    fencing: int
    released: bool = False

    def to_dict(self) -> dict:
        return {
            "owner": self.owner,
            "pid": self.pid,
            "acquired_at": self.acquired_at,
            "expires_at": self.expires_at,
            "fencing": self.fencing,
            "released": self.released,
        }


def default_owner() -> str:
    return "%s:%d" % (socket.gethostname(), os.getpid())


def _path(run_dir: str | Path) -> Path:
    return Path(run_dir) / LEASE_NAME


def _now(now: datetime | None = None) -> datetime:
    return now or datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def read_lease(run_dir: str | Path) -> Lease | None:
    p = _path(run_dir)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    try:
        return Lease(
            owner=str(data["owner"]),
            pid=int(data.get("pid", 0)),
            acquired_at=str(data.get("acquired_at", "")),
            expires_at=str(data["expires_at"]),
            fencing=int(data.get("fencing", 0)),
            released=bool(data.get("released", False)),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _write(run_dir: Path, lease: Lease) -> None:
    target = _path(run_dir)
    tmp = target.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(lease.to_dict(), indent=2, ensure_ascii=False))
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, target)


def is_expired(lease: Lease, *, now: datetime | None = None) -> bool:
    try:
        return _parse(lease.expires_at) <= _now(now)
    except ValueError:
        return True


def acquire(
    run_dir: str | Path,
    *,
    owner: str | None = None,
    ttl: int = DEFAULT_TTL_SECONDS,
    now: datetime | None = None,
) -> Lease:
    """Acquire or renew the run lease. Raises :class:`LeaseBusy` on conflict."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    me = owner or default_owner()
    lock = run_dir / LOCK_NAME
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        # A stale lock left by a crashed process must not deadlock the run.
        try:
            age = _now(now).timestamp() - lock.stat().st_mtime
        except OSError:
            age = ttl + 1
        if age <= ttl:
            raise LeaseBusy("lease lock is held by another process")
        try:
            lock.unlink()
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except (OSError, FileExistsError) as exc:
            raise LeaseBusy("could not take the lease lock") from exc

    try:
        os.write(fd, me.encode("utf-8"))
        os.close(fd)
        current = read_lease(run_dir)
        moment = _now(now)
        if current is not None and not current.released and not is_expired(current, now=moment):
            if current.owner == me:
                lease = Lease(
                    owner=me, pid=os.getpid(),
                    acquired_at=current.acquired_at,
                    expires_at=_iso(moment + timedelta(seconds=ttl)),
                    fencing=current.fencing,
                )
                _write(run_dir, lease)
                return lease
            raise LeaseBusy("run is leased by %s until %s"
                            % (current.owner, current.expires_at))
        # Free (missing / released / expired): monotonic fencing across holders.
        fencing = (current.fencing if current is not None else 0) + 1
        lease = Lease(
            owner=me, pid=os.getpid(),
            acquired_at=_iso(moment),
            expires_at=_iso(moment + timedelta(seconds=ttl)),
            fencing=fencing,
        )
        _write(run_dir, lease)
        return lease
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


def renew(
    run_dir: str | Path,
    lease: Lease,
    *,
    ttl: int = DEFAULT_TTL_SECONDS,
    now: datetime | None = None,
) -> Lease:
    """Extend a lease. Raises :class:`LeaseLost` if we no longer own it."""
    current = read_lease(run_dir)
    if current is None or current.owner != lease.owner or current.fencing != lease.fencing:
        raise LeaseLost("lease is no longer owned by %s" % lease.owner)
    moment = _now(now)
    updated = Lease(
        owner=lease.owner, pid=lease.pid,
        acquired_at=lease.acquired_at,
        expires_at=_iso(moment + timedelta(seconds=ttl)),
        fencing=lease.fencing,
    )
    _write(Path(run_dir), updated)
    return updated


def release(run_dir: str | Path, lease: Lease) -> None:
    """Mark the lease released if we still own it (best effort, never raises).

    The record is kept (with ``released: true``) so ``fencing`` stays monotonic
    across holders — deleting it would let the next owner restart at 1.
    """
    current = read_lease(run_dir)
    if current is None or current.owner != lease.owner or current.fencing != lease.fencing:
        return
    try:
        _write(Path(run_dir), Lease(
            owner=lease.owner, pid=lease.pid,
            acquired_at=lease.acquired_at,
            expires_at=_iso(_now()),
            fencing=lease.fencing,
            released=True,
        ))
    except OSError:
        pass


def check_fencing(lease: Lease, seen_max: int) -> bool:
    """Writers must reject tokens lower than the highest already observed."""
    return lease.fencing >= seen_max
