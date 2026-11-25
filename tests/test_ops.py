"""G7 A7-5/A7-6: cross-run ops view and archive sweep."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from researchclaw.runtime.ops import RUN_INDEX_NAME, build_ops_view, sweep_runs


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _make_run(root: Path, run_id: str) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "checkpoint.json").write_text(
        json.dumps({"last_completed_stage": 12, "status": "running"}),
        encoding="utf-8",
    )
    return run_dir


def test_build_ops_view_reports_restarts_recovery_and_failures(tmp_path: Path) -> None:
    run_a = _make_run(tmp_path, "rc-20261125-000000-aaaaaa")
    _write_jsonl(run_a / "supervisor.jsonl", [
        {"ts": "2026-11-25T02:00:00+00:00", "event": "restart_scheduled"},
        {"ts": "2026-11-25T02:10:00+00:00", "event": "restart_scheduled"},
    ])
    _write_jsonl(run_a / "soak_session.jsonl", [
        {"ts": "2026-11-25T01:00:00+00:00", "event": "restart_injected"},
        {"ts": "2026-11-25T01:00:30+00:00", "event": "worker_started"},
        {"ts": "2026-11-25T01:10:00+00:00", "event": "restart_injected"},
        {"ts": "2026-11-25T01:10:12+00:00", "event": "worker_started"},
    ])
    _write_jsonl(run_a / "stage_events.jsonl", [
        {"seq": 1, "stage": 11, "status": "done"},
        {"seq": 2, "stage": 12, "status": "failed"},
    ])

    run_b = _make_run(tmp_path, "rc-20261125-000001-bbbbbb")
    _write_jsonl(run_b / "events.jsonl", [
        {"seq": 1, "type": "stage.failed", "stage": 9, "payload": {}},
        {"seq": 2, "type": "run.completed", "payload": {}},
    ])

    view = build_ops_view(tmp_path)
    by_id = {row["run_id"]: row for row in view["runs"]}

    a = by_id[run_a.name]
    assert a["restarts"] == 2  # supervisor 与 soak 互斥，按来源取最大而非相加
    assert a["recovery_seconds"] == [30.0, 12.0]
    assert a["failure_stages"] == {"12": 1}
    assert a["last_stage"] == 12
    b = by_id[run_b.name]
    assert b["failure_stages"] == {"9": 1}
    assert b["events"] == 2
    assert view["totals"]["runs"] == 2
    assert view["totals"]["failures"] == 2


def test_build_ops_view_tolerates_a_bad_event_line(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path, "rc-20261125-000000-aaaaaa")
    (run_dir / "events.jsonl").write_text(
        '{"seq": 1, "type": "run.started", "payload": {}}\n{not json\n',
        encoding="utf-8",
    )

    view = build_ops_view(tmp_path)

    assert view["runs"][0]["events"] == 1
    assert view["totals"]["runs"] == 1


def test_build_ops_view_is_read_only(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path, "rc-20261125-000000-aaaaaa")
    _write_jsonl(run_dir / "supervisor.jsonl", [
        {"ts": "2026-11-25T02:00:00+00:00", "event": "restart_scheduled"},
    ])
    before = _tree_digest(tmp_path)

    build_ops_view(tmp_path)

    assert _tree_digest(tmp_path) == before


def test_sweep_runs_archives_old_segments_and_writes_index(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path, "rc-20261125-000000-aaaaaa")
    segment = run_dir / "events.1-2.jsonl"
    _write_jsonl(segment, [
        {"seq": 1, "type": "run.started", "payload": {}},
        {"seq": 2, "type": "stage.started", "payload": {}},
    ])
    old = datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp()
    os.utime(segment, (old, old))
    _write_jsonl(run_dir / "events.jsonl", [
        {"seq": 3, "type": "run.completed", "payload": {}},
    ])
    before_active = (run_dir / "events.jsonl").read_bytes()

    result = sweep_runs(tmp_path, retention_days=30, archive_days=365)

    assert not segment.exists()
    assert (run_dir / "events.1-2.jsonl.gz").is_file()
    with gzip.open(run_dir / "events.1-2.jsonl.gz", "rt", encoding="utf-8") as fh:
        assert "run.started" in fh.read()
    assert (run_dir / "events.jsonl").read_bytes() == before_active
    assert run_dir.is_dir()
    index = [
        json.loads(line)
        for line in (tmp_path / RUN_INDEX_NAME).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert index[-1]["run_id"] == run_dir.name
    assert index[-1]["archived"] == ["events.1-2.jsonl.gz"]
    assert result["runs"][0]["archived"] == ["events.1-2.jsonl.gz"]
