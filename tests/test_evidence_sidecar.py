"""Unit tests for the M3 sidecar client (fake sidecar, no Lean)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from researchclaw.evidence import (
    SidecarConfig,
    SidecarConfigError,
    SidecarError,
    SidecarRequestError,
    SidecarTimeout,
    run_lean_check,
)
from researchclaw.evidence.sidecar import _build_env, _write_json_atomic

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts" / "v1"
FIXTURE = ROOT / "tests" / "fixtures" / "g2" / "ar" / "ar01_positive.json"

FAKE_SRC = '''\
import argparse, json, os, sys, time
p = argparse.ArgumentParser()
p.add_argument("--request")
p.add_argument("--response")
a = p.parse_args()
req = json.loads(open(a.request, encoding="utf-8").read())
mode = os.environ.get("FAKE_MODE", "ok")
if mode == "sleep":
    time.sleep(10)
if mode == "noresponse":
    sys.exit(int(os.environ.get("FAKE_EXIT", "0")))
claim = req["claim"].copy()
if os.environ.get("FAKE_STATUS"):
    claim["status"] = os.environ["FAKE_STATUS"]
if os.environ.get("FAKE_DEPTH"):
    claim["verification_depth"] = os.environ["FAKE_DEPTH"]
resp = {
    "schema_version": "1.0",
    "request_id": req["request_id"],
    "run": {
        "run_id": req["request_id"], "attempt": 1,
        "inputs_digest": "sha256:" + "a" * 64,
        "exit_code": int(os.environ.get("FAKE_EXIT", "0")),
        "status": "succeeded", "usage": {},
    },
    "claim_record": claim,
    "lean": {"available": True, "tree_origin": "compile_only"},
    "degraded_reason": None,
    "lean_unavailable_reason": None,
}
if mode == "bad":
    resp.pop("claim_record")
with open(a.response, "w", encoding="utf-8") as handle:
    json.dump(resp, handle)
sys.exit(int(os.environ.get("FAKE_EXIT", "0")))
'''


def _claim() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _config(tmp_path: Path, **env: str) -> SidecarConfig:
    scripts = tmp_path / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "arb_verify.py").write_text(FAKE_SRC, encoding="utf-8")
    return SidecarConfig(
        python_exe=sys.executable,
        ap_root=tmp_path,
        timeout_s=30.0,
        env_extra=env,
    )


def _run(tmp_path: Path, config: SidecarConfig):
    return run_lean_check(
        _claim(),
        "theorem t : 1 = 1 := rfl",
        "t",
        config=config,
        run_dir=tmp_path / "run",
    )


def test_atomic_write_leaves_no_tmp(tmp_path):
    target = tmp_path / "x.json"
    _write_json_atomic(target, {"a": 1})
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}
    assert not list(tmp_path.glob("*.tmp"))


def test_missing_response_raises(tmp_path):
    with pytest.raises(SidecarError):
        _run(tmp_path, _config(tmp_path, FAKE_MODE="noresponse"))


@pytest.mark.parametrize(
    ("code", "error"),
    [(65, SidecarRequestError), (75, SidecarTimeout), (78, SidecarConfigError)],
)
def test_exit_codes_map_to_errors(tmp_path, code, error):
    with pytest.raises(error) as exc:
        _run(tmp_path, _config(tmp_path, FAKE_EXIT=str(code)))
    assert exc.value.exit_code == code


def test_hard_timeout_kills_and_returns_75(tmp_path):
    from dataclasses import replace

    config = replace(_config(tmp_path, FAKE_MODE="sleep"), timeout_s=1.5)
    with pytest.raises(SidecarTimeout) as exc:
        _run(tmp_path, config)
    assert exc.value.exit_code == 75
    assert exc.value.response["degraded_reason"] == "lean_timeout"


def test_response_validation_rejects_missing_claim(tmp_path):
    with pytest.raises(SidecarError):
        _run(tmp_path, _config(tmp_path, FAKE_MODE="bad"))


def test_full_c4_response(tmp_path):
    result = _run(
        tmp_path,
        _config(tmp_path, FAKE_STATUS="formally_verified", FAKE_DEPTH="stage3"),
    )
    assert result.exit_code == 0
    claim = result.response["claim_record"]
    assert len([key for key in claim if key in {
        "claim_id", "claim_class", "claim_type", "statement", "formal_statement",
        "formality", "assumptions", "evidence", "reasoning_chain",
        "stats_protocol", "falsifier", "verification_depth", "status",
        "policy_version",
    }]) == 14
    schemas = {
        path.name.split(".")[0]: json.loads(path.read_text(encoding="utf-8"))
        for path in CONTRACTS.glob("*.schema.json")
    }
    registry = Registry()
    for schema in schemas.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    errors = list(Draft202012Validator(schemas["c4_claim_record"], registry=registry).iter_errors(claim))
    assert errors == []


def test_env_allowlist_excludes_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("FOO_API_KEY", "secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    env = _build_env(_config(tmp_path))
    assert "FOO_API_KEY" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
    if os.environ.get("USERPROFILE"):
        assert env.get("USERPROFILE") == os.environ["USERPROFILE"]


def test_invalid_theorem_name_rejected(tmp_path):
    with pytest.raises(SidecarRequestError):
        run_lean_check(
            _claim(), "theorem t : True := by trivial", "bad name",
            config=_config(tmp_path), run_dir=tmp_path / "run",
        )
