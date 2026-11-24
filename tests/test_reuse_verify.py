"""P-147: ledger query CLI and manifest reproducibility verification."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from researchclaw.runtime.action_ledger import ActionLedger, query_actions
from researchclaw.runtime.event_log import EventLog
from researchclaw.skills.pipeline_manifest import export_manifest
from researchclaw.skills.reproducibility import verify_reproducibility


def _build_run(tmp_path: Path) -> Path:
    run = tmp_path / "run-1"
    run.mkdir()
    log = EventLog(run, "run-1")
    log.append("run.started", {})
    start = log.append("stage.started", {"stage": 1, "name": "topic_init"}, stage=1).seq
    ledger = ActionLedger(run, "run-1")
    out = run / "out.txt"
    out.write_text("ok", encoding="utf-8")
    rec = ledger.record("echo", {"q": "x"}, outputs=[out],
                        env={"CUDA_VISIBLE_DEVICES": "0"}, event_seq_call=start)
    log.append("stage.completed", {"stage": 1, "name": "topic_init"}, stage=1)
    log.append("stage.started", {"stage": 23, "name": "citation_verify"}, stage=23)
    log.append("stage.completed", {"stage": 23, "name": "citation_verify"}, stage=23)
    log.append("run.completed", {})
    (run / "pipeline_summary.json").write_text('{"ok":true}', encoding="utf-8")
    return run, rec


def _reseal(manifest: dict) -> dict:
    from researchclaw.runtime.event_log import canonical_json

    body = {k: v for k, v in manifest.items() if k != "integrity"}
    digest = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
    manifest["integrity"] = {"algorithm": "sha256", "manifest_sha256": "sha256:" + digest}
    return manifest


def _reseal_tools_empty(skill: Path) -> None:
    """CLI path loads via the strict loader against the real registry; the
    fixture's synthetic tool would be rejected, so clear tools and reseal."""
    path = skill / "pipeline.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["tools"] = []
    path.write_text(json.dumps(_reseal(manifest), indent=2), encoding="utf-8")


def _export(tmp_path: Path, run: Path) -> tuple[Path, dict]:
    skill = tmp_path / "skill"
    manifest = export_manifest(run, skill, name="pipeline-x", tool_versions={"echo": "1.0"})
    return skill, manifest


class TestQueryActions:
    def test_query_all(self, tmp_path: Path) -> None:
        run, rec = _build_run(tmp_path)
        rows = query_actions(run)
        assert len(rows) == 1
        assert rows[0]["action_id"] == rec.action_id
        assert rows[0]["tool"] == "echo"

    def test_filters(self, tmp_path: Path) -> None:
        run, _ = _build_run(tmp_path)
        assert query_actions(run, tool="echo") and query_actions(run, tool="other") == []
        assert query_actions(run, status="ok") and query_actions(run, status="error") == []
        assert query_actions(run, limit=0) == []


class TestVerifyReproducibility:
    def test_passes_on_intact_run(self, tmp_path: Path) -> None:
        run, _ = _build_run(tmp_path)
        _, manifest = _export(tmp_path, run)
        report = verify_reproducibility(manifest, run)
        assert report["reproducible"] is True
        assert report["chain_ok"] is True
        assert report["missing_outputs"] == []
        assert report["unresolved_actions"] == []

    def test_is_read_only(self, tmp_path: Path) -> None:
        run, _ = _build_run(tmp_path)
        _, manifest = _export(tmp_path, run)
        before = {p.name: p.stat().st_mtime for p in run.rglob("*") if p.is_file()}
        verify_reproducibility(manifest, run)
        after = {p.name: p.stat().st_mtime for p in run.rglob("*") if p.is_file()}
        assert before == after

    def test_detects_hash_mismatch(self, tmp_path: Path) -> None:
        run, _ = _build_run(tmp_path)
        _, manifest = _export(tmp_path, run)
        (run / "out.txt").write_text("tampered", encoding="utf-8")
        report = verify_reproducibility(manifest, run)
        assert report["reproducible"] is False
        assert report["hash_mismatches"] and report["hash_mismatches"][0]["path"] == "out.txt"

    def test_detects_missing_output(self, tmp_path: Path) -> None:
        run, _ = _build_run(tmp_path)
        _, manifest = _export(tmp_path, run)
        (run / "out.txt").unlink()
        report = verify_reproducibility(manifest, run)
        assert report["reproducible"] is False
        assert "out.txt" in report["missing_outputs"]

    def test_detects_unresolved_action(self, tmp_path: Path) -> None:
        run, _ = _build_run(tmp_path)
        _, manifest = _export(tmp_path, run)
        manifest["stages"][0]["actions"].append("deadbeef")
        report = verify_reproducibility(manifest, run)
        assert report["reproducible"] is False
        assert "deadbeef" in report["unresolved_actions"]

    def test_detects_broken_chain(self, tmp_path: Path) -> None:
        run, _ = _build_run(tmp_path)
        _, manifest = _export(tmp_path, run)
        # EventLog tolerates a torn *tail* line by design; corrupt an existing
        # record instead so the recomputed payload digest diverges.
        path = run / "events.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        rec = json.loads(lines[0])
        rec["payload"] = {"forged": True}
        lines[0] = json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        report = verify_reproducibility(manifest, run)
        assert report["reproducible"] is False
        assert report["chain_ok"] is False

    def test_empty_manifest_fails_closed(self, tmp_path: Path) -> None:
        run, _ = _build_run(tmp_path)
        report = verify_reproducibility({"manifest_version": 1, "kind": "pipeline-skill",
                                         "stages": []}, run)
        assert report["reproducible"] is False
        assert report["checks"] == 0


class TestCli:
    def _main(self, *argv: str) -> tuple[int, str]:
        import io
        import contextlib
        from researchclaw import cli

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.main(list(argv))
        return code, buf.getvalue()

    def test_actions_cli_filters(self, tmp_path: Path) -> None:
        run, _ = _build_run(tmp_path)
        code, out = self._main("actions", "--run-dir", str(run), "--json")
        assert code == 0
        data = json.loads(out)
        assert data[0]["tool"] == "echo"

        code, out = self._main("actions", "--run-dir", str(run), "--tool", "other")
        assert code == 0 and out.strip() == ""

    def test_verify_cli_pass_and_drift(self, tmp_path: Path) -> None:
        run, _ = _build_run(tmp_path)
        skill, _ = _export(tmp_path, run)
        _reseal_tools_empty(skill)
        code, out = self._main("pipeline-skill", "verify", "--skill-dir", str(skill),
                               "--run-dir", str(run), "--json")
        assert code == 0
        assert json.loads(out)["reproducible"] is True

        (run / "out.txt").write_text("tampered", encoding="utf-8")
        code, out = self._main("pipeline-skill", "verify", "--skill-dir", str(skill),
                               "--run-dir", str(run))
        assert code == 1
        assert "HASH MISMATCH" in out or "hash_mismatch" in out.lower()

    def test_verify_cli_unusable_input(self, tmp_path: Path) -> None:
        run, _ = _build_run(tmp_path)
        code, _ = self._main("pipeline-skill", "verify", "--skill-dir",
                             str(tmp_path / "nope"), "--run-dir", str(run))
        assert code == 2
        code, _ = self._main("pipeline-skill", "verify", "--skill-dir",
                             str(tmp_path / "s2"), "--run-dir", str(tmp_path / "gone"))
        assert code == 2
