"""G2 evidence kernel: mechanical checks and the Lean sidecar client."""
from .ar_checks import CHECKS, SEVERITIES, Finding, check_claim
from .sidecar import (
    SidecarConfig,
    SidecarConfigError,
    SidecarError,
    SidecarRequestError,
    SidecarResult,
    SidecarTimeout,
    run_lean_check,
)

__all__ = [
    "CHECKS",
    "SEVERITIES",
    "Finding",
    "check_claim",
    "SidecarConfig",
    "SidecarConfigError",
    "SidecarError",
    "SidecarRequestError",
    "SidecarResult",
    "SidecarTimeout",
    "run_lean_check",
]
