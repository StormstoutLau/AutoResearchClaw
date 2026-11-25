"""Per-run in-flight LLM call limiter (G7 A7-6).

Design authority: ``spec/arc-g7-concurrency-dual-plane/DESIGN.md`` §5.

Attempt-level fairness across runs is handled by
:mod:`researchclaw.runtime.admission`; this limiter only stops a single run
from fanning out more concurrent provider calls than configured. Tokens are
files so a crashed worker cannot leak a permanent permit.
"""
from __future__ import annotations

import contextlib
import json
import os
import socket
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from researchclaw.runtime.filelock import exclusive_lock
from researchclaw.runtime.lease import is_pid_alive

TOKEN_PREFIX = "token-"
TOKEN_SUFFIX = ".json"
LOCK_NAME = "inflight.lock"
DEFAULT_TTL_SECONDS = 600


class InflightTimeout(RuntimeError):
    """All permits stayed busy for the caller's whole wait budget."""


def _now(now: datetime | None = None) -> datetime:
    return now or datetime.now(timezone.utc)


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


class InflightLimiter:
    def __init__(
        self,
        root: str | Path,
        limit: int,
        *,
        ttl: int = DEFAULT_TTL_SECONDS,
        poll: float = 0.05,
        lock_timeout: float = 10.0,
    ) -> None:
        self.root = Path(root)
        self.limit = int(limit)
        self.ttl = max(1, int(ttl))
        self.poll = max(0.001, float(poll))
        self.lock_timeout = float(lock_timeout)

    # ------------------------------------------------------------ tokens

    def _tokens(self) -> list[Path]:
        if not self.root.is_dir():
            return []
        return sorted(self.root.glob(TOKEN_PREFIX + "*" + TOKEN_SUFFIX))

    def _is_stale(self, path: Path, moment: datetime) -> bool:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            expires = _parse(str(data["expires_at"]))
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return True
        if expires <= moment:
            return True
        if str(data.get("host", "")) != socket.gethostname():
            return False
        return not is_pid_alive(int(data.get("pid", 0) or 0))

    def _prune(self, moment: datetime) -> None:
        for path in self._tokens():
            if self._is_stale(path, moment):
                try:
                    path.unlink()
                except OSError:
                    pass

    def _create(self, moment: datetime) -> Path:
        token = self.root / (
            TOKEN_PREFIX + "%d-%s" % (os.getpid(), uuid.uuid4().hex) + TOKEN_SUFFIX
        )
        payload = {
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "created_at": moment.isoformat(),
            "expires_at": (moment + timedelta(seconds=self.ttl)).isoformat(),
        }
        tmp = token.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, token)
        return token

    def active_count(self, *, now: datetime | None = None) -> int:
        moment = _now(now)
        return sum(1 for path in self._tokens()
                   if not self._is_stale(path, moment))

    # ------------------------------------------------------------ acquire

    @contextlib.contextmanager
    def slot(self, *, timeout: float = 60.0) -> Iterator[None]:
        if self.limit <= 0:
            yield
            return
        token = self._acquire(timeout)
        try:
            yield
        finally:
            try:
                token.unlink()
            except OSError:
                pass

    def _acquire(self, timeout: float) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + max(0.0, float(timeout))
        while True:
            with exclusive_lock(
                self.root / LOCK_NAME, timeout=self.lock_timeout
            ):
                moment = _now()
                self._prune(moment)
                if len(self._tokens()) < self.limit:
                    return self._create(moment)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise InflightTimeout(
                    "no in-flight permit within %.2fs (limit=%d)"
                    % (timeout, self.limit)
                )
            time.sleep(min(self.poll, remaining))
