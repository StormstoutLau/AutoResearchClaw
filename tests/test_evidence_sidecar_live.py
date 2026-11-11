"""Live tests for the M3 sidecar (real Lean 4.20 project; env-gated)."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from researchclaw.evidence import (
    SidecarConfig,
    SidecarConfigError,
    SidecarError,
    SidecarTimeout,
    run_lean_check,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "g2" / "ar" / "ar01_positive.json"

AP_ROOT = Path(os.environ.get("ARB_AP_ROOT", r"F:\Auto_Prover"))
LEAN_PYTHON = os.environ.get("ARB_LEAN_PYTHON", "")
LEAN_PROJECT = os.environ.get("ARB_LEAN_PROJECT", "")

pytestmark = pytest.mark.skipif(
    not (LEAN_PYTHON and LEAN_PROJECT and AP_ROOT.is_dir() and shutil.which("lake")),
    reason="需要 ARB_LEAN_PYTHON / ARB_LEAN_PROJECT / lake",
)


def _claim() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _config(*, require_lean: bool = True, timeout_s: float = 330.0) -> SidecarConfig:
    return SidecarConfig(
        python_exe=LEAN_PYTHON,
        ap_root=AP_ROOT,
        timeout_s=timeout_s,
        require_lean=require_lean,
    )


def _run(tmp_path, claim=None, *, statement, theorem, source=None, config=None):
    return run_lean_check(
        claim or _claim(),
        statement,
        theorem,
        config=config or _config(),
        run_dir=tmp_path / "run",
        source_project=source or LEAN_PROJECT,
        use_per_run_project=True,
    )


def test_l_a_formally_verified(tmp_path):
    result = _run(
        tmp_path,
        statement="theorem probe_nat_add_zero (n : Nat) : n + 0 = n := by simp",
        theorem="probe_nat_add_zero",
    )
    assert result.exit_code == 0
    record = result.response["claim_record"]
    assert record["status"] == "formally_verified"
    assert record["verification_depth"] == "stage3"
    assert result.response["lean"]["tree_origin"] == "compile_only"
    assert result.response["lean"]["legality"]["overall_pass"] is True


def test_l_b_missing_project_is_78(tmp_path):
    with pytest.raises(SidecarConfigError) as exc:
        _run(
            tmp_path,
            statement="theorem t : 1 = 1 := rfl",
            theorem="t",
            source=str(tmp_path / "does-not-exist"),
        )
    assert exc.value.exit_code == 78
    assert exc.value.response["degraded_reason"] == "lean_project_missing"


def test_l_c_missing_lake_is_78_or_0(tmp_path, monkeypatch):
    monkeypatch.setenv("ARB_LEAN_LAKE", str(tmp_path / "no-lake.exe"))
    with pytest.raises(SidecarConfigError) as exc:
        _run(tmp_path, statement="theorem t : 1 = 1 := rfl", theorem="t")
    assert exc.value.exit_code == 78
    assert exc.value.response["degraded_reason"] == "lean_unavailable"

    result = _run(
        tmp_path / "optional",
        statement="theorem t : 1 = 1 := rfl",
        theorem="t",
        config=_config(require_lean=False),
    )
    assert result.exit_code == 0
    assert result.response["claim_record"]["verification_depth"] == "stage2"
    assert result.response["degraded_reason"] == "lean_unavailable"


def test_l_d_sorry_caps_partially(tmp_path):
    result = _run(
        tmp_path,
        statement="theorem probe_sorry : 1 = 1 := by sorry",
        theorem="probe_sorry",
    )
    assert result.response["claim_record"]["status"] == "partially_formalized"
    assert result.response["claim_record"]["verification_depth"] == "stage2"
    assert result.response["degraded_reason"] == "lean_sorry_present"


def test_l_e_compile_failure_is_failed(tmp_path):
    result = _run(
        tmp_path,
        statement="theorem bad : =",
        theorem="bad",
    )
    assert result.exit_code == 0
    assert result.response["claim_record"]["status"] == "failed"
    assert result.response["claim_record"]["verification_depth"] == "stage2"
    assert result.response["degraded_reason"] == "lean_compile_failed"


def test_l_f_axiom_injection_caps_partially(tmp_path):
    result = _run(
        tmp_path,
        statement="axiom cheat : False\ntheorem probe_ax : False := cheat",
        theorem="probe_ax",
    )
    assert result.response["claim_record"]["status"] == "partially_formalized"
    assert result.response["claim_record"]["verification_depth"] == "stage2"
    assert result.response["degraded_reason"] in {"axioms_not_clean", "legality_failed"}


def test_l_g_timeout_is_75(tmp_path):
    with pytest.raises(SidecarTimeout) as exc:
        _run(
            tmp_path,
            statement="import Mathlib\ntheorem slow : 1 = 1 := by simp",
            theorem="slow",
            config=_config(timeout_s=35.0),
        )
    assert exc.value.exit_code == 75
    assert exc.value.response["degraded_reason"] == "lean_timeout"


def test_l_h_dangerous_construct_rejected(tmp_path):
    result = _run(
        tmp_path,
        statement='import Mathlib\ndef probe_io : IO Unit := IO.println "x"',
        theorem="probe_io",
    )
    assert result.response["claim_record"]["status"] == "failed"
    assert result.response["degraded_reason"] == "rejected_dangerous_construct"
