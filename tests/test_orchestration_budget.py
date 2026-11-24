"""T02 — BudgetTracker pre-charge enforcement (P-162)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from experiments.arc_bench.orchestration.model import (  # noqa: E402
    Budget,
    BudgetExceeded,
    BudgetTracker,
)


def _tracker(**overrides) -> BudgetTracker:
    values = {"tokens": 100, "wall_seconds": 10.0, "max_workers": 2, "max_depth": 1}
    values.update(overrides)
    return BudgetTracker(Budget(**values), clock=lambda: 0.0)


def test_token_limit_is_checked_before_charge() -> None:
    tracker = _tracker()
    tracker.charge_tokens(60, reason="seed")
    with pytest.raises(BudgetExceeded) as exc:
        tracker.charge_tokens(41, reason="overflow")
    assert exc.value.kind == "tokens"
    assert tracker.total_tokens == 60
    assert tracker.exceeded is not None and tracker.exceeded["kind"] == "tokens"


def test_worker_limit() -> None:
    tracker = _tracker()
    tracker.register_worker()
    tracker.register_worker()
    with pytest.raises(BudgetExceeded) as exc:
        tracker.register_worker()
    assert exc.value.kind == "workers"
    tracker.release_worker()
    tracker.register_worker()  # a released slot can be reused


def test_depth_limit() -> None:
    tracker = _tracker(max_depth=1)
    tracker.enter_depth(1)
    with pytest.raises(BudgetExceeded) as exc:
        tracker.enter_depth(2)
    assert exc.value.kind == "depth"


def test_wall_limit() -> None:
    now = [0.0]
    tracker = BudgetTracker(
        Budget(tokens=100, wall_seconds=1.0, max_workers=2, max_depth=1),
        clock=lambda: now[0],
    )
    now[0] = 2.0
    with pytest.raises(BudgetExceeded) as exc:
        tracker.check_wall()
    assert exc.value.kind == "wall"
