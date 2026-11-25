"""G7 A7-6: per-run in-flight LLM call limiter."""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from researchclaw.llm.inflight import InflightLimiter, InflightTimeout


def _run_limit(limiter: InflightLimiter, peak: list[int], lock: threading.Lock) -> None:
    current = [0]

    def work() -> None:
        with limiter.slot(timeout=5.0):
            with lock:
                current[0] += 1
                peak[0] = max(peak[0], current[0])
            time.sleep(0.05)
            with lock:
                current[0] -= 1

    threads = [threading.Thread(target=work) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def test_limit_is_never_exceeded(tmp_path: Path) -> None:
    limiter = InflightLimiter(tmp_path, 2, poll=0.01)
    peak = [0]
    lock = threading.Lock()

    _run_limit(limiter, peak, lock)

    assert peak[0] <= 2
    assert limiter.active_count() == 0


def test_zero_limit_is_a_noop(tmp_path: Path) -> None:
    limiter = InflightLimiter(tmp_path, 0)

    with limiter.slot(timeout=0):
        pass

    assert limiter.active_count() == 0


def test_timeout_when_all_tokens_are_held(tmp_path: Path) -> None:
    limiter = InflightLimiter(tmp_path, 1, poll=0.01)

    with limiter.slot(timeout=0):
        with pytest.raises(InflightTimeout):
            with limiter.slot(timeout=0.05):
                pass


def test_expired_token_is_pruned(tmp_path: Path) -> None:
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    token = {
        "pid": 999_999,
        "host": os.uname().nodename if hasattr(os, "uname") else "",
        "expires_at": past.isoformat(),
    }
    (tmp_path / "token-dead.json").write_text(json.dumps(token), encoding="utf-8")

    limiter = InflightLimiter(tmp_path, 1, ttl=600)

    with limiter.slot(timeout=0):
        assert limiter.active_count() == 1
    assert limiter.active_count() == 0
