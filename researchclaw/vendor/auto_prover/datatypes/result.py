"""数据类型 — 验证结果/论文片段/断言裁决"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time

from .core import CURRENT_POLICY_VERSION, CitationLabel, StopStage, TheoremInput
from .retrieval import DependencyGraph
from .hypothesis import HypothesisMiningResult, PreconditionAnalysis
from .numerical import LaTeXAssertion, NumericalVerification
from .translation import ProofSketch
from .proof import ProofTree
from .config import PipelineConfig

@dataclass
class VerifiedProof:
    """完整流水线输出"""
    theorem_name: str
    lean_code: str
    compile_status: str = "unknown"
    proof_tree: Optional[ProofTree] = None
    legality_report: Optional[LegalityReport] = None
    sketch: Optional[ProofSketch] = None
    latex_assertion: Optional[LaTeXAssertion] = None       # Stage 1 产物
    lean4_translation: Optional[Lean4TranslationResult] = None  # Stage 3 翻译产物
    numerical: Optional[NumericalVerification] = None
    total_time: float = 0.0
    stage_times: dict[str, float] = field(default_factory=dict)
    model_calls: list[ModelCallRecord] = field(default_factory=list)
    # 新增: 四个增强能力产物
    hypothesis_mining: Optional[HypothesisMiningResult] = None
    precondition_analysis: Optional[PreconditionAnalysis] = None
    dependency_graph: Optional[DependencyGraph] = None

    @property
    def formalization(self):
        """向后兼容：返回 lean4_translation"""
        return self.lean4_translation

    def summary(self) -> str:
        parts = [f"Theorem: {self.theorem_name}", f"Status: {self.compile_status}"]
        if self.proof_tree:
            parts.append(
                f"Proof Tree: {self.proof_tree.proven}/{self.proof_tree.total_subgoals} proven"
            )
            parts.append(f"Sorry: {self.proof_tree.sorry} (Tier 2/3)")
        if self.legality_report:
            parts.append(f"Legality: {'PASS' if self.legality_report.overall_pass else 'FAIL'}")
        parts.append(f"Time: {self.total_time:.1f}s")
        if self.stage_times:
            parts.append("Breakdown: " + ", ".join(
                f"{k}={v:.1f}s" for k, v in self.stage_times.items()
            ))
        return "\n".join(parts)


# ============================================================================
# 渐进式置信度判定 (核心创新)
# ============================================================================

@dataclass
class PaperReady:
    """论文中可直接引用的片段"""
    formal_statement: str = ""            # LaTeX 格式的定理陈述
    lean4_reference: str = ""             # "See Appendix B / github.com/..."
    numerical_evidence: str = ""          # "Verified by 10^4 Monte Carlo trials"
    open_conditions: list[str] = field(default_factory=list)   # 未解决的前提条件
    deferred_lemmas: list[str] = field(default_factory=list)    # 标记为 sorry 的引理
    proof_sketch: str = ""                # 证明思路（自然语言）

    def to_latex(self) -> str:
        """生成论文中可用的 LaTeX 片段"""
        parts = []
        if self.formal_statement:
            parts.append(self.formal_statement)
        if self.proof_sketch:
            parts.append(f"\\textit{{Proof sketch.}} {self.proof_sketch}")
        if self.numerical_evidence:
            parts.append(f"\\textbf{{Numerical verification.}} {self.numerical_evidence}")
        if self.lean4_reference:
            parts.append(f"\\textbf{{Formal verification.}} {self.lean4_reference}")
        if self.open_conditions:
            parts.append("\\textbf{Open conditions.} " + "; ".join(self.open_conditions))
        if self.deferred_lemmas:
            parts.append("\\textbf{Deferred lemmas.} " + "; ".join(self.deferred_lemmas))
        return "\n\n".join(parts)


@dataclass
class AssertionVerdict:
    """论文断言的渐进式置信度判定

    四层置信度:
      latex_confidence:       Stage 1 多 LLM 共识度 (0.0~1.0) — 无法完全排除幻觉
      numerical_confidence:  Stage 2 数值验证通过率 (0.0~1.0)
      formal_confidence:     Stage 3 核心路径证明率 (proven/total)
      complete_confidence:   所有 sorry 消除率 (1.0 - sorry/total)

    每个阶段通过后都可以停止，输出当前最高置信度的结果。
    """
    assertion: str

    # 四层置信度
    latex_confidence: float = 0.0       # 多 LLM LaTeX 共识度
    numerical_confidence: float = 0.0
    formal_confidence: float = 0.0
    complete_confidence: float = 0.0

    # 论文引用标注
    citation_label: CitationLabel = CitationLabel.FAILED

    # W1 / B-52: 判定策略版本与证据（旧 JSONL 缺 policy_version ⇒ 视为 1）
    policy_version: int = CURRENT_POLICY_VERSION
    verdict_reason: str = ""
    verdict_evidence: dict = field(default_factory=dict)

    # 产物
    latex_assertion: Optional[LaTeXAssertion] = None
    lean_code: Optional[str] = None
    numerical_results: Optional[NumericalVerification] = None
    proof_sketch: Optional[ProofSketch] = None
    proof_tree: Optional[ProofTree] = None

    # 新增: 四个增强能力
    hypothesis_mining: Optional[HypothesisMiningResult] = None
    precondition_analysis: Optional[PreconditionAnalysis] = None
    dependency_graph: Optional[DependencyGraph] = None

    # 论文可直接使用的片段
    paper_ready: PaperReady = field(default_factory=PaperReady)

    # 流水线停在哪个阶段
    stopped_at: StopStage = StopStage.STAGE1

    @property
    def overall_confidence(self) -> float:
        """综合置信度加权"""
        weights = {
            CitationLabel.FORMALLY_VERIFIED: 0.95,
            CitationLabel.PARTIALLY_FORMALIZED: 0.75,
            CitationLabel.NUMERICALLY_VERIFIED: 0.60,
            CitationLabel.LATEX_VERIFIED: 0.35,
            CitationLabel.FALSIFIED: 0.0,
            CitationLabel.FAILED: 0.0,
        }
        return weights.get(self.citation_label, 0.0)

    def is_ready_for_paper(self) -> bool:
        """是否达到论文可引用的最低标准（数值验证通过）"""
        return self.citation_label in (
            CitationLabel.NUMERICALLY_VERIFIED,
            CitationLabel.PARTIALLY_FORMALIZED,
            CitationLabel.FORMALLY_VERIFIED,
        )

    def summary(self) -> str:
        parts = [f"Assertion: {self.assertion[:60]}..."]
        parts.append(
            f"Confidence: latex={self.latex_confidence:.0%} "
            f"numerical={self.numerical_confidence:.0%} "
            f"formal={self.formal_confidence:.0%} "
            f"complete={self.complete_confidence:.0%}"
        )
        parts.append(f"Label: {self.citation_label.value}")
        parts.append(f"Stopped at: {self.stopped_at.value}")
        parts.append(f"Overall: {self.overall_confidence:.0%}")
        # 新增: 假设挖掘摘要
        if self.hypothesis_mining:
            hm = self.hypothesis_mining
            parts.append(
                f"Hypotheses: {hm.total_explicit} explicit + "
                f"{hm.total_implicit} implicit, risk={hm.risk_score:.0%}"
            )
        # 新增: 前提条件复杂度
        if self.precondition_analysis:
            pc = self.precondition_analysis.complexity
            parts.append(
                f"Precondition: complexity={pc.overall_score:.0%}, "
                f"risk={pc.risk_level}, depth={pc.dependency_depth}"
            )
        # 新增: 依赖图
        if self.dependency_graph:
            parts.append(self.dependency_graph.summary())
        return "\n".join(parts)


# ============================================================================
# 流水线结果
# ============================================================================

@dataclass
class PipelineResult:
    """流水线运行结果（包含中间状态和最终判定）"""
    config: PipelineConfig
    theorem_input: TheoremInput
    verified_proof: Optional[VerifiedProof] = None
    assertion_verdict: Optional[AssertionVerdict] = None
    error: Optional[str] = None
    blocked_stage: Optional[str] = None
    start_time: float = field(default_factory=time.time)

    def is_success(self) -> bool:
        return self.verified_proof is not None or (
            self.assertion_verdict is not None
            and self.assertion_verdict.is_ready_for_paper()
        )

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time
