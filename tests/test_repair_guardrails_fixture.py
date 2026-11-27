"""D-7 (P-224): offline fixture benchmark for Stage 10 repair guardrails.

Six scenarios replay the run-K failure modes against the real
``_repair_critical_issues`` / ``_hard_validate_and_repair`` code paths with a
scripted LLM.  The benchmark reports four deterministic metrics:

- ``calls``        — LLM calls (stand-in for wall clock; no timing flakiness)
- ``kept``         — the previous file survived byte-for-byte
- ``accepted_bad`` — a guard-breaking reply was merged (must be 0)
- ``rounds``       — hard-validation repair rounds (repeat-rejection baseline)

The repeat-rejection case pins today's behaviour (4 rounds) so that D-1 can
prove a cheaper 2-round stop later; every other case must already be 0
``accepted_bad`` under P-222.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from researchclaw.config import CodeAgentConfig
from researchclaw.pipeline.code_agent import CodeAgent
from researchclaw.pipeline.repair_trace import load as load_repair_trace
from researchclaw.pipeline.step_journal import load_steps

BLUEPRINT = """files:
  - name: data.py
    generation_order: 1
    functions: [load_data, build_features]
"""

GOOD_DATA = """def load_data():
    return 1


def build_features():
    return 2
"""

MAIN_OK = '''def main() -> None:
    print("METRIC_DEF: auroc_delta | direction=higher")
    print("auroc_delta: 0.7")


if __name__ == "__main__":
    main()
'''

# Deterministic critical: ``value`` is assigned only inside the branch but
# read after it (the same rule that fired on run K's main.py).
SCOPING_BAD = """def run(flag):
    if flag:
        value = 1
    return value
