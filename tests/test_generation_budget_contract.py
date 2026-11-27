"""B-34 M4 (P-210): thinking budget tiering, file budget, symbol contract."""

from __future__ import annotations

import io
import json
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from researchclaw.config import CodeAgentConfig
from researchclaw.llm.client import LLMClient, LLMConfig
from researchclaw.pipeline.code_agent import CodeAgent, ModuleExtractionError
from researchclaw.pipeline.codegen_evidence import (
    check_symbol_contract,
    evaluate_stage10_evidence,
    load_blueprint,
    missing_symbols,
)
from researchclaw.pipeline.step_journal import load_steps

BLUEPRINT = """files:
  - name: config.py
    generation_order: 1
  - name: methods.py
    generation_order: 2
    classes:
      - TauKLMonitor
    functions: [run_experiment]
primary_metric: auroc_delta
"""

CONFIG_PY = '''class RunConfig:
    seed: int = 0
'''

METHODS_PY = '''class TauKLMonitor:
    def score(self, xs):
        return sum(xs)


def run_experiment():
    return TauKLMonitor().score([1, 2])
'''

MAIN_OK = '''def main() -> None:
    print("METRIC_DEF: auroc_delta | direction=higher")
    print("auroc_delta: 0.7")


if __name__ == "__main__":
    main()
'''


