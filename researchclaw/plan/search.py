"""Deterministic budget-bounded candidate search for Stage 9 (G8b / P-156).

This is a *selection* helper, not an LLM tree search: candidates are ranked
deterministically, accumulated against a hard budget, and the report is written
alongside the plan. It never mutates ``exp_plan.yaml`` (D-7).
"""
from __future__ import annotations

from typing import Any, Mapping


def search_experiment_candidates(
    candidates: list[Mapping[str, Any]] | None,
    *,
    budget_usd: float,
    max_candidates: int = 8,
) -> dict:
    """Select candidates by descending score while staying within budget."""
    budget = max(float(budget_usd or 0.0), 0.0)
    items: list[tuple[str, float, float]] = []
    for raw in candidates or []:
        if not isinstance(raw, Mapping):
            continue
        candidate_id = str(raw.get("id") or "")
        if not candidate_id:
            continue
        cost = max(float(raw.get("estimated_usd") or 0.0), 0.0)
        score = float(raw.get("score") or 0.0)
        items.append((candidate_id, cost, score))
    items.sort(key=lambda item: (-item[2], item[0]))

    if budget <= 0:
        return {
            "selected": [],
            "evaluated": 0,
            "spent_usd": 0.0,
            "budget_usd": budget,
            "exhausted": True,
            "skipped_over_budget": [item[0] for item in items],
        }

    selected: list[str] = []
    skipped: list[str] = []
    spent = 0.0
    for candidate_id, cost, _score in items:
        if len(selected) >= max(0, int(max_candidates)):
            break
        if spent + cost > budget + 1e-9:
            skipped.append(candidate_id)
            continue
        selected.append(candidate_id)
        spent += cost

    return {
        "selected": selected,
        "evaluated": len(items),
        "spent_usd": round(spent, 6),
        "budget_usd": budget,
        "exhausted": bool(skipped),
        "skipped_over_budget": skipped,
    }


__all__ = ["search_experiment_candidates"]
