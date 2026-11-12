"""Cross-platform advisory file lock (G3 fix batch, P-080).

Design authority: ``spec/arc-g3-fix-batch/DESIGN.md`` §2.

The lock is **advisory**: it only serialises writers that use this helper.
It exists because artifact registration and stage-event appends are
read-modify-write sequences that lose data when two writers interleave
(P-077 D-1: 150/150 rounds lost a node).
"""
from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path
from typing import Iterator


class LockTimeout(RuntimeError):
    """Raised when an advisory lock cannot be acquired within ``timeout``."""


#: Directory (relative to ``run_dir``) that holds lock files. Kept out of the
#: artifact tree so locks never become registered stage artifacts.
LOCK_DIR_NAME = ".locks"


def _try_lock(fd: int) -> bool:
    if os.name == "nt":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(fd: int) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(fd, fcntl.LOCK_UN)


@contextlib.contextmanager
def exclusive_lock(
    path: str | Path,
    *,
    timeout: float = 30.0,
    poll: float = 0.02,
) -> Iterator[None]:
    """Block until an exclusive lock on *path* is held, then release on exit.

    Raises :class:`LockTimeout` when ``timeout`` seconds elapse. The lock file
    is created on demand (zero bytes); it is never deleted, so unlocking a
    path that another waiter has opened cannot race with an unlink.
    """
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    deadline = time.monotonic() + max(0.0, float(timeout))
    try:
        while True:
            if _try_lock(fd):
                break
            if time.monotonic() >= deadline:
                raise LockTimeout(
                    f"could not acquire {lock_path} within {timeout}s"
                )
            time.sleep(poll)
        try:
            yield
        finally:
            _unlock(fd)
    finally:
        os.close(fd)
