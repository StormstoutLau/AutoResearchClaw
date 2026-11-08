"""H-5: failed executions must not be aggregated, even with metrics."""

from __future__ import annotations

import json
from pathlib import Path

from researchclaw.pipeline._helpers import _collect_experiment_results


def _write_run(stage_runs: Path, name: str, payload: dict) -> None:
    (stage_runs / name).write_text(json.dumps(payload), encoding="utf-8")


def test_failed_run_with_metrics_is_excluded(tmp_path: Path) -> None:
    runs = tmp_path / "stage-12" / "runs"
    runs.mkdir(parents=True)
    _write_run(
        runs,
        "run-1.json",
        {"status": "failed", "returncode": 1, "metrics": {"accuracy": 0.9}},
    )
    _write_run(
        runs,
        "run-2.json",
        {"status": "completed", "returncode": 0, "metrics": {"accuracy": 0.5}},
    )

    collected = _collect_experiment_results(tmp_path, metric_key="accuracy")
    assert collected["metrics_summary"]["accuracy"]["count"] == 1
    assert collected["metrics_summary"]["accuracy"]["mean"] == 0.5
    assert collected["excluded_runs"][0]["returncode"] == 1


def test_nonzero_returncode_excluded_without_status(tmp_path: Path) -> None:
    runs = tmp_path / "stage-12" / "runs"
    runs.mkdir(parents=True)
    _write_run(runs, "run-1.json", {"returncode": 2, "metrics": {"accuracy": 0.8}})

    collected = _collect_experiment_results(tmp_path, metric_key="accuracy")
    assert collected["runs"] == []
    assert collected["metrics_summary"] == {}
    assert len(collected["excluded_runs"]) == 1


def test_completed_run_is_kept(tmp_path: Path) -> None:
    runs = tmp_path / "stage-12" / "runs"
    runs.mkdir(parents=True)
    _write_run(
        runs,
        "run-1.json",
        {"status": "completed", "returncode": 0, "metrics": {"accuracy": 0.7}},
    )

    collected = _collect_experiment_results(tmp_path, metric_key="accuracy")
    assert collected["metrics_summary"]["accuracy"]["count"] == 1
    assert "excluded_runs" not in collected
