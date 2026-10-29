"""LLM cost tracking for pipeline runs.

Records one JSONL line per LLM call in ``<run_dir>/cost_log.jsonl`` so that
budget guardrails (:mod:`researchclaw.hitl.cost_guard`) and post-hoc audits
read the same source of truth.

Cost precedence (D5):
1. provider-reported ``usage.cost``            → ``source="provider_usage"``
2. configured per-1M token prices              → ``source="pricing_table"``
3. neither available                           → ``cost_usd=0.0``, ``source="unknown"``

No vendor price table is bundled: prices drift, so deployments configure
``llm.input_cost_per_1m`` / ``llm.output_cost_per_1m`` or rely on providers
that report cost per response.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

COST_LOG_FILENAME = "cost_log.jsonl"
SCHEMA_VERSION = 1


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class CostRecord:
    """One billable LLM call."""

    timestamp: str
    run_id: str
    stage: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    source: str  # "provider_usage" | "pricing_table" | "unknown"
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CostTracker:
    """Thread-safe accumulator that appends to ``cost_log.jsonl``."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._run_dir: Path | None = None
        self._run_id = ""
        self._stage = ""
        self._total_cost_usd = 0.0
        self._total_tokens = 0
        self._record_count = 0
        self._input_cost_per_1m = 0.0
        self._output_cost_per_1m = 0.0
        self._unknown_models: set[str] = set()
        self._warned_models: set[str] = set()

    # ── configuration / run lifecycle ────────────────────────────

    def configure_pricing(
        self, *, input_cost_per_1m: float, output_cost_per_1m: float
    ) -> None:
        """Set per-1M-token prices used when the provider reports no cost."""
        with self._lock:
            self._input_cost_per_1m = max(0.0, float(input_cost_per_1m or 0.0))
            self._output_cost_per_1m = max(0.0, float(output_cost_per_1m or 0.0))

    def begin_run(self, *, run_dir: Path, run_id: str) -> None:
        """Point the tracker at a run directory.

        Idempotent for the same ``run_id`` (recursive PIVOT/REFINE runs must
        keep accumulating); switching to a different run resets totals.
        """
        run_dir = Path(run_dir)
        with self._lock:
            if self._run_id == run_id and self._run_dir == run_dir:
                return
            if self._run_id != run_id:
                self._total_cost_usd = 0.0
                self._total_tokens = 0
                self._record_count = 0
            self._run_dir = run_dir
            self._run_id = run_id

    def reset(self) -> None:
        """Clear all state (tests, or an explicit fresh run)."""
        with self._lock:
            self._run_dir = None
            self._run_id = ""
            self._stage = ""
            self._total_cost_usd = 0.0
            self._total_tokens = 0
            self._record_count = 0
            self._unknown_models.clear()
            self._warned_models.clear()

    def set_stage(self, stage: str) -> None:
        """Attribute subsequent LLM calls to *stage*."""
        with self._lock:
            self._stage = stage

    @property
    def current_stage(self) -> str:
        return self._stage

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def run_dir(self) -> Path | None:
        return self._run_dir

    # ── recording ────────────────────────────────────────────────

    def record(self, record: CostRecord) -> None:
        """Append *record* to the run cost log and update totals."""
        with self._lock:
            self._total_cost_usd += float(record.cost_usd or 0.0)
            self._total_tokens += int(record.total_tokens or 0)
            self._record_count += 1
            if record.source == "unknown":
                self._unknown_models.add(record.model)
            self._append_locked(record)

    def record_llm_call(
        self,
        *,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        provider_cost: float | None = None,
        input_cost_per_1m: float | None = None,
        output_cost_per_1m: float | None = None,
    ) -> CostRecord:
        """Build and store a :class:`CostRecord` for one LLM response.

        The per-1M prices may be passed per call so that concurrent clients
        with different pricing never share mutable global state.
        """
        prompt_tokens = int(prompt_tokens or 0)
        completion_tokens = int(completion_tokens or 0)
        if not total_tokens:
            total_tokens = prompt_tokens + completion_tokens

        cost_usd, source = self._resolve_cost(
            model,
            prompt_tokens,
            completion_tokens,
            provider_cost,
            input_cost_per_1m,
            output_cost_per_1m,
        )
        record = CostRecord(
            timestamp=_utcnow_iso(),
            run_id=self._run_id,
            stage=self._stage,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=int(total_tokens or 0),
            cost_usd=round(cost_usd, 8),
            source=source,
        )
        self.record(record)
        return record

    def _resolve_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        provider_cost: float | None,
        input_cost_per_1m: float | None = None,
        output_cost_per_1m: float | None = None,
    ) -> tuple[float, str]:
        if isinstance(provider_cost, (int, float)) and not isinstance(
            provider_cost, bool
        ):
            return float(provider_cost), "provider_usage"

        in_price = (
            self._input_cost_per_1m
            if input_cost_per_1m is None
            else max(0.0, float(input_cost_per_1m))
        )
        out_price = (
            self._output_cost_per_1m
            if output_cost_per_1m is None
            else max(0.0, float(output_cost_per_1m))
        )
        if in_price > 0 or out_price > 0:
            cost = (
                prompt_tokens / 1_000_000 * in_price
                + completion_tokens / 1_000_000 * out_price
            )
            return cost, "pricing_table"

        if model not in self._warned_models:
            self._warned_models.add(model)
            logger.warning(
                "No cost source for model %r: set llm.input_cost_per_1m / "
                "llm.output_cost_per_1m, or use a provider that reports "
                "usage.cost. Budget checks will under-report spend.",
                model,
            )
        return 0.0, "unknown"

    def _append_locked(self, record: CostRecord) -> None:
        if self._run_dir is None:
            return
        path = self._run_dir / COST_LOG_FILENAME
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
                handle.flush()
        except OSError as exc:  # never fail a run because accounting failed
            logger.warning("Cannot write %s: %s", path, exc)

    # ── queries ──────────────────────────────────────────────────

    @property
    def total_cost_usd(self) -> float:
        return self._total_cost_usd

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    @property
    def record_count(self) -> int:
        return self._record_count

    @property
    def tracking_complete(self) -> bool:
        """False when at least one call had no usable price information."""
        return not self._unknown_models

    @property
    def unknown_models(self) -> tuple[str, ...]:
        return tuple(sorted(self._unknown_models))

    def check_budget(self, budget_usd: float) -> bool:
        """Return True when spend is still strictly below *budget_usd*.

        A non-positive budget disables the check. Spend exactly equal to the
        budget counts as exhausted.
        """
        if budget_usd is None or float(budget_usd) <= 0:
            return True
        return self._total_cost_usd < float(budget_usd)

    def snapshot(self) -> dict[str, Any]:
        return {
            "run_id": self._run_id,
            "stage": self._stage,
            "total_cost_usd": round(self._total_cost_usd, 6),
            "total_tokens": self._total_tokens,
            "records": self._record_count,
            "tracking_complete": self.tracking_complete,
            "unknown_models": list(self.unknown_models),
            "input_cost_per_1m": self._input_cost_per_1m,
            "output_cost_per_1m": self._output_cost_per_1m,
        }


_GLOBAL_TRACKER = CostTracker()


def get_global_tracker() -> CostTracker:
    """Return the process-wide tracker used by the LLM client and CostGuard."""
    return _GLOBAL_TRACKER


def sum_cost_log(run_dir: Path) -> tuple[float, int, int]:
    """Return ``(cost_usd, total_tokens, lines)`` summed from ``cost_log.jsonl``."""
    path = Path(run_dir) / COST_LOG_FILENAME
    if not path.is_file():
        return 0.0, 0, 0
    total_cost = 0.0
    total_tokens = 0
    lines = 0
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            lines += 1
            try:
                total_cost += float(entry.get("cost_usd", 0.0) or 0.0)
            except (TypeError, ValueError):
                pass
            try:
                total_tokens += int(entry.get("total_tokens", 0) or 0)
            except (TypeError, ValueError):
                pass
    except OSError as exc:
        logger.warning("Cannot read %s: %s", path, exc)
        return 0.0, 0, 0
    return total_cost, total_tokens, lines
