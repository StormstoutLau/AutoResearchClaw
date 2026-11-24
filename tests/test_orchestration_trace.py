"""T12 — trace integrity, usage recomputation, missing/bad artifacts (P-162)."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from experiments.arc_bench.orchestration.judge import judge_run  # noqa: E402
from experiments.arc_bench.orchestration.runner import run_matrix  # noqa: E402
from experiments.arc_bench.orchestration.tasks import load_task  # noqa: E402


def _gold_run(tmp_path: Path) -> tuple[Path, dict, dict]:
    summary = run_matrix(
        results_root=tmp_path,
        run_id="t12",
        task_ids=["D1"],
        adapter_ids=["gold_orchestrator"],
        with_fixtures=False,
    )
    run = summary["runs"]["gold_orchestrator"]["D1"]
    workdir = Path(run["workdir"])
    usage = json.loads((workdir / "usage.json").read_text(encoding="utf-8"))
    trace = [
        json.loads(line)
        for line in (workdir / "trace.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return workdir, usage, {"trace": trace, "judge": run["judge"]}


def test_trace_structure_and_concurrency(tmp_path: Path) -> None:
    _, usage, extra = _gold_run(tmp_path)
    trace = extra["trace"]
    ids = [span["span_id"] for span in trace]
    assert len(ids) == len(set(ids))
    known = set(ids)
    for span in trace:
        parent = span.get("parent_id") or ""
        if parent:
            assert parent in known, span
    worker_spans = [span for span in trace if span["kind"] == "worker"]
    assert len(worker_spans) >= 3
    by_parent: dict[str, list[dict]] = {}
    for span in worker_spans:
        by_parent.setdefault(span.get("parent_id") or "", []).append(span)
    overlapping = False
    for group in by_parent.values():
        for left in group:
            for right in group:
                if left is right:
                    continue
                if (
                    left["thread_id"] != right["thread_id"]
                    and left["start"] < right["end"]
                    and right["start"] < left["end"]
                ):
                    overlapping = True
    assert overlapping is True
    assert usage["max_concurrency"] >= 2
    assert extra["judge"]["checks"]["usage_matches_trace"] is True


def test_tampered_usage_is_rejected(tmp_path: Path) -> None:
    workdir, usage, _ = _gold_run(tmp_path)
    tampered = tmp_path / "tampered"
    shutil.copytree(workdir, tampered)
    payload = json.loads((tampered / "usage.json").read_text(encoding="utf-8"))
    payload["completion_tokens"] += 5
    (tampered / "usage.json").write_text(json.dumps(payload), encoding="utf-8")
    result = judge_run(load_task("D1"), tampered, reference_usage=usage)
    assert result["checks"]["usage_matches_trace"] is False
    assert result["scores"]["cost"] == 0


def test_missing_and_bad_artifacts_zero_the_score(tmp_path: Path) -> None:
    workdir, usage, _ = _gold_run(tmp_path)

    missing = tmp_path / "missing"
    shutil.copytree(workdir, missing)
    (missing / "aggregate.json").unlink()
    result = judge_run(load_task("D1"), missing, reference_usage=usage)
    assert result["total"] == 0
    assert "aggregate.json" in result["checks"]["missing_files"]

    bad = tmp_path / "bad"
    shutil.copytree(workdir, bad)
    with (bad / "trace.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("not json\n")
    result = judge_run(load_task("D1"), bad, reference_usage=usage)
    assert result["total"] == 0
    assert result["checks"]["parse_errors"]


def test_prose_file_does_not_change_the_score(tmp_path: Path) -> None:
    workdir, usage, extra = _gold_run(tmp_path)
    with_prose = tmp_path / "with_prose"
    shutil.copytree(workdir, with_prose)
    (with_prose / "paper.md").write_text("# inflated\nScore 12/12.\n", encoding="utf-8")
    (with_prose / "README.md").write_text("The orchestrator is perfect.\n", encoding="utf-8")
    result = judge_run(load_task("D1"), with_prose, reference_usage=usage)
    assert result["total"] == extra["judge"]["total"]
    assert "paper.md" not in result["inputs_whitelist"]
