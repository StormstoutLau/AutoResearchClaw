"""Offline dual-plane claim audit for finished runs (G2 M5, P-064).

The audit plane per R-03 §5.1 is an *offline batch mode*: it reads a finished
run directory, re-evaluates every claim with the production kernel
(``audit_claim``) through the shared ``compare_claims`` used by Stage 23, and
reports whether the recorded production decisions reproduce. Read-only by
design — nothing is written into the run directory.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .claim_policy import CURRENT_POLICY_VERSION
from .stage_hooks import (
    ClaimStreamError,
    _annotations,
    _claim_key,
    _load_production_gate,
    compare_claims,
    load_claims,
)

__all__ = ["run_offline_audit", "write_audit_report"]


def _claims_for_audit(run_dir: Path) -> list[dict]:
    """Stage-20 claims first; fall back to stage-09 (same precedence as Stage 23)."""
    claims = load_claims(run_dir, stage_prefix="stage-20")
    if not claims:
        claims = load_claims(run_dir)
    return claims


def _policy_version_diffs(
    claims: list[dict], expected_policy_version: int
) -> list[dict]:
    """M5 DoD: both planes must run under the same policy version."""
    diffs: list[dict] = []
    for index, claim in enumerate(claims):
        claim_key = _claim_key(claim, index)
        found = claim.get("policy_version")
        if found != expected_policy_version:
            diffs.append({
                "claim_id": claim_key,
                "reason": "policy_version_mismatch",
                "expected": expected_policy_version,
                "found": found,
            })
    return diffs


def run_offline_audit(
    run_dir: Path,
    expected_policy_version: int = CURRENT_POLICY_VERSION,
) -> dict:
    """Audit a finished run without running the pipeline.

    Returns a JSON-serializable report:

    ```json
    {
      "consistent": true,
      "checked": 3,
      "diffs": [{"claim_id": "c-...", "reason": "status_mismatch", ...}],
      "production": {"c-...": {"status": "...", "deliverable": true}},
      "audit": {"c-...": {"status": "...", "deliverable": true}},
      "expected_policy_version": 2,
      "skipped": "no_production_gate"
    }
    ```

    ``skipped`` is ``no_production_gate`` when claims exist but the run was
    resumed past Stage 20, and ``no_claims`` when the run carries no claim
    artifacts at all. Both keep ``consistent=true`` (mirror the in-pipeline
    Stage 23 semantics). Raises ``FileNotFoundError`` when the run directory
    does not exist and ``ClaimStreamError`` when claim/gate artifacts exist
    but cannot be parsed (fail closed, mirrors Stage 20/23).
    """
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"run directory does not exist: {run_dir}")

    claims = _claims_for_audit(run_dir)
    production = _load_production_gate(run_dir)
    annotations = _annotations(run_dir)

    result = compare_claims(claims, production, annotations)
    diffs: list[dict] = list(result["diffs"])
    diffs.extend(_policy_version_diffs(claims, expected_policy_version))

    payload: dict[str, Any] = {
        "consistent": not diffs,
        "checked": len(claims),
        "diffs": diffs,
        "production": production,
        "audit": result["audit"],
        "expected_policy_version": expected_policy_version,
    }
    if result["skipped"]:
        payload["skipped"] = result["skipped"]
    elif not claims and not production:
        payload["skipped"] = "no_claims"
    return payload


def write_audit_report(report: dict, output: Path) -> Path:
    """Write the audit report to an explicit path (never into the run)."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return output