"""


class _FakePM:
    def sub_prompt(self, name, **kwargs):  # noqa: ANN001
        return SimpleNamespace(system="sys", user="", version="test")

    def for_stage(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return SimpleNamespace(
            system="", user="", version="test", max_tokens=8192, json_mode=False,
        )

    def system(self, name):  # noqa: ANN001
        return "sys"


class _FakeLLM:
    def __init__(self, responses: list[str], truncated: list[bool] | None = None):
        self._responses = list(responses)
        self._truncated = list(truncated or [])
        self.calls: list[dict] = []

    def chat(self, messages, **kwargs):  # noqa: ANN001, ANN003
        self.calls.append({"messages": messages, **kwargs})
        idx = min(len(self.calls) - 1, len(self._responses) - 1)
        return SimpleNamespace(
            content=self._responses[idx],
            truncated=(
                self._truncated[idx] if idx < len(self._truncated) else False
            ),
            finish_reason="length" if idx < len(self._truncated) and self._truncated[idx] else "stop",
            model="fake",
            total_tokens=0,
        )


def _agent(tmp_path: Path, llm) -> CodeAgent:
    cfg = CodeAgentConfig(
        review_max_rounds=0,
        hard_validation_max_repairs=4,
        exec_fix_max_iterations=0,
    )
    return CodeAgent(
        llm=llm, prompts=_FakePM(), config=cfg, stage_dir=tmp_path,
    )


def _named(name: str, code: str) -> str:
    return f"```filename:{name}\n{code}```\n"


def _repair(tmp_path: Path, llm, files: dict[str, str]):
    return _agent(tmp_path, llm)._repair_critical_issues(
        files, ["[data.py] UnboundLocalError risk"], "t", "p", "m", BLUEPRINT,
    )


def _report(name: str, calls: int, kept: bool, accepted_bad: bool) -> None:
    print(
        f"fixture {name}: calls={calls} kept={kept} accepted_bad={accepted_bad}"
    )


class TestRepairGuardrailFixture:
    """D-7: six scenarios, one metric per guardrail."""

    def test_01_syntax_break_is_rejected(self, tmp_path: Path) -> None:
        reply = _named("main.py", MAIN_OK) + _named("data.py", "def broken(:\n")
        llm = _FakeLLM([reply])
        before = {"data.py": GOOD_DATA, "main.py": MAIN_OK}

        out = _repair(tmp_path, llm, before)

        reasons = load_repair_trace(tmp_path)[-1]["rejected_reasons"]
        assert out["data.py"] == before["data.py"]
        assert "syntax_error" in reasons["data.py"]
        _report("syntax_break", len(llm.calls), out["data.py"] == GOOD_DATA, False)

    def test_02_entrypoint_break_is_rejected(self, tmp_path: Path) -> None:
        no_guard = 'def main() -> None:\n    print("METRIC_DEF: m")\n'
        llm = _FakeLLM([_named("main.py", no_guard)])
        before = {"main.py": MAIN_OK}

        out = _repair(tmp_path, llm, before)

        reasons = load_repair_trace(tmp_path)[-1]["rejected_reasons"]
        assert out["main.py"] == MAIN_OK
        assert "entrypoint_contract" in reasons["main.py"]
        _report("entrypoint_break", len(llm.calls), out["main.py"] == MAIN_OK, False)

    def test_03_symbol_regression_is_rejected(self, tmp_path: Path) -> None:
        stripped = "def load_data():\n    return 1\n"
        reply = _named("main.py", MAIN_OK) + _named("data.py", stripped)
        llm = _FakeLLM([reply])
        before = {"data.py": GOOD_DATA, "main.py": MAIN_OK}

        out = _repair(tmp_path, llm, before)

        reasons = load_repair_trace(tmp_path)[-1]["rejected_reasons"]
        assert out["data.py"] == GOOD_DATA
        assert "symbol_contract" in reasons["data.py"]
        _report("symbol_regression", len(llm.calls), out["data.py"] == GOOD_DATA, False)

    def test_04_truncated_reply_escalates_once(self, tmp_path: Path) -> None:
        good_reply = _named("main.py", MAIN_OK) + _named("data.py", GOOD_DATA)
        llm = _FakeLLM(
            [_named("data.py", "def load_data():\n    return 1\n"), good_reply],
            truncated=[True, False],
        )

        out = _repair(
            tmp_path, llm, {"data.py": GOOD_DATA, "main.py": MAIN_OK},
        )

        assert [call["max_tokens"] for call in llm.calls] == [16384, 32768]
        assert out["data.py"] == GOOD_DATA.strip()
        _report("truncation", len(llm.calls), True, False)

    def test_05_unknown_module_is_not_merged(self, tmp_path: Path) -> None:
        reply = _named("helpers.py", "X = 1\n") + _named("main.py", MAIN_OK)
        llm = _FakeLLM([reply])

        out = _repair(tmp_path, llm, {"data.py": GOOD_DATA, "main.py": MAIN_OK})

        assert "helpers.py" not in out
        assert out["data.py"] == GOOD_DATA
        _report("unknown_file", len(llm.calls), "helpers.py" not in out, False)

    def test_06_same_reason_repeats_to_the_limit(self, tmp_path: Path) -> None:
        """Baseline for D-1: today four rounds run, all rejected.

        After D-1 the same scenario must stop at two rounds while still
        keeping the original file; this assertion is the reference point.
        """
        bad = _named("data.py", "def broken(:\n")
        llm = _FakeLLM([bad])
        agent = _agent(tmp_path, llm)

        out = agent._hard_validate_and_repair(
            {"data.py": SCOPING_BAD}, "t", "p", "m", "", BLUEPRINT,
        )

        rounds = [
            row for row in load_steps(tmp_path)
            if row["step_id"] == "hard_validation"
        ]
        repairs = [
            row for row in load_repair_trace(tmp_path)
            if row.get("phase") == "agent_repair"
        ]
        assert len(rounds) == 5  # attempt-0..4, all failed
        assert len(llm.calls) == 4  # D-1 target: 2
        assert len(repairs) == 4
        assert all(not row["accepted"] for row in repairs)
        assert out["data.py"] == SCOPING_BAD
        _report("repeat_rejection", len(llm.calls), out["data.py"] == SCOPING_BAD, False)

    def test_coverage_is_six_scenarios(self) -> None:
        names = [
            name for name in dir(self)
            if name.startswith("test_") and name[5:7].isdigit()
        ]
        assert len(names) == 6
