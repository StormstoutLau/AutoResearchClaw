"""G7 A7-4: rotation + compression still replays by run_id + seq."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from researchclaw.runtime.event_log import EventLog
from researchclaw.soak.verifier import verify_run


def _make_log(run_dir: Path, count: int = 10) -> EventLog:
    run_dir.mkdir(parents=True, exist_ok=True)
    log = EventLog(
        run_dir,
        run_dir.name,
        max_segment_events=3,
        max_segment_bytes=10**9,
        fsync=False,
    )
    for stage in range(1, count + 1):
        log.append("stage.completed", {}, stage=stage)
    (run_dir / "checkpoint.json").write_text(json.dumps({
        "last_completed_stage": count,
        "last_completed_name": "stage-%d" % count,
        "status": "completed",
    }))
    (run_dir / "pipeline_summary.json").write_text(
        json.dumps({"final_status": "completed"})
    )
    return log


def test_rotation_keeps_every_seq_readable_by_run_id(tmp_path: Path) -> None:
    run_dir = tmp_path / "rc-20261125-rotation-aaaaaa"
    _make_log(run_dir)

    segments = sorted(p.name for p in run_dir.glob("events.*.jsonl"))
    assert segments == [
        "events.1-3.jsonl", "events.4-6.jsonl", "events.7-9.jsonl"
    ]

    log = EventLog(run_dir, run_dir.name, fsync=False)
    events = log.read_all()

    assert [row["seq"] for row in events] == list(range(1, 11))
    assert {row["run_id"] for row in events} == {run_dir.name}
    assert log.verify_chain(start_seq=1)[0] is True
    verification = verify_run(run_dir)
    assert verification.ok is True
    assert verification.converged is True


def test_compressed_segments_still_replay(tmp_path: Path) -> None:
    run_dir = tmp_path / "rc-20261125-rotation-bbbbbb"
    _make_log(run_dir)
    old = datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp()
    for segment in run_dir.glob("events.*.jsonl"):
        os.utime(segment, (old, old))
    log = EventLog(run_dir, run_dir.name, fsync=False)

    result = log.apply_retention(retention_days=30, archive_days=365)

    assert sorted(result["archived"]) == [
        "events.1-3.jsonl.gz",
        "events.4-6.jsonl.gz",
        "events.7-9.jsonl.gz",
    ]
    replayed = EventLog(run_dir, run_dir.name, fsync=False)
    assert [row["seq"] for row in replayed.read_all()] == list(range(1, 11))
    assert replayed.verify_chain(start_seq=1)[0] is True
    assert verify_run(run_dir).ok is True


def test_archived_gap_is_reported_as_failure(tmp_path: Path) -> None:
    run_dir = tmp_path / "rc-20261125-rotation-cccccc"
    _make_log(run_dir)
    old = datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp()
    for segment in run_dir.glob("events.*.jsonl"):
        os.utime(segment, (old, old))
    EventLog(run_dir, run_dir.name, fsync=False).apply_retention(
        retention_days=30, archive_days=365
    )
    (run_dir / "events.1-3.jsonl.gz").unlink()

    verification = verify_run(run_dir)

    assert verification.ok is False
    assert verification.converged is False
    assert verification.retention_limited is True
    assert "retention_limited" in verification.problems
    assert verification.first_seq == 4
