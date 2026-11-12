"""P-080: cross-platform advisory file lock."""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from researchclaw.runtime.filelock import LockTimeout, exclusive_lock


def test_exclusive_lock_serialises_threads(tmp_path: Path) -> None:
    counter = tmp_path / "counter.txt"
    counter.write_text("0", encoding="utf-8")
    errors: list[str] = []

    def worker() -> None:
        try:
            for _ in range(50):
                with exclusive_lock(tmp_path / "lock", timeout=10.0):
                    value = int(counter.read_text(encoding="utf-8"))
                    time.sleep(0)
                    counter.write_text(str(value + 1), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert counter.read_text(encoding="utf-8") == "1000"


def test_filelock_times_out_when_held(tmp_path: Path) -> None:
    lock_path = tmp_path / "lock"
    ready = threading.Event()
    release = threading.Event()

    def holder() -> None:
        with exclusive_lock(lock_path, timeout=5.0):
            ready.set()
            release.wait(5.0)

    thread = threading.Thread(target=holder)
    thread.start()
    assert ready.wait(5.0)
    try:
        with pytest.raises(LockTimeout):
            with exclusive_lock(lock_path, timeout=0.2, poll=0.01):
                pass
    finally:
        release.set()
        thread.join(5.0)


def test_filelock_releases_on_exception(tmp_path: Path) -> None:
    lock_path = tmp_path / "lock"
    with pytest.raises(RuntimeError):
        with exclusive_lock(lock_path, timeout=1.0):
            raise RuntimeError("boom")
    with exclusive_lock(lock_path, timeout=1.0):
        pass


def test_filelock_reentrant_across_instances(tmp_path: Path) -> None:
    lock_path = tmp_path / "nested" / "lock"
    with exclusive_lock(lock_path, timeout=1.0):
        pass
    assert lock_path.parent.is_dir()
