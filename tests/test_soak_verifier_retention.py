"""T01-T03 — retention offset chain and escape hatch (P-164)."""
from __future__ import annotations

import json
from pathlib import Path

from researchclaw.runtime.event_log import EventLog
from researchclaw.soak.verifier import verify_run


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _make_rotated_run(root: Path, *, name: str = "run-1", stages: int = 5) -> Path:
    run_dir = root / name
    run_dir.mkdir()
    log = EventLog(run_dir, name, fsync=False, max_segment_bytes=1)
    log.append("run.started", {"topic": "x"})
    for stage in range(1, stages + 1):
        log.append("stage.completed", {"name": "S%d" % stage, "stage": stage}, stage=stage)
    _write_json(run_dir / "checkpoint.json", {
        "last_completed_stage": stages,
        "last_completed_name": "S%d" % stages,
        "run_id": name,
    })
    _write_json(run_dir / "pipeline_summary.json", {
        "run_id": name,
        "final_status": "done",
        "final_stage": stages,
    })
    return run_dir


def _delete_oldest_segment(run_dir: Path) -> str:
    segments = sorted(run_dir.glob("events.1-*.jsonl"))
    assert segments, "expected a rolled first segment"
    removed = segments[0].name
    segments[0].unlink()
    return removed


def test_offset_chain_after_prefix_deletion(tmp_path: Path) -> None:
    run_dir = _make_rotated_run(tmp_path)
    _delete_oldest_segment(run_dir)
    log = EventLog(run_dir, "run-1")

    assert log.verify_chain()[0] is False
    ok, message = log.verify_chain(start_seq=2)
    assert ok, message
    assert "offset" in message


def test_retention_escape_hatch_converges(tmp_path: Path) -> None:
    run_dir = _make_rotated_run(tmp_path)
    _delete_oldest_segment(run_dir)

    strict = verify_run(run_dir)
    assert not strict.ok
    assert strict.retention_limited
    assert "retention_limited" in strict.problems

    relaxed = verify_run(run_dir, allow_retention_gap=True)
    assert relaxed.chain_ok, relaxed.chain_message
    assert relaxed.ok, relaxed.problems
    assert relaxed.converged
    assert relaxed.first_seq == 2


def test_offset_chain_still_detects_tamper(tmp_path: Path) -> None:
    run_dir = _make_rotated_run(tmp_path)
    _delete_oldest_segment(run_dir)
    segment = sorted(run_dir.glob("events.2-*.jsonl"))[0]
    lines = segment.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace('"name":"S1"', '"name":"TAMPERED"')
    segment.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = verify_run(run_dir, allow_retention_gap=True)
    assert not result.chain_ok
    assert "payload_sha256" in result.chain_message


def test_offset_chain_detects_middle_gap(tmp_path: Path) -> None:
    run_dir = _make_rotated_run(tmp_path)
    _delete_oldest_segment(run_dir)
    segment = sorted(run_dir.glob("events.3-*.jsonl"))[0]
    segment.unlink()

    result = verify_run(run_dir, allow_retention_gap=True)
    assert not result.ok
    assert result.seq_gaps
