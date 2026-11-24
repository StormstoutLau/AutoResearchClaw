"""Versioned replanning: diff, completed-node preservation and goal approval (G8b).

Pure functions do the policy checks; ``apply_replan`` is the only writer and it
re-reads ``approvals.json`` so a goal change cannot be approved by a caller flag
alone (invariant J-2).
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping

from researchclaw.plan.schema import plan_digest, seal_plan, validate_plan
from researchclaw.plan.store import (
    append_event,
    load_plan,
    write_replan,
)
from researchclaw.runtime.event_log import canonical_json
from researchclaw.tools.approvals import is_approved

GOAL_APPROVAL_KEY = "plan_goal_change"
DEFAULT_MAX_VERSIONS = 3


class ReplanError(ValueError):
    """A replan violates versioning, completion or approval invariants."""


def _by_id(nodes: Any) -> dict[str, Mapping[str, Any]]:
    return {
        str(node.get("id")): node
        for node in (nodes or [])
        if isinstance(node, Mapping) and node.get("id") is not None
    }


def plan_diff(old: Mapping[str, Any], new: Mapping[str, Any]) -> dict:
    """Four-bucket diff: added / removed / changed / preserved."""
    old_nodes = _by_id(old.get("nodes"))
    new_nodes = _by_id(new.get("nodes"))
    added = sorted(set(new_nodes) - set(old_nodes))
    removed = sorted(set(old_nodes) - set(new_nodes))
    changed: list[str] = []
    preserved: list[str] = []
    for node_id in sorted(set(old_nodes) & set(new_nodes)):
        if canonical_json(old_nodes[node_id]) == canonical_json(new_nodes[node_id]):
            preserved.append(node_id)
        else:
            changed.append(node_id)
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "preserved": preserved,
    }


def replan(
    plan: Mapping[str, Any],
    *,
    nodes: list[Mapping[str, Any]] | None = None,
    goal: str | None = None,
    approved_goal: bool = False,
    reason: str = "human_request",
    max_versions: int | None = None,
) -> dict:
    """Return a new plan version; never mutates ``plan``."""
    if not isinstance(plan, Mapping):
        raise ReplanError("plan must be an object")
    version = plan.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ReplanError("plan version must be an integer >= 1")

    replan_cfg = plan.get("replan") if isinstance(plan.get("replan"), Mapping) else {}
    cap = max_versions if max_versions is not None else replan_cfg.get(
        "max_versions", DEFAULT_MAX_VERSIONS
    )
    if version >= int(cap):
        raise ReplanError(f"max_versions reached: {version} >= {cap}")

    old_goal = str(plan.get("goal") or "")
    if goal is not None and str(goal) != old_goal and not approved_goal:
        raise ReplanError("goal change requires human approval")

    old_nodes = [copy.deepcopy(node) for node in (plan.get("nodes") or [])]
    new_nodes = (
        [copy.deepcopy(dict(node)) for node in nodes]
        if nodes is not None
        else old_nodes
    )
    old_by_id = _by_id(old_nodes)
    new_by_id = _by_id(new_nodes)
    for node_id, old_node in old_by_id.items():
        if old_node.get("status") != "done":
            continue
        new_node = new_by_id.get(node_id)
        if new_node is None or canonical_json(old_node) != canonical_json(new_node):
            raise ReplanError(
                f"completed node cannot be removed or changed: {node_id}"
            )

    updated = copy.deepcopy(dict(plan))
    updated["version"] = version + 1
    updated["parent_version"] = version
    updated["nodes"] = new_nodes
    if goal is not None:
        updated["goal"] = str(goal)
    updated["replan"] = {
        **dict(replan_cfg),
        "preserve_completed": True,
        "last_reason": str(reason),
    }
    return seal_plan(updated)


def apply_replan(
    run_dir: str | Path,
    *,
    nodes: list[Mapping[str, Any]] | None = None,
    goal: str | None = None,
    reason: str = "human_request",
    stage: int = 15,
) -> dict:
    """Validate and persist the next plan version; returns plan plus diff."""
    current = load_plan(run_dir)
    if current is None:
        raise ReplanError("no research plan to replan")
    if current.get("plan_digest") != plan_digest(current):
        raise ReplanError("current plan digest mismatch (in-place edit rejected)")

    goal_changed = goal is not None and str(goal) != str(current.get("goal") or "")
    approved = is_approved(run_dir, GOAL_APPROVAL_KEY) if goal_changed else False
    updated = replan(
        current,
        nodes=nodes,
        goal=goal,
        approved_goal=approved,
        reason=reason,
    )

    constraints = (
        updated.get("constraints")
        if isinstance(updated.get("constraints"), Mapping)
        else {}
    )
    violations = validate_plan(updated, run_budget_usd=constraints.get("budget_usd"))
    if violations:
        raise ReplanError(
            "replanned plan is invalid: "
            + "; ".join(item.message for item in violations[:5])
        )

    diff = plan_diff(current, updated)
    sealed = write_replan(
        run_dir,
        updated,
        stage=stage,
        diff=diff,
        reason=reason,
    )
    return {"plan": sealed, "diff": diff}


def request_replan(
    run_dir: str | Path,
    *,
    reason: str,
    ledger: Mapping[str, Any],
) -> None:
    """Record that a replan is wanted; never mutates the plan (D-8)."""
    append_event(
        run_dir,
        "plan.replan_requested",
        {
            "reason": str(reason),
            "plan_version": ledger.get("plan_version"),
            "next_node": ledger.get("next_node"),
            "is_looping": bool(ledger.get("is_looping")),
            "forward_progress": bool(ledger.get("forward_progress")),
        },
    )


__all__ = [
    "GOAL_APPROVAL_KEY",
    "ReplanError",
    "apply_replan",
    "plan_diff",
    "replan",
    "request_replan",
]
