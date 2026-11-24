"""T06-T08 — real budget overflow must leave readable OB-4 artifacts (P-164)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from experiments.arc_bench.orchestration.adapters import (  # noqa: E402
    GoldOrchestratorAdapter,
    OverBudgetAdapter,
)
from experiments.arc_bench.orchestration.judge import judge_run  # noqa: E402
from experiments.arc_bench.orchestration.model import Budget  # noqa: E402
from experiments.arc_bench.orchestration.tasks import load_task  # noqa: E402

FIVE = ("plan.json", "delegations.json", "aggregate.json", "trace.jsonl", "usage.json")


def _execute(task, budget: Budget, workdir: Path):
    adapter = GoldOrchestratorAdapter()
    handle = adapter.start(task, workdir, budget)
    return adapter.collect(handle, timeout_sec=30.0), handle


def _usage(workdir: Path) -> dict:
    return json.loads((workdir / "usage.json").read_text(encoding="utf-8"))


def test_real_token_overflow_writes_ob4_artifacts(tmp_path: Path) -> None:
    task = load_task("D1")
    workdir = tmp_path / "token_overflow"
    status, handle = _execute(
        task,
        Budget(tokens=300, wall_seconds=60, max_workers=3, max_depth=2),
        workdir,
    )

    assert status == "budget_exceeded", handle.error
    for name in FIVE:
        assert (workdir / name).is_file(), name
    usage = _usage(workdir)
    assert usage["exceeded"] is True
    assert usage["truncated"] is False
    assert usage["status"] == "budget_exceeded"
    assert usage["charged_tokens"] > usage["budget"]["tokens"]

    judge = judge_run(task, workdir)
    assert judge["checks"]["ob4_budget_state_ok"] is True
    assert judge["checks"]["usage_matches_trace"] is True
    assert judge["total"] == 0


def test_real_worker_overflow_writes_ob4_artifacts(tmp_path: Path) -> None:
    task = load_task("D1")
    workdir = tmp_path / "worker_overflow"
    status, handle = _execute(
        task,
        Budget(tokens=999999, wall_seconds=60, max_workers=2, max_depth=2),
        workdir,
    )

    assert status == "budget_exceeded", handle.error
    for name in FIVE:
        assert (workdir / name).is_file(), name
    usage = _usage(workdir)
    assert usage["exceeded"] is True
    assert usage["truncated"] is False
    assert usage["prompt_tokens"] == 0

    judge = judge_run(task, workdir)
    assert judge["checks"]["ob4_budget_state_ok"] is True
    assert judge["checks"]["usage_matches_trace"] is True
    assert judge["total"] == 0


def test_budget_failure_writer_does_not_overwrite_fixture(tmp_path: Path) -> None:
    task = load_task("D1")
    workdir = tmp_path / "fixture_ob"
    adapter = OverBudgetAdapter()
    handle = adapter.start(task, workdir, task.budget)
    assert adapter.collect(handle, timeout_sec=30.0) == "budget_exceeded"

    usage = _usage(workdir)
    assert usage["charged_tokens"] == task.budget.tokens + 1
    assert usage["prompt_tokens"] == task.budget.tokens + 1
