"""数据类型 — Lean4 翻译与证明草图"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time

# Stage 3: LaTeX → Lean4 翻译 + 形式化证明
# ============================================================================

class Lean4TranslationStatus(Enum):
    SUCCESS = "success"
    TYPE_ERROR = "type_error"
    PARSE_ERROR = "parse_error"   # D105: 解析/语法错误（与类型错误分开）
    SEMANTIC_DRIFT = "semantic_drift"
    MATHLIB_CONFLICT = "mathlib_conflict"
    MAX_RETRIES = "max_retries"
    IDENTITY_FAILED = "identity_failed"   # 注入点 D: Mathematica 验证恒等式失败

@dataclass
class Lean4TranslationResult:
    """Stage 3 前半部分输出：LaTeX → Lean4 翻译结果"""
    lean_statement: str
    theorem_name: str
    type_check_passed: bool
    status: Lean4TranslationStatus

    # DeepSeek-Prover style 质量检查
    back_translation: Optional[str] = None
    semantic_similarity: Optional[float] = None
    custom_definitions: list[str] = field(default_factory=list)
    mathlib_references: list[str] = field(default_factory=list)

    # 迭代信息
    iterations: int = 0
    candidates: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # D104 / B-49: 失败门分类（"compile" / "semantic" / "mathlib"）。
    # 成功或其他状态为空串；与 status 互补，便于日志/metrics 精确归因。
    error_class: str = ""


# ============================================================================
# 兼容别名 (旧代码迁移)
# ============================================================================

# 保持向后兼容
FormalizationStatus = Lean4TranslationStatus
FormalizationResult = Lean4TranslationResult


# ============================================================================
# Stage 1.5: Proof Sketching (LongCat)
# ============================================================================

@dataclass
class ProofSketchStep:
    """证明草图中的一个步骤"""
    index: int
    description: str                # 自然语言描述
    tactic_hint: str                # 提示 tactic
    key_lemmas: list[str] = field(default_factory=list)
    subgoal_after: Optional[str] = None

@dataclass
class ProofSketch:
    """Stage 1.5 输出：LongCat 风格的结构化证明草图"""
    theorem_name: str
    approach: str                   # "induction", "epsilon-delta", "contradiction", ...
    steps: list[ProofSketchStep] = field(default_factory=list)
    estimated_total_steps: int = 0
    critical_path: list[int] = field(default_factory=list)
    fallback_approaches: list[str] = field(default_factory=list)
