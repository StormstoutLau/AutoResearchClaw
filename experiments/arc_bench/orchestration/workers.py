"""Deterministic worker simulator.

Workers do not call an LLM: they return the frozen truth rows for their
subgoal and charge a deterministic token amount. Parallel overlap is created
by the caller's barrier, never by sleeping.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import BudgetTracker, OrchestrationTask, Subgoal, Worker


@dataclass(frozen=True)
class WorkerOutput:
    subgoal: str
    worker_id: str
    rows: tuple[dict, ...]
    status: str  # "ok" | "infeasible"
    tokens_in: int
    tokens_out: int


class WorkerSimulator:
    def __init__(self, task: OrchestrationTask) -> None:
        self.task = task
        self._rows: dict[str, list[dict]] = {goal.id: [] for goal in task.subgoals}
        for row in task.truth.get("rows", []):
            self._rows.setdefault(str(row["subgoal"]), []).append(dict(row))

    def capabilities(self, worker_id: str) -> tuple[str, ...]:
        for worker in self.task.worker_pool:
            if worker.id == worker_id:
                return worker.capabilities
        raise ValueError(f"{self.task.id}: unknown worker {worker_id!r}")

    def worker_for(self, subgoal: Subgoal) -> Worker:
        for worker in self.task.worker_pool:
            if subgoal.capability in worker.capabilities:
                return worker
        raise ValueError(f"{self.task.id}: no worker for {subgoal.capability!r}")

    def run(self, subgoal: Subgoal, worker_id: str, tracker: BudgetTracker) -> WorkerOutput:
        rows = tuple(dict(row) for row in self._rows.get(subgoal.id, ()))
        tokens_in = 32 + 6 * len(rows)
        tokens_out = 16 + 10 * len(rows)
        tracker.charge_tokens(tokens_in + tokens_out, reason=f"worker:{subgoal.id}")
        status = "infeasible" if rows and all(not row.get("valid", True) for row in rows) else "ok"
        return WorkerOutput(
            subgoal=subgoal.id,
            worker_id=worker_id,
            rows=rows,
            status=status,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
