"""Contract tests for the shared run-state reader (PR-2).

The dashboard, the projects API and the MCP server must all agree on how a
completed checkpoint / heartbeat is interpreted. These tests pin that contract.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from researchclaw.run_state import RunState, RunStatus, read_run_state


def _iso(delta_sec: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_sec)).isoformat()


def _make_run(tmp_path: Path, name: str = "rc-20261029-120000-abc123") -> Path:
    run_dir = tmp_path / name
    run_dir.mkdir(parents=True)
    return run_dir


def _write_checkpoint(run_dir: Path, **overrides: object) -> None:
    payload = {
        "last_completed_stage": 12,
        "last_completed_name": "EXPERIMENT_RUN",
        "run_id": run_dir.name,
        "timestamp": _iso(),
        "schema_version": 1,
    }
    payload.update(overrides)
    (run_dir / "checkpoint.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def _write_heartbeat(run_dir: Path, timestamp: object, **extra: object) -> None:
    payload = {
        "pid": 4242,
        "last_stage": 12,
        "last_stage_name": "EXPERIMENT_RUN",
        "run_id": run_dir.name,
        "timestamp": timestamp,
    }
    payload.update(extra)
    (run_dir / "heartbeat.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def test_reads_current_checkpoint_schema(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    _write_checkpoint(run_dir)
    _write_heartbeat(run_dir, _iso())

    state = read_run_state(run_dir)

    assert isinstance(state, RunState)
    assert state.current_stage == 12
    assert state.current_stage_name == "EXPERIMENT_RUN"
    assert state.run_id == run_dir.name
    assert state.schema_version == 1


def test_legacy_checkpoint_fields_are_mapped(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    (run_dir / "checkpoint.json").write_text(
        json.dumps({"stage": 5, "stage_name": "LITERATURE_SCREEN", "status": "running"}),
        encoding="utf-8",
    )

    state = read_run_state(run_dir)

    assert state.current_stage == 5
    assert state.current_stage_name == "LITERATURE_SCREEN"
    assert state.schema_version == 0


def test_fresh_iso_heartbeat_is_active(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    _write_checkpoint(run_dir)
    _write_heartbeat(run_dir, _iso())

    state = read_run_state(run_dir)

    assert state.is_active is True
    assert state.status is RunStatus.RUNNING


def test_stale_heartbeat_with_hitl_waiting_is_paused(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    _write_checkpoint(run_dir, hitl={"state": "waiting_human"})
    _write_heartbeat(run_dir, _iso(-3600))

    state = read_run_state(run_dir)

    assert state.is_active is False
    assert state.status is RunStatus.PAUSED


def test_stale_heartbeat_without_hitl_is_unknown(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    _write_checkpoint(run_dir)
    _write_heartbeat(run_dir, _iso(-3600))

    state = read_run_state(run_dir)

    assert state.is_active is False
    assert state.status is RunStatus.UNKNOWN


def test_epoch_heartbeat_is_supported(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    _write_checkpoint(run_dir)
    _write_heartbeat(run_dir, datetime.now(timezone.utc).timestamp())

    state = read_run_state(run_dir)

    assert state.is_active is True


def test_future_heartbeat_is_not_active(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    _write_checkpoint(run_dir)
    _write_heartbeat(run_dir, _iso(3600))

    state = read_run_state(run_dir)

    assert state.is_active is False


def test_missing_and_corrupt_files_do_not_raise(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    (run_dir / "checkpoint.json").write_text("{not json", encoding="utf-8")
    (run_dir / "heartbeat.json").write_text("{not json", encoding="utf-8")

    state = read_run_state(run_dir)

    assert state.current_stage == 0
    assert state.current_stage_name == ""
    assert state.status is RunStatus.UNKNOWN
    assert state.is_active is False


def test_completed_summary_overrides_heartbeat(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    _write_checkpoint(run_dir)
    _write_heartbeat(run_dir, _iso())
    (run_dir / "pipeline_summary.json").write_text(
        json.dumps({"run_id": run_dir.name, "final_status": "done"}),
        encoding="utf-8",
    )

    state = read_run_state(run_dir)

    assert state.status is RunStatus.COMPLETED


def test_failed_summary_maps_to_failed(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    _write_checkpoint(run_dir)
    (run_dir / "pipeline_summary.json").write_text(
        json.dumps({"run_id": run_dir.name, "final_status": "failed"}),
        encoding="utf-8",
    )

    state = read_run_state(run_dir)

    assert state.status is RunStatus.FAILED


@pytest.mark.parametrize("status_value", ["blocked_approval", "paused", "rejected"])
def test_blocking_summary_maps_to_paused(tmp_path: Path, status_value: str) -> None:
    run_dir = _make_run(tmp_path)
    _write_checkpoint(run_dir)
    (run_dir / "pipeline_summary.json").write_text(
        json.dumps({"run_id": run_dir.name, "final_status": status_value}),
        encoding="utf-8",
    )

    state = read_run_state(run_dir)

    assert state.status is RunStatus.PAUSED


def test_topic_falls_back_to_goal_file(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    _write_checkpoint(run_dir)
    stage_dir = run_dir / "stage-01"
    stage_dir.mkdir()
    (stage_dir / "goal.md").write_text("# Sparse mixture-of-experts routing\nbody\n", encoding="utf-8")

    state = read_run_state(run_dir)

    assert "Sparse mixture-of-experts routing" in state.topic


def test_topic_falls_back_to_run_id(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    _write_checkpoint(run_dir)

    state = read_run_state(run_dir)

    assert state.topic == run_dir.name


def test_artifacts_list_stage_directories(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    _write_checkpoint(run_dir)
    (run_dir / "stage-01").mkdir()
    (run_dir / "stage-02").mkdir()

    state = read_run_state(run_dir)

    assert state.artifacts == ("stage-01", "stage-02")


def test_to_dict_is_json_serialisable(tmp_path: Path) -> None:
    run_dir = _make_run(tmp_path)
    _write_checkpoint(run_dir)
    _write_heartbeat(run_dir, _iso())

    payload = read_run_state(run_dir).to_dict()

    assert payload["status"] == "running"
    assert payload["current_stage"] == 12
    assert json.loads(json.dumps(payload))["run_id"] == run_dir.name
