"""Deterministic ResearchPlan rebuild from stage artifacts (P-177).

Used to unblock runs whose plan was derived by the pre-P-177 builders (single
literature hub, duplicated stage nodes). The rebuild is a pure function of the
on-disk artifacts, so it is reproducible; completed/failed/abandoned statuses
are preserved by statement key.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .derive import (
    _node_key,
    add_experiment_nodes,
    add_hypothesis_nodes,
    add_synthesis_gaps,
    build_initial_plan,
)
from .schema import (
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_FANOUT,
    _depth_and_fanout,
    _node_maps,
    seal_plan,
    validate_plan,
)
from .store import load_plan, update_plan

_PROTECTED = ("done", "failed", "abandoned")


def _read(run_dir: Path, rel: str) -> str:
    path = run_dir / rel
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def rebuild_plan(
    run_dir: str | Path,
    *,
    stage: int = 9,
    max_fanout: int | None = None,
    max_depth: int | None = None,
) -> dict[str, Any]:
    """Rebuild and persist a valid plan; returns ``{plan, violations, shape}``."""
    run_dir = Path(run_dir)
    old = load_plan(run_dir)
    old_nodes = list((old or {}).get("nodes") or [])

    goal_text = _read(run_dir, "stage-01/goal.md")
    problem_tree = _read(run_dir, "stage-02/problem_tree.md")
    synthesis = _read(run_dir, "stage-07/synthesis.md")
    hypotheses = _read(run_dir, "stage-08/hypotheses.md")
    exp_text = _read(run_dir, "stage-09/exp_plan.yaml")
    try:
        experiment_plan = yaml.safe_load(exp_text) if exp_text.strip() else {}
    except yaml.YAMLError:
        experiment_plan = {}

    constraints = dict((old or {}).get("constraints") or {})
    budget = float(constraints.get("budget_usd") or 5.0)
    domains = tuple(constraints.get("domains") or ())
    topic = str((old or {}).get("goal") or "").strip() or _first_line(goal_text) or "topic"

    plan = build_initial_plan(
        topic=topic,
        goal_text=goal_text,
        problem_tree=problem_tree,
        run_budget_usd=budget,
        domains=domains,
    )
    if synthesis.strip():
        plan = add_synthesis_gaps(plan, synthesis)
    if hypotheses.strip():
        plan = add_hypothesis_nodes(plan, hypotheses)
    if isinstance(experiment_plan, dict) and experiment_plan:
        plan = add_experiment_nodes(plan, experiment_plan)

    plan["constraints"]["max_depth"] = int(max_depth or DEFAULT_MAX_DEPTH)
    plan["constraints"]["max_fanout"] = int(max_fanout or DEFAULT_MAX_FANOUT)

    status_by_key = {
        _node_key(node): str(node.get("status"))
        for node in old_nodes
        if str(node.get("status")) in _PROTECTED
    }
    for node in plan["nodes"]:
        status = status_by_key.get(_node_key(node))
        if status:
            node["status"] = status

    if old is not None:
        previous = int(old.get("version", 1))
        plan["version"] = previous + 1
        plan["parent_version"] = previous
        plan["replan"] = {
            **dict(old.get("replan") or plan.get("replan") or {}),
            "last_reason": "plan_rebuild",
        }

    sealed = seal_plan(plan)
    violations = validate_plan(sealed, budget)
    if not violations:
        update_plan(run_dir, sealed, stage=stage)

    depth, fanout = _depth_and_fanout(_node_maps(sealed["nodes"]))
    return {
        "plan": sealed,
        "violations": [item.message for item in violations],
        "nodes": len(sealed["nodes"]),
        "depth": depth,
        "fanout": fanout,
        "persisted": not violations,
    }


def _first_line(text: str) -> str:
    for line in str(text or "").splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped and not stripped.startswith((">", "---", "|")):
            return stripped[:120]
    return ""
