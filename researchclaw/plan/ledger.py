"""Progress Ledger: the five Magentic-One questions over a ResearchPlan (G8b / P-156).

The ledger is a pure, deterministic projection of the plan plus plan events and
the previous ledger. It never mutates the plan (invariant J-4).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from researchclaw.plan.store import _atomic_write, plan_dir

LEDGER_NAME = "ledger.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ids(nodes: Iterable[Mapping[str, Any]], status: str) -> list[str]:
    return [
        str(node.get("id"))
        for node in nodes
        if isinstance(node, Mapping) and node.get("status") == status
    ]


def _next_node(
    nodes: list[Mapping[str, Any]],
    terminal: set[str],
) -> Mapping[str, Any] | None:
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        if node.get("status") not in ("proposed", "active"):
            continue
        deps = [str(dep) for dep in (node.get("depends_on") or [])]
        if all(dep in terminal for dep in deps):
            return node
    return None


def _candidates(
    plan: Mapping[str, Any],
    nodes: list[Mapping[str, Any]],
    events: Iterable[Mapping[str, Any]],
    spent_usd: float,
) -> list[dict]:
    failures: dict[str, int] = {}
    ambiguous: set[str] = set()
    for event in events:
        if not isinstance(event, Mapping):
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
        node_id = str(payload.get("node_id") or "")
        if not node_id:
            continue
        if event.get("type") == "node.failed":
            failures[node_id] = failures.get(node_id, 0) + 1
        if payload.get("reason") == "ambiguous":
            ambiguous.add(node_id)

    found: list[dict] = []
    for node_id, count in sorted(failures.items()):
        if count >= 2:
            found.append({"node_id": node_id, "reason": "two_failures"})
    for node_id in sorted(ambiguous):
        if not any(item["node_id"] == node_id for item in found):
            found.append({"node_id": node_id, "reason": "ambiguity"})

    constraints = plan.get("constraints") if isinstance(plan.get("constraints"), Mapping) else {}
    budget = float(constraints.get("budget_usd") or 0.0)
    done = len(_ids(nodes, "done"))
    total = len([node for node in nodes if isinstance(node, Mapping)])
    if budget > 0 and spent_usd / budget >= 0.5 and total and done / total < 0.3:
        for node in nodes:
            if isinstance(node, Mapping) and node.get("status") in ("proposed", "active"):
                found.append(
                    {"node_id": str(node.get("id")), "reason": "budget_half_no_progress"}
                )
                break
    return found


def compute_ledger(
    plan: Mapping[str, Any],
    *,
    previous: Mapping[str, Any] | None = None,
    events: Iterable[Mapping[str, Any]] = (),
    spent_usd: float = 0.0,
) -> dict:
    """Return the deterministic ledger for ``plan``."""
    nodes = [
        node for node in (plan.get("nodes") or []) if isinstance(node, Mapping)
    ]
    completed = _ids(nodes, "done")
    active = _ids(nodes, "active")
    blocked = _ids(nodes, "failed")
    abandoned = _ids(nodes, "abandoned")
    terminal = set(completed) | set(abandoned)
    is_complete = bool(nodes) and all(
        node.get("status") in ("done", "abandoned") for node in nodes
    )

    next_node = _next_node(nodes, terminal)
    next_id = str(next_node.get("id")) if next_node else None
    next_instruction = ""
    if next_node:
        next_instruction = (
            f"{next_node.get('statement', '')} "
            f"(stage {next_node.get('owner_stage', '?')})"
        ).strip()

    prev = previous if isinstance(previous, Mapping) else None
    prev_completed = set(prev.get("completed") or []) if prev else set()
    new_done = set(completed) - prev_completed
    forward_progress = bool(new_done)
    is_looping = bool(
        prev
        and prev.get("next_node") is not None
        and prev.get("next_node") == next_id
        and not new_done
    )
    loop_rounds = int(prev.get("loop_rounds") or 0) + 1 if is_looping else 0

    return {
        "plan_version": int(plan.get("version", 1)),
        "completed": completed,
        "active": active,
        "blocked": blocked,
        "abandoned": abandoned,
        "is_complete": is_complete,
        "is_looping": is_looping,
        "loop_rounds": loop_rounds,
        "forward_progress": forward_progress,
        "next_node": next_id,
        "next_instruction": next_instruction,
        "decompose_candidates": _candidates(plan, nodes, events, spent_usd),
        "generated_at": _now_iso(),
    }


def read_ledger(run_dir: str | Path) -> dict | None:
    path = plan_dir(run_dir) / LEDGER_NAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_ledger(run_dir: str | Path, ledger: Mapping[str, Any]) -> None:
    path = plan_dir(run_dir) / LEDGER_NAME
    _atomic_write(
        path,
        json.dumps(dict(ledger), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
    )


__all__ = ["LEDGER_NAME", "compute_ledger", "read_ledger", "write_ledger"]
