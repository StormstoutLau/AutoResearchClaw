"""G2 evidence kernel: mechanical checks for the academic reasoning rules."""
from .ar_checks import CHECKS, SEVERITIES, Finding, check_claim

__all__ = ["CHECKS", "SEVERITIES", "Finding", "check_claim"]