class _FakePM:
    def sub_prompt(self, name, **kwargs):  # noqa: ANN001
        parts = [f"{key}={value}" for key, value in kwargs.items()]
        return SimpleNamespace(
            system="sys", user="\n".join(parts), version="test",
        )

    def for_stage(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return SimpleNamespace(
            system="", user="", version="test", max_tokens=8192, json_mode=False,
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


def _fenced(code: str) -> str:
    return f"```python\n{code}```\n"


class TestThinkingTier:
    def test_policy_off_sends_nothing(self, tmp_path: Path) -> None:
        agent = _agent(tmp_path, None)
        assert agent._thinking_extra("config.py") == {}
        assert agent._thinking_extra("methods.py") == {}

    @pytest.mark.parametrize(
        "name",
        ["config.py", "settings.py", "schema.py", "utils.py", "io.py", "loader.py"],
    )
    def test_mechanical_modules_get_low_effort(
        self, tmp_path: Path, name: str,
    ) -> None:
        agent = _agent(tmp_path, None, thinking_policy="tiered")
        assert agent._thinking_extra(name) == {"reasoning_effort": "low"}

    def test_design_module_keeps_default_thinking(self, tmp_path: Path) -> None:
        agent = _agent(tmp_path, None, thinking_policy="tiered")
        assert agent._thinking_extra("methods.py") == {}
        assert agent._thinking_extra("tau_kl_model.py") == {}

    def test_design_module_can_be_bounded(self, tmp_path: Path) -> None:
        agent = _agent(
            tmp_path, None,
            thinking_policy="tiered", thinking_core_max_tokens=2048,
        )
        assert agent._thinking_extra("methods.py") == {
            "reasoning": {"max_tokens": 2048},
        }

    def test_mechanical_effort_can_be_configured(self, tmp_path: Path) -> None:
        agent = _agent(
            tmp_path, None,
            thinking_policy="tiered", thinking_mechanical_effort="medium",
        )
        assert agent._thinking_extra("config.py") == {"reasoning_effort": "medium"}

    def test_mechanical_effort_can_be_empty(self, tmp_path: Path) -> None:
        agent = _agent(
            tmp_path, None,
            thinking_policy="tiered", thinking_mechanical_effort="",
        )
        assert agent._thinking_extra("config.py") == {}


class TestSequentialWiring:
    def test_tier_reaches_the_llm_and_prompt_has_budget(
        self, tmp_path: Path,
    ) -> None:
        llm = _FakeLLM([_fenced("X = 1\n"), _fenced("Y = 2\n")])
        agent = _agent(
            tmp_path, llm,
            thinking_policy="tiered", file_max_lines=120,
        )
        blueprint = {"files": [
            {"name": "config.py", "generation_order": 1},
            {"name": "methods.py", "generation_order": 2},
        ]}
        agent._phase2_sequential_generate(
            topic="t", exp_plan="p", metric="m",
            pkg_hint="", arch_spec="", blueprint=blueprint,
        )
        first, second = llm.calls[0], llm.calls[1]
        assert first["extra_body"] == {"reasoning_effort": "low"}
        assert "extra_body" not in second
        assert "at or under 120 lines" in first["messages"][0]["content"]

    def test_core_limit_reaches_design_module(self, tmp_path: Path) -> None:
        llm = _FakeLLM([_fenced("Y = 2\n")])
        agent = _agent(
            tmp_path, llm,
            thinking_policy="tiered", thinking_core_max_tokens=1024,
        )
        blueprint = {"files": [{"name": "methods.py", "generation_order": 1}]}
        agent._phase2_sequential_generate(
            topic="t", exp_plan="p", metric="m",
            pkg_hint="", arch_spec="", blueprint=blueprint,
        )
        assert llm.calls[0]["extra_body"] == {"reasoning": {"max_tokens": 1024}}


class TestLineBudget:
    def test_blueprint_value_wins(self, tmp_path: Path) -> None:
        agent = _agent(tmp_path, None, file_max_lines=300)
        assert agent._module_line_budget({"max_lines": 180}) == 180
    def test_invalid_value_falls_back(self, tmp_path: Path) -> None:
        agent = _agent(tmp_path, None, file_max_lines=300)
        assert agent._module_line_budget({"max_lines": "many"}) == 300

    def test_floor_is_forty(self, tmp_path: Path) -> None:
        agent = _agent(tmp_path, None, file_max_lines=300)
        assert agent._module_line_budget({"max_lines": 5}) == 40


class TestSymbolContract:
    def _bp(self, stage_dir: Path) -> Path:
        (stage_dir / "architecture_spec.yaml").write_text(BLUEPRINT, encoding="utf-8")
        return stage_dir

    def _files(self, **overrides: str) -> dict[str, str]:
        base = {
            "config.py": CONFIG_PY,
            "methods.py": METHODS_PY,
            "main.py": MAIN_OK,
        }
        base.update(overrides)
        return base

    def test_declared_symbols_present_passes(self, tmp_path: Path) -> None:
        blueprint = load_blueprint(self._bp(tmp_path))
        assert check_symbol_contract(blueprint, self._files()) == []

    def test_missing_method_fails(self, tmp_path: Path) -> None:
        blueprint = load_blueprint(self._bp(tmp_path))
        hollow = METHODS_PY.replace("def run_experiment():", "def run():")
        failures = check_symbol_contract(blueprint, self._files(**{"methods.py": hollow}))
        assert [f.code for f in failures] == ["blueprint_symbols_missing"]
        assert "methods.py:run_experiment" in failures[0].detail

    def test_missing_class_fails(self, tmp_path: Path) -> None:
        blueprint = load_blueprint(self._bp(tmp_path))
        hollow = METHODS_PY.replace("class TauKLMonitor:", "class Monitor:")
        failures = check_symbol_contract(blueprint, self._files(**{"methods.py": hollow}))
        assert [f.code for f in failures] == ["blueprint_symbols_missing"]
        assert "TauKLMonitor" in failures[0].detail

    def test_absent_file_is_left_to_the_file_gate(self, tmp_path: Path) -> None:
        blueprint = load_blueprint(self._bp(tmp_path))
        files = {"config.py": CONFIG_PY, "main.py": MAIN_OK}
        assert check_symbol_contract(blueprint, files) == []

    def test_no_declarations_skips_the_gate(self, tmp_path: Path) -> None:
        text = "files:\n  - name: config.py\n    generation_order: 1\n"
        (tmp_path / "architecture_spec.yaml").write_text(text, encoding="utf-8")
        blueprint = load_blueprint(tmp_path)
        assert check_symbol_contract(blueprint, {"config.py": "X = 1\n"}) == []

    def test_unparsable_file_fails_rather_than_passing(self) -> None:
        blueprint = {
            "files": [{
                "name": "methods.py",
                "generation_order": 1,
                "symbols": ["TauKLMonitor"],
            }],
        }
        failures = check_symbol_contract(blueprint, {"methods.py": "def broken(:\n"})
        assert [f.code for f in failures] == ["blueprint_symbols_missing"]

    def test_evaluate_reports_it(self, tmp_path: Path) -> None:
        stage_dir = self._bp(tmp_path)
        hollow = METHODS_PY.replace("def run_experiment():", "def run():")
        report = evaluate_stage10_evidence(
            stage_dir=stage_dir,
            files=self._files(**{"methods.py": hollow}),
            metric="auroc_delta",
        )
        assert "blueprint_symbols_missing" in {f.code for f in report.failures}


class TestConfigParsing:
    """The yaml loader builds fields one by one; new keys must be wired."""

    def test_new_keys_are_parsed(self) -> None:
        from researchclaw.config import _parse_code_agent_config

        cfg = _parse_code_agent_config({
            "thinking_policy": "tiered",
            "thinking_mechanical_effort": "medium",
            "thinking_core_max_tokens": 2048,
            "file_max_lines": 180,
        })
        assert cfg.thinking_policy == "tiered"
        assert cfg.thinking_mechanical_effort == "medium"
        assert cfg.thinking_core_max_tokens == 2048
        assert cfg.file_max_lines == 180

    def test_defaults_survive_an_empty_block(self) -> None:
        from researchclaw.config import _parse_code_agent_config

        cfg = _parse_code_agent_config({})
        assert cfg.thinking_policy == "off"
        assert cfg.thinking_mechanical_effort == "low"
        assert cfg.thinking_core_max_tokens == 0
        assert cfg.file_max_lines == 300


class TestClientPassthrough:
    def _client(self) -> LLMClient:
        return LLMClient(LLMConfig(base_url="http://127.0.0.1:1/v1", api_key="x"))

    def test_extra_body_is_merged_into_payload(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: dict = {}

        class _Resp(io.BytesIO):
            def __enter__(self):  # noqa: ANN204
                return self

            def __exit__(self, *exc):  # noqa: ANN002
                return False

        def fake_urlopen(req, timeout=0):  # noqa: ANN001
            captured["body"] = json.loads(req.data)
            return _Resp(json.dumps({
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                "model": "fake",
            }).encode())

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        client = self._client()
        client._raw_call(
            "fake-model", [{"role": "user", "content": "hi"}], 64, 0.0, False,
            {"reasoning_effort": "low", "chat_template_kwargs": {"enable_thinking": False}},
        )
        body = captured["body"]
        assert body["reasoning_effort"] == "low"
        assert body["chat_template_kwargs"] == {"enable_thinking": False}
        assert body["max_tokens"] == 64

    def test_no_extra_body_keeps_the_payload_clean(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: dict = {}

        class _Resp(io.BytesIO):
            def __enter__(self):  # noqa: ANN204
                return self

            def __exit__(self, *exc):  # noqa: ANN002
                return False

        def fake_urlopen(req, timeout=0):  # noqa: ANN001
            captured["body"] = json.loads(req.data)
            return _Resp(json.dumps({
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                "model": "fake",
            }).encode())

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        client = self._client()
        client._raw_call(
            "fake-model", [{"role": "user", "content": "hi"}], 64, 0.0, False,
        )
        assert "reasoning_effort" not in captured["body"]
        assert "reasoning" not in captured["body"]


class TestModuleSymbolContract:
    """B-34 M5: a module is checked at its own boundary, not at stage exit."""

    @staticmethod
    def _blueprint(**symbols) -> dict:
        return {"files": [{
            "name": "methods.py", "generation_order": 1,
            "symbols": list(symbols.get("symbols", [])),
        }]}

    def test_missing_helper_reports_absent_names(self) -> None:
        bp = self._blueprint(symbols=["TauKLMonitor", "helper"])
        assert missing_symbols(bp, "methods.py", "class TauKLMonitor: pass\n") == [
            "helper",
        ]
        assert missing_symbols(bp, "methods.py", "x = 1\n") == [
            "TauKLMonitor", "helper",
        ]

    def test_satisfied_contract_costs_no_extra_call(self, tmp_path: Path) -> None:
        code = "class TauKLMonitor:\n    pass\n"
        llm = _FakeLLM([_fenced(code)])
        agent = _agent(tmp_path, llm)

        files = agent._phase2_sequential_generate(
            topic="t", exp_plan="p", metric="m", pkg_hint="", arch_spec="",
            blueprint=self._blueprint(symbols=["TauKLMonitor"]),
        )

        assert "TauKLMonitor" in files["methods.py"]
        # The extra calls are the dedicated entrypoint (no main.py declared);
        # none of them may be a symbol-contract repair.
        assert not any(
            "SYMBOL CONTRACT" in call["messages"][0]["content"]
            for call in llm.calls
        )
        rows = [r for r in load_steps(tmp_path) if r["step_id"] == "generate_file"]
        assert rows[-1]["status"] == "done"

    def test_missing_symbol_is_repaired_once(self, tmp_path: Path) -> None:
        broken = _fenced("class Other:\n    pass\n")
        fixed = _fenced(
            "class TauKLMonitor:\n    pass\n\n\ndef helper():\n    return 1\n"
        )
        llm = _FakeLLM([broken, fixed])
        agent = _agent(tmp_path, llm)

        files = agent._phase2_sequential_generate(
            topic="t", exp_plan="p", metric="m", pkg_hint="", arch_spec="",
            blueprint=self._blueprint(symbols=["TauKLMonitor", "helper"]),
        )

        repairs = [
            call for call in llm.calls
            if "SYMBOL CONTRACT" in call["messages"][0]["content"]
        ]
        assert len(repairs) == 1
        assert "TauKLMonitor" in files["methods.py"]
        rows = [r for r in load_steps(tmp_path) if r["step_id"] == "generate_file"]
        assert rows[-1]["status"] == "done"

    def test_unrepaired_module_fails_at_its_own_boundary(
        self, tmp_path: Path,
    ) -> None:
        broken = _fenced("class Other:\n    pass\n")
        llm = _FakeLLM([broken, broken])
        agent = _agent(tmp_path, llm)

        with pytest.raises(ModuleExtractionError) as excinfo:
            agent._phase2_sequential_generate(
                topic="t", exp_plan="p", metric="m", pkg_hint="", arch_spec="",
                blueprint=self._blueprint(symbols=["TauKLMonitor"]),
            )

        assert excinfo.value.reason == "symbols_missing"
        assert excinfo.value.file_name == "methods.py"
        rows = [r for r in load_steps(tmp_path) if r["step_id"] == "generate_file"]
        assert rows[-1]["status"] == "failed"
        assert rows[-1]["variant"] == "methods.py"
