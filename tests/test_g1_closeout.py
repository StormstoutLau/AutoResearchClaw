"""G1 close-out: real subprocess supervision, pid liveness, stream cap (P-033)."""
from __future__ import annotations

import os
import sys
import textwrap

from researchclaw.runtime import attempt, lease
from researchclaw.runtime.event_stream import ConnectionLimiter
from researchclaw.runtime.supervisor import Supervisor


def _worker_script(tmp_path):
    """First run exits 75 (retryable), second exits 0."""
    counter = tmp_path / "counter.txt"
    script = tmp_path / "worker.py"
    script.write_text(textwrap.dedent("""
        import pathlib, sys
        p = pathlib.Path(sys.argv[1])
        n = int(p.read_text()) if p.exists() else 0
        p.write_text(str(n + 1))
        sys.exit(75 if n == 0 else 0)
    """), encoding="utf-8")
    return script, counter


def test_supervisor_restarts_a_real_subprocess(tmp_path):
    """U-1（P-029）：真实子进程按退出码重启，不用 mock。"""
    script, counter = _worker_script(tmp_path)
    sup = Supervisor(
        "run-real", tmp_path / "run",
        [sys.executable, str(script), str(counter)],
        max_restarts=2, base_delay=0.0, cap_delay=0.0, sleep=lambda _d: None,
    )
    result = sup.run()
    assert result.exit_code == 0
    assert result.restarts == 1
    assert counter.read_text() == "2"
    assert (tmp_path / "run" / "supervisor.jsonl").is_file()


def test_is_pid_alive_current_and_bogus():
    """U-3（P-029）：自身存活；不存在的 pid 判为死亡。"""
    assert lease.is_pid_alive(os.getpid()) is True
    assert lease.is_pid_alive(0) is False
    assert lease.is_pid_alive(-1) is False
    # 一个几乎不可能存在的 pid：Windows 走 OpenProcess，POSIX 走 ESRCH
    assert lease.is_pid_alive(2 ** 22 + 12345) is False


def test_session_resume_backend_whitelist():
    """P-037：claude_code 已实测支持续接；未登记的 backend 必须显式降级。"""
    assert attempt.session_resume_supported("claude_code") is True
    assert attempt.session_resume_supported(None) is False
    assert attempt.session_resume_supported("acp") is False
    assert attempt.session_resume_supported("codex") is False


def test_connection_limiter_enforces_cap():
    """U-2（P-031）：单 run 并发流上限。"""
    limiter = ConnectionLimiter(limit=3)
    assert [limiter.acquire("r1") for _ in range(3)] == [True, True, True]
    assert limiter.acquire("r1") is False
    assert limiter.acquire("r2") is True          # 不同 run 互不影响
    limiter.release("r1")
    assert limiter.acquire("r1") is True
    assert limiter.active("r1") == 3
