"""G3 M4: run mandate, handback scope and prompt versioning tests (A3-6..A3-8)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

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
)


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
