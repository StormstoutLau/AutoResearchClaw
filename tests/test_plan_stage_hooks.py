"""P-156 T23-T25: Stage 15 ledger and Stage 9 search report hooks."""
from __future__ import annotations

import json
from pathlib import Path

from researchclaw.plan.schema import seal_plan
from researchclaw.plan.store import read_events, write_plan


def _node(node_id: str, *, node_type: str = "question", status: str = "proposed") -> dict:
    node = {
        "id": node_id,
        "type": node_type,
        "statement": f"Statement {node_id}",
        "depends_on": [],
        "owner_stage": 2,
        "inputs": [],
        "outputs": ["stage-02/problem_tree.md"],
        "acceptance": ["measurable criterion"],
        "evidence_required": False,
        "budget": {"tokens": 100, "usd": 0.5},
        "status": status,
    }
    if node_type == "experiment":
        node.update({"metric": "accuracy", "dataset": "D", "baseline": ["B"]})
    return node


def _plan(nodes: list[dict]) -> dict:
    plan = {
        "schema": "research-plan/1",
        "plan_id": "rp-test",
        "version": 1,
        "parent_version": None,
        "goal": "Test goal",
        "constraints": {
            "budget_usd": 5.0,
            "deadline": None,
            "domains": [],
            "max_depth": 3,
            "max_fanout": 8,
        },
        "facts": [],
        "unknowns": [],
        "assumptions": [],
        "nodes": nodes,
        "replan": {
            "triggers": ["two_failures", "ambiguity", "budget_half_no_progress"],
            "max_versions": 3,
            "preserve_completed": True,
        },
        "provenance": {"prompt_version": "test", "model": "", "created_at": "2026-11-25T00:00:00Z"},
    }
    return seal_plan(plan)


class TestStageHooks:
    def test_stage15_writes_ledger(self, tmp_path: Path) -> None:
        from researchclaw.pipeline.stage_impls._analysis import _update_plan_ledger

        write_plan(tmp_path, _plan([_node("n1")]), stage=2)
        ledger = _update_plan_ledger(tmp_path, "PROCEED")
        assert ledger is not None
        stored = json.loads(
            (tmp_path / "plan" / "ledger.json").read_text(encoding="utf-8")
        )
        assert stored["next_node"] == "n1"
        assert stored["is_complete"] is False

    def test_stage15_requests_replan_on_refine(self, tmp_path: Path) -> None:
        from researchclaw.pipeline.stage_impls._analysis import _update_plan_ledger

        plan = _plan([_node("n1")])
        write_plan(tmp_path, plan, stage=2)
        _update_plan_ledger(tmp_path, "REFINE")
        events = read_events(tmp_path)
        assert events[-1]["type"] == "plan.replan_requested"
        assert events[-1]["payload"]["reason"] == "refine"
        stored = json.loads(
            (tmp_path / "plan" / "plan.v1.json").read_text(encoding="utf-8")
        )
        assert stored["plan_digest"] == plan["plan_digest"]

    def test_stage15_without_plan_is_noop(self, tmp_path: Path) -> None:
        from researchclaw.pipeline.stage_impls._analysis import _update_plan_ledger

        assert _update_plan_ledger(tmp_path, "PROCEED") is None
        assert not (tmp_path / "plan").exists()

    def test_stage9_writes_search_report(self, tmp_path: Path) -> None:
        from researchclaw.pipeline.stage_impls._experiment_design import (
            _write_plan_search_report,
        )

        plan = _plan([_node("n1", node_type="experiment")])
        report = _write_plan_search_report(tmp_path, plan, 5.0)
        assert report is not None
        stored = json.loads(
            (tmp_path / "plan" / "search.json").read_text(encoding="utf-8")
        )
        assert stored["selected"] == ["n1"]
        assert stored["spent_usd"] <= 5.0

    def test_stage9_without_plan_is_noop(self, tmp_path: Path) -> None:
        from researchclaw.pipeline.stage_impls._experiment_design import (
            _write_plan_search_report,
        )

        assert _write_plan_search_report(tmp_path, None, 5.0) is None
        assert not (tmp_path / "plan").exists()
