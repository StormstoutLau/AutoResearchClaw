"""ResearchPlan v1 schema, digest and deterministic validator (G8a / P-152).

Design authority: ``docs/research-plan-design.md`` §4, §6 and §10. The plan is
a constrained task graph on top of the existing 23 stages: it never replaces
stage execution, it only makes decomposition, dependencies and acceptance
mechanically checkable.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping

from researchclaw.runtime.event_log import canonical_json

SCHEMA_ID = "research-plan/1"
NODE_TYPES = (
    "question",
    "literature",
    "hypothesis",
    "experiment",
    "analysis",
    "writing",
    "verification",
)
NODE_STATUSES = ("proposed", "active", "done", "failed", "abandoned")
MAX_NODES = 40
DEFAULT_MAX_DEPTH = 3
DEFAULT_MAX_FANOUT = 8

_REQUIRED_TOP = (
    "schema",
    "plan_id",
    "version",
    "goal",
    "constraints",
    "nodes",
    "replan",
    "provenance",
    "plan_digest",
)
_REQUIRED_NODE = (
    "id",
    "type",
    "statement",
    "depends_on",
    "owner_stage",
    "acceptance",
    "evidence_required",
    "budget",
    "status",
)


@dataclass(frozen=True)
class Violation:
    """One deterministic validator failure (V1..V12)."""

    rule: str
    message: str
    node_id: str | None = None

    def as_dict(self) -> dict:
        data = {"rule": self.rule, "message": self.message}
        if self.node_id is not None:
            data["node_id"] = self.node_id
        return data


def plan_digest(plan: Mapping[str, Any]) -> str:
    """Canonical content digest; excludes ``plan_digest`` itself."""
    body = {key: value for key, value in plan.items() if key != "plan_digest"}
    return "sha256:" + hashlib.sha256(
        canonical_json(body).encode("utf-8")
    ).hexdigest()


def seal_plan(plan: Mapping[str, Any]) -> dict:
    """Return a copy with a freshly computed ``plan_digest``."""
    sealed = dict(plan)
    sealed["plan_digest"] = plan_digest(sealed)
    return sealed


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _node_maps(nodes: list) -> dict[str, Mapping[str, Any]]:
    return {
        str(node.get("id")): node
        for node in nodes
        if isinstance(node, Mapping) and node.get("id") is not None
    }


def _has_cycle(by_id: Mapping[str, Mapping[str, Any]]) -> bool:
    state: dict[str, int] = {}

    def visit(node_id: str) -> bool:
        if state.get(node_id) == 1:
            return True
        if state.get(node_id) == 2:
            return False
        state[node_id] = 1
        for dep in by_id[node_id].get("depends_on") or []:
            if dep in by_id and visit(str(dep)):
                return True
        state[node_id] = 2
        return False

    return any(visit(node_id) for node_id in by_id if state.get(node_id, 0) == 0)


def _depth_and_fanout(by_id: Mapping[str, Mapping[str, Any]]) -> tuple[int, int]:
    children: dict[str, list[str]] = {node_id: [] for node_id in by_id}
    roots: list[str] = []
    for node_id, node in by_id.items():
        deps = [str(dep) for dep in (node.get("depends_on") or []) if str(dep) in by_id]
        if not deps:
            roots.append(node_id)
        for dep in deps:
            children[dep].append(node_id)
    fanout = max((len(items) for items in children.values()), default=0)
    memo: dict[str, int] = {}

    def depth(node_id: str) -> int:
        if node_id in memo:
            return memo[node_id]
        memo[node_id] = 0 if not children[node_id] else 1 + max(
            depth(child) for child in children[node_id]
        )
        return memo[node_id]

    max_depth = max((depth(root) for root in roots), default=0)
    return max_depth, fanout


def validate_plan(
    plan: Mapping[str, Any],
    run_budget_usd: float | None = None,
) -> list[Violation]:
    """Run V1..V12; an empty list means the plan is accepted."""
    violations: list[Violation] = []
    if not isinstance(plan, Mapping):
        return [Violation("V1", "plan must be an object")]

    # V1 — required shape
    for key in _REQUIRED_TOP:
        if key not in plan:
            violations.append(Violation("V1", f"missing top-level field: {key}"))
    if plan.get("schema") != SCHEMA_ID:
        violations.append(Violation("V1", f"schema must be {SCHEMA_ID!r}"))
    if not _is_nonempty_str(plan.get("plan_id")):
        violations.append(Violation("V1", "plan_id must be a non-empty string"))
    version = plan.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        violations.append(Violation("V1", "version must be an integer >= 1"))
    if not _is_nonempty_str(plan.get("goal")):
        violations.append(Violation("V1", "goal must be a non-empty string"))
    constraints = plan.get("constraints")
    if not isinstance(constraints, Mapping):
        violations.append(Violation("V1", "constraints must be an object"))
        constraints = {}
    for key in ("max_depth", "max_fanout", "budget_usd"):
        if key not in constraints:
            violations.append(Violation("V1", f"constraints missing: {key}"))
    max_depth = constraints.get("max_depth", DEFAULT_MAX_DEPTH)
    max_fanout = constraints.get("max_fanout", DEFAULT_MAX_FANOUT)
    nodes = plan.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        violations.append(Violation("V1", "nodes must be a non-empty list"))
        nodes = []

    for node in nodes:
        if not isinstance(node, Mapping):
            violations.append(Violation("V1", "node must be an object"))
            continue
        node_id = node.get("id")
        for key in _REQUIRED_NODE:
            if key not in node:
                violations.append(Violation("V1", f"node missing field: {key}", node_id))
        if node.get("type") not in NODE_TYPES:
            violations.append(Violation("V1", f"unknown node type: {node.get('type')!r}", node_id))
        if node.get("status") not in NODE_STATUSES:
            violations.append(Violation("V1", f"unknown status: {node.get('status')!r}", node_id))
        budget = node.get("budget")
        if not isinstance(budget, Mapping):
            violations.append(Violation("V1", "budget must be an object", node_id))
        else:
            for key in ("tokens", "usd"):
                if not _is_number(budget.get(key)) or budget.get(key, -1) < 0:
                    violations.append(Violation("V1", f"budget.{key} must be >= 0", node_id))
        acceptance = node.get("acceptance")
        if not isinstance(acceptance, list) or not acceptance:
            violations.append(Violation("V1", "acceptance must be a non-empty list", node_id))

    by_id = _node_maps(nodes)

    # V2 — unique ids
    seen: set[str] = set()
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        node_id = node.get("id")
        if node_id in seen:
            violations.append(Violation("V2", f"duplicate node id: {node_id}", node_id))
        seen.add(node_id)

    # V3 — dependencies resolve
    for node_id, node in by_id.items():
        deps = node.get("depends_on")
        if not isinstance(deps, list):
            violations.append(Violation("V1", "depends_on must be a list", node_id))
            continue
        for dep in deps:
            if str(dep) not in by_id:
                violations.append(Violation("V3", f"unresolved dependency: {dep}", node_id))

    # V4 — acyclic
    if by_id and _has_cycle(by_id):
        violations.append(Violation("V4", "dependency graph contains a cycle"))

    # V5 — owner_stage range
    for node_id, node in by_id.items():
        stage = node.get("owner_stage")
        if not isinstance(stage, int) or isinstance(stage, bool) or not 1 <= stage <= 23:
            violations.append(Violation("V5", f"owner_stage out of range: {stage!r}", node_id))

    # V6 — experiment fields
    for node_id, node in by_id.items():
        if node.get("type") != "experiment":
            continue
        for key in ("metric", "dataset"):
            if not _is_nonempty_str(node.get(key)):
                violations.append(Violation("V6", f"experiment missing {key}", node_id))
        baseline = node.get("baseline")
        if not isinstance(baseline, list) or not baseline:
            violations.append(Violation("V6", "experiment missing baseline", node_id))

    # V7 — hypothesis must rest on literature
    for node_id, node in by_id.items():
        if node.get("type") != "hypothesis":
            continue
        deps = [by_id[str(dep)] for dep in (node.get("depends_on") or []) if str(dep) in by_id]
        if not any(dep.get("type") == "literature" for dep in deps):
            violations.append(Violation("V7", "hypothesis must depend on a literature node", node_id))

    # V8 — writing must rest on analysis
    for node_id, node in by_id.items():
        if node.get("type") != "writing":
            continue
        deps = [by_id[str(dep)] for dep in (node.get("depends_on") or []) if str(dep) in by_id]
        if not any(dep.get("type") == "analysis" for dep in deps):
            violations.append(Violation("V8", "writing must depend on an analysis node", node_id))

    # V9 — evidence-bearing nodes declare outputs and acceptance
    for node_id, node in by_id.items():
        if not node.get("evidence_required"):
            continue
        outputs = node.get("outputs")
        if not isinstance(outputs, list) or not outputs:
            violations.append(Violation("V9", "evidence node must declare outputs", node_id))
        acceptance = node.get("acceptance")
        if not isinstance(acceptance, list) or not acceptance:
            violations.append(Violation("V9", "evidence node must declare acceptance", node_id))

    # V10 — budget sum
    total = 0.0
    for node in by_id.values():
        budget = node.get("budget")
        if isinstance(budget, Mapping) and _is_number(budget.get("usd")):
            total += float(budget["usd"])
    cap = run_budget_usd if run_budget_usd is not None else constraints.get("budget_usd")
    if _is_number(cap) and total > float(cap) + 1e-9:
        violations.append(Violation("V10", f"budget {total:.4f} exceeds cap {float(cap):.4f}"))

    # V11 — shape and duplicate statements
    if len(nodes) > MAX_NODES:
        violations.append(Violation("V11", f"node count {len(nodes)} exceeds {MAX_NODES}"))
    if by_id and not _has_cycle(by_id):
        depth, fanout = _depth_and_fanout(by_id)
        if _is_number(max_depth) and depth > int(max_depth):
            violations.append(Violation("V11", f"depth {depth} exceeds {max_depth}"))
        if _is_number(max_fanout) and fanout > int(max_fanout):
            violations.append(Violation("V11", f"fanout {fanout} exceeds {max_fanout}"))
    statements = [
        str(node.get("statement", "")).strip()
        for node in by_id.values()
        if node.get("statement")
    ]
    if len(statements) != len(set(statements)):
        violations.append(Violation("V11", "duplicate node statement"))

    # V12 — digest
    if plan.get("plan_digest") != plan_digest(plan):
        violations.append(Violation("V12", "plan_digest mismatch"))

    return violations
