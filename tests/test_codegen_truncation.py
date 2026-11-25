"""P-178: Stage 10 truncation handling and entrypoint gate."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from researchclaw.config import CodeAgentConfig
from researchclaw.pipeline._helpers import (
    _close_unterminated_fence,
    _extract_code_block,
    _extract_multi_file_blocks,
)
from researchclaw.pipeline.code_agent import CodeAgent
from researchclaw.pipeline.stage_impls._code_generation import _entrypoint_issues

CONFIG_ONLY_MAIN = '''"""Configuration for the experiment."""

N_SAMPLES = 2400
SEEDS = [0, 1, 2]
WINDOW = 80
'''

RUNNABLE_MAIN = '''import numpy as np


def run() -> None:
    score = float(np.mean([1.0, 2.0]))
    print(f"METRIC_DEF: accuracy | direction=higher | desc=mean score")
    print(f"accuracy: {score:.6f}")


if __name__ == "__main__":
    run()
'''


def _resp(content: str, *, truncated: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        content=content,
        truncated=truncated,
        finish_reason="length" if truncated else "stop",
        total_tokens=0,
    )


class _FakePM:
    def sub_prompt(self, name, **kwargs):  # noqa: ANN001
        return SimpleNamespace(system="", user="")

    def for_stage(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return SimpleNamespace(system="", user="", json_mode=False, max_tokens=8192)

    def system(self, name):  # noqa: ANN001
        return ""


class TestTolerantFences:
    def test_close_unterminated_fence(self) -> None:
        assert _close_unterminated_fence("```python\nprint(1)").endswith("```")
        closed = "```python\nprint(1)\n```"
        assert _close_unterminated_fence(closed) == closed

    def test_single_block_without_closing_fence(self) -> None:
        assert _extract_code_block("```python\nprint(1)") == "print(1)"

    def test_multi_file_without_closing_fence(self) -> None:
        content = (
            "```filename:a.py\nx = 1\n```\n"
            "```filename:b.py\ny = 2\n"
        )
        files = _extract_multi_file_blocks(content)
        assert set(files) == {"main.py", "b.py"}
        assert files["b.py"] == "y = 2"


class TestBlueprintFence:
    def test_parse_blueprint_strips_unclosed_fence(self, tmp_path: Path) -> None:
        agent = CodeAgent(
            llm=None,
            prompts=_FakePM(),
            config=CodeAgentConfig(review_max_rounds=0, exec_fix_max_iterations=0),
            stage_dir=tmp_path,
        )
        text = (
            "```yaml\n"
            "files:\n"
            "  - name: a.py\n"
            "    generation_order: 1\n"
            "  - name: b.py\n"
            "    generation_order: 2\n"
        )
        blueprint = agent._parse_blueprint(text)
        assert blueprint is not None
        assert len(blueprint["files"]) == 2

    def test_blueprint_retries_when_truncated(self, tmp_path: Path) -> None:
        agent = CodeAgent(
            llm=None,
            prompts=_FakePM(),
            config=CodeAgentConfig(review_max_rounds=0, exec_fix_max_iterations=0),
            stage_dir=tmp_path,
        )
        calls: list[int] = []
        valid = (
            "```yaml\n"
            "files:\n"
            "  - name: a.py\n"
            "    generation_order: 1\n"
            "  - name: b.py\n"
            "    generation_order: 2\n"
            "```\n"
        )

        def fake_chat(system, user, max_tokens=8192):  # noqa: ANN001
            calls.append(max_tokens)
            if len(calls) == 1:
                return _resp("```yaml\nfiles:\n  - name: a.py\n", truncated=True)
            return _resp(valid)

        agent._chat = fake_chat  # type: ignore[assignment]
        _arch, blueprint = agent._phase1_blueprint("topic", "plan", "accuracy")
        assert calls == [8192, 32768]
        assert blueprint is not None
        assert len(blueprint["files"]) == 2


class TestEntrypointGate:
    def test_config_only_main_is_rejected(self) -> None:
        issues = _entrypoint_issues(CONFIG_ONLY_MAIN)
        assert issues
        assert any("__main__" in item for item in issues)
        assert any("METRIC_DEF" in item for item in issues)

    def test_runnable_main_passes(self) -> None:
        assert _entrypoint_issues(RUNNABLE_MAIN) == []

    def test_empty_main_is_rejected(self) -> None:
        assert _entrypoint_issues("") != []


class TestReviewGuard:
    def _agent(self, tmp_path: Path, cfg: CodeAgentConfig) -> CodeAgent:
        return CodeAgent(
            llm=None,
            prompts=_FakePM(),
            config=cfg,
            stage_dir=tmp_path,
            sandbox_factory=None,
        )

    def test_review_skipped_when_no_files(self, tmp_path: Path) -> None:
        cfg = CodeAgentConfig(
            architecture_planning=False,
            sequential_generation=False,
            hard_validation=False,
            review_max_rounds=2,
            exec_fix_max_iterations=0,
        )
        agent = self._agent(tmp_path, cfg)
        agent._phase2_generate_and_fix = lambda *a, **k: {}  # type: ignore[assignment]

        def boom(*args, **kwargs):  # noqa: ANN002, ANN003
            raise AssertionError("review must not run on empty files")

        agent._phase4_review = boom  # type: ignore[assignment]
        result = agent.generate(topic="t", exp_plan="p", metric="m", pkg_hint="")
        assert result.files == {}
        assert result.review_rounds == 0

    def test_review_changes_are_revalidated(self, tmp_path: Path) -> None:
        cfg = CodeAgentConfig(
            architecture_planning=False,
            sequential_generation=False,
            hard_validation=True,
            review_max_rounds=1,
            exec_fix_max_iterations=1,
        )
        agent = self._agent(tmp_path, cfg)
        agent._phase2_generate_and_fix = lambda *a, **k: {"main.py": "old"}  # type: ignore[assignment]
        agent._phase4_review = lambda files, *a, **k: ({"main.py": "new"}, 1)  # type: ignore[assignment]
        seen: list[str] = []

        def fake_validate(files, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            seen.append(files["main.py"])
            return files

        agent._hard_validate_and_repair = fake_validate  # type: ignore[assignment]
        agent._exec_fix_loop = lambda files: files  # type: ignore[assignment]
        agent.generate(topic="t", exp_plan="p", metric="m", pkg_hint="")
        assert seen[-1] == "new"
