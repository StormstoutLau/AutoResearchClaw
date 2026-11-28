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
    patch_entrypoint_guard,
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

    def test_patches_missing_guard_without_llm(self, tmp_path: Path) -> None:
        llm = _FakeLLM([_fenced(RUNNABLE_MAIN)])
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
        # P-231 (D-1): the structural gap is patched, not regenerated, so the
        # existing body (and any blueprint-declared symbols in it) survives.
        assert llm.calls == []
        assert "def run()" in out["main.py"]
        assert (tmp_path / "main.py").is_file()

    def test_regenerates_when_no_callable_entry_exists(self, tmp_path: Path) -> None:
        llm = _FakeLLM([_fenced(RUNNABLE_MAIN)])
        files = {"main.py": "def run(seed):\n    return seed\n"}
        out = _ensure_entrypoint(
            files,
            llm=llm,
            pm=PromptManager(),
            topic="t",
            metric="accuracy",
            exp_dir=tmp_path,
        )
        assert entrypoint_issues(out["main.py"]) == []
        assert len(llm.calls) == 1

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
        # A callable that needs an argument cannot be patched, so the LLM path
        # runs; both attempts return the same invalid file.
        blocker = "def run(seed):\n    return seed\n"
        files = {"main.py": blocker, "config.py": "X = 1\n"}
        out = _ensure_entrypoint(
            files,
            llm=llm,
            pm=PromptManager(),
            topic="t",
            metric="accuracy",
            exp_dir=tmp_path,
        )
        assert out["main.py"] == blocker
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


class TestPatchEntrypointGuard:
    """P-231 (D-1): patch the guard instead of regenerating main.py."""

    def test_appends_guard_and_keeps_symbols(self) -> None:
        source = (
            "class ExperimentRunner:\n"
            "    def run(self):\n"
            "        return 0.5\n"
            "\n"
            "\n"
            "def main() -> None:\n"
            "    print('METRIC_DEF: accuracy | direction=higher')\n"
            "    print(f'accuracy: {ExperimentRunner().run():.6f}')\n"
        )
        patched = patch_entrypoint_guard(source, "accuracy")
        assert patched is not None
        assert "class ExperimentRunner" in patched
        assert '__main__' in patched
        assert patched.count("METRIC_DEF") == 1
        assert entrypoint_issues(patched) == []

    def test_injects_metric_def_without_fake_value(self) -> None:
        patched = patch_entrypoint_guard(NO_GUARD_MAIN, "accuracy")
        assert patched is not None
        assert "METRIC_DEF: accuracy" in patched
        # The measured line is printed only from a returned mapping.
        assert "isinstance(_result, dict)" in patched
        assert "nan" not in patched

    def test_noop_when_guard_exists(self) -> None:
        assert patch_entrypoint_guard(RUNNABLE_MAIN, "accuracy") is None

    def test_noop_without_zero_arg_entry(self) -> None:
        assert patch_entrypoint_guard(
            "def run(seed):\n    return seed\n", "accuracy",
        ) is None

    def test_noop_on_syntax_error(self) -> None:
        assert patch_entrypoint_guard("def broken(:\n", "accuracy") is None


class TestSymbolContractPrompt:
    def test_contract_block_is_rendered(self) -> None:
        block = "- main.py: ExperimentRunner, main"
        prompt = build_entrypoint_prompt(
            topic="t", metric="accuracy", files={"config.py": "X = 1\n"},
            symbol_contract=block,
        )
        assert "SYMBOL CONTRACT" in prompt
        assert "ExperimentRunner" in prompt
        assert "thin driver" not in prompt


class TestEntrypointSymbolAware:
    """P-231 (D-2): a candidate that drops declared symbols is rejected."""

    def test_rejects_candidate_missing_declared_symbols(self) -> None:
        blueprint = {
            "files": [{
                "name": "main.py",
                "generation_order": 1,
                "symbols": ["ExperimentRunner", "main"],
            }],
        }
        symbol_main = (
            "class ExperimentRunner:\n"
            "    def run(self):\n"
            "        return 0.5\n"
            "\n"
            "\n"
            "def main() -> None:\n"
            "    print('METRIC_DEF: accuracy | direction=higher')\n"
            "    print(f'accuracy: {ExperimentRunner().run():.6f}')\n"
            "\n"
            "\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        )
        llm = _FakeLLM([_fenced(RUNNABLE_MAIN), _fenced(symbol_main)])
        code = _code_generation._generate_entrypoint(
            llm, PromptManager(), topic="t", metric="accuracy",
            files={"config.py": "X = 1\n"}, blueprint=blueprint,
        )
        assert "class ExperimentRunner" in code
        assert len(llm.calls) == 2
        assert "ExperimentRunner" in llm.calls[0]["messages"][0]["content"]
        assert "must define these declared names" in (
            llm.calls[1]["messages"][0]["content"]
        )


class TestContractIssues:
    """P-231 (D-4): one check covers syntax, entrypoint and symbol contracts."""

    def test_reports_all_three_contracts(self) -> None:
        blueprint = {
            "files": [{
                "name": "main.py",
                "generation_order": 1,
                "symbols": ["Runner"],
            }],
        }
        files = {
            "main.py": "def main() -> None:\n    print('METRIC_DEF: m')\n",
            "data.py": "def broken(:\n",
        }
        joined = " ".join(_code_generation._contract_issues(files, blueprint))
        assert "data.py: syntax error" in joined
        assert "__main__" in joined
        assert "Runner" in joined

    def test_clean_files_have_no_issues(self) -> None:
        assert _code_generation._contract_issues(
            {"main.py": RUNNABLE_MAIN}, None,
        ) == []


class TestSmokeModules:
    """P-231 (D-5): compile and import the delivered modules."""

    def test_syntax_error_fails(self, tmp_path: Path) -> None:
        failures, warnings = _code_generation._smoke_modules(
            {"data.py": "def broken(:\n"}, tmp_path,
        )
        assert failures and "data.py" in failures[0]
        assert warnings == []

    def test_valid_modules_pass(self, tmp_path: Path) -> None:
        (tmp_path / "data.py").write_text(
            "def load():\n    return 1\n", encoding="utf-8",
        )
        failures, warnings = _code_generation._smoke_modules(
            {"data.py": "def load():\n    return 1\n"}, tmp_path,
        )
        assert failures == [] and warnings == []

    def test_missing_third_party_is_only_a_warning(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text(
            "import definitely_not_installed_xyz\n", encoding="utf-8",
        )
        failures, warnings = _code_generation._smoke_modules(
            {"main.py": "import definitely_not_installed_xyz\n"}, tmp_path,
        )
        assert failures == []
        assert warnings and "import smoke" in warnings[0]


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
