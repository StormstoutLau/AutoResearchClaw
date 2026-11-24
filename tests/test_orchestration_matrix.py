"""T03/T04/T05/T10/T11 — matrix, negative control, dummy, summary, isolation."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from experiments.arc_bench.orchestration.adapters import (  # noqa: E402
    DummyAdapter,
    OrchestrationAdapter,
)
from experiments.arc_bench.orchestration.runner import run_matrix  # noqa: E402
from experiments.arc_bench.orchestration.tasks import TASK_ORDER, load_task  # noqa: E402

FIVE = ("plan.json", "delegations.json", "aggregate.json", "trace.jsonl", "usage.json")


def _run(tmp_path: Path, run_id: str, **kwargs) -> dict:
    kwargs.setdefault("with_fixtures", False)
    return run_matrix(results_root=tmp_path, run_id=run_id, **kwargs)


def test_t03_gold_scores_and_reproducibility(tmp_path: Path) -> None:
    summary = _run(tmp_path, "t03", adapter_ids=["gold_orchestrator"])
    for task_id in TASK_ORDER:
        judge = summary["runs"]["gold_orchestrator"][task_id]["judge"]
        assert judge["scores"]["aggregation"] == 3, (task_id, judge)
        threshold = 8 if task_id.startswith("C") else 10
        assert judge["total"] >= threshold, (task_id, judge)
        assert judge["gate_zeroed"] is False
    assert summary["gates"]["ob1"]["details"]["reproducible"] is True


def test_t04_single_shot_is_a_negative_control(tmp_path: Path) -> None:
    summary = _run(tmp_path, "t04", adapter_ids=["single_shot"])
    for task_id in TASK_ORDER:
        if task_id.startswith("C"):
            continue
        judge = summary["runs"]["single_shot"][task_id]["judge"]
        assert judge["total"] <= 7, (task_id, judge)
        assert judge["scores"]["decomposition"] <= 1
        assert judge["scores"]["delegation"] == 0
        assert judge["gate_zeroed"] is False, (task_id, judge)


def test_t05_dummy_contract_and_failed_adapter(tmp_path: Path) -> None:
    summary = _run(tmp_path, "t05", task_ids=["D1"], adapter_ids=["dummy"])
    run = summary["runs"]["dummy"]["D1"]
    assert run["status"] == "completed"
    workdir = Path(run["workdir"])
    for name in FIVE:
        assert (workdir / name).is_file(), name
    assert run["judge"]["total"] == 0

    class BoomAdapter(DummyAdapter):
        framework_id = "boom"

        def _execute(self, task, workdir, budget, handle) -> None:  # type: ignore[override]
            raise RuntimeError("boom")

    adapter: OrchestrationAdapter = BoomAdapter()
    task = load_task("D1")
    handle = adapter.start(task, tmp_path / "boom", task.budget)
    assert adapter.collect(handle, timeout_sec=5.0) == "failed"
    assert "boom" in (handle.error or "")


def test_t10_full_matrix_and_gates(tmp_path: Path) -> None:
    started = time.monotonic()
    summary = run_matrix(results_root=tmp_path, run_id="t10")
    elapsed = time.monotonic() - started
    assert elapsed < 120, elapsed
    for gate in ("ob1", "ob2", "ob3", "ob4", "ob5"):
        assert summary["gates"][gate]["ok"] is True, (gate, summary["gates"][gate])
    assert set(summary["runs"]) == {
        "gold_orchestrator",
        "single_shot",
        "dummy",
        "serial_claiming",
        "over_budget",
        "prose_only",
        "over_split",
    }
    assert (tmp_path / "t10" / "summary.json").is_file()


def test_t11_isolation_and_run_id_guard(tmp_path: Path) -> None:
    first = load_task("D1")
    second = load_task("D1")
    before = len(second.truth["rows"])
    first.truth["rows"].append({"subgoal": "x", "valid": False})
    assert len(load_task("D1").truth["rows"]) == before

    left = _run(tmp_path / "left", "same", task_ids=["D1"], adapter_ids=["single_shot"])
    right = _run(tmp_path / "right", "same", task_ids=["D1"], adapter_ids=["single_shot"])
    assert (
        left["runs"]["single_shot"]["D1"]["judge"]["total"]
        == right["runs"]["single_shot"]["D1"]["judge"]["total"]
    )

    with pytest.raises(ValueError):
        run_matrix(results_root=tmp_path, run_id="../escape")
