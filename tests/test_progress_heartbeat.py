"""B-31b/B-33 M2: in-stage heartbeat and step-level progress."""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

from researchclaw.config import CodeAgentConfig
from researchclaw.pipeline.code_agent import CodeAgent
from researchclaw.pipeline.step_journal import append_step, load_steps
from researchclaw.run_state import RunStatus, read_run_state
from researchclaw.runtime.progress import HEARTBEAT_NAME, ProgressKeeper


def _read_heartbeat(run_dir: Path) -> dict:
    return json.loads((run_dir / HEARTBEAT_NAME).read_text(encoding="utf-8"))


def _write_checkpoint(run_dir: Path, **overrides: object) -> None:
    payload = {
        "last_completed_stage": 9,
        "last_completed_name": "RESOURCE_PLANNING",
        "run_id": run_dir.name,
        "timestamp": "2026-11-26T16:00:00+00:00",
    }
    payload.update(overrides)
    (run_dir / "checkpoint.json").write_text(
        json.dumps(payload), encoding="utf-8",
    )


def _write_heartbeat(
    run_dir: Path, *, seconds_ago: float, **extra: object,
) -> None:
    ts = time.time() - seconds_ago
    payload = {
        "pid": 4242,
        "run_id": run_dir.name,
        "stage": 10,
        "stage_name": "CODE_GENERATION",
        "last_stage": 10,
        "last_stage_name": "CODE_GENERATION",
        "status": "running",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(ts)),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(ts)),
        "interval_sec": 30,
        "stale_after_sec": 300,
    }
    payload.update(extra)
    (run_dir / HEARTBEAT_NAME).write_text(
        json.dumps(payload), encoding="utf-8",
    )


