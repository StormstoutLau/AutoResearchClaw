"""Deterministic ResearchPlan builders for stages 2, 7, 8, 9 and 14 (G8a / P-152).

The builders read artefacts that the stages already produce, so planning adds no
extra LLM call and stays reproducible. Stage 2 derives question nodes from
``problem_tree.md``; later stages append literature, hypothesis, experiment and
analysis nodes. Validation happens in the stage hooks, not here.

P-177 hardening:
- extraction accepts H1..H6 headings, ``SQ<n>`` markers and CJK hypothesis markers;
- every builder is idempotent (re-running a stage does not duplicate nodes);
- children are allocated across literature shards so no node exceeds
  ``constraints.max_fanout``; experiments rest on hypotheses when capacity allows.
"""
from __future__ import annotations

import copy
import hashlib
import math
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
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_SQ_HEADING = re.compile(r"^(?:S?Q|Question)\s*\d+\b", re.IGNORECASE)
_HYPOTHESIS_MARK = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:(?:最终|研究|核心|主要)?\s*假设|hypothesis|h)\s*([0-9]+)\b"
    r"[.:：、]?\s*(.*)$",
    re.IGNORECASE,
)
_HYPOTHESIS_SUBHEADINGS = {
    "核心主张",
    "为什么保留这个想法",
    "对反方担忧的回应",
    "可测量预测",
}
_GOAL_SKIP_PREFIXES = (">", "---", "***", "|")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trim(text: str, limit: int = 300) -> str:
    clean = " ".join(str(text).split())
    return clean[:limit]


def _clean_text(text: str) -> str:
    """Strip Markdown heading/emphasis markers from a statement."""
    clean = str(text).strip()
    heading = _HEADING.match(clean)
    if heading:
        clean = heading.group(2)
    clean = clean.strip()
    clean = clean.strip("*_` ")
    return " ".join(clean.split())


def _heading(line: str) -> tuple[int, str] | None:
    match = _HEADING.match(line)
    if not match:
        return None
    return len(match.group(1)), _clean_text(match.group(2))


def _section_block(text: str, keyword: str) -> list[str]:
    """Lines under the first heading containing ``keyword`` (any level)."""
    lines = str(text or "").splitlines()
    start = -1
    level = 0
    for index, line in enumerate(lines):
        heading = _heading(line)
        if heading and keyword.lower() in heading[1].lower():
            start, level = index, heading[0]
            break
    if start < 0:
        return []
    block: list[str] = []
    for line in lines[start + 1:]:
        heading = _heading(line)
        if heading and heading[0] <= level:
            break
        block.append(line)
    return block


