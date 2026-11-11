"""Contract v1 conformance (G2 M0 / A2-1).

Every schema must parse, every fixture must be classified correctly, and the
red-line negatives must fail at the expected field.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts" / "v1"
FIXTURES = CONTRACTS / "fixtures"

EXPECTED_SCHEMAS = {
    "c1_run_envelope": "urn:arc:contracts:v1:run_envelope",
    "c2_task_contract": "urn:arc:contracts:v1:task_contract",
    "c3_gate_result": "urn:arc:contracts:v1:gate_result",
    "c4_claim_record": "urn:arc:contracts:v1:claim_record",
    "c5_evidence_ref": "urn:arc:contracts:v1:evidence_ref",
    "c6_model_role": "urn:arc:contracts:v1:model_role",
    "c7_derived_view": "urn:arc:contracts:v1:derived_view",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _schemas() -> dict[str, dict]:
    return {p.name.split(".")[0]: _load(p) for p in sorted(CONTRACTS.glob("*.schema.json"))}


def _registry(schemas: dict[str, dict]) -> Registry:
    registry = Registry()
    for schema in schemas.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    return registry


@pytest.fixture(scope="module")
def validate():
    schemas = _schemas()
    registry = _registry(schemas)

    def run(contract: str, document: dict) -> list:
        validator = Draft202012Validator(schemas[contract], registry=registry)
        return sorted(validator.iter_errors(document), key=lambda e: list(e.path))

    return run


def _fixture_params() -> list:
    params = []
    for contract in EXPECTED_SCHEMAS:
        for kind in ("valid", "invalid"):
            for path in sorted((FIXTURES / contract / kind).glob("*.json")):
                params.append(pytest.param(path, kind, id=f"{contract}/{kind}/{path.name}"))
    return params


def test_schema_set_is_frozen():
    schemas = _schemas()
    assert set(schemas) == set(EXPECTED_SCHEMAS)
    assert {name: schema["$id"] for name, schema in schemas.items()} == EXPECTED_SCHEMAS


@pytest.mark.parametrize("contract", sorted(EXPECTED_SCHEMAS))
def test_schema_is_valid(contract):
    Draft202012Validator.check_schema(_schemas()[contract])


@pytest.mark.parametrize("contract", sorted(EXPECTED_SCHEMAS))
def test_each_contract_has_positive_and_negative_fixture(contract):
    for kind in ("valid", "invalid"):
        files = list((FIXTURES / contract / kind).glob("*.json"))
        assert files, f"{contract} is missing a {kind} fixture"


@pytest.mark.parametrize("path,kind", _fixture_params())
def test_fixture_classification(validate, path, kind):
    errors = validate(path.parents[1].name, _load(path))
    if kind == "valid":
        assert errors == [], [f"{e.json_path}: {e.message}" for e in errors]
    else:
        assert errors, f"{path} unexpectedly passed validation"


def test_run_envelope_forbids_verdict(validate):
    path = FIXTURES / "c1_run_envelope" / "invalid" / "with_verdict.json"
    errors = validate("c1_run_envelope", _load(path))
    assert any("verdict" in e.message for e in errors), [e.message for e in errors]


def test_claim_record_requires_claim_class(validate):
    path = FIXTURES / "c4_claim_record" / "invalid" / "missing_claim_class.json"
    errors = validate("c4_claim_record", _load(path))
    assert any("claim_class" in e.message for e in errors), [e.message for e in errors]


def test_claim_record_rejects_unknown_status(validate):
    path = FIXTURES / "c4_claim_record" / "invalid" / "bad_status.json"
    errors = validate("c4_claim_record", _load(path))
    assert any(list(e.path) == ["status"] for e in errors), [e.message for e in errors]


def test_evidence_snapshot_requires_readonly(validate):
    path = FIXTURES / "c5_evidence_ref" / "invalid" / "snapshot_without_readonly.json"
    errors = validate("c5_evidence_ref", _load(path))
    assert any(list(e.path) == ["readonly"] for e in errors), [e.message for e in errors]
