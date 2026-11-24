"""P-146: pipeline-skill manifest export, validation and discovery."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from researchclaw.runtime.action_ledger import ActionLedger
from researchclaw.runtime.event_log import EventLog, canonical_json
from researchclaw.skills.pipeline_manifest import (
    MANIFEST_NAME,
    ManifestExportError,
    export_manifest,
    load_pipeline_skill,
    validate_manifest,
)


def _build_run(tmp_path: Path, *, fail: bool = False, stage23: bool = True,
               retries: int = 0, complete: bool = True) -> Path:
    run = tmp_path / "run-1"
    run.mkdir()
    log = EventLog(run, "run-1")
    log.append("run.started", {})
    start_seq = log.append("stage.started", {"stage": 1, "name": "topic_init"}, stage=1).seq
    for _ in range(retries):
        log.append("stage.retried", {"stage": 1}, stage=1)
    ledger = ActionLedger(run, "run-1")
    out = run / "out.txt"
    out.write_text("ok", encoding="utf-8")
    ledger.record("echo", {"q": "x"}, outputs=[out], env={"CUDA_VISIBLE_DEVICES": "0"},
                  event_seq_call=start_seq)
    log.append("stage.completed", {"stage": 1, "name": "topic_init"}, stage=1)
    if fail:
        log.append("stage.failed", {"stage": 2, "error": "boom"}, stage=2)
    if stage23:
        log.append("stage.started", {"stage": 23, "name": "citation_verify"}, stage=23)
        log.append("stage.completed", {"stage": 23, "name": "citation_verify"}, stage=23)
    if complete:
        log.append("run.completed", {})
    (run / "pipeline_summary.json").write_text('{"ok":true}', encoding="utf-8")
    return run


def _reseal(manifest: dict) -> dict:
    body = {k: v for k, v in manifest.items() if k != "integrity"}
    digest = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
    manifest["integrity"] = {"algorithm": "sha256", "manifest_sha256": "sha256:" + digest}
    return manifest


def test_export_writes_manifest_and_skill_md(tmp_path: Path) -> None:
    run = _build_run(tmp_path)
    skill = tmp_path / "skills" / "pipeline-exp"
    manifest = export_manifest(run, skill, name="pipeline-exp", description="demo",
                               tool_versions={"echo": "1.0"})
    assert manifest["manifest_version"] == 1
    assert manifest["kind"] == "pipeline-skill"
    assert [s["stage"] for s in manifest["stages"]] == [1, 23]
    assert manifest["stages"][0]["actions"]
    assert manifest["stages"][0]["outputs"] == {"out.txt": "sha256:" + hashlib.sha256(b"ok").hexdigest()}
    assert manifest["env_keys"] == ["CUDA_VISIBLE_DEVICES"]
    assert manifest["success"]["run_id"] == "run-1"
    assert (skill / MANIFEST_NAME).is_file()
    header = yaml.safe_load((skill / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[1])
    assert header["metadata"]["kind"] == "pipeline"
    assert header["metadata"]["manifest"] == MANIFEST_NAME


def test_export_requires_run_completed(tmp_path: Path) -> None:
    run = _build_run(tmp_path, complete=False)
    with pytest.raises(ManifestExportError, match="run.completed"):
        export_manifest(run, tmp_path / "s", name="pipeline-x")


def test_export_rejects_stage_failure(tmp_path: Path) -> None:
    run = _build_run(tmp_path, fail=True)
    with pytest.raises(ManifestExportError, match="stage.failed"):
        export_manifest(run, tmp_path / "s", name="pipeline-x")


def test_export_requires_stage_23(tmp_path: Path) -> None:
    run = _build_run(tmp_path, stage23=False)
    with pytest.raises(ManifestExportError, match="stage 23"):
        export_manifest(run, tmp_path / "s", name="pipeline-x")


def test_retries_fold_into_attempts(tmp_path: Path) -> None:
    run = _build_run(tmp_path, retries=2)
    manifest = export_manifest(run, tmp_path / "s", name="pipeline-x", tool_versions={"echo": "1.0"})
    assert manifest["stages"][0]["attempts"] == 3


def test_validate_integrity_detects_tamper(tmp_path: Path) -> None:
    run = _build_run(tmp_path)
    manifest = export_manifest(run, tmp_path / "s", name="pipeline-x", tool_versions={"echo": "1.0"})
    manifest["success"]["run_id"] = "other-run"
    errors, _ = validate_manifest(manifest, tool_versions={"echo": "1.0"})
    assert any("manifest_sha256" in e for e in errors)


def test_validate_rejects_stage_map_drift(tmp_path: Path) -> None:
    run = _build_run(tmp_path)
    manifest = export_manifest(run, tmp_path / "s", name="pipeline-x", tool_versions={"echo": "1.0"})
    errors, _ = validate_manifest(manifest, stage_map={"1": "renamed"}, tool_versions={"echo": "1.0"})
    assert any("stage_map" in e for e in errors)


def test_validate_unknown_tool_and_version_drift(tmp_path: Path) -> None:
    run = _build_run(tmp_path)
    manifest = export_manifest(run, tmp_path / "s", name="pipeline-x", tool_versions={"echo": "1.0"})

    bad = _reseal(json.loads(json.dumps(manifest)))
    bad["tools"] = [{"name": "nope", "version": "1.0"}]
    _reseal(bad)
    errors, _ = validate_manifest(bad, tool_versions={"echo": "1.0"})
    assert any("unknown tool" in e for e in errors)

    drift = _reseal(json.loads(json.dumps(manifest)))
    drift["tools"] = [{"name": "echo", "version": "9.9"}]
    _reseal(drift)
    errors, warnings = validate_manifest(drift, tool_versions={"echo": "1.0"})
    assert not errors and any("version drift" in w for w in warnings)


def test_validate_rejects_absolute_output_path(tmp_path: Path) -> None:
    run = _build_run(tmp_path)
    manifest = export_manifest(run, tmp_path / "s", name="pipeline-x", tool_versions={"echo": "1.0"})
    manifest["stages"][0]["outputs"] = {"C:/windows/x": "sha256:00"}
    _reseal(manifest)
    errors, _ = validate_manifest(manifest, tool_versions={"echo": "1.0"})
    assert any("relative" in e for e in errors)


def test_loader_discovers_and_accepts(tmp_path: Path) -> None:
    run = _build_run(tmp_path)
    skill = tmp_path / "s"
    manifest = export_manifest(run, skill, name="pipeline-x", tool_versions={"echo": "1.0"})
    manifest["tools"] = []
    _reseal(manifest)
    (skill / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    loaded, errors = load_pipeline_skill(skill)
    assert errors == []
    assert loaded is not None and loaded["name"] == "pipeline-x"
