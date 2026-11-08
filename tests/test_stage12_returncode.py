"""H-1: Stage 12 run payload must carry returncode and mode."""

from __future__ import annotations

from researchclaw.pipeline.stage_impls._execution import _build_run_payload


def test_payload_carries_returncode_and_mode() -> None:
    payload = _build_run_payload(
        mode="sandbox",
        status="failed",
        metrics={"accuracy": 0.9},
        elapsed_sec=1.25,
        returncode=3,
        timed_out=False,
        stdout="out",
        stderr="err",
    )
    assert payload["returncode"] == 3
    assert payload["mode"] == "sandbox"
    assert payload["task_id"] == "sandbox-main"
    assert payload["metrics"] == {"accuracy": 0.9}


def test_payload_keeps_zero_returncode() -> None:
    payload = _build_run_payload(
        mode="sandbox",
        status="completed",
        metrics={"accuracy": 0.5},
        elapsed_sec=2.0,
        returncode=0,
        timed_out=False,
        stdout="",
        stderr="",
    )
    assert payload["returncode"] == 0
    assert payload["status"] == "completed"


def test_payload_agent_mode_task_id() -> None:
    payload = _build_run_payload(
        mode="agent",
        status="completed",
        metrics={},
        elapsed_sec=0.1,
        returncode=0,
        timed_out=False,
        stdout="",
        stderr="",
    )
    assert payload["task_id"] == "agent-main"
    assert "returncode" in payload
