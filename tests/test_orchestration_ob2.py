"""T09 — OB-2 baseline-compatible entry and submission layout (P-162)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "experiments" / "arc_bench" / "scripts" / "run_orchestration.py"


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_list_tasks() -> None:
    result = _cli("--list-tasks")
    assert result.returncode == 0, result.stderr
    assert "D1" in result.stdout
    assert "C3" in result.stdout


def test_invalid_task_exits_2() -> None:
    result = _cli("--tasks", "Z9", "--no-gate")
    assert result.returncode == 2, (result.returncode, result.stderr)


def test_dummy_run_writes_submission_and_judge_result(tmp_path: Path) -> None:
    result = _cli(
        "--tasks",
        "D1",
        "--adapters",
        "dummy",
        "--run-id",
        "t09",
        "--results-dir",
        str(tmp_path),
        "--no-gate",
    )
    assert result.returncode == 0, result.stderr
    run_dir = tmp_path / "t09" / "dummy" / "D1"
    assert (run_dir / "judge_result.json").is_file()
    assert (run_dir / "submission" / "code").is_dir()
    assert (run_dir / "submission" / "results" / "metrics.json").is_file()
    assert (run_dir / "submission" / "README.md").is_file()
    assert (run_dir / "submission" / "claims.json").is_file()
    assert (run_dir / "submission" / "reproduce.sh").is_file()
    assert (run_dir / "submission" / "reproduce.log").is_file()
    assert (run_dir / "submission" / "reproduce.log.creation_time").is_file()
