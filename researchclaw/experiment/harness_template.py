"""Experiment harness — immutable evaluation infrastructure.

This file is injected into the sandbox project directory at execution time.
The LLM-generated experiment code should import and use this harness for:
- Time budget management (should_stop)
- Metric reporting (report_metric)
- Result finalization (finalize)
- NaN/divergence detection (built-in)

This file is NOT editable by the LLM agent — it provides a trust boundary
for metric reporting, inspired by karpathy/autoresearch's immutable prepare.py.
"""

import atexit
import json
import math
import signal
import sys
import threading
import time


class ExperimentHarness:
    """Immutable experiment infrastructure for time and metric management."""

    def __init__(self, time_budget: int = 120):
        self._start = time.time()
        self._time_budget = max(1, int(time_budget))
        self._metrics: dict[str, float] = {}
        self._partial_results: list[dict[str, object]] = []
        self._step_count = 0
        self._nan_count = 0

    @property
    def elapsed(self) -> float:
        """Seconds elapsed since harness creation."""
        return time.time() - self._start

    @property
    def progress(self) -> float:
        """Fraction of time budget used (0.0 to 1.0)."""
        return min(self.elapsed / self._time_budget, 1.0)

    def should_stop(self) -> bool:
        """Return True if approaching 80% of time budget."""
        return self.elapsed >= self._time_budget * 0.8

    def check_value(self, value: float, name: str = "metric") -> bool:
        """Return True if value is finite. Log warning and count NaN/Inf."""
        if math.isnan(value) or math.isinf(value):
            self._nan_count += 1
            print(
                f"WARNING: {name} = {value} (non-finite, skipped)",
                file=sys.stderr,
            )
            if self._nan_count >= 5:
                print(
                    "FAIL: Too many NaN/Inf values detected. "
                    "Stopping experiment early.",
                    file=sys.stderr,
                )
                self.finalize()
                sys.exit(1)
            return False
        return True

    def report_metric(self, name: str, value: float) -> None:
        """Report a metric value. Validates and prints in standard format.

        Non-finite values (NaN, Inf) are rejected and logged as warnings.
        """
        if not isinstance(value, (int, float)):
            try:
                value = float(value)
            except (TypeError, ValueError):
                print(f"WARNING: Cannot convert {name}={value!r} to float", file=sys.stderr)
                return

        if not self.check_value(value, name):
            return

        self._metrics[name] = value
        # Standard format recognized by sandbox metric parser
        print(f"{name}: {value}")

    def log_result(self, result_dict: dict[str, object]) -> None:
        """Log a structured result row (e.g., per-condition results)."""
        self._partial_results.append(result_dict)

    def finalize(self) -> None:
        """Write results.json with all reported metrics and partial results."""
        output = {
            "metrics": self._metrics,
            "elapsed_sec": round(self.elapsed, 2),
            "time_budget_sec": self._time_budget,
            "steps_completed": self._step_count,
            "nan_count": self._nan_count,
        }
        if self._partial_results:
            output["results"] = self._partial_results

        try:
            with open("results.json", "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2, default=str)
        except OSError as e:
            print(f"WARNING: Could not write results.json: {e}", file=sys.stderr)

    def step(self) -> None:
        """Increment step counter. Call this once per experiment step."""
        self._step_count += 1


# Convenience: create a default harness when imported
_default_harness: ExperimentHarness | None = None


def get_harness(time_budget: int = 120) -> ExperimentHarness:
    """Get or create the default experiment harness."""
    global _default_harness  # noqa: PLW0603
    if _default_harness is None:
        _default_harness = ExperimentHarness(time_budget)
    return _default_harness


def _finalize_default() -> None:
    """Finalize the default harness if one exists (idempotent: finalize()
    only overwrites results.json, so double invocation is harmless)."""
    if _default_harness is not None:
        _default_harness.finalize()


atexit.register(_finalize_default)


def _install_sigterm_handler() -> None:
    """Route SIGTERM through finalize() so artifacts land on disk before
    the container dies (G4-M4 A4-6).

    entrypoint.sh runs the experiment via ``exec python3 -u``, so SIGTERM
    reaches this process directly; the default handler would terminate
    immediately without finalizing. With the handler installed, a TTL
    expiry (docker kill -s TERM) gives the experiment a grace window to
    write results.json.

    Guard: signal handlers may only be installed on the main thread;
    otherwise degrade silently (no handler, atexit still covers normal
    exits).
    """
    if threading.current_thread() is not threading.main_thread():
        return

    def _on_sigterm(signum: int, frame: object) -> None:
        _finalize_default()
        sys.exit(128 + signum)

    try:
        signal.signal(signal.SIGTERM, _on_sigterm)
    except (ValueError, OSError):
        # Not on main thread or restricted environment — degrade silently.
        pass


_install_sigterm_handler()
