"""P-156 T20-T22: deterministic budget-bounded experiment candidate search."""
from __future__ import annotations

from researchclaw.plan.search import search_experiment_candidates


def _candidates() -> list[dict]:
    return [
        {"id": "a", "estimated_usd": 1.0, "score": 0.9},
        {"id": "b", "estimated_usd": 1.5, "score": 0.8},
        {"id": "c", "estimated_usd": 0.5, "score": 0.7},
    ]


class TestExperimentSearch:
    def test_search_selects_within_budget(self) -> None:
        report = search_experiment_candidates(_candidates(), budget_usd=2.0)
        assert report["selected"] == ["a", "c"]
        assert report["spent_usd"] == 1.5
        assert report["skipped_over_budget"] == ["b"]
        assert report["exhausted"] is True

        full = search_experiment_candidates(_candidates(), budget_usd=3.0)
        assert full["selected"] == ["a", "b", "c"]
        assert full["spent_usd"] == 3.0
        assert full["exhausted"] is False

    def test_search_exhausts_budget_deterministically(self) -> None:
        first = search_experiment_candidates(_candidates(), budget_usd=1.2)
        second = search_experiment_candidates(list(reversed(_candidates())), budget_usd=1.2)
        assert first == second
        assert first["selected"] == ["a"]
        assert first["exhausted"] is True

    def test_search_empty_budget_returns_nothing(self) -> None:
        report = search_experiment_candidates(_candidates(), budget_usd=0)
        assert report["selected"] == []
        assert report["spent_usd"] == 0.0
        assert report["exhausted"] is True