class TestProgressKeeper:
    def test_start_writes_heartbeat_immediately(self, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage-10"
        stage_dir.mkdir()
        keeper = ProgressKeeper(
            tmp_path, "run-1", 10, "CODE_GENERATION", stage_dir=stage_dir,
            interval=0.5,
        ).start()
        try:
            payload = _read_heartbeat(tmp_path)
            assert payload["run_id"] == "run-1"
            assert payload["stage"] == 10
            assert payload["stage_name"] == "CODE_GENERATION"
            assert payload["status"] == "running"
            assert payload["updated_at"] == payload["timestamp"]
            assert payload["interval_sec"] == 0.5
            assert payload["last_stage"] == 10
        finally:
            keeper.stop()

    def test_heartbeat_projects_last_journal_step(self, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage-10"
        stage_dir.mkdir()
        append_step(stage_dir, step_id="blueprint", variant="retry", status="done")
        append_step(
            stage_dir, step_id="generate_file", variant="data.py",
            status="done", outputs={"data.py": "sha256:x"},
        )
        keeper = ProgressKeeper(
            tmp_path, "run-1", 10, "CODE_GENERATION", stage_dir=stage_dir,
            interval=0.5,
        ).start()
        try:
            payload = _read_heartbeat(tmp_path)
            assert payload["last_step"] == "generate_file:data.py"
            assert payload["last_step_status"] == "done"
            assert payload["phase"] == "generate"
            assert payload["steps_done"] == 2
        finally:
            keeper.stop()

    def test_heartbeat_refreshes_after_interval(self, tmp_path: Path) -> None:
        stage_dir = tmp_path / "stage-10"
        stage_dir.mkdir()
        keeper = ProgressKeeper(
            tmp_path, "run-1", 10, "CODE_GENERATION", stage_dir=stage_dir,
            interval=0.02,
        ).start()
        try:
            first = _read_heartbeat(tmp_path)["updated_at"]
            deadline = time.time() + 2.0
            second = first
            while time.time() < deadline and second == first:
                time.sleep(0.02)
                second = _read_heartbeat(tmp_path)["updated_at"]
            assert second >= first
        finally:
            keeper.stop()

    def test_write_failure_is_not_fatal(self, tmp_path: Path) -> None:
        blocker = tmp_path / "not-a-dir"
        blocker.write_text("x", encoding="utf-8")
        keeper = ProgressKeeper(
            blocker, "run-1", 10, "CODE_GENERATION", interval=0.02,
        ).start()
        keeper.stop()


class TestRunStateStalled:
    def test_stale_heartbeat_with_in_progress_is_stalled(
        self, tmp_path: Path,
    ) -> None:
        run_dir = tmp_path / "rc-stalled"
        run_dir.mkdir()
        _write_checkpoint(run_dir, in_progress_stage=10,
                          in_progress_name="CODE_GENERATION")
        _write_heartbeat(run_dir, seconds_ago=3600)

        state = read_run_state(run_dir)

        assert state.status is RunStatus.STALLED
        assert state.is_active is False
        assert state.silence_sec >= 3600

    def test_stale_heartbeat_without_in_progress_stays_unknown(
        self, tmp_path: Path,
    ) -> None:
        run_dir = tmp_path / "rc-old"
        run_dir.mkdir()
        _write_checkpoint(run_dir)
        _write_heartbeat(run_dir, seconds_ago=3600)

        state = read_run_state(run_dir)

        assert state.status is RunStatus.UNKNOWN

    def test_interval_extends_the_liveness_window(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "rc-live"
        run_dir.mkdir()
        _write_checkpoint(run_dir, in_progress_stage=10)
        _write_heartbeat(run_dir, seconds_ago=120, interval_sec=30)

        state = read_run_state(run_dir)

        # 3 * 30 = 90s would be too strict; the default 300s floor wins.
        assert state.status is RunStatus.RUNNING
        assert state.is_active is True
        assert 120 <= state.silence_sec < 180

    def test_to_dict_carries_silence(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "rc-dict"
        run_dir.mkdir()
        _write_checkpoint(run_dir)
        _write_heartbeat(run_dir, seconds_ago=0)

        payload = read_run_state(run_dir).to_dict()

        assert "silence_sec" in payload
        assert payload["silence_sec"] >= 0


class _FakePM:
    def sub_prompt(self, name, **kwargs):  # noqa: ANN001
        return SimpleNamespace(
            system="sys", user=json.dumps(kwargs, default=str), version="test",
        )

    def system(self, name):  # noqa: ANN001
        return "sys"


class _FakeLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def chat(self, messages, **kwargs):  # noqa: ANN001, ANN003
        self.calls.append({"messages": messages, **kwargs})
        idx = min(len(self.calls) - 1, len(self._responses) - 1)
        return SimpleNamespace(
            content=self._responses[idx],
            truncated=False,
            finish_reason="stop",
            model="fake",
            total_tokens=0,
        )


def _fenced(code: str) -> str:
    return f"```python\n{code}```\n"


def _agent(tmp_path: Path, llm, **overrides) -> CodeAgent:
    cfg = CodeAgentConfig(
        review_max_rounds=0,
        hard_validation=False,
        exec_fix_max_iterations=0,
        **overrides,
    )
    return CodeAgent(
        llm=llm, prompts=_FakePM(), config=cfg, stage_dir=tmp_path,
    )


MAIN_OK = '''def main() -> None:
    print("METRIC_DEF: auroc | direction=higher")
    print("auroc: 0.7")


if __name__ == "__main__":
    main()
'''


class TestCodeAgentStepJournal:
    def test_each_generated_module_is_journalled(self, tmp_path: Path) -> None:
        llm = _FakeLLM([_fenced("X = 1\n"), _fenced("Y = 2\n")])
        agent = _agent(tmp_path, llm)
        blueprint = {"files": [
            {"name": "a.py", "generation_order": 1},
            {"name": "b.py", "generation_order": 2},
        ]}

        files = agent._phase2_sequential_generate(
            "topic", "plan", "auroc", "", "", blueprint,
        )

        assert sorted(files) == ["a.py", "b.py"]
        rows = [r for r in load_steps(tmp_path) if r["step_id"] == "generate_file"]
        assert [r["variant"] for r in rows] == ["a.py", "b.py"]
        assert all(r["status"] == "done" for r in rows)
        assert all(r["outputs"] for r in rows)

    def test_dedicated_entrypoint_is_journalled(self, tmp_path: Path) -> None:
        llm = _FakeLLM([_fenced("X = 1\n"), _fenced(MAIN_OK)])
        agent = _agent(tmp_path, llm)
        blueprint = {"files": [{"name": "a.py", "generation_order": 1}]}

        files = agent._phase2_sequential_generate(
            "topic", "plan", "auroc", "", "", blueprint,
        )

        assert "main.py" in files
        rows = [r for r in load_steps(tmp_path) if r["step_id"] == "entrypoint"]
        assert rows and rows[-1]["variant"] == "dedicated"
        assert rows[-1]["outputs"]

    def test_hard_validation_round_is_journalled(self, tmp_path: Path) -> None:
        agent = _agent(tmp_path, _FakeLLM([_fenced("X = 1\n")]),
                       hard_validation_max_repairs=0)

        agent._hard_validate_and_repair(
            {"a.py": "X = 1\n"}, "topic", "plan", "auroc", "", "",
        )

        rows = [r for r in load_steps(tmp_path) if r["step_id"] == "hard_validation"]
        assert len(rows) == 1
        assert rows[0]["status"] == "done"
        assert rows[0]["outputs"] == {}

    def test_failed_hard_validation_is_journalled(self, tmp_path: Path) -> None:
        agent = _agent(tmp_path, _FakeLLM([_fenced("X = 1\n")]),
                       hard_validation_max_repairs=0)

        agent._hard_validate_and_repair(
            {"a.py": "def broken(:\n"}, "topic", "plan", "auroc", "", "",
        )

        rows = [r for r in load_steps(tmp_path) if r["step_id"] == "hard_validation"]
        assert rows and rows[-1]["status"] == "failed"

    def test_progress_rows_are_never_reusable(self, tmp_path: Path) -> None:
        from researchclaw.pipeline.step_journal import last_done, should_skip

        agent = _agent(tmp_path, _FakeLLM([_fenced("X = 1\n")]),
                       hard_validation_max_repairs=0)
        agent._hard_validate_and_repair(
            {"a.py": "X = 1\n"}, "topic", "plan", "auroc", "", "",
        )

        last = last_done(load_steps(tmp_path), "hard_validation", "attempt-0")
        assert last is not None
        assert should_skip(
            last, inputs_digest=last["inputs_digest"], files_on_disk={},
        ) is False
