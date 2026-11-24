"""Matrix runner, summary and OB-1..OB-5 gates."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .adapters import ADAPTERS
from .judge import judge_run
from .model import SCHEMA_SUMMARY, OrchestrationArtifacts, OrchestrationTask
from .submission import build_submission
from .tasks import TASK_ORDER, load_task

DEFAULT_RESULTS_ROOT = (
    Path(__file__).resolve().parents[1] / "results" / "orchestration"
)

NORMAL_ADAPTERS: tuple[str, ...] = ("gold_orchestrator", "single_shot", "dummy")
FIXTURE_ADAPTERS: tuple[str, ...] = (
    "serial_claiming",
    "over_budget",
    "prose_only",
    "over_split",
)
FIXTURE_TASKS: dict[str, tuple[str, ...]] = {
    "serial_claiming": ("D1",),
    "over_budget": ("D1",),
    "prose_only": TASK_ORDER,
    "over_split": ("C1", "C2", "C3"),
}
SUBMISSION_FILES: tuple[str, ...] = (
    "submission/code",
    "submission/results/metrics.json",
    "submission/README.md",
    "submission/claims.json",
    "submission/reproduce.sh",
    "submission/reproduce.log",
    "submission/reproduce.log.creation_time",
)


def _empty_artifacts() -> OrchestrationArtifacts:
    return OrchestrationArtifacts(plan={}, delegations=[], aggregate={}, trace=[], usage={})


def _run_one(
    task: OrchestrationTask,
    adapter_id: str,
    base: Path,
    *,
    reference_usage: dict[str, Any] | None,
) -> dict[str, Any]:
    workdir = base / adapter_id / task.id
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    adapter = ADAPTERS[adapter_id]()
    handle = adapter.start(task, workdir, task.budget)
    status = adapter.collect(handle, timeout_sec=30.0)
    try:
        artifacts = adapter.artifacts(handle)
    except Exception:  # noqa: BLE001 - a broken adapter must not kill the matrix
        artifacts = _empty_artifacts()

    judge = judge_run(task, workdir, reference_usage=reference_usage)
    (workdir / "judge_result.json").write_text(
        json.dumps(judge, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    (workdir / "orchestration_meta.json").write_text(
        json.dumps(
            {
                "task_id": task.id,
                "adapter": adapter_id,
                "status": status,
                "error": handle.error,
                "elapsed_sec": handle.elapsed_sec,
                "workdir": str(workdir),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    submission = None
    if status == "completed":
        submission = str(
            build_submission(workdir, task, artifacts.aggregate, adapter_id=adapter_id)
        )
    return {
        "status": status,
        "error": handle.error,
        "workdir": str(workdir),
        "usage": artifacts.usage,
        "judge": judge,
        "submission": submission,
    }


def _run_id_is_safe(run_id: str) -> bool:
    return bool(run_id) and Path(run_id).name == run_id and "/" not in run_id and "\\" not in run_id


def run_matrix(
    task_ids: list[str] | None = None,
    adapter_ids: list[str] | None = None,
    results_root: Path | None = None,
    run_id: str | None = None,
    with_fixtures: bool = True,
    repeat_gold: bool = True,
) -> dict[str, Any]:
    root = Path(results_root) if results_root is not None else DEFAULT_RESULTS_ROOT
    selected_tasks = list(task_ids) if task_ids else list(TASK_ORDER)
    unknown = [task_id for task_id in selected_tasks if task_id not in TASK_ORDER]
    if unknown:
        raise ValueError(f"unknown tasks: {unknown}")

    if run_id is None:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    if not _run_id_is_safe(run_id):
        raise ValueError(f"invalid run_id: {run_id!r}")

    run_root = root / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    if not run_root.resolve().is_relative_to(root.resolve()):
        raise ValueError("run directory escaped the results root")

    if adapter_ids is None:
        adapters = list(NORMAL_ADAPTERS)
        if with_fixtures:
            adapters.extend(FIXTURE_ADAPTERS)
    else:
        adapters = list(adapter_ids)
    unknown_adapters = [adapter for adapter in adapters if adapter not in ADAPTERS]
    if unknown_adapters:
        raise ValueError(f"unknown adapters: {unknown_adapters}")
    ordered = ["gold_orchestrator"] + [
        adapter for adapter in adapters if adapter != "gold_orchestrator"
    ]

    started_at = datetime.now(timezone.utc).isoformat()
    tasks = [load_task(task_id) for task_id in selected_tasks]
    runs: dict[str, dict[str, Any]] = {}
    repeats: dict[str, dict[str, Any]] = {}
    reference: dict[str, dict[str, Any]] = {}

    for task in tasks:
        gold = _run_one(task, "gold_orchestrator", run_root, reference_usage=None)
        runs.setdefault("gold_orchestrator", {})[task.id] = gold
        reference[task.id] = gold["usage"]

        if repeat_gold:
            repeat = _run_one(
                task,
                "gold_orchestrator",
                run_root / "__repeat__",
                reference_usage=reference[task.id],
            )
            repeats[task.id] = {
                "first": gold["judge"]["total"],
                "second": repeat["judge"]["total"],
                "equal": gold["judge"]["total"] == repeat["judge"]["total"],
            }

        for adapter_id in ordered:
            if adapter_id == "gold_orchestrator":
                continue
            allowed = FIXTURE_TASKS.get(adapter_id)
            if allowed is not None and task.id not in allowed:
                continue
            runs.setdefault(adapter_id, {})[task.id] = _run_one(
                task,
                adapter_id,
                run_root,
                reference_usage=reference[task.id],
            )

    per_adapter = {}
    for adapter_id, task_runs in runs.items():
        totals = [record["judge"]["total"] for record in task_runs.values()]
        if not totals:
            continue
        per_adapter[adapter_id] = {
            "count": len(totals),
            "mean_total": round(sum(totals) / len(totals), 4),
            "min_total": min(totals),
            "max_total": max(totals),
        }

    summary: dict[str, Any] = {
        "schema": SCHEMA_SUMMARY,
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "tasks": selected_tasks,
        "adapters": ordered,
        "runs": runs,
        "repeats": repeats,
        "per_adapter": per_adapter,
        "gates": {},
    }
    summary["gates"] = evaluate_gates(summary)
    (run_root / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    return summary


def evaluate_gates(summary: dict[str, Any], runs: dict[str, Any] | None = None) -> dict[str, Any]:
    runs = runs if runs is not None else summary.get("runs", {})
    tasks = summary.get("tasks") or list(TASK_ORDER)
    gold = runs.get("gold_orchestrator", {})
    single = runs.get("single_shot", {})

    gold_threshold_ok = bool(gold) and all(
        gold.get(task_id, {}).get("judge", {}).get("total", 0)
        >= (8 if task_id.startswith("C") else 10)
        for task_id in tasks
    )
    single_threshold_ok = bool(single) and all(
        single.get(task_id, {}).get("judge", {}).get("total", 99) <= 7
        for task_id in tasks
        if not task_id.startswith("C")
    )
    repeats = summary.get("repeats", {})
    reproducible = bool(repeats) and all(
        record.get("equal") is True for record in repeats.values()
    )
    ob1 = {
        "ok": gold_threshold_ok and single_threshold_ok and reproducible,
        "details": {
            "gold_threshold_ok": gold_threshold_ok,
            "single_shot_threshold_ok": single_threshold_ok,
            "reproducible": reproducible,
        },
    }

    dummy = runs.get("dummy", {}).get("D1")
    ob2_files = False
    if dummy is not None:
        workdir = Path(dummy["workdir"])
        ob2_files = all((workdir / name).is_file() for name in (
            "plan.json", "delegations.json", "aggregate.json", "trace.jsonl", "usage.json"
        )) and all((workdir / name).exists() for name in SUBMISSION_FILES) and (
            workdir / "judge_result.json"
        ).is_file()
    ob2 = {
        "ok": bool(dummy and dummy.get("status") == "completed" and ob2_files),
        "details": {"completed": bool(dummy and dummy.get("status") == "completed"), "files": ob2_files},
    }

    serial = runs.get("serial_claiming", {}).get("D1")
    ob3 = {
        "ok": bool(
            serial
            and serial["judge"]["checks"]["ob3_parallel_claim_ok"] is False
            and serial["judge"]["scores"]["delegation"] == 0
            and serial["judge"]["total"] == 0
        ),
        "details": serial["judge"] if serial else None,
    }

    over = runs.get("over_budget", {}).get("D1")
    ob4 = {
        "ok": bool(
            over
            and over.get("status") == "budget_exceeded"
            and over.get("usage", {}).get("exceeded") is True
            and over.get("usage", {}).get("truncated") is False
            and over["judge"]["checks"]["ob4_budget_state_ok"] is True
        ),
        "details": {
            "status": over.get("status") if over else None,
            "usage": over.get("usage") if over else None,
        },
    }

    prose = runs.get("prose_only", {})
    prose_ok = bool(prose) and all(
        prose.get(task_id, {}).get("judge", {}).get("total")
        == gold.get(task_id, {}).get("judge", {}).get("total")
        for task_id in tasks
    )
    over_split = runs.get("over_split", {})
    split_ok = bool(over_split) and all(
        over_split.get(task_id, {}).get("judge", {}).get("total", 99)
        < gold.get(task_id, {}).get("judge", {}).get("total", 0)
        for task_id in ("C1", "C2", "C3")
    )
    ob5 = {"ok": prose_ok and split_ok, "details": {"prose_invariant": prose_ok, "over_split_penalised": split_ok}}

    return {"ob1": ob1, "ob2": ob2, "ob3": ob3, "ob4": ob4, "ob5": ob5}