def _list_items(lines: Iterable[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        match = _NUMBERED.match(line)
        if match:
            value = _clean_text(match.group(1))
            if value:
                out.append(_trim(value))
    return out


def _sub_questions(problem_tree: str) -> list[str]:
    """Extract sub-questions from H1/H2 sections, ``SQ<n>`` headings or lists."""
    text = str(problem_tree or "")
    block: list[str] = []
    for keyword in ("sub-question", "sub question", "research question"):
        block = _section_block(text, keyword)
        if block:
            break
    if not block:
        block = text.splitlines()

    headings = [
        heading[1]
        for heading in (_heading(line) for line in block)
        if heading and _SQ_HEADING.match(heading[1])
    ]
    if headings:
        return headings[:8]
    items = _list_items(block)
    if items:
        return items[:8]
    deeper = [heading[1] for heading in (_heading(line) for line in block) if heading]
    return deeper[:8]


def _goal_statement(goal_text: str) -> str:
    """First substantive line, skipping blockquote notes and separators."""
    for line in str(goal_text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(_GOAL_SKIP_PREFIXES):
            continue
        if stripped.startswith("**") and stripped.endswith("**") and len(stripped) > 4:
            stripped = stripped[2:-2].strip()
        if stripped:
            return _trim(stripped)
    return ""


def _hypothesis_statements(hypotheses_md: str) -> list[str]:
    """Hypothesis statements from ``H1`` / ``Hypothesis 1`` / ``最终假设 1``."""
    lines = str(hypotheses_md or "").splitlines()
    statements: list[str] = []
    for index, line in enumerate(lines):
        match = _HYPOTHESIS_MARK.match(line)
        if not match:
            continue
        text = _clean_text(match.group(2))
        if not text:
            for follow in lines[index + 1: index + 5]:
                heading = _heading(follow)
                if heading:
                    if heading[1].lower() in _HYPOTHESIS_SUBHEADINGS:
                        continue
                    text = heading[1]
                    break
                if follow.strip() and not follow.strip().startswith((">", "|")):
                    text = _clean_text(follow)
                    break
        if text:
            statements.append(_trim(text))
    if statements:
        return statements[:5]
    items = _list_items(_section_block(hypotheses_md, "hypothes"))
    if items:
        return items[:5]
    for line in lines:
        cleaned = _clean_text(line) if line.strip() else ""
        if cleaned and not cleaned.lower().startswith("hypothes"):
            return [_trim(cleaned)]
    return ["Hypothesis"]


def _node_key(node: Mapping[str, Any]) -> tuple[str, str]:
    return (str(node.get("type")), _clean_text(str(node.get("statement", ""))).lower())


def _next_id(plan: Mapping[str, Any]) -> str:
    used = {str(node.get("id")) for node in plan.get("nodes") or []}
    index = 1
    while f"n{index}" in used:
        index += 1
    return f"n{index}"


def _append_raw(plan: dict, node: dict, reuse: Mapping[tuple[str, str], str]) -> dict:
    node = dict(node)
    key = _node_key(node)
    if key in reuse:
        node["id"] = reuse[key]
    else:
        node["id"] = _next_id(plan)
    plan.setdefault("nodes", []).append(node)
    return node


def _take_owned(
    plan: dict, owner_stage: int, types: tuple[str, ...]
) -> dict[tuple[str, str], str]:
    """Remove stage-owned proposed/active nodes; return ``key -> id`` for reuse.

    Nodes referenced from outside the removal set are kept to avoid dangling
    dependencies (for example experiments that already rest on a hypothesis).
    """
    nodes = plan.get("nodes") or []
    drop_ids = {
        str(node.get("id"))
        for node in nodes
        if int(node.get("owner_stage", -1)) == owner_stage
        and node.get("type") in types
        and node.get("status") in ("proposed", "active")
    }
    if not drop_ids:
        return {}
    protected: set[str] = set()
    for node in nodes:
        node_id = str(node.get("id"))
        if node_id in drop_ids:
            continue
        for dep in node.get("depends_on") or []:
            if str(dep) in drop_ids:
                protected.add(str(dep))
    removable = drop_ids - protected
    reuse = {
        _node_key(node): str(node.get("id"))
        for node in nodes
        if str(node.get("id")) in removable
    }
    plan["nodes"] = [
        node for node in nodes if str(node.get("id")) not in removable
    ]
    return reuse


def _child_counts(nodes: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node in nodes:
        for dep in node.get("depends_on") or []:
            key = str(dep)
            counts[key] = counts.get(key, 0) + 1
    return counts


def _max_fanout(plan: Mapping[str, Any]) -> int:
    constraints = plan.get("constraints")
    if isinstance(constraints, Mapping):
        value = constraints.get("max_fanout")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    return DEFAULT_MAX_FANOUT


def _root_ids(plan: Mapping[str, Any]) -> list[str]:
    return [
        str(node.get("id"))
        for node in plan.get("nodes") or []
        if str(node.get("type")) == "question" and not node.get("depends_on")
    ]


def _literature_shards(plan: dict) -> list[str]:
    return [
        str(node.get("id"))
        for node in plan.get("nodes") or []
        if str(node.get("type")) == "literature"
    ]


def _new_literature_shard(plan: dict, *, stage: int) -> str:
    index = len(_literature_shards(plan)) + 1
    node = _append_raw(plan, _base_node(
        node_type="literature",
        statement=f"Literature evidence (group {index}) for: {plan.get('goal', '')}",
        owner_stage=stage,
        outputs=["stage-07/synthesis.md"],
        acceptance=["at least one gap is backed by collected evidence"],
        depends_on=_root_ids(plan),
    ), {})
    return str(node["id"])


def _ensure_literature(plan: dict, *, stage: int, needed: int | None = None) -> list[str]:
    """Return literature shard ids, creating deterministic shards as needed."""
    shards = _literature_shards(plan)
    target = 1
    if needed is not None:
        target = max(1, math.ceil(needed / _max_fanout(plan)))
    while len(shards) < target:
        shards.append(_new_literature_shard(plan, stage=stage))
    return shards


def _allocate(
    plan: dict,
    items: list[dict],
    parents: list[str],
    *,
    stage: int,
    reuse: Mapping[tuple[str, str], str],
) -> None:
    """Attach ``items`` to ``parents`` (<= max_fanout children), adding shards."""
    limit = _max_fanout(plan)
    counts = _child_counts(plan.get("nodes") or [])
    for item in items:
        parent = next((pid for pid in parents if counts.get(pid, 0) < limit), None)
        if parent is None:
            parent = _new_literature_shard(plan, stage=stage)
            parents.append(parent)
            counts[parent] = 0
        item["depends_on"] = [parent]
        _append_raw(plan, item, reuse)
        counts[parent] = counts.get(parent, 0) + 1


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
    questions = _sub_questions(problem_tree)[:8]
    if not questions:
        questions = [_trim(topic) or "Research question"]

    goal = _goal_statement(goal_text)
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
        _append_raw(plan, node, {})
    return seal_plan(plan)


def _gap_statements(synthesis_md: str) -> list[str]:
    gaps: list[str] = []
    lines = synthesis_md.splitlines()
    for index, line in enumerate(lines):
        if not line.strip().lower().startswith("## gap"):
            continue
        heading = _clean_text(line)
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

    reuse = _take_owned(updated, 7, ("question",))
    shards = _ensure_literature(updated, stage=7, needed=len(gaps))
    question_ids = [
        str(node.get("id"))
        for node in updated.get("nodes") or []
        if node.get("type") == "question" and node.get("owner_stage") == 2
    ]
    if question_ids:
        for shard in shards:
            for node in updated["nodes"]:
                if str(node.get("id")) == shard:
                    node["depends_on"] = question_ids[:8]

    nodes = [
        _base_node(
            node_type="question",
            statement=gap,
            owner_stage=7,
            outputs=["stage-07/synthesis.md"],
            acceptance=["gap is answered with cited evidence"],
        )
        for gap in gaps
    ]
    _allocate(updated, nodes, shards, stage=7, reuse=reuse)
    return seal_plan(updated)


def add_hypothesis_nodes(plan: Mapping[str, Any], hypotheses_md: str) -> dict:
    """Stage 8: each hypothesis becomes a node resting on literature."""
    updated = copy.deepcopy(dict(plan))
    shards = _ensure_literature(updated, stage=8, needed=1)
    reuse = _take_owned(updated, 8, ("hypothesis",))
    statements = _hypothesis_statements(hypotheses_md)
    nodes = [
        _base_node(
            node_type="hypothesis",
            statement=statement,
            owner_stage=8,
            outputs=["stage-08/hypotheses.md"],
            acceptance=["hypothesis is falsifiable and has a testable prediction"],
        )
        for statement in statements
    ]
    _allocate(updated, nodes, shards, stage=8, reuse=reuse)
    return seal_plan(updated)


def add_experiment_nodes(plan: Mapping[str, Any], experiment_plan: Mapping[str, Any]) -> dict:
    """Stage 9: one experiment node per proposed method, bound to ``exp_plan``.

    Experiments rest on hypotheses when capacity allows; overflow goes to a
    literature shard so ``fanout`` stays within ``constraints.max_fanout``.
    """
    updated = copy.deepcopy(dict(plan))
    methods = _names(experiment_plan.get("proposed_methods")) or _names(
        experiment_plan.get("ablations")
    )
    if not methods:
        methods = ["default_condition"]
    metrics = _names(experiment_plan.get("metrics")) or ["primary_metric"]
    datasets = _names(experiment_plan.get("datasets")) or ["primary_dataset"]
    baselines = _names(experiment_plan.get("baselines")) or ["baseline"]

    reuse = _take_owned(updated, 9, ("experiment",))

    parents = [
        str(node.get("id"))
        for node in updated.get("nodes") or []
        if node.get("type") == "hypothesis"
    ] or _ensure_literature(updated, stage=9, needed=1)

    nodes: list[dict] = []
    for method in methods:
        node = _base_node(
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
            evidence_required=True,
            budget={"tokens": 4000, "usd": 0.0},
            metric=metrics[0],
            dataset=datasets[0],
            baseline=list(baselines),
            method=method,
        )
        nodes.append(node)
    _allocate(updated, nodes, parents, stage=9, reuse=reuse)
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
        target = _append_raw(updated, _base_node(
            node_type="analysis",
            statement="Analyse experiment results and answer the plan questions",
            owner_stage=14,
            outputs=["stage-14/analysis.md"],
            acceptance=["each experiment node reports a metric or a failure reason"],
            depends_on=experiment_ids,
        ), {})
    target["status"] = status
    if metrics_present:
        for node in updated.get("nodes") or []:
            if node.get("type") == "experiment" and node.get("status") in (
                "proposed",
                "active",
            ):
                node["status"] = "done"
    return seal_plan(updated)
