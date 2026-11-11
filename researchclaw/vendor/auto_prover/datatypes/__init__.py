"""数据类型包 — 逐名再导出 `proof_pipeline.datatypes` 的公开 API。

本包由 `datatypes.py` 拆分而来（W12 / B-58）；导入路径不变。
"""

from __future__ import annotations

from .core import (
    StopStage,
    CitationLabel,
    CURRENT_POLICY_VERSION,
    TheoremInput,
    AtlasStructure,
    CaseRecord,
    KGConcept,
    MathlibLemma,
    ContextBundle,
)

from .retrieval import (
    LaTeXStatus,
    DependencyCheck,
    DependencyNode,
    DependencyGraph,
)

from .hypothesis import (
    HypothesisClass,
    HypothesisProfile,
    HypothesisMiningResult,
    ComplexityScore,
    PreconditionAnalysis,
)

from .numerical import (
    CounterExample,
    CounterExampleSearchResult,
    LaTeXAssertion,
    AssertionKind,
    Falsifiability,
    SemanticVerdict,
    TestCase,
    NumericalVerdict,
    NumericalVerification,
    NumericalArtifact,
)

from .translation import (
    Lean4TranslationStatus,
    Lean4TranslationResult,
    FormalizationStatus,
    FormalizationResult,
    ProofSketchStep,
    ProofSketch,
)

from .proof import (
    NodeStatus,
    ErrorType,
    ProofNode,
    ProofTree,
    BeamCandidate,
    BeamSearchState,
    LegalityCheckResult,
    LegalityReport,
    ModelCallRecord,
)

from .config import (
    PipelineConfig,
    CompileReport,
)

from .result import (
    VerifiedProof,
    PaperReady,
    AssertionVerdict,
    PipelineResult,
)

__all__ = [
    "StopStage",
    "CitationLabel",
    "CURRENT_POLICY_VERSION",
    "TheoremInput",
    "AtlasStructure",
    "CaseRecord",
    "KGConcept",
    "MathlibLemma",
    "ContextBundle",
    "LaTeXStatus",
    "DependencyCheck",
    "DependencyNode",
    "DependencyGraph",
    "HypothesisClass",
    "HypothesisProfile",
    "HypothesisMiningResult",
    "ComplexityScore",
    "PreconditionAnalysis",
    "CounterExample",
    "CounterExampleSearchResult",
    "LaTeXAssertion",
    "AssertionKind",
    "Falsifiability",
    "SemanticVerdict",
    "TestCase",
    "NumericalVerdict",
    "NumericalVerification",
    "NumericalArtifact",
    "Lean4TranslationStatus",
    "Lean4TranslationResult",
    "FormalizationStatus",
    "FormalizationResult",
    "ProofSketchStep",
    "ProofSketch",
    "NodeStatus",
    "ErrorType",
    "ProofNode",
    "ProofTree",
    "BeamCandidate",
    "BeamSearchState",
    "LegalityCheckResult",
    "LegalityReport",
    "ModelCallRecord",
    "PipelineConfig",
    "CompileReport",
    "VerifiedProof",
    "PaperReady",
    "AssertionVerdict",
    "PipelineResult",
]
