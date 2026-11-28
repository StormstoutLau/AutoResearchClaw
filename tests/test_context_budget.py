"""P-228 (G-1..G-4): repair context budget, usage telemetry, truncation stop."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from researchclaw.config import CodeAgentConfig
from researchclaw.pipeline.code_agent import CodeAgent
from researchclaw.pipeline.repair_trace import load as load_repair_trace
from researchclaw.pipeline.step_journal import load_steps

SMALL = "def load_data():\n    return 1\n"
MAIN = '''def main() -> None:
    print("METRIC_DEF: auroc_delta")
    print("auroc_delta: 0.7")


if __name__ == "__main__":
    main()
'''


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
    def __init__(self, responses, truncated=None, usage=None):
        self._responses = list(responses)
        self._truncated = list(truncated or [])
        self._usage = usage or {}
        self.calls: list[dict] = []

    def chat(self, messages, **kwargs):  # noqa: ANN001, ANN003
        self.calls.append({"messages": messages, **kwargs})
        idx = min(len(self.calls) - 1, len(self._responses) - 1)
        truncated = self._truncated[idx] if idx < len(self._truncated) else False
        return SimpleNamespace(
            content=self._responses[idx],
            truncated=truncated,
            finish_reason="length" if truncated else "stop",
            model="fake",
            prompt_tokens=self._usage.get("prompt_tokens", 0),
            completion_tokens=self._usage.get("completion_tokens", 0),
            total_tokens=self._usage.get("total_tokens", 0),
        )


def _agent(tmp_path: Path, llm) -> CodeAgent:
    return CodeAgent(
        llm=llm,
        prompts=_FakePM(),
        config=CodeAgentConfig(
            review_max_rounds=0, exec_fix_max_iterations=0,
            hard_validation_max_repairs=4,
        ),
        stage_dir=tmp_path,
    )


def _named(name: str, code: str) -> str:
    return f"```filename:{name}\n{code}```\n"


class TestMiddleTruncate:
    def test_keeps_head_tail_and_marks_omission(self) -> None:
        text = "H" * 800 + "\n" + "M" * 2000 + "\n" + "T" * 800
        out = CodeAgent._middle_truncate(text, 1000)

        assert out.startswith("H")
        assert out.endswith("T")
        assert "[truncated:" in out
        assert f"original {len(text)} chars" in out
        assert "M" * 500 not in out

    def test_short_text_is_untouched(self) -> None:
        assert CodeAgent._middle_truncate("x" * 10, 100) == "x" * 10


class TestFormatFilesBudget:
    def test_under_budget_is_verbatim(self) -> None:
        files = {"data.py": SMALL, "main.py": MAIN}
        out = CodeAgent._format_files(files, budget=60000)
        assert SMALL in out and MAIN in out
        assert "[summary" not in out

    def test_over_budget_summarizes_untouched_files(self) -> None:
        big = "def helper():\n" + "    x = 1\n" * 9000
        files = {"data.py": SMALL, "big.py": big}
        out = CodeAgent._format_files(files, keep_full={"data.py"}, budget=6000)

        assert SMALL in out
        assert "x = 1" * 500 not in out
        assert "# [summary" in out
        assert len(out) < len(big)


class TestRepairTelemetry:
    def test_usage_and_summary_mode_are_recorded(self, tmp_path: Path) -> None:
        reply = _named("main.py", MAIN) + _named("data.py", SMALL)
        llm = _FakeLLM(
            [reply],
            usage={"prompt_tokens": 1234, "completion_tokens": 567,
                   "total_tokens": 1801},
        )
        agent = _agent(tmp_path, llm)
        big = "def helper():\n" + "    x = 1\n" * 9000

        agent._repair_critical_issues(
            {"data.py": SMALL, "big.py": big}, ["[data.py] boom"],
            "t", "p", "m", "",
        )

        row = load_repair_trace(tmp_path)[-1]
        assert row["usage"]["prompt_tokens"] == 1234
        assert row["usage"]["completion_tokens"] == 567
        assert row["usage"]["finish_reason"] == "stop"
        assert row["summary_mode"] is True
        assert row["reason"] == "merged"


class TestTruncationStops:
    def test_truncated_twice_drops_round_and_hits_stop_loss(
        self, tmp_path: Path,
    ) -> None:
        reply = _named("main.py", MAIN) + _named("data.py", SMALL)
        llm = _FakeLLM(
            [reply], truncated=[True, True, True, True, True],
        )
        agent = _agent(tmp_path, llm)

        first = agent._repair_critical_issues(
            {"data.py": SMALL, "main.py": MAIN}, ["[data.py] boom"],
            "t", "p", "m", "",
        )
        second = agent._repair_critical_issues(
            first, ["[data.py] boom"], "t", "p", "m", "",
        )

        # P-231 (D-6): 16k + 32k for the combined prompt, then one request per
        # affected file (16k + 32k) — a third identical combined call is not
        # sent. Two rounds, then P-226 stops the loop.
        assert len(llm.calls) == 8
        rows = load_repair_trace(tmp_path)
        assert all(
            row.get("reason") == "split_per_file"
            for row in rows if row.get("phase") == "agent_repair"
        )
        assert rows[-1]["rejected_reasons"]["data.py"] == (
            "truncated_after_escalation"
        )
        assert second == first
        assert agent._repeated_rejection() == ("data.py", "truncated_after_escalation", 2)
        assert load_steps(tmp_path) == []
