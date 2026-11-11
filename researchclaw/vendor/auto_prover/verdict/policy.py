"""W1 / B-52: citation_label 的唯一判定出口（纯函数）。

依据 spec/verdict-evidence/DESIGN.md §1。规则:
  - FORMALLY_VERIFIED 只在形式核心成立 + 全部门槛通过时产生；
  - 形式核心 = 根节点 PROVEN 或 synthesis_verified；
  - 非核心门槛失败 ⇒ 最高 PARTIALLY_FORMALIZED；
  - 形式核心不成立 ⇒ 按数值/LaTeX 降级，不授正式标签。
"""
from __future__ import annotations

from dataclasses import dataclass

from ..datatypes import (
    CURRENT_POLICY_VERSION,
    CitationLabel,
    CompileReport,
    LegalityReport,
    NodeStatus,
    ProofTree,
)

POLICY_VERSION = CURRENT_POLICY_VERSION


@dataclass(frozen=True)
class VerdictEvidence:
    """判定所需的全部证据（由 pipeline 组装，policy 不做 I/O）。"""
    latex_ok: bool = False
    numerical_failed: bool = False
    numerical_passed: bool = False
    proof_tree: ProofTree | None = None
    compile_report: CompileReport | None = None
    legality_report: LegalityReport | None = None
    legality_checked: bool = False
    synthesis_verified: bool = False


def _fallback(ev: VerdictEvidence, reason: str) -> tuple[CitationLabel, str]:
    """形式标签不成立时的降级链：数值 > LaTeX > FAILED。"""
    if ev.numerical_passed:
        return CitationLabel.NUMERICALLY_VERIFIED, reason
    if ev.latex_ok:
        return CitationLabel.LATEX_VERIFIED, reason
    return CitationLabel.FAILED, reason


def decide_citation_label(
    ev: VerdictEvidence,
) -> tuple[CitationLabel, str]:
    """返回 (citation_label, reason_code)。纯函数，无副作用。"""
    if ev.numerical_failed:
        return CitationLabel.FALSIFIED, "stage2_counterexample"
    if not ev.latex_ok:
        return CitationLabel.FAILED, "stage1_not_success"

    tree = ev.proof_tree
    if tree is None:
        return _fallback(ev, "no_proof_tree")

    root_status = getattr(getattr(tree, "root", None), "status", None)
    formal_core = root_status == NodeStatus.PROVEN or ev.synthesis_verified
    if not formal_core:
        # 关键修复: 根未证不得授 FORMALLY/PARTIALLY（D108 P1）
        return _fallback(ev, "root_not_proven")

    if tree.sorry > 0 or tree.blocked > 0:
        return CitationLabel.PARTIALLY_FORMALIZED, "tree_partial"

    report = ev.compile_report
    if report is None or not report.success or report.status == "failed":
        return _fallback(ev, "compile_failed")
    if report.status == "success_with_sorry" or report.sorry_warnings:
        return CitationLabel.PARTIALLY_FORMALIZED, "file_sorry"
    if not report.evidence_complete:
        return CitationLabel.PARTIALLY_FORMALIZED, "evidence_incomplete"
    if report.axiom_check == "failed":
        return CitationLabel.PARTIALLY_FORMALIZED, "axioms_not_clean"
    if report.axiom_check != "passed":
        return CitationLabel.PARTIALLY_FORMALIZED, "axiom_check_skipped"

    if not ev.legality_checked or ev.legality_report is None:
        return CitationLabel.PARTIALLY_FORMALIZED, "legality_not_checked"
    if not ev.legality_report.overall_pass:
        return CitationLabel.PARTIALLY_FORMALIZED, "legality_failed"

    return CitationLabel.FORMALLY_VERIFIED, "all_gates_passed"
