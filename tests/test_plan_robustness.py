"""P-177: plan derivation robustness (extraction / idempotency / bounded fanout)."""
from __future__ import annotations

from pathlib import Path

import yaml

from researchclaw.plan import (
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_FANOUT,
    add_experiment_nodes,
    add_hypothesis_nodes,
    add_synthesis_gaps,
    build_initial_plan,
    load_plan,
    validate_plan,
)
from researchclaw.plan.derive import (
    _hypothesis_statements,
    _sub_questions,
)
from researchclaw.plan.exp_plan import ensure_methods
from researchclaw.plan.rebuild import rebuild_plan
from researchclaw.plan.schema import _depth_and_fanout, _node_maps
from researchclaw.runtime.exit_codes import ExitClass, classify_error

PROBLEM_TREE = """# Problem Decomposition

# Sub-questions

## SQ1 — P0: Does A detect drift earlier than B?

**Research question:**
Can A detect drift earlier?

- sub bullet one
- sub bullet two

## SQ2 — P1: Is A stable across windows?

Details.

## SQ3 — P1: Can C localize change points?

Details.

## SQ4 — P2: How to combine A and C?

Details.
"""

SYNTHESIS = "# Synthesis\n\n" + "".join(
    f"## Gap {i}\nGap detail {i} about the topic.\n\n" for i in range(1, 7)
)

HYPOTHESES = """## 最终研究假设综合：从内部漂移到可验证预警

# 最终假设 1

## 伴随状态压缩压力可能更早捕捉内部漂移

### 核心主张

Text.

# 最终假设 2

## 分层监控在金融时序上更稳健

### 核心主张

Text.
"""

GOAL = """# Research Goal

> **Note (Stage 01 — unverified draft):** benchmark names are estimates.

**LNN internal drift monitoring for financial time series**

Body text.
"""

EXP_PLAN = {
    "proposed_methods": [f"M{i}" for i in range(1, 13)],
    "metrics": ["auroc"],
    "datasets": ["D1"],
    "baselines": ["B1", "B2"],
}


def _plan() -> dict:
    return build_initial_plan(
        topic="Drift monitoring",
        goal_text=GOAL,
        problem_tree=PROBLEM_TREE,
        run_budget_usd=5.0,
        domains=["ml"],
    )


def _full_plan() -> dict:
    plan = add_synthesis_gaps(_plan(), SYNTHESIS)
    plan = add_hypothesis_nodes(plan, HYPOTHESES)
    return add_experiment_nodes(plan, EXP_PLAN)


def _shape(plan: dict) -> tuple[int, int]:
    return _depth_and_fanout(_node_maps(plan["nodes"]))


class TestExtraction:
    def test_sub_questions_from_sq_headings(self) -> None:
        questions = _sub_questions(PROBLEM_TREE)
        assert len(questions) == 4
        assert questions[0].startswith("SQ1")

    def test_goal_skips_blockquote_note(self) -> None:
        plan = _plan()
        assert "Note (Stage 01" not in plan["goal"]
        assert plan["goal"].startswith("LNN internal drift")

    def test_hypotheses_from_chinese_markers(self) -> None:
        statements = _hypothesis_statements(HYPOTHESES)
        assert len(statements) == 2
        assert "伴随状态" in statements[0]
        assert "分层监控" in statements[1]

    def test_no_markdown_markers_in_statements(self) -> None:
        plan = _full_plan()
        for node in plan["nodes"]:
            assert not str(node["statement"]).startswith("#")


class TestBoundedFanout:
    def test_realistic_scale_is_valid(self) -> None:
        plan = _full_plan()
        assert validate_plan(plan, 5.0) == []
        depth, fanout = _shape(plan)
        assert depth <= DEFAULT_MAX_DEPTH
        assert fanout <= DEFAULT_MAX_FANOUT

    def test_depth_default_allows_semantic_chain(self) -> None:
        assert DEFAULT_MAX_DEPTH >= 4

    def test_experiments_rest_on_hypotheses(self) -> None:
        plan = _full_plan()
        by = _node_maps(plan["nodes"])
        hypothesis_ids = {nid for nid, n in by.items() if n["type"] == "hypothesis"}
        experiments = [n for n in by.values() if n["type"] == "experiment"]
        assert experiments
        assert all(
            any(str(dep) in hypothesis_ids for dep in node["depends_on"])
            for node in experiments
        )


