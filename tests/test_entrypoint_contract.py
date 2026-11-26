"""B-29: entrypoint contract, dedicated main.py generation, no file promotion."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from researchclaw.config import CodeAgentConfig
from researchclaw.pipeline.code_agent import CodeAgent
from researchclaw.pipeline.entrypoint_contract import (
    ENTRYPOINT_MAX_TOKENS,
    ENTRYPOINT_RETRY_MAX_TOKENS,
    build_entrypoint_prompt,
    entrypoint_issues,
    summarize_modules,
    synthesize_entrypoint,
)
from researchclaw.pipeline.stage_impls import _code_generation
from researchclaw.pipeline.stage_impls._code_generation import (
    _ensure_entrypoint,
    _extract_valid_repair_files,
)
from researchclaw.prompts import PromptManager

RUNNABLE_MAIN = (
    "import numpy as np\n"
    "\n"
    "\n"
    "def run() -> None:\n"
    "    score = float(np.mean([1.0, 2.0]))\n"
    "    print('METRIC_DEF: accuracy | direction=higher | desc=score')\n"
    "    print(f'accuracy: {score:.6f}')\n"
    "\n"
    "\n"
    "if __name__ == '__main__':\n"
    "    run()\n"
)

NO_GUARD_MAIN = (
    "import numpy as np\n"
    "\n"
    "def run() -> None:\n"
    "    print(np.mean([1.0, 2.0]))\n"
)


class _FakeLLM:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def chat(self, messages, **kwargs):  # noqa: ANN001, ANN003
        self.calls.append({"messages": messages, **kwargs})
        idx = min(len(self.calls) - 1, len(self.responses) - 1)
        return SimpleNamespace(
            content=self.responses[idx],
            truncated=False,
            finish_reason="stop",
            total_tokens=0,
        )


def _fenced(code: str) -> str:
    return f"```python\n{code}```\n"


class TestEntrypointIssues:
    def test_valid_entrypoint_passes(self) -> None:
        assert entrypoint_issues(RUNNABLE_MAIN) == []

    def test_missing_guard_is_reported(self) -> None:
        issues = entrypoint_issues(NO_GUARD_MAIN)
        assert any("__main__" in issue for issue in issues)

    def test_missing_metric_def_is_reported(self) -> None:
        code = "if __name__ == '__main__':\n    print('hi')\n"
        assert any("METRIC_DEF" in issue for issue in entrypoint_issues(code))

    def test_syntax_error_is_reported(self) -> None:
        issues = entrypoint_issues("def broken(:\n")
        assert issues and "syntax error" in issues[0]

    def test_empty_is_reported(self) -> None:
        assert entrypoint_issues("") == ["main.py is empty or missing"]

    def test_summarize_modules_lists_classes(self) -> None:
        summary = summarize_modules(
            {"models.py": "class Detector:\n    pass\n\n\ndef score():\n    pass\n"},
        )
        assert "models.py" in summary
        assert "Detector" in summary
        assert "score" in summary


class TestEnsureEntrypoint:
    def test_generates_missing_main(self, tmp_path: Path) -> None:
        llm = _FakeLLM([_fenced(RUNNABLE_MAIN)])
        files = {"config.py": "X = 1\n"}
        out = _ensure_entrypoint(
            files,
            llm=llm,
            pm=PromptManager(),
            topic="t",
            metric="accuracy",
            exp_dir=tmp_path / "experiment",
        )
        assert entrypoint_issues(out["main.py"]) == []
        assert out["config.py"] == "X = 1\n"
        assert (tmp_path / "experiment" / "main.py").is_file()
        assert len(llm.calls) == 1

    def test_regenerates_invalid_main(self, tmp_path: Path) -> None:
        llm = _FakeLLM([_fenced(NO_GUARD_MAIN), _fenced(RUNNABLE_MAIN)])
        files = {"main.py": NO_GUARD_MAIN}
        out = _ensure_entrypoint(
            files,
            llm=llm,
            pm=PromptManager(),
            topic="t",
            metric="accuracy",
            exp_dir=tmp_path,
        )
        assert entrypoint_issues(out["main.py"]) == []
        assert len(llm.calls) == 2
        # The retry prompt must tell the model what was wrong.
        assert "previous attempt" in llm.calls[1]["messages"][0]["content"]

    def test_noop_when_contract_already_satisfied(self, tmp_path: Path) -> None:
        llm = _FakeLLM([_fenced(RUNNABLE_MAIN)])
        files = {"main.py": RUNNABLE_MAIN}
        out = _ensure_entrypoint(
            files,
            llm=llm,
            pm=PromptManager(),
            topic="t",
            metric="accuracy",
            exp_dir=tmp_path,
        )
        assert out["main.py"] == RUNNABLE_MAIN
        assert llm.calls == []

    def test_leaves_files_alone_when_generation_fails(self, tmp_path: Path) -> None:
        llm = _FakeLLM([_fenced(NO_GUARD_MAIN)])
        files = {"main.py": NO_GUARD_MAIN, "config.py": "X = 1\n"}
        out = _ensure_entrypoint(
            files,
            llm=llm,
            pm=PromptManager(),
            topic="t",
            metric="accuracy",
            exp_dir=tmp_path,
            # two attempts: both return the same no-guard file
        )
        assert out["main.py"] == NO_GUARD_MAIN
        assert out["config.py"] == "X = 1\n"
        assert len(llm.calls) == 2

    def test_falls_back_to_synthesized_driver(self, tmp_path: Path) -> None:
        llm = _FakeLLM([_fenced("not python at all ("), _fenced("still bad (")])
        files = {
            "main.py": "X = 1\n",
            "models.py": "def run():\n    return 0.5\n",
        }
        out = _ensure_entrypoint(
            files,
            llm=llm,
            pm=PromptManager(),
            topic="t",
            metric="accuracy",
            exp_dir=tmp_path,
        )
        assert entrypoint_issues(out["main.py"]) == []
        assert "_impl" in out["main.py"]
        assert "models" in out["main.py"]
        assert (tmp_path / "main.py").is_file()


class TestSynthesizeEntrypoint:
    def test_builds_driver_over_entry_function(self) -> None:
        code = synthesize_entrypoint(
            {"models.py": "def train():\n    return {'accuracy': 1.0}\n"},
            "accuracy",
        )
        assert code is not None
        assert entrypoint_issues(code) == []
        assert "import models as _impl" in code
        assert "'train'" in code

    def test_prefers_main_over_train(self) -> None:
        code = synthesize_entrypoint(
            {
                "a.py": "def train():\n    return 1.0\n",
                "b.py": "def main():\n    return 2.0\n",
            },
            "score",
        )
        assert code is not None
        assert "import b as _impl" in code

    def test_returns_none_without_entry_function(self) -> None:
        assert synthesize_entrypoint(
            {"config.py": "X = 1\n", "data.py": "def load():\n    pass\n"},
            "score",
        ) is None

    def test_skips_main_and_syntax_errors(self) -> None:
        assert synthesize_entrypoint(
            {"main.py": "def run():\n    pass\n", "bad.py": "def run(:\n"},
            "score",
        ) is None


class TestEntrypointBudgetEscalation:
    def test_truncation_escalates_to_65536(self, monkeypatch) -> None:
        calls: list[int] = []

        def fake_chat(llm, system, user, **kwargs):  # noqa: ANN001, ANN002, ANN003
            calls.append(int(kwargs["max_tokens"]))
            if len(calls) == 1:
                return SimpleNamespace(
                    content=_fenced(RUNNABLE_MAIN),
                    truncated=True,
                    finish_reason="length",
                    total_tokens=0,
                )
            return SimpleNamespace(
                content=_fenced(RUNNABLE_MAIN),
                truncated=False,
                finish_reason="stop",
                total_tokens=0,
            )

        monkeypatch.setattr(
            _code_generation, "_chat_with_prompt", fake_chat,
        )
        code = _code_generation._generate_entrypoint(
            object(), PromptManager(), topic="t", metric="accuracy",
            files={"config.py": "X = 1\n"},
        )
        assert entrypoint_issues(code) == []
        assert calls == [ENTRYPOINT_MAX_TOKENS, ENTRYPOINT_RETRY_MAX_TOKENS]

    def test_prompt_caps_file_length(self) -> None:
        prompt = build_entrypoint_prompt(
            topic="t", metric="accuracy", files={"config.py": "X = 1\n"},
        )
        assert "at most 150 lines" in prompt
        assert "Do NOT re-implement" in prompt


class TestRepairRejectsBadEntrypoint:
    def test_main_without_guard_is_rejected(self) -> None:
        content = (
            "```filename:main.py\n"
            "X = 1\n"
            "```\n"
            "```filename:data.py\n"
            "Y = 2\n"
            "```\n"
        )
        accepted = _extract_valid_repair_files(content, {"main.py", "data.py"})
        assert accepted == {"data.py": "Y = 2"}

    def test_compliant_main_is_accepted(self) -> None:
        content = f"```filename:main.py\n{RUNNABLE_MAIN}```\n"
        accepted = _extract_valid_repair_files(content, {"main.py"})
        assert set(accepted) == {"main.py"}


class TestCodeAgentEntrypoint:
    def test_sequential_generation_does_not_rename_first_file(
        self, tmp_path: Path,
    ) -> None:
        llm = _FakeLLM([
            _fenced("X = 1\n"),          # config.py
            _fenced("Y = 2\n"),          # data.py
            _fenced(RUNNABLE_MAIN),      # dedicated entrypoint
        ])
        agent = CodeAgent(
            llm=llm,
            prompts=PromptManager(),
            config=CodeAgentConfig(),
            stage_dir=tmp_path,
        )
        blueprint = {
            "files": [
                {"name": "config.py", "generation_order": 1},
                {"name": "data.py", "generation_order": 2},
            ],
        }
        files = agent._phase2_sequential_generate(
            topic="t", exp_plan="p", metric="accuracy",
            pkg_hint="", arch_spec="", blueprint=blueprint,
        )
        assert files["config.py"] == "X = 1"
        assert files["data.py"] == "Y = 2"
        assert entrypoint_issues(files["main.py"]) == []

    def test_entrypoint_generation_retries_on_invalid_output(
        self, tmp_path: Path,
    ) -> None:
        llm = _FakeLLM([_fenced(NO_GUARD_MAIN), _fenced(RUNNABLE_MAIN)])
        agent = CodeAgent(
            llm=llm,
            prompts=PromptManager(),
            config=CodeAgentConfig(),
            stage_dir=tmp_path,
        )
        code = agent._generate_entrypoint_file(
            "t", "p", "accuracy", {"config.py": "X = 1\n"},
        )
        assert entrypoint_issues(code) == []
        assert len(llm.calls) == 2
