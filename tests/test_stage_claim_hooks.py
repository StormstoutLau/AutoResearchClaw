"""G2 M4: Stage 9/20/23 hook wiring and dual-plane consistency tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from researchclaw.adapters import AdapterBundle
from researchclaw.config import RCConfig
from researchclaw.evidence.stage_hooks import (
    ClaimStreamError,
    load_claims,
    run_stage20_gate,
    run_stage23_consistency,
    write_stage9_claims,
)
from researchclaw.pipeline.stages import StageStatus


def _minimal() -> dict:
    return {
        "project": {"name": "m4-demo"},
        "research": {"topic": "Dual-plane claim wiring"},
        "runtime": {"timezone": "UTC"},
        "notifications": {"channel": "console"},
        "knowledge_base": {"root": "docs/kb"},
        "llm": {
            "provider": "openai-compatible",
            "base_url": "https://example.invalid/v1",
            "api_key_env": "OPENAI_API_KEY",
        },
    }


def _config() -> RCConfig:
    return RCConfig.from_dict(_minimal(), check_paths=False)


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


def _write_claim(run_dir: Path, claim: dict, stage: str = "stage-09") -> Path:
    stage_dir = run_dir / stage
    stage_dir.mkdir(parents=True, exist_ok=True)
    path = stage_dir / "claims.jsonl"
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    existing = [line for line in existing if line.strip()]
    existing.append(json.dumps(claim, ensure_ascii=False))
    path.write_text("\n".join(existing) + "\n", encoding="utf-8")
    return path


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ── Stage 9 ─────────────────────────────────────────────────────


def test_stage9_hook_writes_claim_records(tmp_path: Path) -> None:
    stage_dir = tmp_path / "stage-09"
    stage_dir.mkdir()
    artifacts = write_stage9_claims(
        stage_dir,
        "1. Scaling the learning rate by 1/sqrt(d) keeps the loss within 2%.\n",
    )
    assert artifacts == ("claims.jsonl",)
    claims = load_claims(tmp_path)
    assert len(claims) == 1
    assert claims[0]["claim_class"] == "C"
    assert claims[0]["status"] == "speculation"
    assert claims[0]["claim_id"].startswith("c-")


def _plan_yaml() -> str:
    return (
        "baselines:\n"
        "  - name: ResNet-50\n"
        "    description: standard baseline\n"
        "proposed_methods:\n"
        "  - name: GroupNorm variant\n"
        "ablations:\n"
        "  - no-groupnorm\n"
        "datasets: [CIFAR-10]\n"
        "metrics: [accuracy]\n"
        "objectives: Improve accuracy by 2% over the baseline.\n"
    )


class _FakeLLM:
    def __init__(self, text: str) -> None:
        self.text = text

    def chat(self, messages, **kwargs):  # noqa: ANN001, ARG002
        from researchclaw.llm.client import LLMResponse

        return LLMResponse(content=self.text, model="fake-model")


def test_stage9_executor_reports_claim_artifact(tmp_path: Path) -> None:
    from researchclaw.pipeline.stage_impls._experiment_design import (
        _execute_experiment_design,
    )

    run_dir = tmp_path / "run"
    stage_dir = run_dir / "stage-09"
    stage_dir.mkdir(parents=True)
    prior = run_dir / "stage-08"
    prior.mkdir()
    (prior / "hypotheses.md").write_text(
        "# Hypotheses\n\n1. GroupNorm improves CIFAR-10 accuracy by 2%.\n",
        encoding="utf-8",
    )
    result = _execute_experiment_design(
        stage_dir, run_dir, _config(), AdapterBundle(), llm=_FakeLLM(_plan_yaml())
    )
    assert result.status == StageStatus.DONE
    assert "claims.jsonl" in result.artifacts
    assert "stage-09/claims.jsonl" in result.evidence_refs
    assert (stage_dir / "claims.jsonl").is_file()


# ── Stage 20 ────────────────────────────────────────────────────


def test_stage20_gate_passes_speculation_claims(tmp_path: Path) -> None:
    _write_claim(
        tmp_path,
        _claim(
            claim_class="C",
            formal_statement=None,
            evidence=[],
            falsifier={"condition": "", "test_ref": ""},
            status="speculation",
        ),
    )
    stage20 = tmp_path / "stage-20"
    stage20.mkdir()
    gate = run_stage20_gate(stage20, tmp_path)
    assert gate["blocked"] is False
    assert gate["verdict"] == "pass"
    assert gate["payload"]["total"] == 1
    assert (stage20 / "claims.jsonl").is_file()
    assert (stage20 / "claim_gate.json").is_file()


def test_stage20_gate_blocks_falsified_claim(tmp_path: Path) -> None:
    _write_claim(tmp_path, _claim(status="falsified"))
    stage20 = tmp_path / "stage-20"
    stage20.mkdir()
    gate = run_stage20_gate(stage20, tmp_path)
    assert gate["blocked"] is True
    assert gate["verdict"] == "block"
    assert gate["payload"]["blocked"][0]["reasons"] == ["claim_not_deliverable"]


def test_stage20_gate_blocks_numeric_claim_without_annotation(tmp_path: Path) -> None:
    _write_claim(tmp_path, _claim())
    stage20 = tmp_path / "stage-20"
    stage20.mkdir()
    gate = run_stage20_gate(stage20, tmp_path)
    assert gate["blocked"] is True
    assert gate["payload"]["missing_annotation"] == ["c-11111111"]

    (tmp_path / "annotations.json").write_text(
        json.dumps({"c-11111111": "n=5 seeds, 95% CI"}), encoding="utf-8"
    )
    gate = run_stage20_gate(stage20, tmp_path)
    assert gate["blocked"] is False
    assert gate["verdict"] == "pass"


def test_stage20_gate_records_downgrade(tmp_path: Path) -> None:
    _write_claim(
        tmp_path,
        _claim(evidence=[], status="speculation"),
    )
    stage20 = tmp_path / "stage-20"
    stage20.mkdir()
    gate = run_stage20_gate(stage20, tmp_path)
    assert gate["blocked"] is False
    assert gate["verdict"] == "downgraded"
    updated = _read_jsonl(stage20 / "claims.jsonl")
    assert updated[0]["status"] == "speculation"
    assert updated[0]["assumptions"]


def test_stage20_executor_blocks_on_claim_contract(tmp_path: Path) -> None:
    from researchclaw.pipeline.stage_impls._review_publish import (
        _execute_quality_gate,
    )

    _write_claim(tmp_path, _claim(status="falsified"))
    stage19 = tmp_path / "stage-19"
    stage19.mkdir()
    (stage19 / "paper_revised.md").write_text("# Paper\n\nbody\n", encoding="utf-8")
    stage20 = tmp_path / "stage-20"
    stage20.mkdir()

    result = _execute_quality_gate(stage20, tmp_path, _config(), AdapterBundle(), llm=None)
    assert result.status == StageStatus.FAILED
    assert "E20_CLAIM_CONTRACT" in (result.error or "")
    assert "claim_gate.json" in result.artifacts


# ── Stage 23 ────────────────────────────────────────────────────


def _passing_gate(tmp_path: Path) -> None:
    _write_claim(tmp_path, _claim())
    (tmp_path / "annotations.json").write_text(
        json.dumps({"c-11111111": "n=5 seeds, 95% CI"}), encoding="utf-8"
    )
    stage20 = tmp_path / "stage-20"
    stage20.mkdir(exist_ok=True)
    gate = run_stage20_gate(stage20, tmp_path)
    assert gate["blocked"] is False


def test_stage23_consistency_matches_production(tmp_path: Path) -> None:
    _passing_gate(tmp_path)
    stage23 = tmp_path / "stage-23"
    stage23.mkdir()
    result = run_stage23_consistency(stage23, tmp_path)
    assert result["consistent"] is True
    payload = result["payload"]
    assert payload["checked"] == 1
    assert "skipped" not in payload
    assert (stage23 / "claim_consistency.json").is_file()


def test_stage23_detects_status_drift(tmp_path: Path) -> None:
    _passing_gate(tmp_path)
    stage20_claims = tmp_path / "stage-20" / "claims.jsonl"
    claims = _read_jsonl(stage20_claims)
    claims[0]["status"] = "formally_verified"
    stage20_claims.write_text(
        "\n".join(json.dumps(claim) for claim in claims) + "\n", encoding="utf-8"
    )
    stage23 = tmp_path / "stage-23"
    stage23.mkdir()
    result = run_stage23_consistency(stage23, tmp_path)
    assert result["consistent"] is False
    assert result["payload"]["diffs"][0]["reason"] == "status_mismatch"


def test_stage23_detects_deliverable_drift(tmp_path: Path) -> None:
    _passing_gate(tmp_path)
    stage20_claims = tmp_path / "stage-20" / "claims.jsonl"
    claims = _read_jsonl(stage20_claims)
    claims[0]["statement"] = "studies show the method is state of the art"
    stage20_claims.write_text(
        "\n".join(json.dumps(claim) for claim in claims) + "\n", encoding="utf-8"
    )
    stage23 = tmp_path / "stage-23"
    stage23.mkdir()
    result = run_stage23_consistency(stage23, tmp_path)
    assert result["consistent"] is False
    assert result["payload"]["diffs"][0]["reason"] == "deliverable_mismatch"


def test_stage23_skips_without_production_gate(tmp_path: Path) -> None:
    _write_claim(tmp_path, _claim())
    stage23 = tmp_path / "stage-23"
    stage23.mkdir()
    result = run_stage23_consistency(stage23, tmp_path)
    assert result["consistent"] is True
    assert result["payload"]["skipped"] == "no_production_gate"


def test_stage23_executor_blocks_on_drift(tmp_path: Path) -> None:
    from researchclaw.pipeline.stage_impls._review_publish import (
        _execute_citation_verify,
    )

    _passing_gate(tmp_path)
    stage20_claims = tmp_path / "stage-20" / "claims.jsonl"
    claims = _read_jsonl(stage20_claims)
    claims[0]["status"] = "formally_verified"
    stage20_claims.write_text(
        "\n".join(json.dumps(claim) for claim in claims) + "\n", encoding="utf-8"
    )
    stage23 = tmp_path / "stage-23"
    stage23.mkdir()

    result = _execute_citation_verify(
        stage23, tmp_path, _config(), AdapterBundle(), llm=None
    )
    assert result.status == StageStatus.FAILED
    assert "E23_CLAIM_DRIFT" in (result.error or "")
    assert "claim_consistency.json" in result.artifacts


def test_stage23_executor_no_bib_writes_consistency(tmp_path: Path) -> None:
    from researchclaw.pipeline.stage_impls._review_publish import (
        _execute_citation_verify,
    )

    _passing_gate(tmp_path)
    stage23 = tmp_path / "stage-23"
    stage23.mkdir()

    result = _execute_citation_verify(
        stage23, tmp_path, _config(), AdapterBundle(), llm=None
    )
    assert result.status == StageStatus.DONE
    assert "claim_consistency.json" in result.artifacts
    report = json.loads((stage23 / "claim_consistency.json").read_text(encoding="utf-8"))
    assert report["consistent"] is True
    assert report["checked"] == 1


# ── P-063 / D-1: versioned stage dirs after PIVOT ───────────────


def test_load_claims_prefers_live_dir_over_versions(tmp_path: Path) -> None:
    _write_claim(tmp_path, _claim(statement="NEW", claim_id="c-11111111"), stage="stage-09")
    _write_claim(
        tmp_path, _claim(statement="OLD", claim_id="c-22222222"), stage="stage-09_v1"
    )
    assert [claim["statement"] for claim in load_claims(tmp_path)] == ["NEW"]


def test_load_claims_picks_newest_version_without_live_dir(tmp_path: Path) -> None:
    for version, statement, claim_id in (
        (1, "V1", "c-11111111"),
        (10, "V10", "c-22222222"),
        (2, "V2", "c-33333333"),
    ):
        _write_claim(
            tmp_path,
            _claim(statement=statement, claim_id=claim_id),
            stage=f"stage-09_v{version}",
        )
    assert [claim["statement"] for claim in load_claims(tmp_path)] == ["V10"]


def test_stage20_gate_ignores_stale_version_after_pivot(tmp_path: Path) -> None:
    _write_claim(
        tmp_path,
        _claim(
            claim_class="C",
            formal_statement=None,
            evidence=[],
            falsifier={"condition": "", "test_ref": ""},
            status="speculation",
            claim_id="c-11111111",
        ),
        stage="stage-09",
    )
    _write_claim(
        tmp_path,
        _claim(status="falsified", claim_id="c-22222222"),
        stage="stage-09_v1",
    )
    stage20 = tmp_path / "stage-20"
    stage20.mkdir()
    gate = run_stage20_gate(stage20, tmp_path)
    assert gate["blocked"] is False
    assert gate["payload"]["total"] == 1
    assert gate["payload"]["decisions"]["c-11111111"]["status"] == "speculation"


# ── P-063 / D-2: fail-closed reads and atomic writes ────────────


def test_load_claims_rejects_corrupt_line(tmp_path: Path) -> None:
    _write_claim(tmp_path, _claim())
    path = tmp_path / "stage-09" / "claims.jsonl"
    path.write_text(
        path.read_text(encoding="utf-8") + '{"claim_id": "c-badbad00" BROKEN\n',
        encoding="utf-8",
    )
    with pytest.raises(ClaimStreamError):
        load_claims(tmp_path)


def test_stage20_executor_fails_closed_on_corrupt_claims(tmp_path: Path) -> None:
    from researchclaw.pipeline.stage_impls._review_publish import (
        _execute_quality_gate,
    )

    _write_claim(tmp_path, _claim())
    path = tmp_path / "stage-09" / "claims.jsonl"
    path.write_text(
        path.read_text(encoding="utf-8") + '{"claim_id": "c-badbad00" BROKEN\n',
        encoding="utf-8",
    )
    stage19 = tmp_path / "stage-19"
    stage19.mkdir()
    (stage19 / "paper_revised.md").write_text("# Paper\n\nbody\n", encoding="utf-8")
    stage20 = tmp_path / "stage-20"
    stage20.mkdir()

    result = _execute_quality_gate(stage20, tmp_path, _config(), AdapterBundle(), llm=None)
    assert result.status == StageStatus.FAILED
    assert "E20_CLAIM_CONTRACT_INTERNAL" in (result.error or "")


def test_write_claims_is_atomic_on_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from researchclaw.evidence import stage_hooks

    path = tmp_path / "claims.jsonl"
    original = '{"claim_id": "c-aaaaaaaa"}\n'
    path.write_text(original, encoding="utf-8")

    def _boom(_src: str, _dst: str) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(stage_hooks.os, "replace", _boom)
    with pytest.raises(OSError):
        stage_hooks._write_claims(path, [_claim(claim_id="c-bbbbbbbb")])
    assert path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob("*.tmp")) == []


def test_stage23_executor_fails_closed_on_corrupt_gate(tmp_path: Path) -> None:
    from researchclaw.pipeline.stage_impls._review_publish import (
        _execute_citation_verify,
    )

    _passing_gate(tmp_path)
    (tmp_path / "stage-20" / "claim_gate.json").write_text(
        "{broken", encoding="utf-8"
    )
    stage23 = tmp_path / "stage-23"
    stage23.mkdir()

    result = _execute_citation_verify(
        stage23, tmp_path, _config(), AdapterBundle(), llm=None
    )
    assert result.status == StageStatus.FAILED
    assert "E23_CLAIM_DRIFT_INTERNAL" in (result.error or "")


# ── P-063 / D-3: gate-level structural validation ───────────────


def test_stage20_gate_blocks_invalid_status(tmp_path: Path) -> None:
    _write_claim(
        tmp_path,
        {"claim_id": "c-11111111", "statement": "x", "status": "excellent"},
    )
    stage20 = tmp_path / "stage-20"
    stage20.mkdir()
    gate = run_stage20_gate(stage20, tmp_path)
    assert gate["blocked"] is True
    entry = gate["payload"]["blocked"][0]
    assert entry["reasons"] == ["invalid_claim_record"]
    assert "status" in entry["problems"]
    assert any(problem.startswith("missing:") for problem in entry["problems"])


def test_stage20_gate_blocks_missing_claim_id(tmp_path: Path) -> None:
    claim = _claim()
    del claim["claim_id"]
    _write_claim(tmp_path, claim)
    stage20 = tmp_path / "stage-20"
    stage20.mkdir()
    gate = run_stage20_gate(stage20, tmp_path)
    assert gate["blocked"] is True
    entry = gate["payload"]["blocked"][0]
    assert entry["claim_id"] == "<invalid-1>"
    assert "claim_id" in entry["problems"]
