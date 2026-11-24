"""T06/T07/T08 — OB-3, OB-4, OB-5 negative fixtures (P-162)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from experiments.arc_bench.orchestration.runner import run_matrix  # noqa: E402
from experiments.arc_bench.orchestration.tasks import TASK_ORDER  # noqa: E402


def _run(tmp_path: Path, run_id: str, **kwargs) -> dict:
    kwargs.setdefault("with_fixtures", False)
    return run_matrix(results_root=tmp_path, run_id=run_id, **kwargs)


def test_t06_serial_claiming_scores_zero(tmp_path: Path) -> None:
    summary = _run(tmp_path, "t06", task_ids=["D1"], adapter_ids=["serial_claiming"])
    judge = summary["runs"]["serial_claiming"]["D1"]["judge"]
    assert judge["checks"]["ob3_parallel_claim_ok"] is False
    assert judge["scores"]["delegation"] == 0
    assert judge["total"] == 0
    assert judge["gate_zeroed"] is True


def test_t07_over_budget_is_not_silently_truncated(tmp_path: Path) -> None:
    summary = _run(tmp_path, "t07", task_ids=["D1"], adapter_ids=["over_budget"])
    run = summary["runs"]["over_budget"]["D1"]
    assert run["status"] == "budget_exceeded"
    assert run["usage"]["exceeded"] is True
    assert run["usage"]["truncated"] is False
    judge = run["judge"]
    assert judge["checks"]["ob4_budget_state_ok"] is True
    assert judge["scores"]["cost"] == 0


def test_t08_prose_invariance_and_over_split_penalty(tmp_path: Path) -> None:
    summary = _run(
        tmp_path,
        "t08",
        adapter_ids=["prose_only", "over_split"],
    )
    gold = summary["runs"]["gold_orchestrator"]
    for task_id in TASK_ORDER:
        assert (
            summary["runs"]["prose_only"][task_id]["judge"]["total"]
            == gold[task_id]["judge"]["total"]
        ), task_id
    for task_id in ("C1", "C2", "C3"):
        split = summary["runs"]["over_split"][task_id]["judge"]
        assert split["scores"]["decomposition"] == 0, (task_id, split)
        assert split["total"] < gold[task_id]["judge"]["total"], (task_id, split)

    whitelist = summary["runs"]["prose_only"]["D1"]["judge"]["inputs_whitelist"]
    assert "paper.md" not in whitelist
    assert "README.md" not in whitelist
    assert len(whitelist) == 6
