"""G3 M4: run mandate, handback scope and prompt versioning tests (A3-6..A3-8)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from researchclaw.pipeline.runner import _apply_handback_guard
from researchclaw.pipeline.stages import Stage, StageStatus
from researchclaw.pipeline._helpers import StageResult
from researchclaw.prompts import PromptManager
from researchclaw.runtime.mandate import (
    E_HANDBACK_SCOPE,
    HandbackScopeError,
    MandateError,
    StageHandback,
    ensure_run_mandate,
    prompt_version,
    read_handback,
    write_handback,
    write_handback_file,
)
from researchclaw.runtime.prompt_context import get_prompt_version


def test_mandate_is_written_once_and_immutable(tmp_path: Path) -> None:
    first = ensure_run_mandate(tmp_path, run_id="run-a", created_at="2026-11-13T00:00:00+00:00")
    second = ensure_run_mandate(tmp_path, run_id="run-a")
    assert first == second
    data = json.loads((tmp_path / "run_mandate.json").read_text(encoding="utf-8"))
    assert data["run_id"] == "run-a"
    assert data["created_at"] == "2026-11-13T00:00:00+00:00"
    assert "stage:1-23" in data["scope"]
    assert data["strength"] == "write"


def test_mandate_rejects_other_run_id(tmp_path: Path) -> None:
    ensure_run_mandate(tmp_path, run_id="run-a")
    with pytest.raises(MandateError):
        ensure_run_mandate(tmp_path, run_id="run-b")


def test_handback_in_scope_roundtrips(tmp_path: Path) -> None:
    mandate = ensure_run_mandate(tmp_path, run_id="run-a")
    stage_dir = tmp_path / "stage-07"
    handback = StageHandback(
        reason="needs review",
        evidence=("stage-07/report.json",),
        requested_scope=("stage:1-23",),
    )
    path = write_handback(stage_dir, handback, mandate)
    assert path.is_file()
    assert read_handback(stage_dir) == handback


def test_handback_out_of_scope_is_rejected(tmp_path: Path) -> None:
    mandate = ensure_run_mandate(tmp_path, run_id="run-a")
    handback = StageHandback(
        reason="needs shell",
        requested_scope=("tool:shell",),
    )
    with pytest.raises(HandbackScopeError) as excinfo:
        write_handback(tmp_path / "stage-07", handback, mandate)
    assert E_HANDBACK_SCOPE in str(excinfo.value)
    assert not (tmp_path / "stage-07" / "handback.json").exists()


def test_handback_stage_subrange_is_covered(tmp_path: Path) -> None:
    mandate = ensure_run_mandate(tmp_path, run_id="run-a")
    handback = StageHandback(
        reason="rerun experiment",
        requested_scope=("stage:12-14",),
    )
    path = write_handback(tmp_path / "stage-17", handback, mandate)
    assert path.is_file()


def test_handback_single_stage_is_covered(tmp_path: Path) -> None:
    mandate = ensure_run_mandate(tmp_path, run_id="run-a")
    write_handback(
        tmp_path / "stage-05",
        StageHandback(reason="single stage", requested_scope=("stage:5",)),
        mandate,
    )


def test_handback_subrange_outside_mandate_is_rejected(tmp_path: Path) -> None:
    mandate = ensure_run_mandate(
        tmp_path, run_id="run-a", scope=("stage:1-11",)
    )
    with pytest.raises(HandbackScopeError) as excinfo:
        write_handback(
            tmp_path / "stage-12",
            StageHandback(reason="too far", requested_scope=("stage:12-14",)),
            mandate,
        )
    assert "stage:12-14" in str(excinfo.value)


def test_handback_unknown_scope_format_is_rejected(tmp_path: Path) -> None:
    mandate = ensure_run_mandate(tmp_path, run_id="run-a")
    with pytest.raises(HandbackScopeError):
        write_handback(
            tmp_path / "stage-03",
            StageHandback(reason="bad format", requested_scope=("stage:1-x",)),
            mandate,
        )


def test_handback_requires_reason(tmp_path: Path) -> None:
    mandate = ensure_run_mandate(tmp_path, run_id="run-a")
    with pytest.raises(HandbackScopeError):
        write_handback(
            tmp_path / "stage-07",
            StageHandback(reason="  ", requested_scope=("stage:1-23",)),
            mandate,
        )


def test_prompt_version_is_deterministic_and_sensitive() -> None:
    kwargs = dict(
        system="sys",
        user_template="user {x}",
        model_role="paper_draft",
        prompt_bank_version="1.0",
    )
    first = prompt_version(**kwargs)
    assert first == prompt_version(**kwargs)
    assert first.startswith("sha256:")
    changed = dict(kwargs, system="sys2")
    assert prompt_version(**changed) != first


def test_rendered_prompt_carries_version() -> None:
    pm = PromptManager()
    first = pm.for_stage("export_publish", revised="draft")
    second = pm.for_stage("export_publish", revised="draft")
    assert first.version.startswith("sha256:")
    assert first.version == second.version
    # Version identifies the template/role, not the interpolated variables.
    assert pm.for_stage("export_publish", revised="other").version == first.version


def test_for_stage_sets_request_context_version() -> None:
    pm = PromptManager()
    rendered = pm.for_stage("export_publish", revised="draft")
    assert get_prompt_version() == rendered.version


def test_mandate_survives_config_change(tmp_path: Path) -> None:
    first = ensure_run_mandate(
        tmp_path, run_id="run-a", created_at="2026-11-13T00:00:00+00:00"
    )
    (tmp_path / "config.yaml").write_text(
        "experiment:\n  mode: docker\n", encoding="utf-8"
    )
    assert ensure_run_mandate(tmp_path, run_id="run-a") == first


def test_runner_guard_rejects_out_of_scope_handback(tmp_path: Path) -> None:
    mandate = ensure_run_mandate(tmp_path, run_id="run-a")
    stage_dir = tmp_path / "stage-01"
    stage_dir.mkdir()
    write_handback_file(
        stage_dir,
        StageHandback(reason="needs shell", requested_scope=("tool:shell",)),
    )
    result = StageResult(
        stage=Stage.TOPIC_INIT, status=StageStatus.PAUSED, artifacts=()
    )
    guarded = _apply_handback_guard(tmp_path, 1, result, mandate)
    assert guarded.status == StageStatus.FAILED
    assert E_HANDBACK_SCOPE in (guarded.error or "")
