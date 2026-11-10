"""Runner ↔ runtime wiring (G1a): event emission, lease lifecycle, recursion guard."""
from __future__ import annotations

import json

from researchclaw.pipeline import runner
from researchclaw.runtime.event_log import EventLog
from researchclaw.runtime.lease import read_lease


def _types(run_dir):
    lines = (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(ln)["type"] for ln in lines]


def test_runtime_roundtrip_emits_and_releases(tmp_path):
    log, lease, owns = runner._runtime_begin(
        tmp_path, "run-x", {"from_stage": 1, "to_stage": None})
    assert owns and log is not None and lease is not None
    runner._emit(log, "stage.started", {"name": "TOPIC_INIT"}, stage=1)
    runner._runtime_end(log, lease, owns, "run.completed", {"stages_run": 1})

    assert _types(tmp_path) == ["run.started", "stage.started", "run.completed"]
    summary = json.loads((tmp_path / "events_summary.json").read_text(encoding="utf-8"))
    assert summary["count"] == 3
    assert read_lease(tmp_path).released is True
    assert EventLog(tmp_path, "run-x").verify_chain()[0] is True


def test_nested_call_reuses_outer_log(tmp_path):
    log, lease, owns = runner._runtime_begin(
        tmp_path, "run-y", {"from_stage": 1, "to_stage": None})
    nested, nested_lease, nested_owns = runner._runtime_begin(
        tmp_path, "run-y", {"from_stage": 7, "to_stage": None})
    assert nested is log and nested_owns is False and nested_lease is None

    runner._runtime_end(nested, nested_lease, nested_owns, "run.completed", {})
    # 内层收口不应结束外层
    assert _types(tmp_path) == ["run.started"]
    runner._runtime_end(log, lease, owns, "run.completed", {})
    assert _types(tmp_path) == ["run.started", "run.completed"]


def test_runtime_can_be_disabled_with_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_EVENTS_DISABLED", "1")
    log, lease, owns = runner._runtime_begin(tmp_path, "run-z", {})
    assert (log, lease, owns) == (None, None, False)
    assert not (tmp_path / "events.jsonl").exists()


def test_read_checkpoint_recovers_from_event_log(tmp_path):
    """A1-5: corrupt checkpoint.json → rebuild from the event log."""
    log = EventLog(tmp_path, "run-r")
    log.append("run.started", {})
    log.append("stage.completed", {"name": "LITERATURE_SEARCH", "stage": 5}, stage=5)
    (tmp_path / "checkpoint.json").write_text("{not json", encoding="utf-8")

    nxt = runner.read_checkpoint(tmp_path)
    assert int(nxt) == 6
    recovered = json.loads((tmp_path / "checkpoint.json").read_text(encoding="utf-8"))
    assert recovered["recovered"] is True
    assert recovered["last_completed_stage"] == 5


def test_read_checkpoint_returns_none_without_events(tmp_path):
    (tmp_path / "checkpoint.json").write_text("{broken", encoding="utf-8")
    assert runner.read_checkpoint(tmp_path) is None
