"""Claim policy: AR checks + publish predicates + dual-plane evaluation (M4)."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping

from .ar_checks import Finding, check_claim
from researchclaw.vendor.auto_prover.datatypes.core import CitationLabel

# M3: single source of truth for the label vocabulary. ``speculation`` is the
# only C4 status that does not exist in the vendor enum (pre-publication state).
CITATION_LABELS = frozenset(label.value for label in CitationLabel)

STATUS_ORDER = {
    "formally_verified": 7,
    "partially_formalized": 6,
    "numerically_verified": 5,
    "latex_verified": 4,
    "speculation": 3,
    "failed": 2,
    "falsified": 1,
}
TERMINAL = {"failed", "falsified"}
HIGH_STATUSES = {"formally_verified", "partially_formalized", "numerically_verified"}

# M5 DoD: production and audit paths must run under the same policy version.
CURRENT_POLICY_VERSION = 2

# C4 v1 required keys (contracts/v1/c4_claim_record.schema.json).
REQUIRED_CLAIM_FIELDS = (
    "claim_id",
    "claim_class",
    "claim_type",
    "statement",
    "formal_statement",
    "formality",
    "assumptions",
    "evidence",
    "reasoning_chain",
    "stats_protocol",
    "falsifier",
    "verification_depth",
    "status",
    "policy_version",
)
CLAIM_ID_RE = re.compile(r"^c-[0-9a-f]{8}$")

INVALID_CLAIM_RECORD = "invalid_claim_record"


def validate_claim_shape(claim: Mapping[str, Any]) -> tuple[str, ...]:
    """Minimal C4 gate check: id shape, required keys, status vocabulary."""
    if not isinstance(claim, Mapping):
        return ("not_object",)
    problems: list[str] = []
    claim_id = claim.get("claim_id")
    if not isinstance(claim_id, str) or not CLAIM_ID_RE.fullmatch(claim_id):
        problems.append("claim_id")
    missing = [name for name in REQUIRED_CLAIM_FIELDS if name not in claim]
    if missing:
        problems.append("missing:" + ",".join(missing))
    if claim.get("status") not in STATUS_ORDER:
        problems.append("status")
    return tuple(problems)


@dataclass(frozen=True)
class ClaimDecision:
    claim: dict
    findings: tuple[Finding, ...] = ()
    deliverable: bool = True
    blocked_reasons: tuple[str, ...] = ()
    downgraded: bool = False
    capped: bool = False
    cap_reasons: tuple[str, ...] = ()
    problems: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "claim_id": self.claim.get("claim_id"),
            "status": self.claim.get("status"),
            "deliverable": self.deliverable,
            "blocked_reasons": list(self.blocked_reasons),
            "downgraded": self.downgraded,
            "capped": self.capped,
            "cap_reasons": list(self.cap_reasons),
            "problems": list(self.problems),
            "findings": [
                {"code": f.code, "severity": f.severity, "field": f.field}
                for f in self.findings
            ],
        }


def _citation_complete(claim: Mapping[str, Any]) -> bool:
    """Mirror AR-01's citation notion: A -> evidence triple, B -> chain refs."""
    if claim.get("claim_class") == "B":
        chain = [
            step
            for step in claim.get("reasoning_chain") or []
            if isinstance(step, dict)
        ]
        return bool(chain) and all(bool(step.get("source_refs")) for step in chain)
    return any(
        isinstance(item, dict)
        and str(item.get("source_id", "")).strip()
        and str(item.get("locator", "")).strip()
        and str(item.get("quote", "")).strip()
        for item in claim.get("evidence", [])
    )


def downgrade_missing_citation(claim: Mapping[str, Any]) -> tuple[dict, bool]:
    """A/B claims without a complete citation move to assumptions + speculation."""
    working = dict(claim)
    if working.get("claim_class") not in ("A", "B"):
        return working, False
    if _citation_complete(working):
        return working, False
    assumptions = list(working.get("assumptions") or [])
    statement = str(working.get("statement", ""))
    if statement and not any(a.get("statement") == statement for a in assumptions if isinstance(a, dict)):
        assumptions.append({"statement": statement, "why": "缺引文/证据（AR-01）"})
    working["assumptions"] = assumptions
    working["status"] = "speculation"
    return working, True


