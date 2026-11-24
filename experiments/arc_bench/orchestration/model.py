"""Data model and budget enforcement for the orchestration harness.

Everything here is stdlib-only and import-free from the legacy ARC-Bench
scripts so the harness cannot mutate their scoring semantics.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

SCHEMA_TASK = "arc-orchestration-task/1"
SCHEMA_PLAN = "arc-orchestration-plan/1"
SCHEMA_DELEGATIONS = "arc-orchestration-delegations/1"
SCHEMA_AGGREGATE = "arc-orchestration-aggregate/1"
SCHEMA_TRACE = "arc-orchestration-trace/1"
SCHEMA_USAGE = "arc-orchestration-usage/1"
SCHEMA_RESULT = "arc-orchestration-result/1"
SCHEMA_SUMMARY = "arc-orchestration-summary/1"


@dataclass(frozen=True)
class Subgoal:
    id: str
    capability: str
    depends_on: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    acceptance: str


@dataclass(frozen=True)
class Worker:
    id: str
    capabilities: tuple[str, ...]


@dataclass(frozen=True)
class AggregateSpec:
    columns: tuple[str, ...]
    key: tuple[str, ...]
    invalid_policy: str
    conflict_required: bool
    conflict_rule: str | None
    arithmetic: str | None
    group_by: tuple[str, ...]


@dataclass(frozen=True)
class Trap:
    kind: str
    subgoals: tuple[str, ...]
    hint: str


@dataclass(frozen=True)
class Budget:
    tokens: int
    wall_seconds: float
    max_workers: int
    max_depth: int


@dataclass(frozen=True)
class OrchestrationTask:
    id: str
    cls: str
    title: str
    source_manifest: str
    version: int
    prompt: str
    delegation_style: str
    subgoals: tuple[Subgoal, ...]
    worker_pool: tuple[Worker, ...]
    aggregate: AggregateSpec
    trap: Trap | None
    budget: Budget
    truth: dict[str, Any]


class BudgetExceeded(RuntimeError):
    """Raised *before* a charge is applied; nothing is silently truncated."""

    def __init__(self, kind: str, limit: float, observed: float) -> None:
        super().__init__(f"budget exceeded: {kind} limit={limit} observed={observed}")
        self.kind = kind
        self.limit = limit
        self.observed = observed


class BudgetTracker:
    def __init__(
        self,
        budget: Budget,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.budget = budget
        self._clock = clock
        self._started = clock()
        self._tokens = 0
        self._workers = 0
        self._max_workers_seen = 0
        self._lock = threading.Lock()
        self._exceeded: dict[str, Any] | None = None

    def _fail(self, kind: str, limit: float, observed: float) -> None:
        self._exceeded = {"kind": kind, "limit": limit, "observed": observed}
        raise BudgetExceeded(kind, limit, observed)

    def charge_tokens(self, tokens: int, *, reason: str) -> None:
        if tokens < 0:
            raise ValueError("tokens must be non-negative")
        with self._lock:
            if self._tokens + tokens > self.budget.tokens:
                self._fail("tokens", self.budget.tokens, self._tokens + tokens)
            self._tokens += tokens

    def check_wall(self) -> None:
        elapsed = self._clock() - self._started
        if elapsed > self.budget.wall_seconds:
            self._fail("wall", self.budget.wall_seconds, round(elapsed, 6))

    def register_worker(self) -> None:
        with self._lock:
            if self._workers + 1 > self.budget.max_workers:
                self._fail("workers", self.budget.max_workers, self._workers + 1)
            self._workers += 1
            self._max_workers_seen = max(self._max_workers_seen, self._workers)

    def release_worker(self) -> None:
        with self._lock:
            self._workers = max(0, self._workers - 1)

    def enter_depth(self, depth: int) -> None:
        if depth > self.budget.max_depth:
            self._fail("depth", self.budget.max_depth, depth)

    @property
    def total_tokens(self) -> int:
        with self._lock:
            return self._tokens

    @property
    def max_workers_seen(self) -> int:
        with self._lock:
            return self._max_workers_seen

    @property
    def exceeded(self) -> dict[str, Any] | None:
        return self._exceeded


@dataclass
class RunHandle:
    run_id: str
    workdir: Path
    status: str = "running"
    error: str | None = None
    started_at: float = 0.0
    elapsed_sec: float = 0.0
    task_id: str = ""
    adapter_id: str = ""
    thread: threading.Thread | None = field(default=None, repr=False)


@dataclass(frozen=True)
class OrchestrationArtifacts:
    plan: dict[str, Any]
    delegations: list[dict[str, Any]]
    aggregate: dict[str, Any]
    trace: list[dict[str, Any]]
    usage: dict[str, Any]
