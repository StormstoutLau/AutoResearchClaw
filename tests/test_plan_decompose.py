"""P-156 T16-T19: ADaPT-style lazy decomposition with trigger evidence and limits."""
from __future__ import annotations

import pytest

from researchclaw.plan.decompose import (
    DecomposeError,
    decompose_node,
    should_decompose,
)
from researchclaw.plan.schema import seal_plan, validate_plan


def _node(node_id: str, *, status: str = "proposed", deps=(), **extra) -> dict:
    node = {
        "id": node_id,
        "type": "question",
        "statement": f"Statement {node_id}",
        "depends_on": list(deps),
        "owner_stage": 2,
        "inputs": [],
        "outputs": ["stage-02/problem_tree.md"],
        "acceptance": ["measurable criterion"],
        "evidence_required": False,
        "budget": {"tokens": 100, "usd": 0.0},
        "status": status,
    }
    node.update(extra)
    return node


def _plan(nodes: list[dict], **constraints) -> dict:
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
            **constraints,
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


def _children() -> list[dict]:
    return [
        {"type": "question", "statement": "Child A", "owner_stage": 7, "acceptance": ["a"]},
        {"type": "question", "statement": "Child B", "owner_stage": 7, "acceptance": ["b"]},
    ]


class TestLazyDecompose:
    def test_should_decompose_requires_trigger(self) -> None:
        node = _node("n1")
        assert should_decompose(node, attempts=1) == (False, "no_trigger")
        assert should_decompose(node, attempts=2) == (True, "two_failures")
        assert should_decompose(node, ambiguous=True) == (True, "ambiguity")
        assert should_decompose(
            node, budget_ratio=0.6, progress_ratio=0.2
        ) == (True, "budget_half_no_progress")
        assert should_decompose(node, depth=3, max_depth=3) == (False, "limits")

    def test_decompose_node_requires_evidence(self) -> None:
        plan = _plan([_node("n1")])
        with pytest.raises(DecomposeError):
            decompose_node(plan, "n1", _children(), trigger="two_failures", attempts=0)

    def test_decompose_node_respects_limits(self) -> None:
        plan = _plan([_node("n1")], max_depth=0)
        with pytest.raises(DecomposeError):
            decompose_node(
                plan, "n1", _children(), trigger="ambiguity", ambiguous=True
            )

    def test_decompose_node_adds_children_with_deps(self) -> None:
        plan = _plan([_node("n1")])
        updated = decompose_node(
            plan, "n1", _children(), trigger="two_failures", attempts=2
        )
        assert updated["nodes"][0]["status"] == "active"
        children = [node for node in updated["nodes"] if node["depends_on"] == ["n1"]]
        assert len(children) == 2
        assert {child["statement"] for child in children} == {"Child A", "Child B"}
        assert validate_plan(updated, 5.0) == []
