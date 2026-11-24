"""Soak verifier (A7-1/A7-4, P-160)."""
from __future__ import annotations

import json
from pathlib import Path

from researchclaw.runtime.event_log import EventLog
from researchclaw.soak.verifier import (
    convergence_signature,
    event_seq_coverage,
    verify_run,
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _make_run(root: Path, *, name: str = "run-1", stages=(1, 2, 3),
              final_status: str = "done", fsync: bool = False,
              max_segment_bytes: int | None = None) -> Path:
    run_dir = root / name
    run_dir.mkdir()
    kw = {"fsync": fsync}
    if max_segment_bytes is not None:
        kw["max_segment_bytes"] = max_segment_bytes
    log = EventLog(run_dir, name, **kw)
    log.append("run.started", {"topic": "x"})
    for stage in stages:
        log.append("stage.completed", {"name": "S%d" % stage}, stage=stage)
    last = stages[-1] if stages else 0
    _write_json(run_dir / "checkpoint.json", {
        "last_completed_stage": last,
        "last_completed_name": "S%d" % last if last else "",
        "run_id": name,
    })
    _write_json(run_dir / "pipeline_summary.json", {
        "run_id": name,
        "final_status": final_status,
        "final_stage": last,
        "stages_done": len(stages),
        "generated": "2026-01-01T00:00:00+00:00",
    })
    return run_dir


def test_verify_run_accepts_valid_chain(tmp_path):
    run_dir = _make_run(tmp_path)
    snapshot = {p.name: p.read_bytes() for p in run_dir.iterdir() if p.is_file()}

    result = verify_run(run_dir)

    assert result.ok, result.problems
    assert result.chain_ok
    assert result.seq_gaps == ()
    assert result.duplicate_seqs == ()
    assert result.max_completed_stage == 3
    assert result.checkpoint_stage == 3
    assert result.terminal_status == "completed"
    assert result.converged
    assert not result.retention_limited
    after = {p.name: p.read_bytes() for p in run_dir.iterdir() if p.is_file()}
    assert after == snapshot, "verify_run must be read-only"


def test_verify_run_detects_payload_tamper(tmp_path):
    run_dir = _make_run(tmp_path)
    path = run_dir / "events.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace('"name":"S1"', '"name":"TAMPERED"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = verify_run(run_dir)

    assert not result.ok
    assert not result.chain_ok
    assert "payload_sha256" in result.chain_message or "prev_sha256" in result.chain_message


def test_verify_run_detects_seq_gap(tmp_path):
    run_dir = _make_run(tmp_path)
    path = run_dir / "events.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines = [line for line in lines if '"seq":2' not in line]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = verify_run(run_dir)

    assert not result.ok
    assert 2 in result.seq_gaps
    assert not result.chain_ok


def test_verify_run_detects_run_id_mismatch(tmp_path):
    run_dir = _make_run(tmp_path)
    path = run_dir / "events.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace('"run_id":"run-1"', '"run_id":"other-run"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = verify_run(run_dir, expected_run_id="run-1")

    assert not result.ok
    assert result.run_id_mismatches


def test_verify_run_detects_checkpoint_behind_events(tmp_path):
    run_dir = _make_run(tmp_path)
    _write_json(run_dir / "checkpoint.json", {
        "last_completed_stage": 1,
        "last_completed_name": "S1",
        "run_id": "run-1",
    })

    result = verify_run(run_dir)

    assert not result.ok
    assert any("checkpoint" in problem for problem in result.problems)


def test_verify_run_replays_after_rotation(tmp_path):
    run_dir = _make_run(tmp_path, stages=(1, 2, 3, 4, 5), max_segment_bytes=1)
    log = EventLog(run_dir, "run-1")

    result = verify_run(run_dir)

    assert result.ok, result.problems
    assert result.first_seq == 1 and result.last_seq == 6   # run.started + 5 stages
    assert result.seq_gaps == ()
    assert any(seg["file"].startswith("events.") for seg in result.segments)
    assert [e["seq"] for e in log.read_after(3)] == [4, 5, 6]


def test_verify_run_reference_mismatch(tmp_path):
    baseline = _make_run(tmp_path, name="baseline", stages=(1, 2, 3))
    soak = _make_run(tmp_path, name="soak", stages=(1, 2))

    result = verify_run(soak, reference_run_dir=baseline)

    assert not result.converged
    assert result.reference_signature is not None
    assert any("signature" in problem for problem in result.problems)


def test_convergence_signature_ignores_volatile_fields(tmp_path):
    left = _make_run(tmp_path, name="left", stages=(1, 2, 3))
    right = _make_run(tmp_path, name="right", stages=(1, 2, 3))
    # 只改易变字段
    summary = json.loads((right / "pipeline_summary.json").read_text(encoding="utf-8"))
    summary["generated"] = "2030-01-01T00:00:00+00:00"
    _write_json(right / "pipeline_summary.json", summary)

    assert convergence_signature(left) == convergence_signature(right)


def test_verify_run_accepts_checkpoint_ahead_of_events(tmp_path):
    """F-4 崩溃窗口：checkpoint 已写、stage.completed 未写，仍应视为收敛。"""
    run_dir = _make_run(tmp_path, stages=(1, 2))
    _write_json(run_dir / "checkpoint.json", {
        "last_completed_stage": 3,
        "last_completed_name": "S3",
        "run_id": "run-1",
    })
    _write_json(run_dir / "pipeline_summary.json", {
        "run_id": "run-1",
        "final_status": "done",
        "final_stage": 3,
    })

    result = verify_run(run_dir)

    assert result.ok, result.problems
    assert result.event_checkpoint_skew == 1
    assert result.converged


def test_verify_run_collects_failure_stages(tmp_path):
    run_dir = _make_run(tmp_path)
    log = EventLog(run_dir, "run-1")
    log.append("stage.failed", {"name": "S3", "status": "failed"}, stage=3)
    log.append("stage.failed", {"name": "S3", "status": "failed"}, stage=3)

    result = verify_run(run_dir)

    assert result.failure_stages == ((3, 2),)


def test_event_seq_coverage_reports_gap_and_duplicate():
    gaps, duplicates = event_seq_coverage([
        {"seq": 1}, {"seq": 2}, {"seq": 2}, {"seq": 4},
    ])
    assert gaps == (3,)
    assert duplicates == (2,)
