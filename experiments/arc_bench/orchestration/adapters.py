"""Orchestration adapters: three normal entries plus four negative fixtures."""

from __future__ import annotations

import json
import os
import statistics
import threading
import time
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .judge import usage_from_trace
from .model import (
    SCHEMA_AGGREGATE,
    SCHEMA_DELEGATIONS,
    SCHEMA_PLAN,
    SCHEMA_TRACE,
    SCHEMA_USAGE,
    Budget,
    BudgetExceeded,
    BudgetTracker,
    OrchestrationArtifacts,
    OrchestrationTask,
    RunHandle,
    Subgoal,
)
from .tasks import topological_levels
from .workers import WorkerOutput, WorkerSimulator

_EMPTY: dict[str, Any] = {
    "plan": {},
    "delegations": [],
    "aggregate": {},
    "trace": [],
    "usage": {},
}


class SpanRecorder:
    def __init__(self, task_id: str, run_id: str, adapter_id: str) -> None:
        seed = f"{run_id}|{task_id}|{adapter_id}"
        self.trace_id = str(uuid.uuid5(uuid.NAMESPACE_URL, seed))
        self._start = time.monotonic()
        self._lock = threading.Lock()
        self.spans: list[dict[str, Any]] = []

    def now(self) -> float:
        return round(time.monotonic() - self._start, 6)

    def add(
        self,
        name: str,
        kind: str,
        parent_id: str | None,
        attributes: dict[str, Any],
        *,
        start: float,
        end: float,
    ) -> str:
        with self._lock:
            index = len(self.spans)
            span_id = str(
                uuid.uuid5(uuid.NAMESPACE_URL, f"{self.trace_id}|{name}|{index}")
            )
            self.spans.append(
                {
                    "schema": SCHEMA_TRACE,
                    "trace_id": self.trace_id,
                    "span_id": span_id,
                    "parent_id": parent_id or "",
                    "name": name,
                    "kind": kind,
                    "start": round(float(start), 6),
                    "end": round(float(end), 6),
                    "pid": os.getpid(),
                    "thread_id": threading.get_ident(),
                    "attributes": attributes,
                }
            )
            return span_id


def _project(row: dict[str, Any], columns: tuple[str, ...]) -> dict[str, Any]:
    return {column: row.get(column) for column in columns}


def _numeric(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 9)
    return value


def _empty_aggregate(task: OrchestrationTask) -> dict[str, Any]:
    return {
        "schema": SCHEMA_AGGREGATE,
        "task_id": task.id,
        "rows": [],
        "invalid": [],
        "conflicts": [],
        "summary": {},
    }