def requires_annotation(claim: Mapping[str, Any]) -> bool:
    return claim.get("status") == "numerically_verified"


def can_enter_deliverables(
    claim: Mapping[str, Any], findings: tuple[Finding, ...] = ()
) -> bool:
    if claim.get("status") in TERMINAL:
        return False
    return not any(item.severity == "fail" for item in findings)


def _cap_status(claim: dict, cap: str) -> tuple[dict, bool]:
    status = claim.get("status")
    if status in TERMINAL or cap not in STATUS_ORDER:
        return claim, False
    if STATUS_ORDER.get(status, 0) <= STATUS_ORDER[cap]:
        return claim, False
    working = dict(claim)
    working["status"] = cap
    return working, True


def evaluate_claim(claim: Mapping[str, Any], annotation: str | None = None) -> ClaimDecision:
    """Production/audit shared evaluation: shape, downgrade, AR checks, caps, predicates."""
    raw = dict(claim) if isinstance(claim, Mapping) else {"claim_id": None}
    problems = validate_claim_shape(raw)
    if problems:
        # D-3: a malformed record must never reach the publish predicates.
        return ClaimDecision(
            claim=raw,
            deliverable=False,
            blocked_reasons=(INVALID_CLAIM_RECORD,),
            problems=problems,
        )
    working, downgraded = downgrade_missing_citation(raw)
    findings = tuple(check_claim(working))
    capped = False
    cap_reasons: list[str] = []
    for finding in findings:
        if finding.cap:
            working, did_cap = _cap_status(working, finding.cap)
            capped = capped or did_cap
            if did_cap:
                reason = f"{finding.code}:{finding.cap}"
                if reason not in cap_reasons:
                    cap_reasons.append(reason)
    blocked: list[str] = []
    if not can_enter_deliverables(working, findings):
        blocked.append("claim_not_deliverable")
    if requires_annotation(working) and not (annotation or "").strip():
        blocked.append("missing_annotation")
    return ClaimDecision(
        claim=working,
        findings=findings,
        deliverable=not blocked,
        blocked_reasons=tuple(blocked),
        downgraded=downgraded,
        capped=capped,
        cap_reasons=tuple(cap_reasons),
    )


def audit_claim(claim: Mapping[str, Any], annotation: str | None = None) -> ClaimDecision:
    """Dual-plane entry: same pure evaluation, no pipeline IO."""
    return evaluate_claim(claim, annotation)


def _claim_id(text: str) -> str:
    return "c-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def build_claim_records(hypotheses_text: str, plan: Mapping[str, Any] | None = None) -> list[dict]:
    """Extract C-class ClaimRecords from hypotheses.md (or plan objectives)."""
    statements: list[str] = []
    for raw in (hypotheses_text or "").splitlines():
        line = raw.strip().lstrip("-*").strip()
        line = line.lstrip("0123456789.、) ").strip()
        if not line or line.startswith("#") or len(line) < 12:
            continue
        if line not in statements:
            statements.append(line)
    if not statements and isinstance(plan, Mapping):
        objective = str(plan.get("objectives", "")).strip()
        if objective:
            statements.append(objective)
    records = []
    for statement in statements[:50]:
        records.append({
            "claim_id": _claim_id(statement),
            "claim_class": "C",
            "claim_type": "exploratory",
            "statement": statement,
            "formal_statement": None,
            "formality": {"status": "formal", "reason": None},
            "assumptions": [],
            "evidence": [],
            "reasoning_chain": [],
            "stats_protocol": None,
            "falsifier": {"condition": "", "test_ref": ""},
            "verification_depth": "stage1",
            "status": "speculation",
            "policy_version": CURRENT_POLICY_VERSION,
        })
    return records
