"""G7 A7-6/A7-7: attempt slots, HITL reservation and budget pre-rejection."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from researchclaw.runtime.admission import (
    AdmissionTimeout,
    BudgetRejected,
    RegistryCorrupt,
    SlotRegistry,
    preflight_budget,
)


def _past(hours: int = 2) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def test_acquire_makes_one_slot_and_release_frees_it(tmp_path: Path) -> None:
    reg = SlotRegistry(tmp_path, max_attempts=2, hitl_priority_slots=1)

    slot = reg.acquire("run-a")

    assert slot.slot_class == "normal"
    assert slot.fencing == 1
    assert slot.slot_id == "s1"
    snap = reg.snapshot()
    assert snap["active"] == 1
    assert snap["by_class"] == {"normal": 1, "hitl": 0}
    assert reg.release(slot) is True
    assert reg.snapshot()["active"] == 0
    assert reg.release(slot) is False


def test_same_run_is_idempotent_and_does_not_take_two_slots(tmp_path: Path) -> None:
    reg = SlotRegistry(tmp_path, max_attempts=2, hitl_priority_slots=1)

    first = reg.acquire("run-a")
    again = reg.acquire("run-a")

    assert again.slot_id == first.slot_id
    assert again.fencing == first.fencing
    assert reg.snapshot()["active"] == 1


def test_normal_capacity_reserves_a_slot_for_hitl(tmp_path: Path) -> None:
    reg = SlotRegistry(tmp_path, max_attempts=2, hitl_priority_slots=1)

    reg.acquire("run-a")  # normal_capacity = 2 - 1 = 1
    with pytest.raises(AdmissionTimeout):
        reg.acquire("run-b", timeout=0)

    snap = reg.snapshot()
    assert snap["queue"][0]["run_id"] == "run-b"
    assert snap["queue"][0]["priority"] == 1

    hitl = reg.acquire("hitl-1", slot_class="hitl", timeout=0)

    assert hitl.slot_class == "hitl"
    assert hitl.fencing == 2
    assert reg.snapshot()["active"] == 2


def test_hitl_cannot_exceed_total_capacity(tmp_path: Path) -> None:
    reg = SlotRegistry(tmp_path, max_attempts=2, hitl_priority_slots=1)

    reg.acquire("run-a")
    reg.acquire("hitl-1", slot_class="hitl")

    with pytest.raises(AdmissionTimeout):
        reg.acquire("hitl-2", slot_class="hitl", timeout=0)


def test_releasing_a_normal_slot_lets_the_queued_run_start(tmp_path: Path) -> None:
    reg = SlotRegistry(tmp_path, max_attempts=2, hitl_priority_slots=1)
    running = reg.acquire("run-a")
    with pytest.raises(AdmissionTimeout):
        reg.acquire("run-b", timeout=0)

    reg.release(running)
    started = reg.acquire("run-b", timeout=0)

    assert started.slot_id == "s2"
    assert started.fencing == running.fencing + 1
    assert [row["run_id"] for row in reg.snapshot()["queue"]] == []


def test_expired_slot_is_reclaimed_but_live_slot_is_not(tmp_path: Path) -> None:
    reg = SlotRegistry(tmp_path, max_attempts=2, hitl_priority_slots=1, ttl=1)
    stale = reg.acquire("run-old", now=_past())
    assert stale.fencing == 1

    takeover = reg.acquire("run-new", timeout=0)

    assert takeover.fencing == 2
    assert takeover.run_id == "run-new"
    assert [row["run_id"] for row in reg.snapshot()["slots"]] == ["run-new"]


def test_registry_file_is_readable_and_fencing_is_monotonic(tmp_path: Path) -> None:
    reg = SlotRegistry(tmp_path, max_attempts=1, hitl_priority_slots=0)
    first = reg.acquire("run-a")
    reg.release(first)
    second = reg.acquire("run-b")

    data = json.loads((tmp_path / "registry.json").read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert second.fencing == data["fencing"] == 2
    assert first.fencing == 1


def test_corrupt_primary_recovers_from_backup(tmp_path: Path) -> None:
    reg = SlotRegistry(tmp_path, max_attempts=1, hitl_priority_slots=0)
    first = reg.acquire("run-a")
    reg.release(first)
    (tmp_path / "registry.json").write_text("{not json", encoding="utf-8")

    slot = reg.acquire("run-b", timeout=0)

    assert reg.last_error == "recovered_from_backup"
    assert slot.fencing == 2
    assert reg.snapshot()["active"] == 1
    assert json.loads((tmp_path / "registry.json").read_text(encoding="utf-8"))


def test_missing_primary_recovers_from_backup(tmp_path: Path) -> None:
    reg = SlotRegistry(tmp_path, max_attempts=1, hitl_priority_slots=0)
    first = reg.acquire("run-a")
    reg.release(first)
    (tmp_path / "registry.json").unlink()

    slot = reg.acquire("run-b", timeout=0)

    assert reg.last_error == "recovered_from_backup"
    assert slot.fencing == 2
    assert (tmp_path / "registry.json").is_file()


def test_both_copies_corrupt_fail_closed(tmp_path: Path) -> None:
    reg = SlotRegistry(tmp_path, max_attempts=1, hitl_priority_slots=0)
    reg.acquire("run-a")
    (tmp_path / "registry.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "registry.bak.json").write_text("[]", encoding="utf-8")

    with pytest.raises(RegistryCorrupt):
        reg.acquire("run-b", timeout=0)
    with pytest.raises(RegistryCorrupt):
        reg.snapshot()


def test_preflight_budget_rejects_at_or_over_limit(tmp_path: Path) -> None:
    log = tmp_path / "cost_log.jsonl"
    log.write_text(
        "\n".join([
            json.dumps({"cost_usd": 4.0, "total_tokens": 10}),
            json.dumps({"cost_usd": 1.5, "total_tokens": 5}),
        ]) + "\n",
        encoding="utf-8",
    )

    assert preflight_budget(tmp_path, 10.0)["ok"] is True
    with pytest.raises(BudgetRejected):
        preflight_budget(tmp_path, 5.5)
    with pytest.raises(BudgetRejected):
        preflight_budget(tmp_path, 5.0)
    assert preflight_budget(tmp_path, 0.0)["ok"] is True


def test_preflight_budget_without_log_is_ok(tmp_path: Path) -> None:
    result = preflight_budget(tmp_path, 1.0)

    assert result == {"ok": True, "budget_usd": 1.0, "spent_usd": 0.0}
