"""Cost budget guardrails: pause pipeline when spending exceeds thresholds.

Monitors cumulative LLM API costs and triggers HITL pauses at
configurable thresholds (e.g., 50%, 80%, 100% of budget).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CostStatus:
    """Current cost tracking status."""

    total_usd: float = 0.0
    budget_usd: float = 0.0
    percent_used: float = 0.0
    over_budget: bool = False
    threshold_breached: str = ""  # "" | "50%" | "80%" | "100%"
    total_tokens: int = 0
    tracking_complete: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_usd": round(self.total_usd, 4),
            "budget_usd": round(self.budget_usd, 2),
            "percent_used": round(self.percent_used, 1),
            "over_budget": self.over_budget,
            "threshold_breached": self.threshold_breached,
            "total_tokens": self.total_tokens,
            "tracking_complete": self.tracking_complete,
        }


class CostGuard:
    """Monitor and enforce cost budgets for HITL-aware pipelines.

    Checks the global cost tracker (if available) and triggers
    pauses at configurable thresholds.
    """

    def __init__(
        self,
        budget_usd: float = 0.0,
        thresholds: tuple[float, ...] = (0.5, 0.8, 1.0),
    ) -> None:
        self.budget_usd = budget_usd
        self.thresholds = sorted(thresholds)
        self._notified_thresholds: set[float] = set()

    def check(self, run_dir: Path | None = None) -> CostStatus:
        """Check current cost against budget.

        Returns CostStatus with information about whether a threshold
        was breached.
        """
        total, tokens, tracking_complete = self._read_cost(run_dir)

        if self.budget_usd <= 0:
            return CostStatus(
                total_usd=total,
                total_tokens=tokens,
                tracking_complete=tracking_complete,
            )

        pct = total / self.budget_usd
        status = CostStatus(
            total_usd=total,
            budget_usd=self.budget_usd,
            percent_used=pct * 100,
            over_budget=pct >= 1.0,
            total_tokens=tokens,
            tracking_complete=tracking_complete,
        )
        if not tracking_complete:
            logger.warning(
                "Cost guard: some models had no price source — spend is "
                "under-reported and the budget may not be enforced accurately."
            )

        # Check thresholds
        for threshold in self.thresholds:
            if pct >= threshold and threshold not in self._notified_thresholds:
                self._notified_thresholds.add(threshold)
                status.threshold_breached = f"{int(threshold * 100)}%"
                logger.warning(
                    "Cost guard: %.1f%% of $%.2f budget used ($%.4f)",
                    pct * 100,
                    self.budget_usd,
                    total,
                )
                break

        return status

    def should_pause(self, run_dir: Path | None = None) -> bool:
        """Return True if cost has breached a new threshold."""
        status = self.check(run_dir)
        return bool(status.threshold_breached)

    def format_display(self, run_dir: Path | None = None) -> str:
        """Format cost info for TUI display."""
        status = self.check(run_dir)
        if self.budget_usd <= 0:
            return f"Cost: ${status.total_usd:.4f} (no budget set)"

        bar_width = 20
        filled = int(bar_width * min(status.percent_used / 100, 1.0))
        bar = "█" * filled + "░" * (bar_width - filled)
        return (
            f"Cost: ${status.total_usd:.4f} / ${status.budget_usd:.2f} "
            f"[{bar}] {status.percent_used:.0f}%"
        )

    def _get_total_cost(self, run_dir: Path | None) -> float:
        """Read total cost from the global cost tracker or cost log."""
        return self._read_cost(run_dir)[0]

    def _read_cost(self, run_dir: Path | None) -> tuple[float, int, bool]:
        """Return ``(total_usd, total_tokens, tracking_complete)``."""
        # Prefer the in-process tracker, but only for the run it tracks —
        # inspecting another run's directory must read that run's log.
        try:
            from researchclaw.cost_tracker import get_global_tracker

            tracker = get_global_tracker()
            if tracker.run_id and (
                run_dir is None
                or tracker.run_dir is None
                or Path(run_dir).resolve() == tracker.run_dir.resolve()
            ):
                return (
                    tracker.total_cost_usd,
                    tracker.total_tokens,
                    tracker.tracking_complete,
                )
        except Exception:  # noqa: BLE001 - fall back to the log below
            pass

        # Fall back to summing cost_log.jsonl (e.g. a finished run inspected
        # in a fresh process).
        if run_dir is not None:
            try:
                from researchclaw.cost_tracker import sum_cost_log

                total, tokens, lines = sum_cost_log(run_dir)
                return total, tokens, lines > 0
            except Exception:  # noqa: BLE001
                pass

        return 0.0, 0, True
