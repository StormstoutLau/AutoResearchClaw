"""T04 — POSIX process-tree spawn/kill helpers (P-164)."""
from __future__ import annotations

import signal

import pytest

from researchclaw.soak.driver import _posix_kill_tree, _spawn_kwargs


class _Proc:
    pid = 123

    def __init__(self) -> None:
        self.killed = False

    def kill(self) -> None:
        self.killed = True


def test_spawn_kwargs_are_posix_only() -> None:
    assert _spawn_kwargs("posix") == {"start_new_session": True}
    assert _spawn_kwargs("nt") == {}


def test_killpg_used_for_group_leader() -> None:
    proc = _Proc()
    calls: list[tuple[int, int]] = []

    verdict = _posix_kill_tree(
        proc,
        getpgid=lambda pid: 123,
        killpg=lambda pgid, sig: calls.append((pgid, sig)),
    )

    assert verdict == "group"
    assert calls == [(123, getattr(signal, "SIGKILL", 9))]
    assert proc.killed is False


def test_fallback_when_child_is_not_group_leader() -> None:
    proc = _Proc()
    calls: list[tuple[int, int]] = []

    verdict = _posix_kill_tree(
        proc,
        getpgid=lambda pid: 999,
        killpg=lambda pgid, sig: calls.append((pgid, sig)),
    )

    assert verdict == "process"
    assert calls == []
    assert proc.killed is True


def test_fallback_when_getpgid_fails() -> None:
    proc = _Proc()

    def boom(pid):
        raise ProcessLookupError(pid)

    verdict = _posix_kill_tree(proc, getpgid=boom, killpg=lambda pgid, sig: None)

    assert verdict == "process"
    assert proc.killed is True


def test_fallback_when_killpg_fails() -> None:
    proc = _Proc()

    def boom(pgid, sig):
        raise PermissionError("nope")

    verdict = _posix_kill_tree(proc, getpgid=lambda pid: 123, killpg=boom)

    assert verdict == "process"
    assert proc.killed is True
