"""T01-T10 — drift guard metrics, FA-1..FA-3 and Stage 15 wiring (P-167)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from researchclaw.guards.drift import (
    DriftThresholds,
    assess_drift,
    extract_conclusion,
    lexical_cosine,
    p_only_ratio,
    read_scope_change_approval,
    write_scope_change_approval,
)
from researchclaw.pipeline.stage_impls._analysis import _apply_drift_guard
from researchclaw.pipeline.stages import StageStatus

GOAL = (
    "# Goal\n\n"
    "We study dropout regularization and expected calibration error for shallow MLPs "
    "on tabular datasets. Hypothesis: MC dropout lowers ECE versus standard dropout.\n"
)
ANALYSIS_RELATED = (
    "# Conclusion\n\n"
    "We study dropout regularization and expected calibration error for shallow MLPs "
    "on tabular datasets. MC dropout lowers ECE by 0.03 with an effect size of 0.6.\n"
)
ANALYSIS_UNRELATED = (
    "# Analysis\n\n"
    "The poem uses iambic pentameter and medieval imagery. [Doe, 2024]\n"
    "The castle archive was catalogued in the fifteenth century. [Roe, 1999]\n"
)
DECISION_PROCEED = (
    "# Research Decision\n\n## Decision\nPROCEED\n\n"
    "## Justification\nWe keep the original research question.\n"
)


def _run_dir(tmp_path: Path, *, analysis: str = ANALYSIS_RELATED,
             decision: str = DECISION_PROCEED, goal: str = GOAL,
             hypotheses: str = "- H1: MC dropout lowers ECE.\n",
             scope: dict | None = None) -> tuple[Path, Path]:
    run = tmp_path / "run-1"
    for stage, name, text in (
        ("stage-01", "goal.md", goal),
        ("stage-08", "hypotheses.md", hypotheses),
        ("stage-14", "analysis.md", analysis),
        ("stage-15", "decision.md", decision),
    ):
        directory = run / stage
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text(text, encoding="utf-8")
    stage_dir = run / "stage-15"
    if scope is not None:
        (stage_dir / "scope_change_approval.json").write_text(
            json.dumps(scope), encoding="utf-8"
        )
    return run, stage_dir


def test_tokenize_and_cosine() -> None:
    assert lexical_cosine("dropout calibration tabular", "dropout calibration tabular") == 1.0
    assert lexical_cosine(GOAL, ANALYSIS_RELATED) > 0.45
    assert lexical_cosine(GOAL, ANALYSIS_UNRELATED) < 0.20
    assert lexical_cosine("", "anything") == 0.0


def test_conclusion_and_p_only() -> None:
    text = "# Intro\nfoo\n## Conclusion\nbar\n## Discussion\nbaz"
    conclusion = extract_conclusion(text)
    assert "bar" in conclusion and "baz" in conclusion and "foo" not in conclusion

    p_only = p_only_ratio(
        "The result is significant (p < 0.05). "
        "The gain is also significant (p < 0.01) with an effect size of 0.6 and a 95% CI."
    )
    assert p_only == 0.5


def test_fa1_unrelated_analysis_pauses(tmp_path: Path) -> None:
    run, stage_dir = _run_dir(tmp_path, analysis=ANALYSIS_UNRELATED)
    report, pause = _apply_drift_guard(
        stage_dir, run, "PROCEED", DECISION_PROCEED, ANALYSIS_UNRELATED
    )

    assert report.action == "pause", report.to_dict()
    assert report.rq_cos is not None and report.rq_cos < 0.20
    assert report.unsupported_ratio is not None and report.unsupported_ratio > 0.40
    assert pause is not None and pause.status is StageStatus.PAUSED
    assert pause.error == "E_DRIFT_DETECTED"
    assert (stage_dir / "drift_report.json").is_file()
    assert "RQ Re-anchoring" in (stage_dir / "decision.md").read_text(encoding="utf-8")


def test_fa2_related_analysis_proceeds(tmp_path: Path) -> None:
    run, stage_dir = _run_dir(tmp_path)
    report, pause = _apply_drift_guard(
        stage_dir, run, "PROCEED", DECISION_PROCEED, ANALYSIS_RELATED
    )

    assert report.action == "pass", report.to_dict()
    assert pause is None


def test_fa3_approved_scope_change_exempts(tmp_path: Path) -> None:
    scope = {"approved": True, "reason": "approved pivot", "approved_by": "hitl"}
    run, stage_dir = _run_dir(tmp_path, analysis=ANALYSIS_UNRELATED, scope=scope)
    report, pause = _apply_drift_guard(
        stage_dir, run, "PIVOT", DECISION_PROCEED, ANALYSIS_UNRELATED
    )

    assert report.action == "exempt", report.to_dict()
    assert pause is None


def test_pivot_without_approval_is_judged(tmp_path: Path) -> None:
    run, stage_dir = _run_dir(tmp_path, analysis=ANALYSIS_UNRELATED)
    report, pause = _apply_drift_guard(
        stage_dir, run, "PIVOT", DECISION_PROCEED, ANALYSIS_UNRELATED
    )

    assert report.action == "pause"
    assert pause is not None


def test_bad_scope_file_is_treated_as_unapproved(tmp_path: Path) -> None:
    run, stage_dir = _run_dir(tmp_path, analysis=ANALYSIS_UNRELATED)
    (stage_dir / "scope_change_approval.json").write_text("{not json", encoding="utf-8")

    assert read_scope_change_approval(stage_dir) is None
    report, pause = _apply_drift_guard(
        stage_dir, run, "PIVOT", DECISION_PROCEED, ANALYSIS_UNRELATED
    )
    assert report.action == "pause"
    assert pause is not None


def test_insufficient_inputs_warn_only(tmp_path: Path) -> None:
    run, stage_dir = _run_dir(tmp_path, goal="", hypotheses="", analysis="short")
    report = assess_drift(run, stage_dir, "PROCEED", "short", "short")

    assert report.action == "warn"
    assert "insufficient_inputs" in report.reasons


def test_p_only_warn(tmp_path: Path) -> None:
    decision = (
        "## Decision\nPROCEED\n\n"
        "The result is significant (p < 0.05) but the magnitude is not reported.\n"
    )
    run, stage_dir = _run_dir(tmp_path, decision=decision)
    report = assess_drift(
        run, stage_dir, "PROCEED", decision, ANALYSIS_RELATED
    )

    assert report.action == "warn"
    assert report.p_only_ratio is not None and report.p_only_ratio > 0.50


def test_thresholds_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARC_DRIFT_RQ_WARN", "0.9")
    monkeypatch.setenv("ARC_DRIFT_RQ_PAUSE", "0.8")
    monkeypatch.setenv("ARC_DRIFT_LEXICAL_PAUSE", "0.7")
    monkeypatch.setenv("ARC_DRIFT_P_ONLY_WARN", "not-a-float")
    thresholds = DriftThresholds.from_env()
    assert thresholds.rq_warn == 0.9
    assert thresholds.rq_pause == 0.8
    assert thresholds.lexical_pause == 0.7
    assert thresholds.p_only_warn == 0.50


def test_scope_approval_roundtrip(tmp_path: Path) -> None:
    stage_dir = tmp_path / "stage-15"
    stage_dir.mkdir()
    path = write_scope_change_approval(
        stage_dir, approved=True, reason="ok", approved_by="human"
    )
    payload = read_scope_change_approval(stage_dir)
    assert path.is_file()
    assert payload is not None and payload["approved"] is True
    assert payload["schema"] == "arc-scope-change-approval/1"


def test_report_schema_and_determinism(tmp_path: Path) -> None:
    run, stage_dir = _run_dir(tmp_path)
    first = assess_drift(run, stage_dir, "PROCEED", DECISION_PROCEED, ANALYSIS_RELATED)
    second = assess_drift(run, stage_dir, "PROCEED", DECISION_PROCEED, ANALYSIS_RELATED)

    payload = first.to_dict()
    assert payload["schema"] == "arc-drift-report/1"
    assert payload["backend"] == "lexical_tfidf"
    assert set(payload["thresholds"]) == {
        "rq_warn", "rq_pause", "unsupported_pause", "p_only_warn", "lexical_pause"
    }
    assert first.action == second.action
    assert first.rq_cos == second.rq_cos
    assert first.unsupported_ratio == second.unsupported_ratio
