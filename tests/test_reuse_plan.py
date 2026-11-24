"""P-148: sanitized config snapshot and reuse plan."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from researchclaw.runtime.action_ledger import ActionLedger
from researchclaw.runtime.event_log import EventLog, canonical_json
from researchclaw.skills.config_sanitizer import (
    SNAPSHOT_NAME,
    ConfigSanitizeError,
    sanitize_config,
    write_sanitized_snapshot,
)
from researchclaw.skills.pipeline_manifest import export_manifest, load_pipeline_skill


def _build_run(tmp_path: Path) -> Path:
    run = tmp_path / "run-1"
    run.mkdir()
    log = EventLog(run, "run-1")
    log.append("run.started", {})
    start = log.append("stage.started", {"stage": 1, "name": "topic_init"}, stage=1).seq
    ActionLedger(run, "run-1").record(
        "echo", {"q": "x"},
        outputs=[_write(run / "out.txt", "ok")], event_seq_call=start)
    log.append("stage.completed", {"stage": 1, "name": "topic_init"}, stage=1)
    log.append("stage.started", {"stage": 23, "name": "citation_verify"}, stage=23)
    log.append("stage.completed", {"stage": 23, "name": "citation_verify"}, stage=23)
    log.append("run.completed", {})
    _write(run / "pipeline_summary.json", '{"ok":true}')
    return run


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _config(tmp_path: Path) -> Path:
    payload = {
        "project": {"name": "demo", "output_dir": "C:/runs/demo"},
        "llm": {"api_key": "sk-live-secret", "api_key_env": "OPENAI_API_KEY",
                "model": "gpt-x"},
        "literature_search": {"s2_api_key": "s2-secret"},
        "experiment": {"ssh_remote": {"key_path": "~/.ssh/id_rsa"}},
    }
    return _write(tmp_path / "config.yaml", yaml.safe_dump(payload, sort_keys=False))


def _reseal(manifest: dict) -> dict:
    body = {k: v for k, v in manifest.items() if k != "integrity"}
    digest = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
    manifest["integrity"] = {"algorithm": "sha256", "manifest_sha256": "sha256:" + digest}
    return manifest


def _strip_tools(skill: Path) -> None:
    path = skill / "pipeline.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["tools"] = []
    path.write_text(json.dumps(_reseal(manifest), indent=2), encoding="utf-8")


class TestSanitizer:
    def test_redacts_secrets_and_paths(self, tmp_path: Path) -> None:
        data = yaml.safe_load(_config(tmp_path).read_text(encoding="utf-8"))
        cleaned, redacted = sanitize_config(data)
        assert cleaned["llm"]["api_key"] == "***REDACTED***"
        assert cleaned["literature_search"]["s2_api_key"] == "***REDACTED***"
        assert cleaned["project"]["output_dir"] == "<REDACTED_PATH>"
        assert cleaned["llm"]["api_key_env"] == "OPENAI_API_KEY"  # env name is not a secret
        assert "llm.api_key" in redacted
        assert "project.output_dir" in redacted

    def test_does_not_mutate_input(self, tmp_path: Path) -> None:
        data = yaml.safe_load(_config(tmp_path).read_text(encoding="utf-8"))
        sanitize_config(data)
        assert data["llm"]["api_key"] == "sk-live-secret"

    def test_rejects_non_mapping(self) -> None:
        with pytest.raises(ConfigSanitizeError):
            sanitize_config(["not", "a", "dict"])  # type: ignore[arg-type]

    def test_snapshot_has_no_secret_bytes(self, tmp_path: Path) -> None:
        meta = write_sanitized_snapshot(_config(tmp_path), tmp_path / "skill")
        text = (tmp_path / "skill" / SNAPSHOT_NAME).read_text(encoding="utf-8")
        assert "sk-live-secret" not in text
        assert "s2-secret" not in text
        assert "C:/runs/demo" not in text
        assert meta["sha256"].startswith("sha256:")


class TestExportV2:
    def test_export_with_config(self, tmp_path: Path) -> None:
        run = _build_run(tmp_path)
        skill = tmp_path / "skill"
        manifest = export_manifest(run, skill, name="pipeline-x",
                                   tool_versions={"echo": "1.0"},
                                   config_path=_config(tmp_path))
        assert manifest["manifest_version"] == 2
        assert manifest["config"]["pointer"] == SNAPSHOT_NAME
        assert (skill / SNAPSHOT_NAME).is_file()
        assert sorted(manifest["config"]["redacted_keys"]) == [
            "experiment.ssh_remote.key_path", "literature_search.s2_api_key",
            "llm.api_key", "project.output_dir"]

    def test_export_without_config_stays_v1(self, tmp_path: Path) -> None:
        run = _build_run(tmp_path)
        manifest = export_manifest(run, tmp_path / "s", name="pipeline-x",
                                   tool_versions={"echo": "1.0"})
        assert manifest["manifest_version"] == 1
        assert "config" not in manifest

    def test_loader_rejects_tampered_snapshot(self, tmp_path: Path) -> None:
        run = _build_run(tmp_path)
        skill = tmp_path / "skill"
        export_manifest(run, skill, name="pipeline-x", tool_versions={"echo": "1.0"},
                        config_path=_config(tmp_path))
        _strip_tools(skill)
        (skill / SNAPSHOT_NAME).write_text("project: {}\n", encoding="utf-8")
        loaded, errors = load_pipeline_skill(skill)
        assert loaded is None
        assert any("config snapshot hash mismatch" in e for e in errors)

    def test_v2_requires_config_block(self, tmp_path: Path) -> None:
        run = _build_run(tmp_path)
        skill = tmp_path / "skill"
        manifest = export_manifest(run, skill, name="pipeline-x",
                                   tool_versions={"echo": "1.0"},
                                   config_path=_config(tmp_path))
        manifest.pop("config")
        _reseal(manifest)
        (skill / "pipeline.json").write_text(json.dumps(manifest), encoding="utf-8")
        loaded, errors = load_pipeline_skill(skill)
        assert loaded is None
        assert any("config snapshot block is missing" in e for e in errors)


class TestPlanCli:
    def _main(self, *argv: str) -> tuple[int, str]:
        import contextlib
        import io

        from researchclaw import cli

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.main(list(argv))
        return code, buf.getvalue()

    def test_plan_v2(self, tmp_path: Path) -> None:
        run = _build_run(tmp_path)
        skill = tmp_path / "skill"
        export_manifest(run, skill, name="pipeline-x", tool_versions={"echo": "1.0"},
                        config_path=_config(tmp_path))
        _strip_tools(skill)
        code, out = self._main("pipeline-skill", "plan", "--skill-dir", str(skill), "--json")
        assert code == 0
        plan = json.loads(out)
        assert "researchclaw run --config" in plan["command"]
        assert plan["stages"] == [1, 23]
        assert plan["needs_manual_fill"] is True
        assert "llm.api_key" in plan["redacted_keys"]

    def test_plan_v1_rejected(self, tmp_path: Path) -> None:
        run = _build_run(tmp_path)
        skill = tmp_path / "skill"
        export_manifest(run, skill, name="pipeline-x", tool_versions={"echo": "1.0"})
        _strip_tools(skill)
        code, _ = self._main("pipeline-skill", "plan", "--skill-dir", str(skill))
        assert code == 2

    def test_plan_missing_dir(self, tmp_path: Path) -> None:
        code, _ = self._main("pipeline-skill", "plan", "--skill-dir", str(tmp_path / "nope"))
        assert code == 2
