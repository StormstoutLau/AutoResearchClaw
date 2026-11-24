"""Task corpus loader and validator for the orchestration harness."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .model import (
    SCHEMA_TASK,
    AggregateSpec,
    Budget,
    OrchestrationTask,
    Subgoal,
    Trap,
    Worker,
)

TASKS_DIR = Path(__file__).resolve().parent / "tasks"
REPO_ROOT = Path(__file__).resolve().parents[3]

TASK_ORDER: tuple[str, ...] = (
    "D1", "D2", "D3", "D4",
    "L1", "L2", "L3", "L4",
    "A1", "A2", "A3", "A4",
    "C1", "C2", "C3",
)

_CLASSES = frozenset({"D", "L", "A", "C"})
_INVALID_POLICIES = frozenset({"exclude", "keep_with_flag"})
_CONFLICT_RULES = frozenset({"prefer_higher_n", "dedupe_overlap", "method_evidence"})


def _tuple(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in (value or ()))


def _parse_task(data: dict[str, Any], path: Path) -> OrchestrationTask:
    if data.get("schema") != SCHEMA_TASK:
        raise ValueError(f"{path.name}: unsupported schema {data.get('schema')!r}")

    aggregate = data["aggregate"]
    budget = data["budget"]
    trap_data = data.get("trap")
    task = OrchestrationTask(
        id=str(data["id"]),
        cls=str(data["class"]),
        title=str(data.get("title", "")),
        source_manifest=str(data["source_manifest"]),
        version=int(data.get("version", 1)),
        prompt=str(data["prompt"]),
        delegation_style=str(data.get("delegation_style", "capability")),
        subgoals=tuple(
            Subgoal(
                id=str(item["id"]),
                capability=str(item["capability"]),
                depends_on=_tuple(item.get("depends_on")),
                inputs=_tuple(item.get("inputs")),
                outputs=_tuple(item.get("outputs")),
                acceptance=str(item.get("acceptance", "")),
            )
            for item in data["subgoals"]
        ),
        worker_pool=tuple(
            Worker(id=str(item["id"]), capabilities=_tuple(item.get("capabilities")))
            for item in data["worker_pool"]
        ),
        aggregate=AggregateSpec(
            columns=_tuple(aggregate["columns"]),
            key=_tuple(aggregate["key"]),
            invalid_policy=str(aggregate.get("invalid_policy", "exclude")),
            conflict_required=bool(aggregate.get("conflict_required", False)),
            conflict_rule=aggregate.get("conflict_rule"),
            arithmetic=aggregate.get("arithmetic"),
            group_by=_tuple(aggregate.get("group_by")),
        ),
        trap=(
            Trap(
                kind=str(trap_data["kind"]),
                subgoals=_tuple(trap_data.get("subgoals")),
                hint=str(trap_data.get("hint", "")),
            )
            if trap_data
            else None
        ),
        budget=Budget(
            tokens=int(budget["tokens"]),
            wall_seconds=float(budget["wall_seconds"]),
            max_workers=int(budget["max_workers"]),
            max_depth=int(budget["max_depth"]),
        ),
        truth=copy.deepcopy(data["truth"]),
    )
    if path.stem != task.id:
        raise ValueError(f"{path.name}: id {task.id!r} does not match filename")
    return task


def topological_levels(task: OrchestrationTask) -> list[tuple[Subgoal, ...]]:
    """Return Kahn levels; raises ValueError on a cycle or unknown dependency."""
    order = {goal.id: index for index, goal in enumerate(task.subgoals)}
    remaining = {goal.id: set(goal.depends_on) for goal in task.subgoals}
    unknown = {dep for deps in remaining.values() for dep in deps if dep not in order}
    if unknown:
        raise ValueError(f"{task.id}: unknown dependencies {sorted(unknown)}")

    levels: list[tuple[Subgoal, ...]] = []
    resolved: set[str] = set()
    while remaining:
        ready = sorted(
            (goal_id for goal_id, deps in remaining.items() if deps <= resolved),
            key=order.__getitem__,
        )
        if not ready:
            raise ValueError(f"{task.id}: dependency cycle")
        levels.append(tuple(next(g for g in task.subgoals if g.id == goal_id) for goal_id in ready))
        for goal_id in ready:
            remaining.pop(goal_id)
            resolved.add(goal_id)
    return levels


def validate_task(task: OrchestrationTask) -> list[str]:
    issues: list[str] = []
    if task.cls not in _CLASSES:
        issues.append(f"unknown class {task.cls!r}")
    if task.delegation_style not in {"capability", "distinct_roles"}:
        issues.append(f"unknown delegation_style {task.delegation_style!r}")
    if not (REPO_ROOT / task.source_manifest).is_file():
        issues.append(f"source_manifest missing: {task.source_manifest}")
    if not task.prompt.strip():
        issues.append("prompt is empty")

    ids = [goal.id for goal in task.subgoals]
    if len(ids) != len(set(ids)):
        issues.append("duplicate subgoal id")
    for goal in task.subgoals:
        if not goal.capability or not goal.inputs or not goal.outputs or not goal.acceptance:
            issues.append(f"subgoal {goal.id} has an incomplete contract")
        for dep in goal.depends_on:
            if dep not in ids:
                issues.append(f"subgoal {goal.id} depends on unknown {dep}")
    try:
        levels = topological_levels(task)
    except ValueError as exc:
        issues.append(str(exc))
        levels = []

    covered = {cap for worker in task.worker_pool for cap in worker.capabilities}
    for goal in task.subgoals:
        if goal.capability not in covered:
            issues.append(f"capability {goal.capability!r} has no worker")

    spec = task.aggregate
    if not spec.columns or not spec.key:
        issues.append("aggregate columns/key must be non-empty")
    if not set(spec.key) <= set(spec.columns):
        issues.append("aggregate key must be a subset of columns")
    if spec.invalid_policy not in _INVALID_POLICIES:
        issues.append(f"unknown invalid_policy {spec.invalid_policy!r}")
    if spec.conflict_required and spec.conflict_rule not in _CONFLICT_RULES:
        issues.append("conflict_required needs a known conflict_rule")
    if spec.arithmetic not in (None, "mean_by_group"):
        issues.append(f"unknown arithmetic {spec.arithmetic!r}")
    if spec.arithmetic == "mean_by_group" and not spec.group_by:
        issues.append("mean_by_group needs group_by")

    budget = task.budget
    if min(budget.tokens, budget.wall_seconds, budget.max_workers, budget.max_depth) <= 0:
        issues.append("budget entries must be positive")
    if levels and max(len(level) for level in levels) > budget.max_workers:
        issues.append("max_workers is smaller than the widest DAG level")

    rows = task.truth.get("rows") or []
    if not rows:
        issues.append("truth.rows is empty")
    if any("subgoal" not in row for row in rows):
        issues.append("every truth row needs a subgoal")
    invalid_declared = set(_tuple(task.truth.get("invalid_subgoals")))
    invalid_derived = {
        str(row["subgoal"])
        for row in rows
        if not row.get("valid", True)
    }
    if invalid_declared != invalid_derived:
        issues.append(
            f"invalid_subgoals {sorted(invalid_declared)} != rows {sorted(invalid_derived)}"
        )
    if spec.conflict_required and not task.truth.get("expected_conflicts"):
        issues.append("conflict tasks need expected_conflicts")
    if spec.conflict_required and not task.truth.get("expected_rows"):
        issues.append("conflict tasks need expected_rows")
    return issues


def load_task(task_id: str, tasks_dir: Path | None = None) -> OrchestrationTask:
    directory = Path(tasks_dir) if tasks_dir is not None else TASKS_DIR
    path = directory / f"{task_id}.json"
    if not path.is_file():
        raise ValueError(f"unknown task: {task_id}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name}: invalid JSON: {exc}") from exc
    task = _parse_task(data, path)
    issues = validate_task(task)
    if issues:
        raise ValueError(f"{task_id}: " + "; ".join(issues))
    return task


def load_tasks(tasks_dir: Path | None = None) -> list[OrchestrationTask]:
    return [load_task(task_id, tasks_dir) for task_id in TASK_ORDER]
