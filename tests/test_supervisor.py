"""G1b supervisor loop and lease keeper (A1-3, R-2, R-3)."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from researchclaw.runtime import exit_codes
from researchclaw.runtime.lease import LeaseKeeper, acquire, read_lease
from researchclaw.runtime.supervisor import Supervisor, full_jitter


class FakeProc:
    def __init__(self, rc: int) -> None:
        self.rc = rc

    def wait(self) -> int:
        return self.rc


def _supervisor(tmp_path, codes, sleeps, **kw):
    seq = iter(codes)
    return Supervisor(
        "run-s", tmp_path, ["worker"],
        spawn=lambda *a, **k: FakeProc(next(seq)),
        sleep=lambda d: sleeps.append(d),
        **kw,
    )


def test_retryable_exit_restarts_with_backoff(tmp_path):
    sleeps = []
    sup = _supervisor(tmp_path, [75, 75, 0], sleeps, max_restarts=3,
                      base_delay=1.0, cap_delay=10.0)
    result = sup.run()
    assert result.exit_code == 0
    assert result.restarts == 2
    assert len(sleeps) == 2
    assert all(0 <= d <= 10.0 for d in sleeps)


def test_paused_exit_stops_without_restart(tmp_path):
    """R-1：正常暂停不得触发重启。"""
    sleeps = []
    sup = _supervisor(tmp_path, [exit_codes.PAUSED], sleeps)
    result = sup.run()
    assert result.exit_code == exit_codes.PAUSED
    assert result.restarts == 0
    assert sleeps == []
    assert not result.exhausted


def test_terminal_failure_stops(tmp_path):
    sleeps = []
    sup = _supervisor(tmp_path, [exit_codes.REVOKED], sleeps)
    result = sup.run()
    assert result.exit_code == exit_codes.REVOKED
    assert result.restarts == 0 and sleeps == []


def test_budget_exhaustion(tmp_path):
    sleeps = []
    sup = _supervisor(tmp_path, [75] * 10, sleeps, max_restarts=2)
    result = sup.run()
    assert result.exhausted is True
    assert result.restarts == 3          # 首次 + 2 次重启后仍失败
    assert len(sleeps) == 2


def test_supervisor_log_and_no_lease(tmp_path):
    """R-2：supervisor 自己不持有 run 租约。"""
    sup = _supervisor(tmp_path, [0], [], max_restarts=1)
    sup.run()
    assert (tmp_path / "supervisor.jsonl").is_file()
    assert read_lease(tmp_path) is None


def test_stale_lease_is_released_before_restart(tmp_path):
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    lease = acquire(tmp_path, owner="old:1", ttl=1, now=past)
    assert read_lease(tmp_path).released is False
    sup = _supervisor(tmp_path, [0], [])
    sup.run()
    assert read_lease(tmp_path).released is True
    assert lease.fencing == 1


def test_full_jitter_bounds():
    for attempt in range(0, 8):
        for _ in range(20):
            delay = full_jitter(attempt, base=2.0, cap=300.0)
            assert 0.0 <= delay <= min(300.0, 2.0 * (2 ** attempt))


def test_lease_keeper_renews(tmp_path):
    lease = acquire(tmp_path, owner="me:1", ttl=300)
    first = read_lease(tmp_path).expires_at
    keeper = LeaseKeeper(tmp_path, lease, ttl=300, interval=0.02).start()
    time.sleep(0.12)
    keeper.stop()
    assert read_lease(tmp_path).expires_at >= first


def test_lease_keeper_reports_loss(tmp_path):
    lease = acquire(tmp_path, owner="me:1", ttl=300)
    lost = []
    keeper = LeaseKeeper(tmp_path, lease, ttl=300, interval=0.02,
                         on_lost=lambda: lost.append(True)).start()
    # 另一写者用未来时间接管（模拟租约被夺走）
    acquire(tmp_path, owner="other:2", ttl=300,
            now=datetime.now(timezone.utc) + timedelta(hours=1))
    time.sleep(0.15)
    keeper.stop()
    assert lost, "keeper 必须在租约丢失时回调"
