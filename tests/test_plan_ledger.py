"""P-156 T01-T06: Progress Ledger five questions, loop detection and candidates."""
from __future__ import annotations

import hashlib
import json

from researchclaw.plan.ledger import compute_ledger
from researchclaw.plan.schema import seal_plan


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


class TestProgressLedger:
    def test_ledger_completes_when_all_done(self) -> None:
        plan = _plan([_node("n1", status="done"), _node("n2", status="abandoned")])
        ledger = compute_ledger(plan)
        assert ledger["is_complete"] is True
        assert ledger["next_node"] is None
        assert ledger["completed"] == ["n1"]

    def test_ledger_identifies_next_node(self) -> None:
        plan = _plan([_node("n1", status="done"), _node("n2", deps=["n1"])])
        ledger = compute_ledger(plan)
        assert ledger["next_node"] == "n2"
        assert "Statement n2" in ledger["next_instruction"]
        assert "2" in ledger["next_instruction"]

    def test_ledger_detects_loop_after_two_rounds(self) -> None:
        plan = _plan([_node("n1", status="done"), _node("n2", deps=["n1"])])
        first = compute_ledger(plan)
        second = compute_ledger(plan, previous=first)
        assert second["is_looping"] is True
        assert second["loop_rounds"] >= 1
        assert second["forward_progress"] is False

    def test_ledger_progress_breaks_loop(self) -> None:
        first_plan = _plan([_node("n1", status="done"), _node("n2", deps=["n1"])])
        first = compute_ledger(first_plan)
        progressed = _plan(
            [
                _node("n1", status="done"),
                _node("n2", status="done", deps=["n1"]),
                _node("n3", deps=["n2"]),
            ]
        )
        second = compute_ledger(progressed, previous=first)
        assert second["is_looping"] is False
        assert second["forward_progress"] is True

    def test_ledger_lists_decompose_candidates(self) -> None:
        plan = _plan([_node("n1", status="active"), _node("n2")])
        events = [
            {"type": "node.failed", "payload": {"node_id": "n1"}},
            {"type": "node.failed", "payload": {"node_id": "n1"}},
            {"type": "node.failed", "payload": {"node_id": "n2"}},
        ]
        ledger = compute_ledger(plan, events=events)
        candidates = {item["node_id"]: item["reason"] for item in ledger["decompose_candidates"]}
        assert candidates == {"n1": "two_failures"}

    def test_ledger_is_read_only(self) -> None:
        plan = _plan([_node("n1", status="done"), _node("n2")])
        before = hashlib.sha256(json.dumps(plan, sort_keys=True).encode("utf-8")).hexdigest()
        compute_ledger(plan, events=[{"type": "node.failed", "payload": {"node_id": "n2"}}])
        after = hashlib.sha256(json.dumps(plan, sort_keys=True).encode("utf-8")).hexdigest()
        assert before == after
