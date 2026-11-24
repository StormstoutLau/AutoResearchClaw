#!/usr/bin/env python3
"""CLI for the offline orchestration evaluation harness (G7 / OB-1..OB-5)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.arc_bench.orchestration.runner import run_matrix  # noqa: E402
from experiments.arc_bench.orchestration.tasks import (  # noqa: E402
    TASK_ORDER,
    load_tasks,
)


def _parse_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _print_tasks() -> None:
    print(f"{'id':<4} {'class':<6} {'subgoals':<8} source_manifest")
    for task in load_tasks():
        print(
            f"{task.id:<4} {task.cls:<6} {len(task.subgoals):<8} {task.source_manifest}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", default="all", help="all or comma-separated task ids")
    parser.add_argument(
        "--adapters",
        default=None,
        help="comma-separated adapter ids (default: gold, single_shot, dummy + fixtures)",
    )
    parser.add_argument("--results-dir", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--no-fixtures", action="store_true")
    parser.add_argument("--no-gate", action="store_true")
    parser.add_argument("--list-tasks", action="store_true")
    args = parser.parse_args(argv)

    if args.list_tasks:
        _print_tasks()
        return 0

    task_ids = list(TASK_ORDER) if args.tasks == "all" else _parse_list(args.tasks)
    adapter_ids = None if args.adapters is None else _parse_list(args.adapters)
    try:
        summary = run_matrix(
            task_ids=task_ids,
            adapter_ids=adapter_ids,
            results_root=Path(args.results_dir) if args.results_dir else None,
            run_id=args.run_id,
            with_fixtures=not args.no_fixtures,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"run_id: {summary['run_id']}")
    for adapter_id, stats in sorted(summary["per_adapter"].items()):
        print(
            f"  {adapter_id:<18} n={stats['count']:<3} "
            f"mean={stats['mean_total']:<6} min={stats['min_total']:<3} max={stats['max_total']}"
        )
    for gate_id, gate in summary["gates"].items():
        print(f"  {gate_id}: {'PASS' if gate['ok'] else 'FAIL'}")

    if args.no_gate:
        return 0
    failed = [gate_id for gate_id, gate in summary["gates"].items() if not gate["ok"]]
    if failed:
        print(f"gate failures: {failed}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
