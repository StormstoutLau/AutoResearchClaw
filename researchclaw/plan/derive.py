"""Deterministic ResearchPlan builders for stages 2, 7, 8, 9 and 14 (G8a / P-152).

The builders read artefacts that the stages already produce, so planning adds no
extra LLM call and stays reproducible. Stage 2 derives question nodes from
``problem_tree.md``; later stages append literature, hypothesis, experiment and
analysis nodes. Validation happens in the stage hooks, not here.
"""
from __future__ import annotations

import copy
import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from researchclaw.plan.schema import (
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_FANOUT,
    SCHEMA_ID,
    seal_plan,
)

_NUMBERED = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+(.+)$")
_HYPOTHESIS = re.compile(r"^\s*(?:#{2,4}\s*)?(H\d+[.:)]?\s+.+)$", re.IGNORECASE)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trim(text: str, limit: int = 300) -> str:
    clean = " ".join(str(text).split())
    return clean[:limit]


def _section_lines(text: str, keyword: str) -> list[str]:
    lines = text.splitlines()
    out: list[str] = []
    active = False
    for line in lines:
        if line.startswith("## "):
            active = keyword.lower() in line.lower()
            continue
        if active:
            out.append(line)
    return out


def _list_items(lines: Iterable[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        match = _NUMBERED.match(line)
        if match:
            value = _trim(match.group(1))
            if value:
                out.append(value)
    return out


def _next_id(plan: Mapping[str, Any]) -> str:
    used = {str(node.get("id")) for node in plan.get("nodes") or []}
    index = 1
    while f"n{index}" in used:
        index += 1
    return f"n{index}"


def _append_node(plan: dict, node: dict) -> dict:
    node = dict(node)
    node["id"] = _next_id(plan)
    plan.setdefault("nodes", []).append(node)
    return node


def _base_node(
    *,
    node_type: str,
    statement: str,
    owner_stage: int,
    outputs: list[str],
    acceptance: list[str],
    depends_on: list[str] | None = None,
    evidence_required: bool = False,
    budget: Mapping[str, Any] | None = None,
    **extra: Any,
) -> dict:
    node = {
        "id": "",
        "type": node_type,
        "statement": _trim(statement),
        "depends_on": list(depends_on or []),
        "owner_stage": int(owner_stage),
        "inputs": [],
        "outputs": list(outputs),
        "acceptance": list(acceptance),
        "evidence_required": bool(evidence_required),
        "budget": dict(budget or {"tokens": 1200, "usd": 0.0}),
        "status": "proposed",
    }
    node.update(extra)
    return node


def _names(items: Any) -> list[str]:
    out: list[str] = []
    for item in items or []:
        if isinstance(item, str):
            value = item.strip()
        elif isinstance(item, Mapping):
            value = str(
                item.get("name") or item.get("method") or item.get("title") or ""
            ).strip()
        else:
            value = ""
        if value:
            out.append(value)
    return out


def build_initial_plan(
    *,
    topic: str,
    goal_text: str,
    problem_tree: str,
    run_budget_usd: float = 5.0,
    domains: Iterable[str] = (),
) -> dict:
    """Stage 2: derive question nodes from the decomposition artefact."""
    questions = _list_items(_section_lines(problem_tree, "Sub-questions"))[:8]
    if not questions:
        questions = [_trim(topic) or "Research question"]

    goal = ""
    for line in (goal_text or "").splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        goal = _trim(candidate)
        break
    if not goal:
        for line in (goal_text or "").splitlines():
            candidate = line.strip().lstrip("#").strip()
            if candidate:
                goal = _trim(candidate)
                break
    goal = goal or _trim(topic) or "Research goal"

    budget = max(float(run_budget_usd or 0.0), 0.0)
    # Floor to micro-dollars so the sum never exceeds the cap by rounding.
    per_node = int((budget / max(len(questions), 1)) * 1_000_000) / 1_000_000
    nodes = [
        _base_node(
            node_type="question",
            statement=question,
            owner_stage=2,
            outputs=["stage-02/problem_tree.md"],
            acceptance=["answer the sub-question with at least one measurable criterion"],
            budget={"tokens": 1200, "usd": per_node},
        )
        for question in questions
    ]

    plan = {
        "schema": SCHEMA_ID,
        "plan_id": "rp-" + hashlib.sha256((topic or "topic").encode("utf-8")).hexdigest()[:8],
        "version": 1,
        "parent_version": None,
        "goal": goal,
        "constraints": {
            "budget_usd": budget,
            "deadline": None,
            "domains": [str(domain) for domain in domains],
            "max_depth": DEFAULT_MAX_DEPTH,
            "max_fanout": DEFAULT_MAX_FANOUT,
        },
        "facts": [],
        "unknowns": [],
        "assumptions": [],
        "nodes": [],
        "replan": {
            "triggers": [
                "gate_reject",
                "two_failures",
                "contradiction",
                "budget_half_no_progress",
                "human_request",
            ],
            "max_versions": 3,
            "preserve_completed": True,
        },
        "provenance": {
            "prompt_version": "problem_decompose@derived",
            "model": "",
            "created_at": _now_iso(),
        },
    }
    for node in nodes:
        _append_node(plan, node)
    return seal_plan(plan)


def _gap_statements(synthesis_md: str) -> list[str]:
    gaps: list[str] = []
    lines = synthesis_md.splitlines()
    for index, line in enumerate(lines):
        if not line.strip().lower().startswith("## gap"):
            continue
        heading = _trim(line.lstrip("#").strip())
        detail = ""
        for follow in lines[index + 1: index + 4]:
            if follow.strip() and not follow.startswith("#"):
                detail = _trim(follow)
                break
        gaps.append(_trim(f"{heading}: {detail}" if detail else heading))
    return [gap for gap in gaps if gap]


def add_synthesis_gaps(plan: Mapping[str, Any], synthesis_md: str) -> dict:
    """Stage 7: gaps become unknowns plus literature and question nodes."""
    updated = copy.deepcopy(dict(plan))
    gaps = _gap_statements(synthesis_md) or ["Unresolved gap identified during synthesis"]
    unknowns = list(updated.get("unknowns") or [])
    for gap in gaps:
        if gap not in unknowns:
            unknowns.append(gap)
    updated["unknowns"] = unknowns

    question_ids = [
        str(node.get("id"))
        for node in updated.get("nodes") or []
        if node.get("type") == "question"
    ]
    literature = _append_node(updated, _base_node(
        node_type="literature",
        statement=f"Collect the literature evidence behind: {updated.get('goal', '')}",
        owner_stage=7,
        outputs=["stage-07/synthesis.md"],
        acceptance=["at least one gap is backed by collected evidence"],
        depends_on=question_ids[:8],
    ))
    for gap in gaps:
        _append_node(updated, _base_node(
            node_type="question",
            statement=gap,
            owner_stage=7,
            outputs=["stage-07/synthesis.md"],
            acceptance=["gap is answered with cited evidence"],
            depends_on=[literature["id"]],
        ))
    return seal_plan(updated)


def _hypothesis_statements(hypotheses_md: str) -> list[str]:
    statements = [
        _trim(match.group(1))
        for line in hypotheses_md.splitlines()
        if (match := _HYPOTHESIS.match(line))
    ]
    if statements:
        return statements[:5]
    items = _list_items(_section_lines(hypotheses_md, "Hypotheses"))
    return items[:5] or [_trim(hypotheses_md.splitlines()[0] if hypotheses_md.strip() else "Hypothesis")]


def add_hypothesis_nodes(plan: Mapping[str, Any], hypotheses_md: str) -> dict:
    """Stage 8: each hypothesis becomes a node resting on literature."""
    updated = copy.deepcopy(dict(plan))
    literature_ids = [
        str(node.get("id"))
        for node in updated.get("nodes") or []
        if node.get("type") == "literature"
    ]
    if not literature_ids:
        literature = _append_node(updated, _base_node(
            node_type="literature",
            statement=f"Literature evidence for hypotheses on: {updated.get('goal', '')}",
            owner_stage=8,
            outputs=["stage-08/hypotheses.md"],
            acceptance=["hypothesis cites at least one source"],
        ))
        literature_ids = [literature["id"]]
    for statement in _hypothesis_statements(hypotheses_md):
        _append_node(updated, _base_node(
            node_type="hypothesis",
            statement=statement,
            owner_stage=8,
            outputs=["stage-08/hypotheses.md"],
            acceptance=["hypothesis is falsifiable and has a testable prediction"],
            depends_on=[literature_ids[-1]],
        ))
    return seal_plan(updated)


def add_experiment_nodes(plan: Mapping[str, Any], experiment_plan: Mapping[str, Any]) -> dict:
    """Stage 9: one experiment node per proposed method, bound to ``exp_plan``."""
    updated = copy.deepcopy(dict(plan))
    if any(node.get("type") == "experiment" for node in updated.get("nodes") or []):
        return seal_plan(updated)

    methods = _names(experiment_plan.get("proposed_methods")) or _names(
        experiment_plan.get("ablations")
    )
    if not methods:
        methods = ["default_condition"]
    metrics = _names(experiment_plan.get("metrics")) or ["primary_metric"]
    datasets = _names(experiment_plan.get("datasets")) or ["primary_dataset"]
    baselines = _names(experiment_plan.get("baselines")) or ["baseline"]

    # Bind experiments to the literature evidence (fallbacks: hypothesis,
    # question) so the question → literature → experiment → analysis chain
    # stays within max_depth=3.
    support_ids = [
        str(node.get("id"))
        for node in updated.get("nodes") or []
        if node.get("type") == "literature"
    ] or [
        str(node.get("id"))
        for node in updated.get("nodes") or []
        if node.get("type") == "hypothesis"
    ] or [
        str(node.get("id"))
        for node in updated.get("nodes") or []
        if node.get("type") == "question"
    ]

    for method in methods:
        _append_node(updated, _base_node(
            node_type="experiment",
            statement=f"Run {method} on {datasets[0]} against {', '.join(baselines[:2])}",
            owner_stage=9,
            inputs=["stage-09/exp_plan.yaml"],
            outputs=["stage-12/run_results.json"],
            acceptance=[
                "each condition runs with at least 3 seeds",
                "report mean and variance",
                "record process returncode",
            ],
            depends_on=support_ids[-3:],
            evidence_required=True,
            budget={"tokens": 4000, "usd": 0.0},
            metric=metrics[0],
            dataset=datasets[0],
            baseline=list(baselines),
            method=method,
        ))
    return seal_plan(updated)


def check_experiment_plan_consistency(
    plan: Mapping[str, Any],
    experiment_plan: Mapping[str, Any],
) -> list[str]:
    """Two-way check between experiment nodes and ``exp_plan.yaml``."""
    mismatches: list[str] = []
    nodes = [node for node in plan.get("nodes") or [] if node.get("type") == "experiment"]
    if not nodes:
        return ["plan has no experiment nodes"]

    expected_methods = set(_names(experiment_plan.get("proposed_methods"))) or set(
        _names(experiment_plan.get("ablations"))
    )
    actual_methods = {str(node.get("method", "")) for node in nodes}
    if not expected_methods:
        mismatches.append("exp_plan has no proposed_methods")
    elif expected_methods != actual_methods:
        mismatches.append(
            "condition mismatch: plan=%s exp_plan=%s"
            % (sorted(actual_methods), sorted(expected_methods))
        )

    metrics = set(_names(experiment_plan.get("metrics")))
    datasets = set(_names(experiment_plan.get("datasets")))
    baselines = set(_names(experiment_plan.get("baselines")))
    for node in nodes:
        if metrics and str(node.get("metric", "")) not in metrics:
            mismatches.append(f"{node.get('id')}: metric not in exp_plan")
        if datasets and str(node.get("dataset", "")) not in datasets:
            mismatches.append(f"{node.get('id')}: dataset not in exp_plan")
        if baselines and not set(node.get("baseline") or []).issubset(baselines):
            mismatches.append(f"{node.get('id')}: baseline not in exp_plan")
    return mismatches


def mark_analysis_done(plan: Mapping[str, Any], *, metrics_present: bool) -> dict:
    """Stage 14: record whether result analysis actually produced metrics."""
    updated = copy.deepcopy(dict(plan))
    status = "done" if metrics_present else "failed"
    experiment_ids = [
        str(node.get("id"))
        for node in updated.get("nodes") or []
        if node.get("type") == "experiment"
    ]
    analysis_nodes = [
        node for node in updated.get("nodes") or [] if node.get("type") == "analysis"
    ]
    if analysis_nodes:
        target = analysis_nodes[-1]
    else:
        target = _append_node(updated, _base_node(
            node_type="analysis",
            statement="Analyse experiment results and answer the plan questions",
            owner_stage=14,
            outputs=["stage-14/analysis.md"],
            acceptance=["each experiment node reports a metric or a failure reason"],
            depends_on=experiment_ids,
        ))
    target["status"] = status
    if metrics_present:
        for node in updated.get("nodes") or []:
            if node.get("type") == "experiment" and node.get("status") in (
                "proposed",
                "active",
            ):
                node["status"] = "done"
    return seal_plan(updated)
