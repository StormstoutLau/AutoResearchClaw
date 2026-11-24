"""Reproducibility verification for pipeline skills (P-147).

Offline, read-only check that a recorded success path is still intact:
artifact hashes, action attribution, event chain, readpoints. This is the
mechanically verifiable form of "reuse"; re-execution needs prompts and is
out of scope (P-145 D-7, P-147 U-1).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from researchclaw.runtime.action_ledger import ActionLedger, hash_path
from researchclaw.runtime.event_log import EventLog


def _empty_report() -> dict:
    return {
        "reproducible": False,
        "checks": 0,
        "chain_ok": False,
        "missing_outputs": [],
        "hash_mismatches": [],
        "unresolved_actions": [],
        "readpoint_failures": [],
    }


def verify_reproducibility(manifest: Mapping[str, Any], run_dir: str | Path) -> dict:
    """Verify a manifest against its run directory. Read-only; never raises on
    drift — drift is reported, not thrown. Missing inputs raise (nothing was
    recorded, nothing can be checked)."""
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"run directory does not exist: {run_dir}")

    report = _empty_report()
    stages = manifest.get("stages") or []
    if not stages:
        return report

    # 1. Event chain
    log = EventLog(run_dir, run_dir.name)
    chain_ok, _msg = log.verify_chain()
    report["chain_ok"] = bool(chain_ok)
    report["checks"] += 1

    # 2. Action attribution
    ledger = ActionLedger(run_dir, run_dir.name, fsync=False)
    known = {str(rec.get("action_id", "")) for rec in ledger.read_all()}
    unresolved: list[str] = []
    actions_total = 0
    for node in stages:
        for action_id in node.get("actions") or []:
            actions_total += 1
            if str(action_id) not in known:
                unresolved.append(str(action_id))
    report["unresolved_actions"] = sorted(set(unresolved))
    if actions_total:
        report["checks"] += 1

    # 3. Output artifacts
    missing: list[str] = []
    mismatches: list[dict] = []
    outputs_total = 0
    for node in stages:
        for rel, digest in (node.get("outputs") or {}).items():
            outputs_total += 1
            target = run_dir / rel
            if not target.is_file():
                missing.append(rel)
                continue
            actual = hash_path(target)
            if actual != digest:
                mismatches.append({"path": rel, "expected": digest, "actual": actual})
    report["missing_outputs"] = sorted(missing)
    report["hash_mismatches"] = sorted(mismatches, key=lambda m: m["path"])
    if outputs_total:
        report["checks"] += 1

    # 4. Readpoints
    rp_failures: list[dict] = []
    readpoints = manifest.get("readpoints") or []
    for rp in readpoints:
        report["checks"] += 1
        artifact = run_dir / str(rp.get("artifact", ""))
        if not artifact.is_file():
            rp_failures.append({"artifact": str(rp.get("artifact", "")), "reason": "missing"})
            continue
        if hash_path(artifact) != rp.get("digest"):
            rp_failures.append({"artifact": str(rp.get("artifact", "")), "reason": "hash"})

    report["readpoint_failures"] = rp_failures
    report["reproducible"] = bool(
        report["chain_ok"]
        and report["checks"] > 0
        and not report["missing_outputs"]
        and not report["hash_mismatches"]
        and not report["unresolved_actions"]
        and not report["readpoint_failures"]
    )
    return report
