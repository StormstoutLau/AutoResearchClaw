"""G3 M1 (P-075): pipeline_summary canonical form and sidecar check."""
from __future__ import annotations

import json
from pathlib import Path

from researchclaw.evidence.summary_check import (
    SIDECAR_NAME,
    SUMMARY_NAME,
    canonical_summary,
    summary_digest,
    verify_summary,
    write_summary,
)
from researchclaw.pipeline.runner import _write_pipeline_summary


def _summary() -> dict:
    return {
        "run_id": "run-1",
        "stages_executed": 3,
        "stages_done": 2,
        "stages_paused": 0,
        "stages_blocked": 0,
        "stages_failed": 1,
        "degraded": False,
        "from_stage": 1,
        "final_stage": 3,
        "final_status": "failed",
        "generated": "2026-11-11T00:00:00+00:00",
        "data_origin": "sandbox",
        "content_metrics": {},
    }


def test_write_and_verify_summary(tmp_path: Path) -> None:
    write_summary(tmp_path, _summary())
    assert (tmp_path / SUMMARY_NAME).is_file()
    assert (tmp_path / SIDECAR_NAME).is_file()
    result = verify_summary(tmp_path)
    assert result["ok"] is True
    assert result["errors"] == []
    assert result["digest"] == summary_digest(_summary())


def test_summary_is_canonical(tmp_path: Path) -> None:
    write_summary(tmp_path, _summary())
    raw = (tmp_path / SUMMARY_NAME).read_bytes()
    assert raw == canonical_summary(_summary()) + b"\n"
    first = canonical_summary(_summary())
    second = canonical_summary(dict(reversed(list(_summary().items()))))
    assert first == second


def test_tampered_summary_is_detected(tmp_path: Path) -> None:
    write_summary(tmp_path, _summary())
    path = tmp_path / SUMMARY_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["stages_failed"] = 0
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = verify_summary(tmp_path)
    assert result["ok"] is False
    assert any(e["code"] == "E_SUMMARY_TAMPERED" for e in result["errors"])


def test_missing_sidecar_is_detected(tmp_path: Path) -> None:
    (tmp_path / SUMMARY_NAME).write_text(json.dumps(_summary()), encoding="utf-8")
    result = verify_summary(tmp_path)
    assert result["ok"] is False
    assert any(e["code"] == "E_SUMMARY_TAMPERED" for e in result["errors"])


def test_missing_summary_is_detected(tmp_path: Path) -> None:
    result = verify_summary(tmp_path)
    assert result["ok"] is False
    assert result["errors"][0]["code"] == "E_SUMMARY_MISSING"


def test_require_event_without_anchor(tmp_path: Path) -> None:
    write_summary(tmp_path, _summary())
    result = verify_summary(tmp_path, require_event=True)
    assert result["ok"] is False
    assert any(e["code"] == "E_SUMMARY_EVENT_MISSING" for e in result["errors"])


def test_require_event_with_matching_anchor(tmp_path: Path) -> None:
    write_summary(tmp_path, _summary())
    digest = summary_digest(_summary())
    (tmp_path / "events.jsonl").write_text(
        json.dumps({"type": "pipeline.summary", "payload": {"digest": digest}}) + "\n",
        encoding="utf-8",
    )
    result = verify_summary(tmp_path, require_event=True)
    assert result["ok"] is True


def test_require_event_with_mismatched_anchor(tmp_path: Path) -> None:
    write_summary(tmp_path, _summary())
    (tmp_path / "events.jsonl").write_text(
        json.dumps({"type": "pipeline.summary", "payload": {"digest": "sha256:" + "0" * 64}}) + "\n",
        encoding="utf-8",
    )
    result = verify_summary(tmp_path, require_event=True)
    assert result["ok"] is False
    assert any(e["code"] == "E_SUMMARY_TAMPERED" for e in result["errors"])


def test_runner_writer_emits_sidecar(tmp_path: Path) -> None:
    _write_pipeline_summary(tmp_path, _summary())
    assert (tmp_path / SIDECAR_NAME).is_file()
    assert verify_summary(tmp_path)["ok"] is True
