"""G2 M4: publish predicates and the dual-plane claim evaluation (A2-4..A2-6)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from researchclaw.evidence.claim_policy import (
    audit_claim,
    build_claim_records,
    can_enter_deliverables,
    downgrade_missing_citation,
    evaluate_claim,
    requires_annotation,
)
from researchclaw.evidence.ar_checks import Finding

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts" / "v1"


def _c4_validator() -> Draft202012Validator:
    schemas = {
        path.name.split(".")[0]: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(CONTRACTS.glob("*.schema.json"))
    }
    registry = Registry()
    for schema in schemas.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return Draft202012Validator(schemas["c4_claim_record"], registry=registry)


def _claim(**overrides) -> dict:
    claim = {
        "claim_id": "c-11111111",
        "claim_class": "A",
        "claim_type": "exploratory",
        "statement": "Table 3 reports a 1.3% deviation from the baseline.",
        "formal_statement": "Theorem 1",
        "formality": {"status": "formal", "reason": None},
        "assumptions": [],
        "evidence": [
            {
                "evidence_id": "e-001",
                "source_layer": "T1",
                "tier": "E1",
                "kind": "pointer",
                "source_id": "arXiv:1706.03762",
                "locator": "Table 3",
                "quote": "deviation 1.3%",
                "digest": "sha256:" + "a" * 64,
                "independent": True,
                "replay_cmd": None,
            }
        ],
        "reasoning_chain": [],
        "stats_protocol": None,
        "falsifier": {"condition": "deviation > 2%", "test_ref": "e-001"},
        "verification_depth": "stage1",
        "status": "numerically_verified",
        "policy_version": 2,
    }
    claim.update(overrides)
    return claim


def _c_claim(**overrides) -> dict:
    claim = _claim(
        claim_class="C",
        formal_statement=None,
        evidence=[],
        falsifier={"condition": "", "test_ref": ""},
        status="speculation",
    )
    claim.update(overrides)
    return claim


# ── A2-4: can_enter_deliverables ────────────────────────────────


@pytest.mark.parametrize("status", ["falsified", "failed"])
def test_terminal_statuses_are_blocked(status):
    assert can_enter_deliverables(_c_claim(status=status)) is False


@pytest.mark.parametrize(
    "status",
    [
        "formally_verified",
        "partially_formalized",
        "numerically_verified",
        "latex_verified",
        "speculation",
    ],
)
def test_non_terminal_statuses_are_allowed(status):
    assert can_enter_deliverables(_c_claim(status=status)) is True


def test_fail_finding_blocks_deliverables():
    finding = Finding("AR-03", "fail", "banned phrase", "statement")
    assert can_enter_deliverables(_c_claim(), (finding,)) is False


def test_warn_and_downgrade_findings_do_not_block():
    findings = (
        Finding("AR-01", "downgrade", "missing evidence", "evidence"),
        Finding("AR-05", "warn", "missing falsifier", "falsifier", cap="latex_verified"),
    )
    assert can_enter_deliverables(_c_claim(), findings) is True


# ── A2-5: requires_annotation ───────────────────────────────────


def test_numerically_verified_requires_annotation():
    assert requires_annotation(_claim(status="numerically_verified")) is True


@pytest.mark.parametrize(
    "status",
    [
        "formally_verified",
        "partially_formalized",
        "latex_verified",
        "speculation",
        "failed",
        "falsified",
    ],
)
def test_other_statuses_do_not_require_annotation(status):
    assert requires_annotation(_claim(status=status)) is False


def test_numeric_claim_without_annotation_is_blocked():
    decision = evaluate_claim(_claim())
    assert decision.deliverable is False
    assert decision.blocked_reasons == ("missing_annotation",)


def test_numeric_claim_with_annotation_is_deliverable():
    decision = evaluate_claim(_claim(), annotation="n=5 seeds, 95% CI")
    assert decision.deliverable is True
    assert decision.blocked_reasons == ()


# ── A2-6: downgrade_missing_citation ────────────────────────────


def test_a_claim_without_citation_is_downgraded_not_blocked():
    claim = _claim(evidence=[], status="speculation")
    working, downgraded = downgrade_missing_citation(claim)
    assert downgraded is True
    assert working["status"] == "speculation"
    assert any(item["statement"] == claim["statement"] for item in working["assumptions"])
    # The original mapping is never mutated.
    assert claim["assumptions"] == []


def test_downgrade_does_not_fail_the_claim():
    decision = evaluate_claim(_claim(evidence=[], status="speculation"))
    assert decision.downgraded is True
    assert decision.deliverable is True
    assert "missing_annotation" not in decision.blocked_reasons
    assert any(item.severity == "downgrade" for item in decision.findings)


def test_complete_citation_is_not_downgraded():
    working, downgraded = downgrade_missing_citation(_claim(status="formally_verified"))
    assert downgraded is False
    assert working["assumptions"] == []


def test_partial_citation_counts_as_missing():
    claim = _claim(
        evidence=[{"source_id": "arXiv:1706.03762", "locator": "", "quote": "x"}],
        status="speculation",
    )
    _, downgraded = downgrade_missing_citation(claim)
    assert downgraded is True


def test_c_class_is_never_downgraded_for_citation():
    _, downgraded = downgrade_missing_citation(_c_claim())
    assert downgraded is False


def test_b_claim_with_reasoning_chain_is_not_downgraded():
    claim = _claim(
        claim_class="B",
        evidence=[],
        reasoning_chain=[
            {"step": 1, "detail": "The baseline shares the same seed.", "source_refs": ["e-001"]}
        ],
        status="speculation",
    )
    _, downgraded = downgrade_missing_citation(claim)
    assert downgraded is False


def test_b_claim_without_reasoning_chain_is_downgraded():
    claim = _claim(claim_class="B", evidence=[], reasoning_chain=[], status="speculation")
    _, downgraded = downgrade_missing_citation(claim)
    assert downgraded is True


# ── status caps ─────────────────────────────────────────────────


def test_missing_falsifier_caps_formally_verified_at_latex():
    decision = evaluate_claim(
        _claim(status="formally_verified", falsifier={"condition": "", "test_ref": ""})
    )
    assert decision.capped is True
    assert decision.claim["status"] == "latex_verified"
    assert decision.deliverable is True


def test_consensus_used_as_evidence_caps_status():
    decision = evaluate_claim(
        _claim(
            claim_class="C",
            formal_statement=None,
            evidence=[],
            status="numerically_verified",
            consensus={"models": ["m1"], "agreement": 0.9, "used_as": "model"},
        )
    )
    assert decision.capped is True
    assert decision.claim["status"] == "latex_verified"


def test_falsified_is_never_lifted_by_a_cap():
    decision = evaluate_claim(_c_claim(status="falsified"))
    assert decision.claim["status"] == "falsified"
    assert decision.capped is False
    assert decision.deliverable is False


# ── dual plane ──────────────────────────────────────────────────


def test_audit_matches_production_for_same_input():
    claim = _claim()
    production = evaluate_claim(claim, annotation="n=5")
    audit = audit_claim(copy.deepcopy(claim), annotation="n=5")
    assert audit.claim == production.claim
    assert audit.findings == production.findings
    assert audit.deliverable == production.deliverable
    assert audit.blocked_reasons == production.blocked_reasons
    assert audit.as_dict() == production.as_dict()


def test_evaluation_is_deterministic():
    first = evaluate_claim(_claim())
    second = evaluate_claim(_claim())
    assert first.as_dict() == second.as_dict()


# ── D-3: structural gate checks ─────────────────────────────────


def test_invalid_status_is_not_deliverable():
    decision = evaluate_claim(_claim(status="excellent"))
    assert decision.deliverable is False
    assert decision.blocked_reasons == ("invalid_claim_record",)
    assert decision.problems == ("status",)
    assert decision.as_dict()["problems"] == ["status"]


def test_missing_required_fields_are_not_deliverable():
    decision = evaluate_claim({"claim_id": "c-11111111"})
    assert decision.deliverable is False
    assert decision.problems[0] == "missing:" + ",".join(
        name for name in (
            "claim_class", "claim_type", "statement", "formal_statement",
            "formality", "assumptions", "evidence", "reasoning_chain",
            "stats_protocol", "falsifier", "verification_depth", "status",
            "policy_version",
        )
    )


def test_bad_claim_id_is_not_deliverable():
    decision = evaluate_claim(_claim(claim_id="C-123"))
    assert decision.deliverable is False
    assert "claim_id" in decision.problems


def test_valid_claim_has_no_shape_problems():
    decision = evaluate_claim(_claim(), annotation="n=5")
    assert decision.problems == ()
    assert decision.as_dict()["problems"] == []


# ── Stage 9 claim extraction ────────────────────────────────────


def test_build_claim_records_extracts_hypotheses():
    text = (
        "# Hypotheses\n"
        "1. Scaling the learning rate by 1/sqrt(d) keeps the loss within 2%.\n"
        "- The AdamW optimizer improves convergence on CIFAR-10.\n"
        "- Scaling the learning rate by 1/sqrt(d) keeps the loss within 2%.\n"
        "Short.\n"
    )
    records = build_claim_records(text)
    assert len(records) == 2
    assert {item["claim_class"] for item in records} == {"C"}
    assert {item["status"] for item in records} == {"speculation"}
    assert {item["verification_depth"] for item in records} == {"stage1"}
    assert {item["policy_version"] for item in records} == {2}
    assert len({item["claim_id"] for item in records}) == 2
    validator = _c4_validator()
    for record in records:
        assert list(validator.iter_errors(record)) == []


def test_build_claim_records_falls_back_to_plan_objectives():
    records = build_claim_records("", {"objectives": "Measure the effect of depth."})
    assert len(records) == 1
    assert records[0]["statement"] == "Measure the effect of depth."


def test_build_claim_records_empty_input():
    assert build_claim_records("", None) == []