class TestIdempotency:
    def test_stage7_twice_is_stable(self) -> None:
        once = add_synthesis_gaps(_plan(), SYNTHESIS)
        twice = add_synthesis_gaps(once, SYNTHESIS)
        assert len(twice["nodes"]) == len(once["nodes"])
        assert validate_plan(twice, 5.0) == []

    def test_stage8_twice_is_stable(self) -> None:
        once = add_hypothesis_nodes(add_synthesis_gaps(_plan(), SYNTHESIS), HYPOTHESES)
        twice = add_hypothesis_nodes(once, HYPOTHESES)
        assert len(twice["nodes"]) == len(once["nodes"])
        assert validate_plan(twice, 5.0) == []

    def test_stage9_twice_is_stable(self) -> None:
        once = add_experiment_nodes(
            add_hypothesis_nodes(add_synthesis_gaps(_plan(), SYNTHESIS), HYPOTHESES),
            EXP_PLAN,
        )
        twice = add_experiment_nodes(once, EXP_PLAN)
        assert len(twice["nodes"]) == len(once["nodes"])
        assert validate_plan(twice, 5.0) == []


class TestFailFast:
    def test_plan_violation_is_not_retryable(self) -> None:
        cls = classify_error("invalid research plan after Stage 9: fanout 9 exceeds 8")
        assert cls != ExitClass.RETRYABLE

    def test_exp_plan_mismatch_is_not_retryable(self) -> None:
        cls = classify_error(
            "research plan / exp_plan mismatch: exp_plan has no proposed_methods"
        )
        assert cls != ExitClass.RETRYABLE


class _FakeLLM:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0

    def chat(self, messages, **kwargs):  # noqa: ANN001
        self.calls += 1
        return type("_Resp", (), {"content": self.content})()


class TestExpPlanContract:
    def test_repair_fills_missing_methods(self) -> None:
        llm = _FakeLLM(
            "```yaml\nproposed_methods:\n  - repaired_method\ndatasets:\n  - D1\n```"
        )
        plan = {"topic": "t", "datasets": ["D1"]}
        repaired = ensure_methods(plan, llm=llm, topic="t", hypotheses="")
        assert repaired["proposed_methods"] == ["repaired_method"]
        assert llm.calls == 1

    def test_existing_methods_skip_llm(self) -> None:
        llm = _FakeLLM("should not be called")
        plan = {"proposed_methods": ["M1"]}
        repaired = ensure_methods(plan, llm=llm, topic="t", hypotheses="")
        assert repaired["proposed_methods"] == ["M1"]
        assert llm.calls == 0


class TestRebuild:
    def _write_run(self, run_dir: Path) -> None:
        (run_dir / "stage-01").mkdir(parents=True)
        (run_dir / "stage-02").mkdir()
        (run_dir / "stage-07").mkdir()
        (run_dir / "stage-08").mkdir()
        (run_dir / "stage-09").mkdir()
        (run_dir / "stage-01" / "goal.md").write_text(GOAL, encoding="utf-8")
        (run_dir / "stage-02" / "problem_tree.md").write_text(PROBLEM_TREE, encoding="utf-8")
        (run_dir / "stage-07" / "synthesis.md").write_text(SYNTHESIS, encoding="utf-8")
        (run_dir / "stage-08" / "hypotheses.md").write_text(HYPOTHESES, encoding="utf-8")
        (run_dir / "stage-09" / "exp_plan.yaml").write_text(
            yaml.safe_dump(EXP_PLAN, allow_unicode=True), encoding="utf-8"
        )

    def test_rebuild_produces_valid_plan(self, tmp_path: Path) -> None:
        self._write_run(tmp_path)
        result = rebuild_plan(tmp_path, stage=9)
        assert result["violations"] == []
        plan = load_plan(tmp_path)
        assert plan is not None
        assert validate_plan(plan, 5.0) == []
        depth, fanout = _shape(plan)
        assert depth <= DEFAULT_MAX_DEPTH
        assert fanout <= DEFAULT_MAX_FANOUT
        assert plan["version"] >= 1
