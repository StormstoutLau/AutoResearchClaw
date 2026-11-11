# SPDX-License-Identifier: Apache-2.0
# Vendored from Auto_Prover tests/test_d110_verdict_policy.py at bd95f02.
# Modified by AutoResearchClaw on 2026-11-11: imports point at the vendored kernel.
"""W1 / B-52: citation_label 判定策略矩阵 (纯函数, 零 Lean 依赖)

TDD 红: 本文件先于实现落地。旧实现只看 proven/sorry ⇒ A1/A2 直接失败。
"""
from __future__ import annotations

import asyncio
import json

import pytest

from researchclaw.vendor.auto_prover.datatypes import (
    AssertionVerdict,
    CitationLabel,
    CompileReport,
    LegalityCheckResult,
    LegalityReport,
    NodeStatus,
    ProofNode,
    ProofTree,
    StopStage,
)
from researchclaw.vendor.auto_prover.verdict import POLICY_VERSION
from researchclaw.vendor.auto_prover.verdict.policy import VerdictEvidence, decide_citation_label


def _tree(root_status=NodeStatus.PROVEN, *, proven=1, sorry=0, blocked=0):
    root = ProofNode(id="root", goal="G", tier=1, status=root_status)
    return ProofTree(
        root=root,
        total_subgoals=max(1, proven + sorry + blocked),
        proven=proven, sorry=sorry, blocked=blocked,
    )


def _report(*, status="success", success=True, axioms=None,
            axiom_check="passed", evidence_complete=True):
    return CompileReport(
        success=success,
        status=status,
        axioms=list(axioms or []),
        axiom_check=axiom_check,
        evidence_complete=evidence_complete,
    )


def _legal(passed=True):
    return LegalityReport(
        checks=[LegalityCheckResult(layer=1, layer_name="L1", passed=passed)],
        overall_pass=passed,
    )


def _decide(**overrides):
    base = dict(
        latex_ok=True,
        numerical_failed=False,
        numerical_passed=False,
        proof_tree=None,
        compile_report=None,
        legality_report=None,
        legality_checked=False,
        synthesis_verified=False,
    )
    base.update(overrides)
    return decide_citation_label(VerdictEvidence(**base))


class TestPolicyVersion:
    def test_version_is_two(self):
        assert POLICY_VERSION == 2

    def test_assertion_verdict_defaults_to_current_version(self):
        v = AssertionVerdict(assertion="x")
        assert v.policy_version == POLICY_VERSION
        assert v.verdict_reason == ""
        assert v.verdict_evidence == {}


class TestRootGate:
    def test_root_blocked_with_all_subgoals_proven_is_not_formally_verified(self):
        # D108 P1 原样复现: proven=2 / sorry=0 / blocked=1, 根 BLOCKED
        label, reason = _decide(
            proof_tree=_tree(NodeStatus.BLOCKED, proven=2, blocked=1),
            compile_report=_report(), legality_report=_legal(),
            legality_checked=True,
        )
        assert label != CitationLabel.FORMALLY_VERIFIED
        assert reason == "root_not_proven"

    def test_partial_proof_with_blocked_rest_is_not_formally_verified(self):
        label, reason = _decide(
            proof_tree=_tree(NodeStatus.BLOCKED, proven=1, blocked=4),
            compile_report=_report(), legality_report=_legal(),
            legality_checked=True,
        )
        assert label != CitationLabel.FORMALLY_VERIFIED
        assert reason == "root_not_proven"

    def test_root_blocked_falls_back_to_numerical(self):
        label, reason = _decide(
            proof_tree=_tree(NodeStatus.BLOCKED, proven=2, blocked=1),
            compile_report=_report(), numerical_passed=True,
        )
        assert label == CitationLabel.NUMERICALLY_VERIFIED
        assert reason == "root_not_proven"

    def test_root_blocked_falls_back_to_latex(self):
        label, _ = _decide(
            proof_tree=_tree(NodeStatus.BLOCKED, proven=1, blocked=1),
            compile_report=_report(),
        )
        assert label == CitationLabel.LATEX_VERIFIED


