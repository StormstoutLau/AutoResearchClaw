"""P-156 T07-T15: versioned replanning, completed-node preservation and approval."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from researchclaw.plan.replan import ReplanError, apply_replan, plan_diff, replan
from researchclaw.plan.schema import seal_plan
from researchclaw.plan.store import read_events, write_plan


def _node(node_id: str, *, status: str = "proposed", statement: str = "", deps=()) -> dict:
    return {
        "id": node_id,
        "type": "question",
        "statement": statement or f"Statement {node_id}",
        "depends_on": list(deps),
        "owner_stage": 2,
        "inputs": [],
        "outputs": ["stage-02/problem_tree.md"],
        "acceptance": ["measurable criterion"],
        "evidence_required": False,
        "budget": {"tokens": 100, "usd": 0.0},
        "status": status,
    }


def _plan(nodes: list[dict], *, version: int = 1, goal: str = "Test goal") -> dict:
    plan = {
        "schema": "research-plan/1",
        "plan_id": "rp-test",
        "version": version,
        "parent_version": None if version == 1 else version - 1,
        "goal": goal,
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


class TestReplan:
    def test_replan_preserves_done_nodes(self) -> None:
        old = _plan([_node("n1", status="done"), _node("n2")])
        new_nodes = [_node("n1", status="done"), _node("n2"), _node("n3")]
        updated = replan(old, nodes=new_nodes)
        diff = plan_diff(old, updated)
        assert diff["preserved"] == ["n1", "n2"]
        assert diff["added"] == ["n3"]
        assert updated["version"] == 2
        assert updated["parent_version"] == 1

    def test_replan_rejects_removing_done_node(self) -> None:
        old = _plan([_node("n1", status="done"), _node("n2")])
        with pytest.raises(ReplanError):
            replan(old, nodes=[_node("n2")])

    def test_replan_requires_approved_goal(self) -> None:
        old = _plan([_node("n1")])
        with pytest.raises(ReplanError):
            replan(old, goal="Different goal")

    def test_replan_with_approved_goal_bumps_version(self) -> None:
        old = _plan([_node("n1")])
        updated = replan(old, goal="Different goal", approved_goal=True)
        assert updated["goal"] == "Different goal"
        assert updated["version"] == 2
        assert updated["parent_version"] == 1

    def test_replan_diff_has_four_buckets(self) -> None:
        old = _plan(
            [
                _node("n1", status="done"),
                _node("n2", statement="old"),
                _node("n3"),
            ]
        )
        new_nodes = [
            _node("n1", status="done"),
            _node("n2", statement="new"),
            _node("n4"),
        ]
        updated = replan(old, nodes=new_nodes)
        diff = plan_diff(old, updated)
        assert sorted(diff["added"]) == ["n4"]
        assert sorted(diff["removed"]) == ["n3"]
        assert sorted(diff["changed"]) == ["n2"]
        assert sorted(diff["preserved"]) == ["n1"]

    def test_replan_rejects_max_versions(self) -> None:
        old = _plan([_node("n1")], version=3)
        with pytest.raises(ReplanError):
            replan(old, nodes=[_node("n1"), _node("n2")])

    def test_apply_replan_writes_versioned_file_and_event(self, tmp_path: Path) -> None:
        old = _plan([_node("n1"), _node("n2")])
        write_plan(tmp_path, old, stage=2)
        result = apply_replan(
            tmp_path,
            nodes=[_node("n1"), _node("n2"), _node("n3")],
            reason="two_failures",
        )
        assert result["plan"]["version"] == 2
        assert (tmp_path / "plan" / "plan.v2.json").is_file()
        index = json.loads((tmp_path / "plan" / "index.json").read_text(encoding="utf-8"))
        assert index["version"] == 2
        events = read_events(tmp_path)
        assert events[-1]["type"] == "plan.replanned"
        assert events[-1]["payload"]["diff"]["added"] == ["n3"]

    def test_apply_replan_rejects_in_place_digest_drift(self, tmp_path: Path) -> None:
        old = _plan([_node("n1")])
        write_plan(tmp_path, old, stage=2)
        path = tmp_path / "plan" / "plan.v1.json"
        tampered = json.loads(path.read_text(encoding="utf-8"))
        tampered["goal"] = "Silently changed"
        path.write_text(json.dumps(tampered), encoding="utf-8")
        with pytest.raises(ReplanError):
            apply_replan(tmp_path, nodes=[_node("n1"), _node("n2")])

    def test_apply_replan_reads_approvals_fail_closed(self, tmp_path: Path) -> None:
        old = _plan([_node("n1")])
        write_plan(tmp_path, old, stage=2)
        with pytest.raises(ReplanError):
            apply_replan(tmp_path, goal="New goal")
        (tmp_path / "approvals.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(ReplanError):
            apply_replan(tmp_path, goal="New goal")
        (tmp_path / "approvals.json").write_text(
            json.dumps({"plan_goal_change": {"approved": True, "by": "tester"}}),
            encoding="utf-8",
        )
        result = apply_replan(tmp_path, goal="New goal")
        assert result["plan"]["goal"] == "New goal"
