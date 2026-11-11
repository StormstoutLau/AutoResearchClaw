"""G2 M1: AR-01..08 checks, fixtures, and pre-red mutation selftest (A2-2)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from researchclaw.evidence import CHECKS, SEVERITIES, check_claim

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "g2" / "ar"
CONTRACTS = ROOT / "contracts" / "v1"

EXPECTED_SEVERITY = {
    "AR-01": "downgrade",
    "AR-02": "downgrade",
    "AR-03": "fail",
    "AR-04": "fail",
    "AR-05": "warn",
    "AR-06": "warn",
    "AR-07": "fail",
    "AR-08": "fail",
}


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _stem(code: str) -> str:
    return code.lower().replace("-", "")


def _findings(code: str, claim: dict) -> list:
    return [item for item in check_claim(claim) if item.code == code]


def _c4_validator() -> Draft202012Validator:
    schemas = {
        path.name.split(".")[0]: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(CONTRACTS.glob("*.schema.json"))
    }
    registry = Registry()
    for schema in schemas.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return Draft202012Validator(schemas["c4_claim_record"], registry=registry)


@pytest.mark.parametrize("code,severity", sorted(EXPECTED_SEVERITY.items()))
def test_negative_fixture_triggers_expected_severity(code, severity):
    findings = _findings(code, _load(f"{_stem(code)}_negative.json"))
    assert findings, f"{code} did not fire on its negative fixture"
    assert {item.severity for item in findings} == {severity}
    assert severity in SEVERITIES


@pytest.mark.parametrize("code", sorted(EXPECTED_SEVERITY))
def test_positive_fixture_does_not_trigger_its_check(code):
    assert _findings(code, _load(f"{_stem(code)}_positive.json")) == []


@pytest.mark.parametrize("code", sorted(EXPECTED_SEVERITY))
def test_pre_red_disabling_check_clears_finding(monkeypatch, code):
    claim = _load(f"{_stem(code)}_negative.json")
    assert _findings(code, claim), f"{code} fixture is not red to begin with"
    monkeypatch.setitem(CHECKS, code, lambda _claim: [])
    assert _findings(code, claim) == [], f"{code} still fires after being disabled"


def test_declared_formalization_debt_is_warn_not_fail():
    claim = _load("ar07_negative.json")
    claim["formality"] = {"status": "debt", "reason": "Lean is not enabled for this claim."}
    findings = _findings("AR-07", claim)
    assert [item.severity for item in findings] == ["warn"]
    assert findings[0].cap is None


def test_positive_fixtures_are_valid_claim_records():
    validator = _c4_validator()
    for code in sorted(EXPECTED_SEVERITY):
        claim = _load(f"{_stem(code)}_positive.json")
        errors = sorted(validator.iter_errors(claim), key=lambda item: list(item.path))
        assert errors == [], [f"{e.json_path}: {e.message}" for e in errors]


def test_all_checks_registered():
    assert set(CHECKS) == set(EXPECTED_SEVERITY)


def test_findings_are_sorted():
    claim = _load("ar01_negative.json")
    findings = check_claim(claim)
    assert findings == sorted(findings, key=lambda item: (item.code, item.field, item.message))