class OrchestrationAdapter(ABC):
    framework_id: str = "unknown"

    def start(self, task: OrchestrationTask, workdir: Path, budget: Budget) -> RunHandle:
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        handle = RunHandle(
            run_id=f"{self.framework_id}:{task.id}:{time.time_ns()}",
            workdir=workdir,
            task_id=task.id,
            adapter_id=self.framework_id,
        )
        handle.started_at = time.monotonic()

        def target() -> None:
            try:
                self._execute(task, workdir, budget, handle)
                handle.status = "completed"
            except BudgetExceeded as exc:
                handle.status = "budget_exceeded"
                handle.error = str(exc)
            except BaseException as exc:  # noqa: BLE001 - surfaced via handle
                handle.status = "failed"
                handle.error = f"{type(exc).__name__}: {exc}"
            finally:
                handle.elapsed_sec = time.monotonic() - handle.started_at

        handle.thread = threading.Thread(
            target=target,
            name=f"{self.framework_id}:{task.id}",
            daemon=True,
        )
        handle.thread.start()
        return handle

    def collect(self, handle: RunHandle, timeout_sec: float = 30.0) -> str:
        if handle.thread is not None:
            handle.thread.join(timeout_sec)
            if handle.thread.is_alive():
                handle.status = "timeout"
        return handle.status

    def artifacts(self, handle: RunHandle) -> OrchestrationArtifacts:
        workdir = handle.workdir
        readers = {
            "plan": ("plan.json", "json"),
            "delegations": ("delegations.json", "json"),
            "aggregate": ("aggregate.json", "json"),
            "trace": ("trace.jsonl", "jsonl"),
            "usage": ("usage.json", "json"),
        }
        data: dict[str, Any] = {}
        for key, (name, kind) in readers.items():
            path = workdir / name
            if not path.is_file():
                data[key] = _EMPTY[key]
                continue
            try:
                text = path.read_text(encoding="utf-8")
                if kind == "jsonl":
                    data[key] = [
                        json.loads(line) for line in text.splitlines() if line.strip()
                    ]
                else:
                    data[key] = json.loads(text)
            except (json.JSONDecodeError, OSError):
                data[key] = _EMPTY[key]
        delegations = data["delegations"]
        if isinstance(delegations, dict):
            delegations = delegations.get("delegations", [])
        return OrchestrationArtifacts(
            plan=data["plan"],
            delegations=list(delegations or []),
            aggregate=data["aggregate"],
            trace=list(data["trace"] or []),
            usage=data["usage"],
        )

    @abstractmethod
    def _execute(
        self,
        task: OrchestrationTask,
        workdir: Path,
        budget: Budget,
        handle: RunHandle,
    ) -> None:
        ...

    # ---------- helpers -----------------------------------------------------

    def _write(
        self,
        task: OrchestrationTask,
        workdir: Path,
        *,
        plan: dict[str, Any],
        delegations: list[dict[str, Any]],
        aggregate: dict[str, Any],
        trace: list[dict[str, Any]],
        usage: dict[str, Any],
    ) -> None:
        workdir.mkdir(parents=True, exist_ok=True)
        (workdir / "plan.json").write_text(
            json.dumps(plan, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )
        (workdir / "delegations.json").write_text(
            json.dumps(
                {"schema": SCHEMA_DELEGATIONS, "task_id": task.id, "delegations": delegations},
                indent=2,
                sort_keys=True,
                default=str,
            ),
            encoding="utf-8",
        )
        (workdir / "aggregate.json").write_text(
            json.dumps(aggregate, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )
        (workdir / "trace.jsonl").write_text(
            "".join(json.dumps(span, sort_keys=True, default=str) + "\n" for span in trace),
            encoding="utf-8",
        )
        (workdir / "usage.json").write_text(
            json.dumps(usage, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )

    def _usage(
        self,
        task: OrchestrationTask,
        trace: list[dict[str, Any]],
        tracker: BudgetTracker,
        *,
        status: str,
    ) -> dict[str, Any]:
        payload = usage_from_trace(trace)
        return {
            "schema": SCHEMA_USAGE,
            "task_id": task.id,
            "adapter": self.framework_id,
            **payload,
            "charged_tokens": tracker.total_tokens,
            "exceeded": tracker.exceeded is not None,
            "truncated": False,
            "status": status,
            "budget": {
                "tokens": task.budget.tokens,
                "wall_seconds": task.budget.wall_seconds,
                "max_workers": task.budget.max_workers,
                "max_depth": task.budget.max_depth,
            },
        }


class GoldOrchestratorAdapter(OrchestrationAdapter):
    framework_id = "gold_orchestrator"
    sequential = False
    split_factor = 1

    def _execute(
        self,
        task: OrchestrationTask,
        workdir: Path,
        budget: Budget,
        handle: RunHandle,
    ) -> None:
        tracker = BudgetTracker(budget)
        recorder = SpanRecorder(task.id, handle.run_id, self.framework_id)
        simulator = WorkerSimulator(task)
        subgoal_count = len(task.subgoals)

        plan_tokens = 64 + 24 * subgoal_count
        plan_start = recorder.now()
        plan_span = recorder.add(
            "plan",
            "orchestrator",
            None,
            {"tokens_in": plan_tokens, "tokens_out": 0},
            start=plan_start,
            end=plan_start,
        )
        tracker.charge_tokens(plan_tokens, reason="plan")

        assignments = self._assignments(task, simulator)
        nodes = self._build_nodes(task, assignments)
        plan = {
            "schema": SCHEMA_PLAN,
            "task_id": task.id,
            "nodes": nodes,
        }

        real_node = {
            goal.id: (goal.id if self.split_factor == 1 else f"{goal.id}__0")
            for goal in task.subgoals
        }
        outputs: dict[str, WorkerOutput] = {}
        delegations: list[dict[str, Any]] = []
        errors: list[BaseException] = []
        lock = threading.Lock()

        levels = topological_levels(task)
        for depth, level in enumerate(levels):
            tracker.enter_depth(depth)
            tracker.check_wall()
            siblings = [goal.id for goal in level]
            if self.sequential or len(level) == 1:
                for goal in level:
                    try:
                        self._run_goal(
                            task,
                            goal,
                            real_node[goal.id],
                            assignments[goal.id],
                            simulator,
                            tracker,
                            recorder,
                            plan_span,
                            siblings,
                            None,
                            outputs,
                            delegations,
                            lock,
                        )
                    except BaseException as exc:  # noqa: BLE001
                        errors.append(exc)
            else:
                barrier = threading.Barrier(len(level), timeout=5.0)

                def target(goal: Subgoal) -> None:
                    try:
                        self._run_goal(
                            task,
                            goal,
                            real_node[goal.id],
                            assignments[goal.id],
                            simulator,
                            tracker,
                            recorder,
                            plan_span,
                            siblings,
                            barrier,
                            outputs,
                            delegations,
                            lock,
                        )
                    except BaseException as exc:  # noqa: BLE001
                        errors.append(exc)

                threads = [
                    threading.Thread(target=target, args=(goal,), daemon=True)
                    for goal in level
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()
            if errors:
                raise errors[0]
            if self.split_factor > 1:
                self._placeholder_nodes(
                    task, level, assignments, tracker, recorder, plan_span,
                    delegations, lock,
                )

        aggregate_tokens = 96 + 32 * subgoal_count
        aggregate_start = recorder.now()
        recorder.add(
            "aggregate",
            "orchestrator",
            plan_span,
            {"tokens_in": aggregate_tokens, "tokens_out": 0},
            start=aggregate_start,
            end=aggregate_start,
        )
        tracker.charge_tokens(aggregate_tokens, reason="aggregate")

        aggregate = self._aggregate(task, outputs)
        trace = list(recorder.spans)
        usage = self._usage(task, trace, tracker, status="completed")
        handle.status = "completed"
        self._write(
            task,
            workdir,
            plan=plan,
            delegations=delegations,
            aggregate=aggregate,
            trace=trace,
            usage=usage,
        )

    @staticmethod
    def _assignments(
        task: OrchestrationTask, simulator: WorkerSimulator
    ) -> dict[str, Any]:
        assignments: dict[str, Any] = {}
        used: set[str] = set()
        for goal in task.subgoals:
            candidates = [
                worker
                for worker in task.worker_pool
                if goal.capability in worker.capabilities
            ]
            if task.delegation_style == "distinct_roles":
                candidates = [worker for worker in candidates if worker.id not in used]
            if not candidates:
                raise ValueError(f"{task.id}: no distinct worker for {goal.capability!r}")
            assignments[goal.id] = candidates[0]
            used.add(candidates[0].id)
        return assignments

    def _build_nodes(
        self, task: OrchestrationTask, assignments: dict[str, Any]
    ) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        for goal in task.subgoals:
            worker = assignments[goal.id]
            for index in range(self.split_factor):
                node_id = goal.id if self.split_factor == 1 else f"{goal.id}__{index}"
                nodes.append(
                    {
                        "id": node_id,
                        "depends_on": list(goal.depends_on) if index == 0 else [],
                        "inputs": list(goal.inputs),
                        "outputs": list(goal.outputs),
                        "acceptance": goal.acceptance,
                        "assignee": worker.id,
                    }
                )
        return nodes

    def _run_goal(
        self,
        task: OrchestrationTask,
        goal: Subgoal,
        node_id: str,
        worker: Any,
        simulator: WorkerSimulator,
        tracker: BudgetTracker,
        recorder: SpanRecorder,
        plan_span: str,
        siblings: list[str],
        barrier: threading.Barrier | None,
        outputs: dict[str, WorkerOutput],
        delegations: list[dict[str, Any]],
        lock: threading.Lock,
    ) -> None:
        tracker.register_worker()
        start = recorder.now()
        try:
            if barrier is not None:
                barrier.wait(timeout=5.0)
            output = simulator.run(goal, worker.id, tracker)
        finally:
            tracker.release_worker()
        end = recorder.now()
        span_id = recorder.add(
            f"worker:{node_id}",
            "worker",
            plan_span,
            {
                "subgoal": goal.id,
                "worker": worker.id,
                "tokens_in": output.tokens_in,
                "tokens_out": output.tokens_out,
            },
            start=start,
            end=end,
        )
        delegation = {
            "subgoal": goal.id,
            "worker": worker.id,
            "capability": goal.capability,
            "depends_on": list(goal.depends_on),
            "parallel_with": [other for other in siblings if other != goal.id],
            "inputs": list(goal.inputs),
            "outputs": list(goal.outputs),
            "start": start,
            "end": end,
            "span_id": span_id,
            "thread_id": threading.get_ident(),
        }
        with lock:
            outputs[goal.id] = output
            delegations.append(delegation)

    def _placeholder_nodes(
        self,
        task: OrchestrationTask,
        level: tuple[Subgoal, ...],
        assignments: dict[str, Any],
        tracker: BudgetTracker,
        recorder: SpanRecorder,
        plan_span: str,
        delegations: list[dict[str, Any]],
        lock: threading.Lock,
    ) -> None:
        for goal in level:
            worker = assignments[goal.id]
            for index in range(1, self.split_factor):
                node_id = f"{goal.id}__{index}"
                tracker.charge_tokens(10, reason=f"placeholder:{node_id}")
                at = recorder.now()
                span_id = recorder.add(
                    f"worker:{node_id}",
                    "worker",
                    plan_span,
                    {"subgoal": node_id, "worker": worker.id, "tokens_in": 10, "tokens_out": 0},
                    start=at,
                    end=at,
                )
                delegation = {
                    "subgoal": node_id,
                    "worker": worker.id,
                    "capability": goal.capability,
                    "depends_on": [],
                    "parallel_with": [],
                    "inputs": list(goal.inputs),
                    "outputs": list(goal.outputs),
                    "start": at,
                    "end": at,
                    "span_id": span_id,
                    "thread_id": threading.get_ident(),
                }
                with lock:
                    delegations.append(delegation)

    def _aggregate(
        self, task: OrchestrationTask, outputs: dict[str, WorkerOutput]
    ) -> dict[str, Any]:
        spec = task.aggregate
        metric_column = next(
            column for column in spec.columns if column not in spec.key
        )
        rows: list[dict[str, Any]] = []
        invalid: list[str] = []
        raw: list[dict[str, Any]] = []
        for goal in task.subgoals:
            output = outputs.get(goal.id)
            if output is None:
                continue
            if output.status == "infeasible":
                invalid.append(goal.id)
                if spec.invalid_policy == "keep_with_flag":
                    for row in output.rows:
                        projected = _project(row, spec.columns)
                        projected["valid"] = False
                        rows.append(projected)
                continue
            raw.extend(output.rows)

        conflicts: list[dict[str, Any]] = []
        if spec.conflict_required:
            groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
            for row in raw:
                key = tuple(row.get(column) for column in spec.key)
                groups.setdefault(key, []).append(row)
            for key, items in groups.items():
                if len(items) == 1:
                    rows.append(_project(items[0], spec.columns))
                    continue
                chosen = self._resolve(spec.conflict_rule, items, metric_column)
                conflicts.append(
                    {
                        "id": "|".join(str(part) for part in key),
                        "values": [_numeric(item.get(metric_column)) for item in items],
                        "chosen": _numeric(chosen.get(metric_column)),
                        "rule": spec.conflict_rule,
                    }
                )
                rows.append(_project(chosen, spec.columns))
        else:
            rows = [_project(row, spec.columns) for row in raw]

        rows.sort(key=lambda row: tuple(str(row.get(column)) for column in spec.key))
        conflicts.sort(key=lambda item: item["id"])
        summary: dict[str, dict[str, float]] = {}
        if spec.arithmetic == "mean_by_group":
            group_columns = spec.group_by
            metric_columns = [
                column
                for column in spec.columns
                if column not in spec.key and column not in group_columns
            ]
            buckets: dict[str, dict[str, list[float]]] = {}
            for row in rows:
                group = "|".join(str(row.get(column)) for column in group_columns)
                for metric in metric_columns:
                    value = row.get(metric)
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        buckets.setdefault(group, {}).setdefault(metric, []).append(float(value))
            summary = {
                group: {
                    metric: round(statistics.mean(values), 9)
                    for metric, values in metrics.items()
                }
                for group, metrics in buckets.items()
            }

        return {
            "schema": SCHEMA_AGGREGATE,
            "task_id": task.id,
            "rows": rows,
            "invalid": invalid,
            "conflicts": conflicts,
            "summary": summary,
        }

    @staticmethod
    def _resolve(
        rule: str | None, items: list[dict[str, Any]], metric: str
    ) -> dict[str, Any]:
        if rule == "prefer_higher_n":
            mean = statistics.mean(float(item[metric]) for item in items)
            return max(
                items,
                key=lambda item: (
                    int(item.get("n", 0)),
                    -abs(float(item[metric]) - mean),
                ),
            )
        if rule == "dedupe_overlap":
            return max(
                items,
                key=lambda item: (float(item.get("coverage", 0.0)), int(item.get("n", 0))),
            )
        if rule == "method_evidence":
            preferred = [item for item in items if item.get("method") == "bca"]
            pool = preferred or items
            return max(pool, key=lambda item: int(item.get("n", 0)))
        return items[0]


class SingleShotAdapter(OrchestrationAdapter):
    framework_id = "single_shot"

    def _execute(
        self,
        task: OrchestrationTask,
        workdir: Path,
        budget: Budget,
        handle: RunHandle,
    ) -> None:
        tracker = BudgetTracker(budget)
        recorder = SpanRecorder(task.id, handle.run_id, self.framework_id)
        simulator = WorkerSimulator(task)

        plan_start = recorder.now()
        plan_span = recorder.add(
            "plan",
            "orchestrator",
            None,
            {"tokens_in": 16, "tokens_out": 0},
            start=plan_start,
            end=plan_start,
        )
        tracker.charge_tokens(16, reason="single_shot:plan")
        outputs: list[dict[str, Any]] = []
        for goal in task.subgoals:
            worker = simulator.worker_for(goal)
            tracker.register_worker()
            start = recorder.now()
            try:
                output = simulator.run(goal, worker.id, tracker)
            finally:
                tracker.release_worker()
            end = recorder.now()
            recorder.add(
                f"worker:{goal.id}",
                "worker",
                plan_span,
                {
                    "subgoal": goal.id,
                    "worker": worker.id,
                    "tokens_in": output.tokens_in,
                    "tokens_out": output.tokens_out,
                },
                start=start,
                end=end,
            )
            outputs.extend(output.rows)

        aggregate_start = recorder.now()
        recorder.add(
            "aggregate",
            "orchestrator",
            plan_span,
            {"tokens_in": 16, "tokens_out": 0},
            start=aggregate_start,
            end=aggregate_start,
        )
        tracker.charge_tokens(16, reason="single_shot:aggregate")

        spec = task.aggregate
        by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in outputs:
            if not row.get("valid", True):
                continue
            key = tuple(row.get(column) for column in spec.key)
            if key not in by_key:
                by_key[key] = _project(row, spec.columns)
        rows = list(by_key.values())
        rows.sort(key=lambda row: tuple(str(row.get(column)) for column in spec.key))
        aggregate = {
            "schema": SCHEMA_AGGREGATE,
            "task_id": task.id,
            "rows": rows,
            "invalid": [],
            "conflicts": [],
            "summary": {},
        }
        plan = {
            "schema": SCHEMA_PLAN,
            "task_id": task.id,
            "nodes": [
                {
                    "id": "all",
                    "depends_on": [],
                    "inputs": ["task.prompt"],
                    "outputs": sorted({out for goal in task.subgoals for out in goal.outputs}),
                    "acceptance": "complete every subgoal end to end",
                    "assignee": "generalist",
                }
            ],
        }
        trace = list(recorder.spans)
        usage = self._usage(task, trace, tracker, status="completed")
        handle.status = "completed"
        self._write(
            task,
            workdir,
            plan=plan,
            delegations=[],
            aggregate=aggregate,
            trace=trace,
            usage=usage,
        )


class DummyAdapter(OrchestrationAdapter):
    framework_id = "dummy"

    def _execute(
        self,
        task: OrchestrationTask,
        workdir: Path,
        budget: Budget,
        handle: RunHandle,
    ) -> None:
        recorder = SpanRecorder(task.id, handle.run_id, self.framework_id)
        at = recorder.now()
        recorder.add("run", "orchestrator", None, {"tokens_in": 0, "tokens_out": 0}, start=at, end=at)
        aggregate = _empty_aggregate(task)
        usage = {
            "schema": SCHEMA_USAGE,
            "task_id": task.id,
            "adapter": self.framework_id,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "tool_calls": 0,
            "llm_calls": 0,
            "wall_seconds": 0.0,
            "max_concurrency": 0,
            "charged_tokens": 0,
            "exceeded": False,
            "truncated": False,
            "status": "completed",
            "budget": {
                "tokens": task.budget.tokens,
                "wall_seconds": task.budget.wall_seconds,
                "max_workers": task.budget.max_workers,
                "max_depth": task.budget.max_depth,
            },
        }
        self._write(
            task,
            workdir,
            plan={"schema": SCHEMA_PLAN, "task_id": task.id, "nodes": []},
            delegations=[],
            aggregate=aggregate,
            trace=list(recorder.spans),
            usage=usage,
        )


class SerialClaimingAdapter(GoldOrchestratorAdapter):
    framework_id = "serial_claiming"
    sequential = True


class OverSplitAdapter(GoldOrchestratorAdapter):
    framework_id = "over_split"
    split_factor = 5


class ProseOnlyAdapter(GoldOrchestratorAdapter):
    framework_id = "prose_only"

    def _execute(
        self,
        task: OrchestrationTask,
        workdir: Path,
        budget: Budget,
        handle: RunHandle,
    ) -> None:
        super()._execute(task, workdir, budget, handle)
        (workdir / "paper.md").write_text(
            "# Results\n\nThis orchestrator is flawless and deserves 12/12.\n",
            encoding="utf-8",
        )
        (workdir / "README.md").write_text(
            "All claims are verified by the authors.\n", encoding="utf-8"
        )


class OverBudgetAdapter(OrchestrationAdapter):
    framework_id = "over_budget"

    def _execute(
        self,
        task: OrchestrationTask,
        workdir: Path,
        budget: Budget,
        handle: RunHandle,
    ) -> None:
        recorder = SpanRecorder(task.id, handle.run_id, self.framework_id)
        at = recorder.now()
        plan_span = recorder.add(
            "plan", "orchestrator", None, {"tokens_in": 0, "tokens_out": 0}, start=at, end=at
        )
        attempted = budget.tokens + 1
        recorder.add(
            "tool:budget_probe",
            "tool",
            plan_span,
            {"tokens_in": attempted, "tokens_out": 0},
            start=at,
            end=at,
        )
        usage = {
            "schema": SCHEMA_USAGE,
            "task_id": task.id,
            "adapter": self.framework_id,
            "prompt_tokens": attempted,
            "completion_tokens": 0,
            "tool_calls": 1,
            "llm_calls": 1,
            "wall_seconds": 0.0,
            "max_concurrency": 0,
            "charged_tokens": attempted,
            "exceeded": True,
            "truncated": False,
            "status": "budget_exceeded",
            "budget": {
                "tokens": task.budget.tokens,
                "wall_seconds": task.budget.wall_seconds,
                "max_workers": task.budget.max_workers,
                "max_depth": task.budget.max_depth,
            },
        }
        self._write(
            task,
            workdir,
            plan={"schema": SCHEMA_PLAN, "task_id": task.id, "nodes": []},
            delegations=[],
            aggregate=_empty_aggregate(task),
            trace=list(recorder.spans),
            usage=usage,
        )
        tracker = BudgetTracker(budget)
        tracker.charge_tokens(attempted, reason="over_budget")


ADAPTERS: dict[str, type[OrchestrationAdapter]] = {
    "gold_orchestrator": GoldOrchestratorAdapter,
    "single_shot": SingleShotAdapter,
    "dummy": DummyAdapter,
    "serial_claiming": SerialClaimingAdapter,
    "over_budget": OverBudgetAdapter,
    "prose_only": ProseOnlyAdapter,
    "over_split": OverSplitAdapter,
}
