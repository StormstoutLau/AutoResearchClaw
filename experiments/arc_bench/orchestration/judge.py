"""Deterministic orchestration judge.

Reads only the five artifacts plus the in-memory task. Prose files are never
opened. Every score is derived from file content and frozen truth rows; an
optional residual hook receives a whitelisted payload only.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path
from typing import Any, Callable

from .model import (
    SCHEMA_AGGREGATE,
    SCHEMA_DELEGATIONS,
    SCHEMA_PLAN,
    SCHEMA_RESULT,
    SCHEMA_TRACE,
    SCHEMA_USAGE,
    OrchestrationArtifacts,
    OrchestrationTask,
)

WHITELIST: tuple[str, ...] = (
    "task.json",
    "plan.json",
    "delegations.json",
    "aggregate.json",
    "trace.jsonl",
    "usage.json",
)

_EPS = 1e-9


def _norm(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 9)
    return value


def _row_key(row: dict[str, Any], columns: tuple[str, ...]) -> tuple[Any, ...]:
    return tuple(_norm(row.get(column)) for column in columns)


def _project(row: dict[str, Any], columns: tuple[str, ...]) -> dict[str, Any]:
    return {column: row.get(column) for column in columns}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            spans.append(json.loads(line))
    return spans


def _max_concurrency(spans: list[dict[str, Any]]) -> int:
    events: list[tuple[float, int]] = []
    for span in spans:
        events.append((float(span["start"]), 1))
        events.append((float(span["end"]), -1))
    events.sort(key=lambda item: (item[0], item[1]))
    active = 0
    peak = 0
    for _, delta in events:
        active += delta
        peak = max(peak, active)
    return peak


def usage_from_trace(trace: list[dict[str, Any]]) -> dict[str, Any]:
    prompt = sum(int(span.get("attributes", {}).get("tokens_in", 0)) for span in trace)
    completion = sum(int(span.get("attributes", {}).get("tokens_out", 0)) for span in trace)
    workers = [span for span in trace if span.get("kind") == "worker"]
    if trace:
        start = min(float(span["start"]) for span in trace)
        end = max(float(span["end"]) for span in trace)
        wall = max(0.0, end - start)
    else:
        wall = 0.0
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "tool_calls": len(workers),
        "llm_calls": len(workers) + 2,
        "wall_seconds": round(wall, 6),
        "max_concurrency": _max_concurrency(workers),
    }


def _failure(
    task: OrchestrationTask,
    adapter: str,
    *,
    missing: list[str] | None = None,
    parse_errors: list[str] | None = None,
) -> dict[str, Any]:
    max_score = 9 if task.cls == "C" else 12
    checks = {
        "plan_ok": False,
        "delegation_ok": False,
        "aggregate_ok": False,
        "trace_ok": False,
        "budget_ok": False,
        "ob3_parallel_claim_ok": False,
        "ob4_budget_state_ok": False,
        "usage_matches_trace": False,
        "invalid_policy_ok": False,
        "conflicts_ok": False,
        "arithmetic_ok": None,
        "cost_reference_missing": False,
        "missing_files": missing or [],
        "parse_errors": parse_errors or [],
    }
    return {
        "schema": SCHEMA_RESULT,
        "task_id": task.id,
        "class": task.cls,
        "adapter": adapter,
        "scores": {"decomposition": 0, "delegation": 0, "aggregation": 0, "cost": 0},
        "max_score": max_score,
        "total": 0,
        "gate_zeroed": True,
        "gate_reasons": ["missing_or_unparseable_artifacts"],
        "checks": checks,
        "inputs_whitelist": list(WHITELIST),
        "reference": None,
        "residual": {"enabled": False, "score": 0},
    }


def judge_run(
    task: OrchestrationTask,
    run_dir: Path,
    *,
    reference_usage: dict[str, Any] | None = None,
    residual_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    missing: list[str] = []
    parse_errors: list[str] = []
    loaded: dict[str, Any] = {}

    readers = {
        "plan.json": _read_json,
        "delegations.json": _read_json,
        "aggregate.json": _read_json,
        "trace.jsonl": _read_jsonl,
        "usage.json": _read_json,
    }
    for name, reader in readers.items():
        path = run_dir / name
        if not path.is_file():
            missing.append(name)
            continue
        try:
            loaded[name] = reader(path)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            parse_errors.append(f"{name}: {exc}")

    if missing or parse_errors:
        adapter = "unknown"
        if isinstance(loaded.get("usage.json"), dict):
            adapter = str(loaded["usage.json"].get("adapter", adapter))
        return _failure(task, adapter, missing=missing, parse_errors=parse_errors)

    plan = loaded["plan.json"]
    delegations = loaded["delegations.json"].get("delegations", [])
    aggregate = loaded["aggregate.json"]
    trace = loaded["trace.jsonl"]
    usage = loaded["usage.json"]
    adapter = str(usage.get("adapter", "unknown"))

    schema_errors = []
    for name, payload, schema in (
        ("plan.json", plan, SCHEMA_PLAN),
        ("delegations.json", loaded["delegations.json"], SCHEMA_DELEGATIONS),
        ("aggregate.json", aggregate, SCHEMA_AGGREGATE),
        ("usage.json", usage, SCHEMA_USAGE),
    ):
        if payload.get("schema") != schema:
            schema_errors.append(f"{name}: schema {payload.get('schema')!r}")
        if payload.get("task_id") != task.id:
            schema_errors.append(f"{name}: task_id mismatch")
    if any(span.get("schema") != SCHEMA_TRACE for span in trace):
        schema_errors.append("trace.jsonl: schema mismatch")
    if schema_errors:
        return _failure(task, adapter, parse_errors=schema_errors)

    artifacts = OrchestrationArtifacts(
        plan=plan,
        delegations=delegations,
        aggregate=aggregate,
        trace=trace,
        usage=usage,
    )
    return _judge_core(
        task,
        artifacts,
        adapter=adapter,
        reference_usage=reference_usage,
        residual_fn=residual_fn,
    )


def judge_artifacts(
    task: OrchestrationTask,
    artifacts: OrchestrationArtifacts,
    *,
    reference_usage: dict[str, Any] | None = None,
    residual_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    adapter = str(artifacts.usage.get("adapter", "unknown"))
    return _judge_core(
        task,
        artifacts,
        adapter=adapter,
        reference_usage=reference_usage,
        residual_fn=residual_fn,
    )


def _judge_core(
    task: OrchestrationTask,
    artifacts: OrchestrationArtifacts,
    *,
    adapter: str,
    reference_usage: dict[str, Any] | None,
    residual_fn: Callable[[dict[str, Any]], dict[str, Any]] | None,
) -> dict[str, Any]:
    plan_score, plan_issues = _score_plan(task, artifacts.plan)
    delegation_score, ob3, delegation_issues = _score_delegations(
        task, artifacts.delegations
    )
    aggregation_score, aggregate_checks = _score_aggregate(task, artifacts.aggregate)
    cost_score, cost_checks = _score_cost(
        task, artifacts.usage, artifacts.trace, reference_usage
    )
    trace_ok = _trace_structure_ok(artifacts.trace)

    checks = {
        "plan_ok": plan_score >= 3,
        "delegation_ok": delegation_score >= 3,
        "aggregate_ok": aggregation_score >= 3,
        "trace_ok": trace_ok,
        "budget_ok": cost_checks["budget_ok"],
        "ob3_parallel_claim_ok": ob3,
        "ob4_budget_state_ok": cost_checks["ob4_ok"],
        "usage_matches_trace": cost_checks["usage_matches_trace"],
        "invalid_policy_ok": aggregate_checks["invalid_policy_ok"],
        "conflicts_ok": aggregate_checks["conflicts_ok"],
        "arithmetic_ok": aggregate_checks["arithmetic_ok"],
        "cost_reference_missing": reference_usage is None,
        "missing_files": [],
        "parse_errors": [],
        "plan_issues": plan_issues,
        "delegation_issues": delegation_issues,
    }

    scores = {
        "decomposition": plan_score,
        "delegation": delegation_score,
        "aggregation": aggregation_score,
        "cost": cost_score if trace_ok else 0,
    }

    residual = {"enabled": False, "score": 0}
    if residual_fn is not None:
        payload = {
            "task_id": task.id,
            "class": task.cls,
            "prompt": task.prompt,
            "subgoals": [
                {"id": goal.id, "outputs": list(goal.outputs)} for goal in task.subgoals
            ],
            "plan": artifacts.plan,
            "delegations": artifacts.delegations,
            "aggregate": artifacts.aggregate,
            "trace": artifacts.trace,
            "usage": artifacts.usage,
        }
        outcome = residual_fn(payload) or {}
        delta = max(-1, min(1, int(outcome.get("decomposition_delta", 0))))
        scores["decomposition"] = max(0, min(3, scores["decomposition"] + delta))
        residual = {
            "enabled": True,
            "score": delta,
            "reason": str(outcome.get("reason", "")),
            "prompt_hash": hashlib.sha256(
                json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest(),
        }

    gate_reasons: list[str] = []
    if scores["aggregation"] == 0:
        gate_reasons.append("aggregation_zero")
    if not ob3:
        gate_reasons.append("parallel_claim_mismatch")

    if task.cls == "C":
        max_score = 9
        total = scores["decomposition"] + scores["delegation"] + scores["cost"]
    else:
        max_score = 12
        total = sum(scores.values())
    if gate_reasons:
        total = 0
    total = max(0, min(max_score, total))

    reference = None
    if reference_usage is not None:
        reference = {
            "adapter": reference_usage.get("adapter", "gold_orchestrator"),
            "total_tokens": _usage_total(reference_usage),
        }

    return {
        "schema": SCHEMA_RESULT,
        "task_id": task.id,
        "class": task.cls,
        "adapter": adapter,
        "scores": scores,
        "max_score": max_score,
        "total": total,
        "gate_zeroed": bool(gate_reasons),
        "gate_reasons": gate_reasons,
        "checks": checks,
        "inputs_whitelist": list(WHITELIST),
        "reference": reference,
        "residual": residual,
    }


def _score_plan(task: OrchestrationTask, plan: dict[str, Any]) -> tuple[int, list[str]]:
    nodes = plan.get("nodes") or []
    required = {goal.id: goal for goal in task.subgoals}
    if not nodes:
        return 0, ["empty plan"]
    if len(nodes) > 2 * len(required):
        return 0, [f"over-split: {len(nodes)} nodes for {len(required)} subgoals"]

    ids = [str(node.get("id")) for node in nodes]
    missing = set(required) - set(ids)
    extra = set(ids) - set(required)
    contracts_ok = all(
        node.get("inputs") and node.get("outputs") and node.get("acceptance")
        for node in nodes
    )
    deps_ok = True
    outputs_ok = True
    for node in nodes:
        node_id = str(node.get("id"))
        if node_id not in required:
            continue
        goal = required[node_id]
        if set(node.get("depends_on") or []) != set(goal.depends_on):
            deps_ok = False
        if set(node.get("outputs") or []) != set(goal.outputs):
            outputs_ok = False

    issues: list[str] = []
    if missing:
        issues.append(f"missing subgoals: {sorted(missing)}")
        return (1 if len(nodes) <= 1 else 2), issues
    if extra:
        issues.append(f"extra nodes: {sorted(extra)}")
        return 2, issues
    if not contracts_ok:
        issues.append("incomplete node contract")
        return 2, issues
    if not deps_ok:
        issues.append("dependency edges differ from task DAG")
        return 2, issues
    if not outputs_ok:
        issues.append("declared outputs differ from task contract")
        return 2, issues
    return 3, issues


def _worker_capabilities(task: OrchestrationTask, worker_id: str) -> tuple[str, ...] | None:
    for worker in task.worker_pool:
        if worker.id == worker_id:
            return worker.capabilities
    return None


def _score_delegations(
    task: OrchestrationTask, delegations: list[dict[str, Any]]
) -> tuple[int, bool, list[str]]:
    required = {goal.id: goal for goal in task.subgoals}
    if not delegations:
        return 0, True, ["no delegations"]

    issues: list[str] = []
    by_subgoal: dict[str, list[dict[str, Any]]] = {}
    for delegation in delegations:
        by_subgoal.setdefault(str(delegation.get("subgoal")), []).append(delegation)
    missing = set(required) - set(by_subgoal)
    extra = set(by_subgoal) - set(required)

    capability_ok = True
    for subgoal_id, items in by_subgoal.items():
        goal = required.get(subgoal_id)
        if goal is None:
            continue
        for delegation in items:
            capabilities = _worker_capabilities(task, str(delegation.get("worker")))
            if capabilities is None or goal.capability not in capabilities:
                capability_ok = False
            if delegation.get("capability") != goal.capability:
                capability_ok = False
    if not capability_ok:
        issues.append("worker capability mismatch")

    roles_ok = True
    inputs_ok = True
    if task.delegation_style == "distinct_roles":
        real = [d for d in delegations if str(d.get("subgoal")) in required]
        workers = [str(d.get("worker")) for d in real]
        roles_ok = len(workers) == len(set(workers)) == len(required)
        for delegation in real:
            goal = required[str(delegation.get("subgoal"))]
            if set(delegation.get("inputs") or []) != set(goal.inputs):
                inputs_ok = False
        if not roles_ok:
            issues.append("duplicate role assignment")
        if not inputs_ok:
            issues.append("delegation inputs break role isolation")

    order_ok = True
    for subgoal_id, items in by_subgoal.items():
        goal = required.get(subgoal_id)
        if goal is None:
            continue
        for delegation in items:
            start = float(delegation.get("start", 0.0))
            for dep in goal.depends_on:
                dep_items = by_subgoal.get(dep) or []
                if not dep_items:
                    order_ok = False
                    continue
                if max(float(item.get("end", 0.0)) for item in dep_items) > start + _EPS:
                    order_ok = False
    if not order_ok:
        issues.append("delegation order violates the DAG")

    ob3 = True
    real_by_subgoal = {sid: items[0] for sid, items in by_subgoal.items() if sid in required}
    for subgoal_id, delegation in real_by_subgoal.items():
        for other_id in delegation.get("parallel_with") or []:
            other = real_by_subgoal.get(str(other_id))
            if other is None:
                ob3 = False
                continue
            overlap = float(delegation["start"]) < float(other["end"]) and float(
                other["start"]
            ) < float(delegation["end"])
            different_thread = delegation.get("thread_id") != other.get("thread_id")
            if not overlap or not different_thread:
                ob3 = False
    if not ob3:
        issues.append("declared parallel work did not overlap on distinct threads")

    duplicate_assignment = any(len(items) > 1 for items in by_subgoal.values())
    if not capability_ok or not ob3:
        return 0, ob3, issues
    if len(delegations) > 2 * len(required):
        issues.append("excessive delegation count")
        return 1, ob3, issues
    if missing:
        issues.append(f"missing delegations: {sorted(missing)}")
        return (1 if len(delegations) <= 1 else 2), ob3, issues
    if extra or duplicate_assignment:
        issues.append("redundant delegations")
        return 2, ob3, issues
    if not roles_ok or not inputs_ok or not order_ok:
        return 2, ob3, issues
    return 3, ob3, issues


def _score_aggregate(
    task: OrchestrationTask, aggregate: dict[str, Any]
) -> tuple[int, dict[str, Any]]:
    spec = task.aggregate
    columns = spec.columns
    rows = aggregate.get("rows")
    invalid = aggregate.get("invalid") or []
    conflicts = aggregate.get("conflicts") or []
    summary = aggregate.get("summary") or {}
    checks = {
        "invalid_policy_ok": False,
        "conflicts_ok": not spec.conflict_required,
        "arithmetic_ok": None if spec.arithmetic is None else False,
    }
    if not isinstance(rows, list) or not rows:
        return 0, checks
    if any(not isinstance(row, dict) or any(col not in row for col in columns) for row in rows):
        return 0, checks

    truth = task.truth
    invalid_ids = set(task.truth.get("invalid_subgoals") or [])
    expected_source = truth.get("expected_rows")
    if expected_source:
        expected_rows = [_project(row, columns) for row in expected_source]
    else:
        expected_rows = [
            _project(row, columns)
            for row in truth.get("rows", [])
            if row.get("valid", True)
        ]
    actual = sorted(_row_key(row, columns) for row in rows)
    expected = sorted(_row_key(row, columns) for row in expected_rows)

    duplicate_keys = len({_row_key(row, spec.key) for row in rows}) != len(rows)
    score = 3
    if actual != expected:
        full_rows = sorted(
            _row_key(_project(row, columns), columns) for row in truth.get("rows", [])
        )
        if spec.invalid_policy == "exclude" and actual == full_rows:
            checks["invalid_policy_ok"] = False
            score = min(score, 2)
        else:
            return 0, checks

    if spec.invalid_policy == "exclude":
        if set(map(str, invalid)) != invalid_ids:
            checks["invalid_policy_ok"] = False
            score = min(score, 2)
        else:
            checks["invalid_policy_ok"] = True
    else:
        checks["invalid_policy_ok"] = True

    if spec.conflict_required:
        expected_conflicts = {
            str(item["id"]): (item.get("chosen"), item.get("rule"))
            for item in truth.get("expected_conflicts", [])
        }
        actual_conflicts = {
            str(item.get("id")): (item.get("chosen"), item.get("rule"))
            for item in conflicts
        }
        if actual_conflicts != expected_conflicts:
            checks["conflicts_ok"] = False
            score = min(score, 2)
        else:
            checks["conflicts_ok"] = True
    elif conflicts:
        checks["conflicts_ok"] = False
        score = min(score, 2)

    if spec.arithmetic == "mean_by_group":
        recomputed = _recompute_summary(task, rows)
        checks["arithmetic_ok"] = _summary_equal(recomputed, summary)
        if not checks["arithmetic_ok"]:
            score = min(score, 2)

    if duplicate_keys:
        score = min(score, 1)
    return score, checks


def _recompute_summary(
    task: OrchestrationTask, rows: list[dict[str, Any]]
) -> dict[str, dict[str, float]]:
    spec = task.aggregate
    group_columns = spec.group_by
    metric_columns = [
        column
        for column in spec.columns
        if column not in spec.key and column not in group_columns
    ]
    buckets: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        group = "|".join(str(row[column]) for column in group_columns)
        for metric in metric_columns:
            value = row.get(metric)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                buckets.setdefault(group, {}).setdefault(metric, []).append(float(value))
    return {
        group: {metric: round(statistics.mean(values), 9) for metric, values in metrics.items()}
        for group, metrics in buckets.items()
    }


def _summary_equal(expected: dict[str, dict[str, float]], actual: dict[str, Any]) -> bool:
    if not isinstance(actual, dict) or set(actual) != set(expected):
        return False
    for group, metrics in expected.items():
        if not isinstance(actual.get(group), dict):
            return False
        if set(actual[group]) != set(metrics):
            return False
        for metric, value in metrics.items():
            observed = actual[group].get(metric)
            if not isinstance(observed, (int, float)):
                return False
            if abs(float(observed) - value) > 1e-6:
                return False
    return True


def _usage_total(usage: dict[str, Any]) -> int:
    return int(usage.get("prompt_tokens", 0)) + int(usage.get("completion_tokens", 0))


def _score_cost(
    task: OrchestrationTask,
    usage: dict[str, Any],
    trace: list[dict[str, Any]],
    reference_usage: dict[str, Any] | None,
) -> tuple[int, dict[str, Any]]:
    expected = usage_from_trace(trace)
    usage_matches = (
        int(usage.get("prompt_tokens", -1)) == expected["prompt_tokens"]
        and int(usage.get("completion_tokens", -1)) == expected["completion_tokens"]
    )
    status = str(usage.get("status", "completed"))
    exceeded = bool(usage.get("exceeded"))
    truncated = bool(usage.get("truncated"))
    budget = usage.get("budget") or {}
    charged = int(usage.get("charged_tokens", _usage_total(usage)))

    if status == "budget_exceeded":
        ob4_ok = exceeded and not truncated
    elif exceeded or truncated:
        ob4_ok = False
    else:
        ob4_ok = True
    budget_ok = charged <= int(budget.get("tokens", task.budget.tokens)) or (
        exceeded and status == "budget_exceeded"
    )

    checks = {
        "usage_matches_trace": usage_matches,
        "ob4_ok": ob4_ok,
        "budget_ok": budget_ok,
    }
    if not usage_matches or not ob4_ok or not budget_ok:
        return 0, checks
    if status in {"budget_exceeded", "timeout"}:
        return 0, checks
    if reference_usage is None:
        return 2, checks
    reference_total = _usage_total(reference_usage)
    if reference_total <= 0:
        return 2, checks
    ratio = _usage_total(usage) / reference_total
    if ratio <= 0.8 + _EPS:
        return 3, checks
    if ratio <= 1.0 + _EPS:
        return 2, checks
    if ratio <= 1.5 + _EPS:
        return 1, checks
    return 0, checks


def _trace_structure_ok(trace: list[dict[str, Any]]) -> bool:
    ids = [str(span.get("span_id")) for span in trace]
    if len(ids) != len(set(ids)):
        return False
    known = set(ids)
    for span in trace:
        parent = span.get("parent_id")
        if parent and str(parent) not in known:
            return False
        for key in ("start", "end", "thread_id", "pid"):
            if key not in span:
                return False
        if float(span["end"]) < float(span["start"]):
            return False
    return True
