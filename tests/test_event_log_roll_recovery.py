"""Event-log roll-boundary recovery (F-1/F-2, P-160)."""
from __future__ import annotations

import json
from pathlib import Path

from researchclaw.pipeline.runner import read_checkpoint
from researchclaw.pipeline.stages import Stage
from researchclaw.runtime.event_log import EventLog


def _run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    return run_dir


def test_reopen_after_roll_without_active_continues_seq(tmp_path):
    """F-1：崩溃在 os.replace 之后、新 active 写入之前，重开不得重置 seq。"""
    run_dir = _run_dir(tmp_path)
    log = EventLog(run_dir, "run-1", max_segment_bytes=1, fsync=False)
    log.append("stage.completed", {"name": "S1"}, stage=1)
    log.append("stage.completed", {"name": "S2"}, stage=2)
    log.append("stage.completed", {"name": "S3"}, stage=3)
    assert [p.name for p in run_dir.glob("events.*.jsonl")]
    (run_dir / "events.jsonl").unlink()

    reopened = EventLog(run_dir, "run-1", max_segment_bytes=1, fsync=False)

    assert reopened.last_seq == 2
    assert reopened.count == 2
    next_event = reopened.append("stage.completed", {"name": "S4"}, stage=4)
    assert next_event.seq == 3
    ok, message = reopened.verify_chain()
    assert ok, message
    assert [e["seq"] for e in reopened.read_all()] == [1, 2, 3]


def test_torn_tail_is_truncated_before_append(tmp_path):
    """F-1b：坏尾行必须截断，否则后续事件会被 read_all 永久遮蔽。"""
    run_dir = _run_dir(tmp_path)
    log = EventLog(run_dir, "run-1", fsync=False)
    log.append("stage.completed", {"name": "S1"}, stage=1)
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as fh:
        fh.write('{"seq":2,"broken"')

    reopened = EventLog(run_dir, "run-1", fsync=False)
    assert reopened.truncated is True
    next_event = reopened.append("stage.completed", {"name": "S2"}, stage=2)

    assert next_event.seq == 2
    assert [e["seq"] for e in reopened.read_all()] == [1, 2]
    ok, message = reopened.verify_chain()
    assert ok, message


def test_checkpoint_recovery_from_archived_segment(tmp_path):
    """F-2：active 缺失时，归档段里的 stage.completed 仍可恢复 checkpoint。"""
    run_dir = _run_dir(tmp_path)
    log = EventLog(run_dir, "run-1", max_segment_bytes=1, fsync=False)
    log.append("stage.completed", {"name": "S1"}, stage=1)
    log.append("stage.completed", {"name": "S2"}, stage=2)
    log.append("stage.completed", {"name": "S3"}, stage=3)
    (run_dir / "events.jsonl").unlink()
    (run_dir / "checkpoint.json").write_text("{broken", encoding="utf-8")

    next_stage = read_checkpoint(run_dir)

    assert next_stage == Stage.SEARCH_STRATEGY
    checkpoint = json.loads((run_dir / "checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["last_completed_stage"] == 2
    assert checkpoint["recovered"] is True
