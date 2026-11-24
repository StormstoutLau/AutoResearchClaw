"""Soak toolchain (G7, P-160)."""

from researchclaw.soak.driver import (
    FIELD_WALL_SECONDS,
    MIN_FIELD_RESTARTS,
    RestartRecord,
    SoakConfig,
    SoakDriver,
    SoakResult,
)
from researchclaw.soak.report import build_report, render_markdown, write_report
from researchclaw.soak.verifier import (
    RunVerification,
    collect_failure_stages,
    convergence_signature,
    event_seq_coverage,
    read_terminal_status,
    verify_run,
)

__all__ = [
    "FIELD_WALL_SECONDS",
    "MIN_FIELD_RESTARTS",
    "RestartRecord",
    "RunVerification",
    "SoakConfig",
    "SoakDriver",
    "SoakResult",
    "build_report",
    "collect_failure_stages",
    "convergence_signature",
    "event_seq_coverage",
    "read_terminal_status",
    "render_markdown",
    "verify_run",
    "write_report",
]
