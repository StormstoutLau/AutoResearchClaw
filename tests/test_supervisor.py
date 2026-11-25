"""G1b supervisor loop and lease keeper (A1-3, R-2, R-3)."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

import pytest

from researchclaw.runtime import exit_codes
import researchclaw.runtime.lease as lease_mod
from researchclaw.runtime.admission import SlotRegistry
from researchclaw.runtime.lease import (
    LeaseKeeper,
    LeaseLost,
    acquire,
    read_lease,
    renew,
)
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


def test_renew_holds_lease_lock(tmp_path, monkeypatch):
    """P-134：renew 必须在 lease.lock 保护下读取租约。"""
    lease = acquire(tmp_path, owner="me:1", ttl=300)
    lock_seen = []
    real_read = lease_mod.read_lease

    def spy_read(run_dir):
        lock_seen.append((tmp_path / "lease.lock").exists())
        return real_read(run_dir)

    monkeypatch.setattr(lease_mod, "read_lease", spy_read)
    renew(tmp_path, lease)

    assert lock_seen and all(lock_seen), "renew 读取租约时未持锁"


def test_renew_maps_busy_lock_to_lease_lost(tmp_path):
    """P-134：锁被他人持有时，renew 以 LeaseLost 结束。"""
    lease = acquire(tmp_path, owner="me:1", ttl=300)
    (tmp_path / "lease.lock").write_text("other", encoding="utf-8")

    with pytest.raises(LeaseLost):
        renew(tmp_path, lease)


def test_renew_after_takeover_raises(tmp_path):
    """P-134：接管后续约必须 LeaseLost，且 fencing 不回滚。"""
    lease = acquire(tmp_path, owner="me:1", ttl=300)
    acquire(
        tmp_path,
        owner="other:2",
        ttl=300,
        now=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    with pytest.raises(LeaseLost):
        renew(tmp_path, lease)
    assert read_lease(tmp_path).fencing == lease.fencing + 1


def test_renew_same_owner_keeps_fencing(tmp_path):
    """P-134：无接管时续约成功且 fencing 不变。"""
    lease = acquire(tmp_path, owner="me:1", ttl=300)

    renewed = renew(tmp_path, lease)

    assert renewed.fencing == lease.fencing
    assert read_lease(tmp_path).fencing == lease.fencing


# ── A7-7: worker slots are reserved synchronously ───────────────────


def _admitted(tmp_path, codes, spawned, **kw):
    seq = iter(codes)
    reg = kw.pop("registry", None) or SlotRegistry(
        tmp_path / "slots", max_attempts=1, hitl_priority_slots=0
    )

    def spawn(*_args, **_kwargs):
        spawned.append([row["run_id"] for row in reg.snapshot()["slots"]])
        return FakeProc(next(seq))

    sup = Supervisor("run-s", tmp_path, ["worker"], spawn=spawn,
                     sleep=lambda _d: None, admission=reg, **kw)
    return sup, reg


def test_slot_is_held_before_spawn_and_released_after(tmp_path):
    spawned = []
    sup, reg = _admitted(tmp_path, [0], spawned)

    result = sup.run()

    assert spawned == [["run-s"]]
    assert result.exit_code == 0
    assert result.queued is False
    assert reg.snapshot()["active"] == 0


def test_admission_timeout_does_not_spawn(tmp_path):
    reg = SlotRegistry(tmp_path / "slots", max_attempts=1, hitl_priority_slots=0)
    holder = reg.acquire("other-run")
    spawned = []
    sup, _ = _admitted(tmp_path, [0], spawned, registry=reg, admission_timeout=0)

    result = sup.run()

    assert spawned == []
    assert result.queued is True
    assert result.exit_code == exit_codes.CONFIG
    assert reg.snapshot()["active"] == 1
    reg.release(holder)


def test_budget_is_rejected_before_spawn(tmp_path):
    (tmp_path / "cost_log.jsonl").write_text(
        '{"cost_usd": 10.0, "total_tokens": 1}\n', encoding="utf-8"
    )
    spawned = []
    sup, reg = _admitted(tmp_path, [0], spawned, run_budget_usd=5.0)

    result = sup.run()

    assert spawned == []
    assert result.exit_code == exit_codes.CONFIG
    assert result.queued is False
    assert reg.snapshot()["active"] == 0


def test_corrupt_registry_fails_closed_without_spawning(tmp_path):
    slot_root = tmp_path / "slots"
    slot_root.mkdir()
    (slot_root / "registry.json").write_text("{not json", encoding="utf-8")
    (slot_root / "registry.bak.json").write_text("[]", encoding="utf-8")
    reg = SlotRegistry(slot_root, max_attempts=1, hitl_priority_slots=0)
    spawned = []
    sup, _ = _admitted(tmp_path, [0], spawned, registry=reg)

    result = sup.run()

    assert spawned == []
    assert result.exit_code == exit_codes.CONFIG
    assert result.queued is False
    events = [
        json.loads(line) for line in
        (tmp_path / "supervisor.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert any(row.get("event") == "admission_corrupt" for row in events)


def test_hitl_slot_uses_the_reserved_capacity(tmp_path):
    reg = SlotRegistry(tmp_path / "slots", max_attempts=2, hitl_priority_slots=1)
    reg.acquire("batch-run")  # normal capacity is now exhausted
    spawned = []
    sup, _ = _admitted(tmp_path, [0], spawned, registry=reg, slot_class="hitl")

    result = sup.run()

    assert len(spawned) == 1
    assert result.exit_code == 0
    assert reg.snapshot()["by_class"] == {"normal": 1, "hitl": 0}