class TestFormalGates:
    def test_all_gates_pass_yields_formally_verified(self):
        label, reason = _decide(
            proof_tree=_tree(NodeStatus.PROVEN, proven=1),
            compile_report=_report(), legality_report=_legal(),
            legality_checked=True,
        )
        assert label == CitationLabel.FORMALLY_VERIFIED
        assert reason == "all_gates_passed"

    def test_synthesis_verified_substitutes_root_status(self):
        label, _ = _decide(
            proof_tree=_tree(NodeStatus.IN_PROGRESS, proven=0),
            compile_report=_report(), legality_report=_legal(),
            legality_checked=True, synthesis_verified=True,
        )
        assert label == CitationLabel.FORMALLY_VERIFIED

    def test_compile_failed_downgrades_to_numerical(self):
        label, reason = _decide(
            proof_tree=_tree(NodeStatus.PROVEN),
            compile_report=_report(status="failed", success=False),
            numerical_passed=True,
        )
        assert label == CitationLabel.NUMERICALLY_VERIFIED
        assert reason == "compile_failed"

    def test_compile_failed_without_numerical_falls_to_latex(self):
        label, _ = _decide(
            proof_tree=_tree(NodeStatus.PROVEN),
            compile_report=_report(status="failed", success=False),
        )
        assert label == CitationLabel.LATEX_VERIFIED

    def test_success_with_sorry_is_partially_formalized(self):
        label, reason = _decide(
            proof_tree=_tree(NodeStatus.PROVEN),
            compile_report=_report(status="success_with_sorry"),
            legality_report=_legal(), legality_checked=True,
        )
        assert label == CitationLabel.PARTIALLY_FORMALIZED
        assert reason == "file_sorry"

    def test_file_level_sorry_warning_is_partially_formalized(self):
        report = _report()
        report.sorry_warnings = ["Main.lean:3:8: warning: declaration uses 'sorry'"]
        label, reason = _decide(
            proof_tree=_tree(NodeStatus.PROVEN), compile_report=report,
            legality_report=_legal(), legality_checked=True,
        )
        assert label == CitationLabel.PARTIALLY_FORMALIZED
        assert reason == "file_sorry"

    def test_custom_axiom_is_partially_formalized(self):
        label, reason = _decide(
            proof_tree=_tree(NodeStatus.PROVEN),
            compile_report=_report(axioms=["propext", "MyAxiom"],
                                   axiom_check="failed"),
            legality_report=_legal(), legality_checked=True,
        )
        assert label == CitationLabel.PARTIALLY_FORMALIZED
        assert reason == "axioms_not_clean"

    def test_axiom_check_skipped_is_partially_formalized(self):
        label, reason = _decide(
            proof_tree=_tree(NodeStatus.PROVEN),
            compile_report=_report(axiom_check="skipped"),
            legality_report=_legal(), legality_checked=True,
        )
        assert label == CitationLabel.PARTIALLY_FORMALIZED
        assert reason == "axiom_check_skipped"

    def test_legacy_evidence_incomplete_is_partially_formalized(self):
        label, reason = _decide(
            proof_tree=_tree(NodeStatus.PROVEN),
            compile_report=_report(evidence_complete=False),
            legality_report=_legal(), legality_checked=True,
        )
        assert label == CitationLabel.PARTIALLY_FORMALIZED
        assert reason == "evidence_incomplete"

    def test_tree_sorry_is_partially_formalized(self):
        label, reason = _decide(
            proof_tree=_tree(NodeStatus.PROVEN, proven=1, sorry=2),
            compile_report=_report(), legality_report=_legal(),
            legality_checked=True,
        )
        assert label == CitationLabel.PARTIALLY_FORMALIZED
        assert reason == "tree_partial"

    def test_tree_blocked_with_proven_root_is_partially_formalized(self):
        label, reason = _decide(
            proof_tree=_tree(NodeStatus.PROVEN, proven=2, blocked=1),
            compile_report=_report(), legality_report=_legal(),
            legality_checked=True,
        )
        assert label == CitationLabel.PARTIALLY_FORMALIZED
        assert reason == "tree_partial"

    def test_legality_not_checked_is_partially_formalized(self):
        label, reason = _decide(
            proof_tree=_tree(NodeStatus.PROVEN), compile_report=_report(),
            legality_report=None, legality_checked=False,
        )
        assert label == CitationLabel.PARTIALLY_FORMALIZED
        assert reason == "legality_not_checked"

    def test_legality_failed_is_partially_formalized(self):
        label, reason = _decide(
            proof_tree=_tree(NodeStatus.PROVEN), compile_report=_report(),
            legality_report=_legal(False), legality_checked=True,
        )
        assert label == CitationLabel.PARTIALLY_FORMALIZED
        assert reason == "legality_failed"


class TestUpstreamPrecedence:
    def test_numerical_failure_is_falsified(self):
        label, _ = _decide(
            numerical_failed=True,
            proof_tree=_tree(NodeStatus.PROVEN), compile_report=_report(),
            legality_report=_legal(), legality_checked=True,
        )
        assert label == CitationLabel.FALSIFIED

    def test_latex_failure_is_failed(self):
        label, _ = _decide(latex_ok=False, numerical_passed=True)
        assert label == CitationLabel.FAILED


class TestDownstreamReadyGate:
    def test_legacy_formal_labels_blocked_but_numeric_allowed(self):
        from researchclaw.vendor.auto_prover.kg.i2_extractor import _is_ready

        base = {"assertion": "x", "lean_code": "c"}
        assert _is_ready({**base, "citation_label": "formally_verified"}) is False
        assert _is_ready({**base, "citation_label": "partially_formalized"}) is False
        assert _is_ready({**base, "citation_label": "numerically_verified"}) is True
        assert _is_ready({**base, "citation_label": "formally_verified",
                          "policy_version": 2}) is True


class TestWriterEvidence:
    def test_writer_records_policy_and_evidence(self, tmp_path):
        from researchclaw.vendor.auto_prover.kg.verdict_writer import VerdictWriter

        v = AssertionVerdict(
            assertion="w1 writer", citation_label=CitationLabel.NUMERICALLY_VERIFIED,
            stopped_at=StopStage.STAGE2, policy_version=POLICY_VERSION,
            verdict_reason="all_gates_passed",
            verdict_evidence={"compile": {"status": "success"}},
        )
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(VerdictWriter(str(tmp_path)).write(v))
        finally:
            loop.close()
        rec = json.loads(next(tmp_path.glob("verdicts_*.jsonl")).read_text(
            encoding="utf-8").strip())
        assert rec["policy_version"] == 2
        assert rec["verdict_reason"] == "all_gates_passed"
        assert rec["verdict_evidence"]["compile"]["status"] == "success"
