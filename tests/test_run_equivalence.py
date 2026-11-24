"""P-149: rerun equivalence comparator and the deterministic double-run check."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from researchclaw.evidence.run_equivalence import compare_runs
from researchclaw.runtime.action_ledger import ActionLedger
from researchclaw.runtime.event_log import EventLog


def _build_run(
    root: Path,
    name: str,
    *,
    stage_23: bool = True,
    stage_23_failed: bool = False,
    tool: str = "echo",
    params: dict | None = None,
    output: str = "ok",
    status: str = "ok",
) -> Path:
    """One deterministic fixture run; volatile fields vary by construction."""
    run = root / name
    run.mkdir(parents=True)
    log = EventLog(run, name, fsync=False)
    log.append("run.started", {})
    log.append("stage.started", {"stage": 1, "name": "topic_init"}, stage=1)
    ledger = ActionLedger(run, name, fsync=False)
    artifact = run / "out.txt"
    artifact.write_text(output, encoding="utf-8")
    ledger.record(
        tool,
        {"q": "x"} if params is None else params,
        outputs=[artifact],
        status=status,
        exit_code=0 if status == "ok" else 1,
        event_seq_call=2,
    )
    log.append("stage.completed", {"stage": 1, "name": "topic_init"}, stage=1)
    if stage_23_failed:
        log.append("stage.failed", {"stage": 23, "name": "citation_verify"}, stage=23)
    elif stage_23:
        log.append("stage.started", {"stage": 23, "name": "citation_verify"}, stage=23)
        log.append("stage.completed", {"stage": 23, "name": "citation_verify"}, stage=23)
    log.append("run.completed", {})
    (run / "pipeline_summary.json").write_text('{"ok":true}', encoding="utf-8")
    return run


def _tamper_event(run: Path) -> None:
    path = run / "events.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    record["payload"] = {"forged": True}
    lines[0] = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _tamper_action(run: Path) -> None:
    path = run / "actions.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    record["tool"] = "forged"
    path.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _kinds(report: dict) -> set[str]:
    return {item["kind"] for item in report["differences"]}


class TestCompareRuns:
    def test_identical_runs_are_equivalent(self, tmp_path: Path) -> None:
        left = _build_run(tmp_path, "run-a")
        right = _build_run(tmp_path, "run-b")
        report = compare_runs(left, right)
        assert report["equivalent"] is True
        assert report["differences"] == []
        assert report["checks"] == 8

    def test_detects_stage_sequence_difference(self, tmp_path: Path) -> None:
        left = _build_run(tmp_path, "run-a")
        right = _build_run(tmp_path, "run-b", stage_23=False)
        report = compare_runs(left, right)
        assert report["equivalent"] is False
        assert "stage_sequence" in _kinds(report)

    def test_detects_stage_failure(self, tmp_path: Path) -> None:
        left = _build_run(tmp_path, "run-a")
        right = _build_run(tmp_path, "run-b", stage_23_failed=True, stage_23=False)
        report = compare_runs(left, right)
        assert report["equivalent"] is False
        assert "stage_failures" in _kinds(report)

    def test_detects_tool_sequence_difference(self, tmp_path: Path) -> None:
        left = _build_run(tmp_path, "run-a")
        right = _build_run(tmp_path, "run-b", tool="python")
        report = compare_runs(left, right)
        assert report["equivalent"] is False
        assert _kinds(report) == {"tool_sequence"}

    def test_detects_params_difference(self, tmp_path: Path) -> None:
        left = _build_run(tmp_path, "run-a")
        right = _build_run(tmp_path, "run-b", params={"q": "y"})
        report = compare_runs(left, right)
        assert report["equivalent"] is False
        assert _kinds(report) == {"params_sequence"}

    def test_detects_status_difference(self, tmp_path: Path) -> None:
        left = _build_run(tmp_path, "run-a")
        right = _build_run(tmp_path, "run-b", status="error")
        report = compare_runs(left, right)
        assert report["equivalent"] is False
        assert _kinds(report) == {"status_sequence"}

    def test_detects_artifact_hash_difference(self, tmp_path: Path) -> None:
        left = _build_run(tmp_path, "run-a")
        right = _build_run(tmp_path, "run-b", output="tampered")
        report = compare_runs(left, right)
        assert report["equivalent"] is False
        diff = next(item for item in report["differences"] if item["kind"] == "artifacts")
        assert diff["changed"] == ["out.txt"]

    def test_volatile_fields_are_ignored(self, tmp_path: Path) -> None:
        # Different run_id, timestamps, action ids and absolute output paths
        # must not make two otherwise identical runs non-equivalent.
        left = _build_run(tmp_path / "one", "run-a")
        right = _build_run(tmp_path / "two", "run-b")
        assert compare_runs(left, right)["equivalent"] is True

    def test_detects_broken_event_chain(self, tmp_path: Path) -> None:
        left = _build_run(tmp_path, "run-a")
        right = _build_run(tmp_path, "run-b")
        _tamper_event(right)
        report = compare_runs(left, right)
        assert report["equivalent"] is False
        assert "event_chain" in _kinds(report)

    def test_detects_broken_action_chain(self, tmp_path: Path) -> None:
        left = _build_run(tmp_path, "run-a")
        right = _build_run(tmp_path, "run-b")
        _tamper_action(right)
        report = compare_runs(left, right)
        assert report["equivalent"] is False
        assert "action_chain" in _kinds(report)

    def test_empty_runs_fail_closed(self, tmp_path: Path) -> None:
        (tmp_path / "empty-a").mkdir()
        (tmp_path / "empty-b").mkdir()
        report = compare_runs(tmp_path / "empty-a", tmp_path / "empty-b")
        assert report["equivalent"] is False
        assert _kinds(report) == {"activity"}

    def test_missing_run_dir_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            compare_runs(tmp_path / "gone", tmp_path / "gone-too")

    def test_is_read_only(self, tmp_path: Path) -> None:
        left = _build_run(tmp_path, "run-a")
        right = _build_run(tmp_path, "run-b", output="tampered")
        before = {
            str(p): p.stat().st_mtime
            for run in (left, right)
            for p in run.rglob("*")
            if p.is_file()
        }
        compare_runs(left, right)
        after = {
            str(p): p.stat().st_mtime
            for run in (left, right)
            for p in run.rglob("*")
            if p.is_file()
        }
        assert before == after


class TestCli:
    def _main(self, *argv: str) -> tuple[int, str]:
        import contextlib
        import io

        from researchclaw import cli

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.main(list(argv))
        return code, buf.getvalue()

    def test_compare_reports_equivalent(self, tmp_path: Path) -> None:
        left = _build_run(tmp_path, "run-a")
        right = _build_run(tmp_path, "run-b")
        code, out = self._main(
            "runs", "compare", "--left", str(left), "--right", str(right), "--json"
        )
        assert code == 0
        assert json.loads(out)["equivalent"] is True

    def test_compare_exit_one_on_difference(self, tmp_path: Path) -> None:
        left = _build_run(tmp_path, "run-a")
        right = _build_run(tmp_path, "run-b", output="tampered")
        code, out = self._main("runs", "compare", "--left", str(left), "--right", str(right))
        assert code == 1
        assert "DIFFERENT" in out and "artifacts" in out

    def test_compare_exit_two_on_missing_dir(self, tmp_path: Path) -> None:
        left = _build_run(tmp_path, "run-a")
        code, _ = self._main(
            "runs", "compare", "--left", str(left), "--right", str(tmp_path / "gone")
        )
        assert code == 2
