"""P-152: ResearchPlan v1 schema, store and stage builders."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from researchclaw.plan import (
    SCHEMA_ID,
    add_experiment_nodes,
    add_hypothesis_nodes,
    add_synthesis_gaps,
    build_initial_plan,
    check_experiment_plan_consistency,
    load_plan,
    mark_analysis_done,
    plan_digest,
    read_events,
    seal_plan,
    update_plan,
    validate_plan,
    write_plan,
)

PROBLEM_TREE = """# Problem Decomposition

## Sub-questions
1. How robust is X under iid shift?
2. How robust is X under ood shift?
3. Which baseline closes the gap?

## Priority Ranking
1. Robustness
2. Baselines

## Risks
- Dataset leakage
"""

SYNTHESIS = """# Synthesis

## Gap 1
Limited consistency across benchmark protocols.

## Gap 2
Under-reported failure behavior under distribution shift.
"""

HYPOTHESES = """# Hypotheses

### H1: X degrades less than the baseline under shift.
### H2: Calibration reduces the ood gap.
"""

EXPERIMENT_PLAN = {
    "proposed_methods": ["X", "X-calibrated"],
    "metrics": ["accuracy"],
    "datasets": ["Y"],
    "baselines": ["B1", "B2"],
}


def _plan() -> dict:
    return build_initial_plan(
        topic="Robustness of X",
        goal_text="# Goal\nCompare X under distribution shift.",
        problem_tree=PROBLEM_TREE,
        run_budget_usd=5.0,
        domains=["ml"],
    )


def _rules(violations) -> set[str]:
    return {violation.rule for violation in violations}


def _experiment_node(**overrides) -> dict:
    node = {
        "id": "n99",
        "type": "experiment",
        "statement": "Run X on Y",
        "depends_on": [],
        "owner_stage": 9,
        "inputs": [],
        "outputs": ["stage-12/run_results.json"],
        "acceptance": ["at least 3 seeds"],
        "evidence_required": True,
        "budget": {"tokens": 1, "usd": 0.0},
        "status": "proposed",
        "metric": "accuracy",
        "dataset": "Y",
        "baseline": ["B1"],
        "method": "X",
    }
    node.update(overrides)
    return node


class TestValidator:
    def test_initial_plan_is_valid(self) -> None:
        plan = _plan()
        assert validate_plan(plan, 5.0) == []
        assert plan["schema"] == SCHEMA_ID
        assert len(plan["nodes"]) == 3
        assert all(node["type"] == "question" for node in plan["nodes"])

    def test_missing_acceptance_rejected(self) -> None:
        plan = copy.deepcopy(_plan())
        plan["nodes"][0].pop("acceptance")
        plan = seal_plan(plan)
        assert "V1" in _rules(validate_plan(plan, 5.0))

    def test_cycle_rejected(self) -> None:
        plan = copy.deepcopy(_plan())
        first, second = plan["nodes"][0]["id"], plan["nodes"][1]["id"]
        plan["nodes"][0]["depends_on"] = [second]
        plan["nodes"][1]["depends_on"] = [first]
        plan = seal_plan(plan)
        assert "V4" in _rules(validate_plan(plan, 5.0))

    def test_owner_stage_out_of_range(self) -> None:
        plan = copy.deepcopy(_plan())
        plan["nodes"][0]["owner_stage"] = 99
        plan = seal_plan(plan)
        assert "V5" in _rules(validate_plan(plan, 5.0))

    def test_experiment_requires_baseline(self) -> None:
        plan = copy.deepcopy(_plan())
        plan["nodes"].append(_experiment_node(baseline=[]))
        plan = seal_plan(plan)
        assert "V6" in _rules(validate_plan(plan, 5.0))

    def test_budget_exceeded(self) -> None:
        plan = copy.deepcopy(_plan())
        for node in plan["nodes"]:
            node["budget"]["usd"] = 2.0
        plan = seal_plan(plan)
        assert "V10" in _rules(validate_plan(plan, 5.0))

    def test_node_cap(self) -> None:
        plan = copy.deepcopy(_plan())
        template = plan["nodes"][0]
        plan["nodes"] = [
            dict(copy.deepcopy(template), id=f"n{i}", statement=f"Question {i}")
            for i in range(41)
        ]
        plan = seal_plan(plan)
        assert "V11" in _rules(validate_plan(plan, 5.0))

    def test_duplicate_statement(self) -> None:
        plan = copy.deepcopy(_plan())
        plan["nodes"][1]["statement"] = plan["nodes"][0]["statement"]
        plan = seal_plan(plan)
        assert "V11" in _rules(validate_plan(plan, 5.0))

    def test_digest_tamper(self) -> None:
        plan = copy.deepcopy(_plan())
        plan["plan_digest"] = "sha256:" + "0" * 64
        assert "V12" in _rules(validate_plan(plan, 5.0))

    def test_hypothesis_requires_literature(self) -> None:
        plan = copy.deepcopy(_plan())
        plan["nodes"].append({
            "id": "n98",
            "type": "hypothesis",
            "statement": "X reduces the gap",
            "depends_on": [plan["nodes"][0]["id"]],
            "owner_stage": 8,
            "inputs": [],
            "outputs": ["stage-08/hypotheses.md"],
            "acceptance": ["falsifiable"],
            "evidence_required": False,
            "budget": {"tokens": 1, "usd": 0.0},
            "status": "proposed",
        })
        plan = seal_plan(plan)
        assert "V7" in _rules(validate_plan(plan, 5.0))

    def test_writing_requires_analysis(self) -> None:
        plan = copy.deepcopy(_plan())
        plan["nodes"].append({
            "id": "n97",
            "type": "writing",
            "statement": "Write the paper",
            "depends_on": [plan["nodes"][0]["id"]],
            "owner_stage": 17,
            "inputs": [],
            "outputs": ["stage-17/paper.md"],
            "acceptance": ["draft exists"],
            "evidence_required": False,
            "budget": {"tokens": 1, "usd": 0.0},
            "status": "proposed",
        })
        plan = seal_plan(plan)
        assert "V8" in _rules(validate_plan(plan, 5.0))

    def test_evidence_node_requires_outputs(self) -> None:
        plan = copy.deepcopy(_plan())
        plan["nodes"].append(_experiment_node(id="n96", outputs=[]))
        plan = seal_plan(plan)
        assert "V9" in _rules(validate_plan(plan, 5.0))


class TestStore:
    def test_roundtrip(self, tmp_path: Path) -> None:
        plan = _plan()
        written = write_plan(tmp_path, plan, stage=2)
        loaded = load_plan(tmp_path)
        assert loaded is not None
        assert loaded["plan_digest"] == written["plan_digest"] == plan_digest(loaded)
        index = json.loads((tmp_path / "plan" / "index.json").read_text(encoding="utf-8"))
        assert index["digest"] == loaded["plan_digest"]
        events = read_events(tmp_path)
        assert len(events) == 1 and events[0]["type"] == "plan.created"

    def test_update_appends_event(self, tmp_path: Path) -> None:
        plan = _plan()
        write_plan(tmp_path, plan, stage=2)
        plan["nodes"][0]["statement"] = "Updated question"
        updated = update_plan(tmp_path, plan, stage=7)
        events = read_events(tmp_path)
        assert len(events) == 2
        assert events[-1]["type"] == "plan.updated"
        assert load_plan(tmp_path)["plan_digest"] == updated["plan_digest"]
        assert "Updated question" in (tmp_path / "plan" / "plan.v1.json").read_text(
            encoding="utf-8"
        )


class TestStageBuilders:
    def test_stage7_adds_gaps(self) -> None:
        plan = add_synthesis_gaps(_plan(), SYNTHESIS)
        assert validate_plan(plan, 5.0) == []
        assert len(plan["unknowns"]) == 2
        types = [node["type"] for node in plan["nodes"]]
        assert types.count("literature") == 1
        assert types.count("question") == 5

    def test_stage8_adds_hypotheses(self) -> None:
        plan = add_synthesis_gaps(_plan(), SYNTHESIS)
        plan = add_hypothesis_nodes(plan, HYPOTHESES)
        assert validate_plan(plan, 5.0) == []
        hypotheses = [node for node in plan["nodes"] if node["type"] == "hypothesis"]
        assert len(hypotheses) == 2
        literature_ids = {
            node["id"] for node in plan["nodes"] if node["type"] == "literature"
        }
        assert all(literature_ids & set(node["depends_on"]) for node in hypotheses)

    def test_stage9_adds_experiments_and_consistency(self) -> None:
        plan = add_synthesis_gaps(_plan(), SYNTHESIS)
        plan = add_hypothesis_nodes(plan, HYPOTHESES)
        plan = add_experiment_nodes(plan, EXPERIMENT_PLAN)
        assert validate_plan(plan, 5.0) == []
        experiments = [node for node in plan["nodes"] if node["type"] == "experiment"]
        assert len(experiments) == 2
        assert {node["method"] for node in experiments} == {"X", "X-calibrated"}
        assert check_experiment_plan_consistency(plan, EXPERIMENT_PLAN) == []

    def test_stage9_consistency_detects_missing_condition(self) -> None:
        plan = add_synthesis_gaps(_plan(), SYNTHESIS)
        plan = add_experiment_nodes(plan, EXPERIMENT_PLAN)
        fewer = dict(EXPERIMENT_PLAN, proposed_methods=["X"])
        mismatches = check_experiment_plan_consistency(plan, fewer)
        assert any("condition mismatch" in item for item in mismatches)

    def test_stage14_marks_analysis_done(self) -> None:
        plan = add_synthesis_gaps(_plan(), SYNTHESIS)
        plan = add_experiment_nodes(plan, EXPERIMENT_PLAN)
        plan = mark_analysis_done(plan, metrics_present=True)
        assert validate_plan(plan, 5.0) == []
        analysis = [node for node in plan["nodes"] if node["type"] == "analysis"]
        assert analysis and analysis[0]["status"] == "done"
        experiments = [node for node in plan["nodes"] if node["type"] == "experiment"]
        assert all(node["status"] == "done" for node in experiments)

    def test_stage14_marks_failed_without_metrics(self) -> None:
        plan = add_synthesis_gaps(_plan(), SYNTHESIS)
        plan = add_experiment_nodes(plan, EXPERIMENT_PLAN)
        plan = mark_analysis_done(plan, metrics_present=False)
        analysis = [node for node in plan["nodes"] if node["type"] == "analysis"]
        assert analysis and analysis[0]["status"] == "failed"


class TestStage2Integration:
    def test_stage2_writes_valid_plan(self, tmp_path: Path, monkeypatch) -> None:
        from researchclaw.adapters import AdapterBundle
        from researchclaw.config import RCConfig
        from researchclaw.pipeline.stage_impls import _topic as topic_impl
        from researchclaw.pipeline.stages import StageStatus

        config = RCConfig.from_dict(
            {
                "project": {"name": "plan-test", "mode": "docs-first"},
                "research": {"topic": "Robustness of X", "domains": ["ml"]},
                "runtime": {"timezone": "UTC"},
                "notifications": {"channel": "local"},
                "knowledge_base": {
                    "backend": "markdown",
                    "root": str(tmp_path / "kb"),
                },
                "llm": {
                    "provider": "openai-compatible",
                    "base_url": "http://localhost:1234/v1",
                    "api_key_env": "RC_TEST_KEY",
                    "api_key": "inline-test-key",
                    "primary_model": "fake-model",
                },
                "experiment": {"mode": "sandbox"},
            },
            project_root=tmp_path,
            check_paths=False,
        )
        run_dir = tmp_path / "run"
        stage_dir = run_dir / "stage-02"
        stage_dir.mkdir(parents=True)
        prior = run_dir / "stage-01"
        prior.mkdir()
        (prior / "goal.md").write_text("# Goal\nCompare X under shift.", encoding="utf-8")

        class _Hardware:
            has_gpu = False
            gpu_name = ""
            gpu_type = ""
            vram_mb = 0
            warning = ""

            def to_dict(self) -> dict:
                return {"has_gpu": False}

        monkeypatch.setattr(topic_impl, "detect_hardware", lambda **_: _Hardware())

        result = topic_impl._execute_problem_decompose(
            stage_dir, run_dir, config, AdapterBundle(), llm=None
        )
        assert result.status == StageStatus.DONE
        assert "plan_meta.json" in result.artifacts
        plan = load_plan(run_dir)
        assert plan is not None
        assert validate_plan(plan, 5.0) == []
        assert (run_dir / "plan" / "index.json").is_file()
        assert read_events(run_dir)[0]["type"] == "plan.created"
