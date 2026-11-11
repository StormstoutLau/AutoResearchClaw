"""G2 M5 (P-064): offline dual-plane audit core + CLI.

M5 DoD (R-03 §5.2): the same claim must yield the same ``status`` in the
production and audit paths under the same ``policy_version``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from researchclaw.cli import main as cli_main
from researchclaw.evidence.offline_audit import run_offline_audit
from researchclaw.evidence.stage_hooks import (
    ClaimStreamError,
    run_stage20_gate,
    run_stage23_consistency,
)

STATUSES = [
    "formally_verified",
    "partially_formalized",
    "numerically_verified",
    "latex_verified",
    "speculation",
    "failed",
    "falsified",
]


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


def _write_claim(run_dir: Path, claim: dict, stage: str = "stage-09") -> None:
    stage_dir = run_dir / stage
    stage_dir.mkdir(parents=True, exist_ok=True)
    path = stage_dir / "claims.jsonl"
    existing = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []
    existing.append(json.dumps(claim, ensure_ascii=False))
    path.write_text("\n".join(existing) + "\n", encoding="utf-8")


def _passing_gate(tmp_path: Path) -> None:
    _write_claim(tmp_path, _claim())
    (tmp_path / "annotations.json").write_text(
        json.dumps({"c-11111111": "n=5 seeds, 95% CI"}), encoding="utf-8"
    )
    stage20 = tmp_path / "stage-20"
    stage20.mkdir(exist_ok=True)
    gate = run_stage20_gate(stage20, tmp_path)
    assert gate["blocked"] is False


def _snapshot(run_dir: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(run_dir)): path.read_bytes()
        for path in sorted(run_dir.rglob("*"))
        if path.is_file()
    }


# ── core: happy paths ───────────────────────────────────────────


def test_offline_audit_consistent_with_production(tmp_path: Path) -> None:
    _passing_gate(tmp_path)
    report = run_offline_audit(tmp_path)
    assert report["consistent"] is True
    assert report["checked"] == 1
    assert report["diffs"] == []
    assert report["expected_policy_version"] == 2
    assert "skipped" not in report
    assert report["audit"]["c-11111111"]["status"] == "numerically_verified"


@pytest.mark.parametrize("status", STATUSES)
def test_offline_audit_status_matrix_reproduces_production(
    tmp_path: Path, status: str
) -> None:
    """M5 DoD: same claim, same status, both planes, same policy_version."""
    _write_claim(tmp_path, _claim(status=status))
    (tmp_path / "annotations.json").write_text(
        json.dumps({"c-11111111": "n=5 seeds"}), encoding="utf-8"
    )
    stage20 = tmp_path / "stage-20"
    stage20.mkdir()
    run_stage20_gate(stage20, tmp_path)
    report = run_offline_audit(tmp_path)
    assert report["consistent"] is True
    assert report["audit"]["c-11111111"]["status"] == status


def test_offline_audit_is_deterministic(tmp_path: Path) -> None:
    _passing_gate(tmp_path)
    first = json.dumps(run_offline_audit(tmp_path), sort_keys=True)
    second = json.dumps(run_offline_audit(tmp_path), sort_keys=True)
    assert first == second


def test_offline_audit_is_read_only(tmp_path: Path) -> None:
    _passing_gate(tmp_path)
    before = _snapshot(tmp_path)
    run_offline_audit(tmp_path)
    assert _snapshot(tmp_path) == before


def test_offline_audit_prefers_stage20_over_stage09(tmp_path: Path) -> None:
    _passing_gate(tmp_path)
    _write_claim(
        tmp_path,
        _claim(statement="Stage 9 stale copy of the hypothesis statement.", claim_id="c-22222222"),
    )
    report = run_offline_audit(tmp_path)
    assert report["checked"] == 1
    assert "c-22222222" not in report["audit"]


def test_offline_audit_prefers_live_dir_over_versioned(tmp_path: Path) -> None:
    _passing_gate(tmp_path)  # stage-09 live + stage-20 artifacts
    _write_claim(
        tmp_path,
        _claim(status="falsified", claim_id="c-33333333"),
        stage="stage-09_v1",
    )
    report = run_offline_audit(tmp_path)
    assert report["checked"] == 1
    assert "c-33333333" not in report["audit"]


# ── core: drift detection ───────────────────────────────────────


def test_offline_audit_detects_status_drift(tmp_path: Path) -> None:
    _passing_gate(tmp_path)
    stage20_claims = tmp_path / "stage-20" / "claims.jsonl"
    claims = [json.loads(line) for line in stage20_claims.read_text(encoding="utf-8").splitlines() if line.strip()]
    claims[0]["status"] = "formally_verified"
    stage20_claims.write_text(
        "\n".join(json.dumps(claim) for claim in claims) + "\n", encoding="utf-8"
    )
    report = run_offline_audit(tmp_path)
    assert report["consistent"] is False
    assert report["diffs"][0]["reason"] == "status_mismatch"
    assert report["diffs"][0]["production"] == "numerically_verified"
    assert report["diffs"][0]["audit"] == "formally_verified"


def test_offline_audit_detects_deliverable_drift(tmp_path: Path) -> None:
    _passing_gate(tmp_path)
    stage20_claims = tmp_path / "stage-20" / "claims.jsonl"
    claims = [json.loads(line) for line in stage20_claims.read_text(encoding="utf-8").splitlines() if line.strip()]
    claims[0]["statement"] = "studies show the method is state of the art"
    stage20_claims.write_text(
        "\n".join(json.dumps(claim) for claim in claims) + "\n", encoding="utf-8"
    )
    report = run_offline_audit(tmp_path)
    assert report["consistent"] is False
    assert report["diffs"][0]["reason"] == "deliverable_mismatch"


def test_offline_audit_detects_missing_production_decision(tmp_path: Path) -> None:
    _passing_gate(tmp_path)
    extra = _claim(statement="An appended claim has no recorded gate decision.", claim_id="c-44444444")
    stage20_claims = tmp_path / "stage-20" / "claims.jsonl"
    stage20_claims.write_text(
        stage20_claims.read_text(encoding="utf-8") + json.dumps(extra) + "\n",
        encoding="utf-8",
    )
    report = run_offline_audit(tmp_path)
    assert report["consistent"] is False
    assert any(
        diff["claim_id"] == "c-44444444" and diff["reason"] == "missing_production_decision"
        for diff in report["diffs"]
    )


def test_offline_audit_detects_policy_version_mismatch(tmp_path: Path) -> None:
    _passing_gate(tmp_path)
    stage20_claims = tmp_path / "stage-20" / "claims.jsonl"
    claims = [json.loads(line) for line in stage20_claims.read_text(encoding="utf-8").splitlines() if line.strip()]
    claims[0]["policy_version"] = 1
    stage20_claims.write_text(
        "\n".join(json.dumps(claim) for claim in claims) + "\n", encoding="utf-8"
    )
    report = run_offline_audit(tmp_path)
    assert report["consistent"] is False
    assert report["diffs"][0]["reason"] == "policy_version_mismatch"
    assert report["diffs"][0]["expected"] == 2
    assert report["diffs"][0]["found"] == 1


def test_offline_audit_policy_version_opt_in(tmp_path: Path) -> None:
    _passing_gate(tmp_path)
    report = run_offline_audit(tmp_path, expected_policy_version=2)
    assert report["consistent"] is True


# ── core: skip semantics ────────────────────────────────────────


def test_offline_audit_skips_without_production_gate(tmp_path: Path) -> None:
    _write_claim(tmp_path, _claim())
    report = run_offline_audit(tmp_path)
    assert report["consistent"] is True
    assert report["skipped"] == "no_production_gate"
    assert report["checked"] == 1


def test_offline_audit_no_claims_is_vacuously_consistent(tmp_path: Path) -> None:
    (tmp_path / "stage-20").mkdir(parents=True)
    report = run_offline_audit(tmp_path)
    assert report["consistent"] is True
    assert report["checked"] == 0
    assert report["skipped"] == "no_claims"


# ── core: fail-closed inputs ────────────────────────────────────


def test_offline_audit_missing_run_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_offline_audit(tmp_path / "does-not-exist")


def test_offline_audit_corrupt_claims_fail_closed(tmp_path: Path) -> None:
    _passing_gate(tmp_path)
    path = tmp_path / "stage-20" / "claims.jsonl"
    path.write_text(
        path.read_text(encoding="utf-8") + '{"claim_id": "c-badbad00" BROKEN\n',
        encoding="utf-8",
    )
    with pytest.raises(ClaimStreamError):
        run_offline_audit(tmp_path)


def test_offline_audit_corrupt_gate_fail_closed(tmp_path: Path) -> None:
    _passing_gate(tmp_path)
    (tmp_path / "stage-20" / "claim_gate.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(ClaimStreamError):
        run_offline_audit(tmp_path)


# ── CLI ─────────────────────────────────────────────────────────


def test_cli_audit_consistent_exit_0(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _passing_gate(tmp_path)
    rc = cli_main(["audit", "--run-dir", str(tmp_path)])
    assert rc == 0
    assert "CONSISTENT" in capsys.readouterr().out


def test_cli_audit_drift_exit_1(tmp_path: Path) -> None:
    _passing_gate(tmp_path)
    stage20_claims = tmp_path / "stage-20" / "claims.jsonl"
    claims = [json.loads(line) for line in stage20_claims.read_text(encoding="utf-8").splitlines() if line.strip()]
    claims[0]["status"] = "formally_verified"
    stage20_claims.write_text(
        "\n".join(json.dumps(claim) for claim in claims) + "\n", encoding="utf-8"
    )
    assert cli_main(["audit", "--run-dir", str(tmp_path)]) == 1


def test_cli_audit_missing_run_dir_exit_2(tmp_path: Path) -> None:
    assert cli_main(["audit", "--run-dir", str(tmp_path / "nope")]) == 2


def test_cli_audit_corrupt_exit_2(tmp_path: Path) -> None:
    _passing_gate(tmp_path)
    (tmp_path / "stage-20" / "claim_gate.json").write_text("{broken", encoding="utf-8")
    assert cli_main(["audit", "--run-dir", str(tmp_path)]) == 2


def test_cli_audit_json_flag_prints_report(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    _passing_gate(tmp_path)
    rc = cli_main(["audit", "--run-dir", str(tmp_path), "--json"])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["consistent"] is True
    assert report["checked"] == 1


def test_cli_audit_policy_version_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    _passing_gate(tmp_path)
    rc = cli_main(
        ["audit", "--run-dir", str(tmp_path), "--json", "--policy-version", "1"]
    )
    assert rc == 1
    report = json.loads(capsys.readouterr().out)
    assert any(d["reason"] == "policy_version_mismatch" for d in report["diffs"])


def test_cli_audit_output_flag_writes_report(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    _passing_gate(tmp_path)
    out = tmp_path_factory.mktemp("reports") / "audit_report.json"
    rc = cli_main(["audit", "--run-dir", str(tmp_path), "--output", str(out)])
    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["consistent"] is True


# ── P-068 / D-1: orphan production decisions ────────────────────


def _two_claim_run(tmp_path: Path) -> None:
    _write_claim(tmp_path, _claim())
    _write_claim(
        tmp_path,
        _claim(
            claim_id="c-22222222",
            statement="Second hypothesis is stated here.",
        ),
    )
    (tmp_path / "annotations.json").write_text(
        json.dumps({"c-11111111": "n=5", "c-22222222": "n=5"}), encoding="utf-8"
    )
    (tmp_path / "stage-20").mkdir()
    gate = run_stage20_gate(tmp_path / "stage-20", tmp_path)
    assert gate["blocked"] is False


def _drop_last_stage20_claim_line(run_dir: Path) -> None:
    path = run_dir / "stage-20" / "claims.jsonl"
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    path.write_text(lines[0] + "\n", encoding="utf-8")


def test_offline_audit_detects_orphan_production_decision(tmp_path: Path) -> None:
    _two_claim_run(tmp_path)
    _drop_last_stage20_claim_line(tmp_path)
    report = run_offline_audit(tmp_path)
    assert report["consistent"] is False
    assert report["checked"] == 1
    orphan = next(d for d in report["diffs"] if d["reason"] == "orphan_production_decision")
    assert orphan["claim_id"] == "c-22222222"
    assert orphan["production"] == "numerically_verified"


def test_stage23_detects_orphan_production_decision(tmp_path: Path) -> None:
    _two_claim_run(tmp_path)
    _drop_last_stage20_claim_line(tmp_path)
    (tmp_path / "stage-23").mkdir()
    payload = run_stage23_consistency(tmp_path / "stage-23", tmp_path)["payload"]
    assert payload["consistent"] is False
    assert any(d["reason"] == "orphan_production_decision" for d in payload["diffs"])


def test_offline_audit_all_claims_deleted_is_drift(tmp_path: Path) -> None:
    _passing_gate(tmp_path)
    (tmp_path / "stage-20" / "claims.jsonl").unlink()
    (tmp_path / "stage-09" / "claims.jsonl").unlink()
    report = run_offline_audit(tmp_path)
    assert report["consistent"] is False
    assert report["checked"] == 0
    assert "skipped" not in report
    assert report["diffs"][0]["reason"] == "orphan_production_decision"


# ── P-068 / D-4: duplicate claim ids ────────────────────────────


def test_stage20_gate_blocks_duplicate_claim_id(tmp_path: Path) -> None:
    _write_claim(tmp_path, _claim())
    _write_claim(
        tmp_path,
        _claim(
            claim_id="c-11111111",
            statement="A duplicate identifier arrives from an external import.",
        ),
    )
    (tmp_path / "annotations.json").write_text(
        json.dumps({"c-11111111": "n=5"}), encoding="utf-8"
    )
    (tmp_path / "stage-20").mkdir()
    gate = run_stage20_gate(tmp_path / "stage-20", tmp_path)
    assert gate["blocked"] is True
    assert gate["verdict"] == "block"
    assert gate["payload"]["duplicate_claim_ids"] == ["c-11111111"]
    assert any(
        "duplicate_claim_id" in entry["reasons"]
        for entry in gate["payload"]["blocked"]
    )


def test_offline_audit_detects_duplicate_claim_id(tmp_path: Path) -> None:
    _write_claim(tmp_path, _claim())
    _write_claim(
        tmp_path,
        _claim(
            claim_id="c-11111111",
            statement="A duplicate identifier arrives from an external import.",
        ),
    )
    (tmp_path / "annotations.json").write_text(
        json.dumps({"c-11111111": "n=5"}), encoding="utf-8"
    )
    (tmp_path / "stage-20").mkdir()
    run_stage20_gate(tmp_path / "stage-20", tmp_path)
    report = run_offline_audit(tmp_path)
    assert report["consistent"] is False
    assert any(d["reason"] == "duplicate_claim_id" for d in report["diffs"])


# ── P-068 / D-2, D-3, O-B: CLI semantics ────────────────────────


def test_cli_audit_rejects_policy_version_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    _passing_gate(tmp_path)
    rc = cli_main(
        ["audit", "--run-dir", str(tmp_path), "--policy-version", "0"]
    )
    captured = capsys.readouterr()
    assert rc == 2
    assert "--policy-version must be >= 1" in captured.err
    assert captured.out == ""


def test_cli_audit_json_output_keeps_stdout_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    _passing_gate(tmp_path)
    out = tmp_path / "audit_report.json"
    rc = cli_main(
        ["audit", "--run-dir", str(tmp_path), "--json", "--output", str(out)]
    )
    captured = capsys.readouterr()
    assert rc == 0
    report = json.loads(captured.out)
    assert report["consistent"] is True
    assert "report written" in captured.err
    assert json.loads(out.read_text(encoding="utf-8"))["consistent"] is True
