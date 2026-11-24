"""ADaPT-style lazy decomposition with trigger evidence and shape limits (G8b).

Decomposition is allowed only when a node actually failed twice, was flagged
ambiguous, or burned half the budget without progress. The trigger must be
justified at the mutation boundary, so a planner cannot "decompose everything
up front" (invariant J-6).
"""
from __future__ import annotations

import copy
from typing import Any, Mapping

from researchclaw.plan.schema import (
    MAX_NODES,
    NODE_TYPES,
    seal_plan,
)

TRIGGERS = ("two_failures", "ambiguity", "budget_half_no_progress")


class DecomposeError(ValueError):
    """A decomposition lacks trigger evidence or violates plan limits."""


def _depths(plan: Mapping[str, Any]) -> dict[str, int]:
    nodes = {
        str(node.get("id")): node
        for node in (plan.get("nodes") or [])
        if isinstance(node, Mapping) and node.get("id") is not None
    }
    children: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    roots: list[str] = []
    for node_id, node in nodes.items():
        deps = [str(dep) for dep in (node.get("depends_on") or []) if str(dep) in nodes]
        if not deps:
            roots.append(node_id)
        for dep in deps:
            children[dep].append(node_id)
    memo: dict[str, int] = {}

    def depth(node_id: str) -> int:
        if node_id in memo:
            return memo[node_id]
        memo[node_id] = 0 if not children[node_id] else 1 + max(
            depth(child) for child in children[node_id]
        )
        return memo[node_id]

    for root in roots:
        depth(root)
    return memo


def _fanout(plan: Mapping[str, Any], node_id: str) -> int:
    count = 0
    for node in plan.get("nodes") or []:
        if not isinstance(node, Mapping):
            continue
        if node_id in [str(dep) for dep in (node.get("depends_on") or [])]:
            count += 1
    return count


def should_decompose(
    node: Mapping[str, Any],
    *,
    attempts: int = 0,
    ambiguous: bool = False,
    budget_ratio: float = 0.0,
    progress_ratio: float = 1.0,
    depth: int = 0,
    fanout: int = 0,
    max_depth: int = 3,
    max_fanout: int = 8,
) -> tuple[bool, str]:
    """Return ``(allowed, reason)``; reasons are stable strings."""
    if not isinstance(node, Mapping):
        return False, "shape"
    if node.get("status") not in ("proposed", "active"):
        return False, "status"
    if depth >= max_depth or fanout >= max_fanout:
        return False, "limits"
    if int(attempts) >= 2:
        return True, "two_failures"
    if ambiguous:
        return True, "ambiguity"
    if float(budget_ratio) >= 0.5 and float(progress_ratio) < 0.3:
        return True, "budget_half_no_progress"
    return False, "no_trigger"


def _next_id(plan: Mapping[str, Any]) -> str:
    used = {str(node.get("id")) for node in (plan.get("nodes") or [])}
    index = 1
    while f"n{index}" in used:
        index += 1
    return f"n{index}"


def _child_node(child: Mapping[str, Any], *, node_id: str, parent_id: str) -> dict:
    if child.get("type") not in NODE_TYPES:
        raise DecomposeError(f"invalid child type: {child.get('type')!r}")
    statement = " ".join(str(child.get("statement") or "").split())[:300]
    if not statement:
        raise DecomposeError("child statement must be non-empty")
    owner_stage = child.get("owner_stage")
    if not isinstance(owner_stage, int) or isinstance(owner_stage, bool) or not 1 <= owner_stage <= 23:
        raise DecomposeError(f"child owner_stage out of range: {owner_stage!r}")
    acceptance = child.get("acceptance")
    if not isinstance(acceptance, list) or not acceptance:
        raise DecomposeError("child acceptance must be a non-empty list")
    return {
        "id": node_id,
        "type": str(child["type"]),
        "statement": statement,
        "depends_on": [parent_id],
        "owner_stage": int(owner_stage),
        "inputs": list(child.get("inputs") or []),
        "outputs": list(child.get("outputs") or []),
        "acceptance": list(acceptance),
        "evidence_required": bool(child.get("evidence_required", False)),
        "budget": dict(child.get("budget") or {"tokens": 100, "usd": 0.0}),
        "status": "proposed",
    }


def decompose_node(
    plan: Mapping[str, Any],
    node_id: str,
    children: list[Mapping[str, Any]],
    *,
    trigger: str,
    attempts: int = 0,
    ambiguous: bool = False,
    budget_ratio: float = 0.0,
    progress_ratio: float = 1.0,
) -> dict:
    """Split ``node_id`` into validated children, or raise ``DecomposeError``."""
    if trigger not in TRIGGERS:
        raise DecomposeError(f"unknown decomposition trigger: {trigger!r}")
    nodes = {
        str(node.get("id")): node
        for node in (plan.get("nodes") or [])
        if isinstance(node, Mapping) and node.get("id") is not None
    }
    parent = nodes.get(str(node_id))
    if parent is None:
        raise DecomposeError(f"unknown node: {node_id}")

    constraints = (
        plan.get("constraints")
        if isinstance(plan.get("constraints"), Mapping)
        else {}
    )
    max_depth = int(constraints.get("max_depth", 3))
    max_fanout = int(constraints.get("max_fanout", 8))
    depth = _depths(plan).get(str(node_id), 0)
    fanout = _fanout(plan, str(node_id))
    allowed, reason = should_decompose(
        parent,
        attempts=attempts,
        ambiguous=ambiguous,
        budget_ratio=budget_ratio,
        progress_ratio=progress_ratio,
        depth=depth,
        fanout=fanout,
        max_depth=max_depth,
        max_fanout=max_fanout,
    )
    if not allowed or reason != trigger:
        raise DecomposeError(
            f"decomposition trigger not justified: wanted {trigger}, got {reason}"
        )

    if not 2 <= len(children) <= max_fanout:
        raise DecomposeError(f"child count must be 2..{max_fanout}")
    if len(nodes) + len(children) > MAX_NODES:
        raise DecomposeError(f"node cap {MAX_NODES} would be exceeded")

    updated = copy.deepcopy(dict(plan))
    new_nodes = list(updated.get("nodes") or [])
    parent_copy = next(
        node for node in new_nodes if str(node.get("id")) == str(node_id)
    )
    parent_copy["status"] = "active"
    for child in children:
        if not isinstance(child, Mapping):
            raise DecomposeError("child must be an object")
        child_id = _next_id(updated)
        built = _child_node(child, node_id=child_id, parent_id=str(node_id))
        updated.setdefault("nodes", []).append(built)
    return seal_plan(updated)


__all__ = [
    "TRIGGERS",
    "DecomposeError",
    "decompose_node",
    "should_decompose",
]
