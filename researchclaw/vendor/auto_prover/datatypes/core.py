"""数据类型 — 输入/上下文/停止点"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time

# ============================================================================
# 流水线停止点
# ============================================================================

class StopStage(Enum):
    """流水线在哪个阶段停止

    三阶段: LaTeX形式化 → 数值验证 → Lean4严格验证
    """
    STAGE1 = "stage1"          # LaTeX 形式化后停止（多 LLM 验证 + 依赖检查）
    STAGE2 = "stage2"          # 数值验证后停止（快速证伪，先用起来）
    STAGE3 = "stage3"          # Lean4 翻译 + 形式化证明后停止（核心路径通过，允许 sorry）
    STAGE3_5 = "stage3_5"      # 合法性检测后停止（论文级完整验证）

class CitationLabel(Enum):
    """论文引用标注"""
    FORMALLY_VERIFIED = "formally_verified"        # Lean4 编译通过，核心路径无 sorry
    PARTIALLY_FORMALIZED = "partially_formalized"   # 核心路径通过，部分 sorry
    NUMERICALLY_VERIFIED = "numerically_verified"    # 数值验证通过
    LATEX_VERIFIED = "latex_verified"               # LaTeX 形式化通过（多 LLM 共识 + 依赖无错误）
    FALSIFIED = "falsified"                          # 数值验证发现反例
    FAILED = "failed"                                # LaTeX 形式化失败


# W1 / B-52: 判定策略版本。旧 JSONL 记录缺该字段 ⇒ 视为 1。
CURRENT_POLICY_VERSION = 2



# ============================================================================
# 输入
# ============================================================================

@dataclass
class TheoremInput:
    """用户输入的自然语言断言（论文或教材中的声明）

    latex 字段可选：如果用户已有 LaTeX 版本则提供，否则由 Stage 1 生成。
    """
    nl_statement: str              # "设 X₁,...,Xₙ 为 i.i.d. 样本，则样本均值依概率收敛到期望"
    latex: str = ""                # 可选：已有的 LaTeX 版本，空则由 Stage 1 生成
    source_textbook: str = ""      # "Jun Shao, Ch5" 或论文引用
    hypotheses: list[str] = field(default_factory=list)  # ["i.i.d.", "E|X₁| < ∞"]
    tier: str = "core"             # "core" | "supporting" | "utility"

    # 论文断言特有字段
    source_paper: str = ""         # 论文标题/arXiv ID
    known_truth: Optional[bool] = None  # None=未知, True=已知为真, False=已知为假
    paper_section: str = ""        # 论文中的章节位置
    referenced_papers: list[str] = field(default_factory=list)  # 依赖的参考文献


# ============================================================================
# Stage 0: 知识检索
# ============================================================================

@dataclass
class AtlasStructure:
    """ATLAS 数学框架中的结构定义"""
    name: str
    kind: str                       # "group", "ring", "measure_space", "probability_space" ...
    properties: list[str] = field(default_factory=list)
    mathlib_path: Optional[str] = None

@dataclass
class CaseRecord:
    r"""proof_pipeline 侧的证明案例镜像 (对应 D:\Textbook Lean4Case)

    字段对齐 Lean4Case.to_dict() 输出: id/kind/statement/code
    (lean4_case_library.py:215-253, search_similar 返回 List[Dict])

    Phase 5b-A1 (O1 方案 B): 与 AtlasStructure 分离,避免类型污染
    """
    case_id: str                    # Lean4Case.id
    kind: str                       # "theorem" / "definition" / "lemma"
    statement: str                  # NL 数学命题 (可能为空)
    code: str                       # Lean4 代码
    source: str = "textbook_lean4_cases"  # 数据来源标识

@dataclass
class KGConcept:
    r"""D:\Textbook 知识图谱中的概念节点"""
    name: str
    textbook_ref: str               # "Jun Shao, Ch5.2"
    dependencies: list[str] = field(default_factory=list)
    mathlib_mapping: Optional[str] = None
    statement_latex: str = ""
    layer: str = "core"             # "core" | "supporting" | "utility"

@dataclass
class MathlibLemma:
    """mathlib4 检索到的引理"""
    name: str
    statement: str                  # Lean4 类型签名
    path: str                       # mathlib 文件路径
    relevance_score: float          # 0.0 ~ 1.0
    usage_count: int = 0            # 在 mathlib 中被引用的次数
    proof_body: Optional[str] = None  # 完整证明体（压缩模式下为 None）

@dataclass
class ContextBundle:
    """Stage 0 输出：组装后的知识上下文"""
    atlas_structures: list[AtlasStructure] = field(default_factory=list)
    kg_concepts: list[KGConcept] = field(default_factory=list)
    mathlib_lemmas: list[MathlibLemma] = field(default_factory=list)
    cases: list[CaseRecord] = field(default_factory=list)  # Phase 5b-A1 新增, 向后兼容
    compressed: bool = False
    compressed_token_count: int = 0
    raw_token_count: int = 0

    def top_lemmas(self, k: int = 5) -> list[MathlibLemma]:
        return sorted(self.mathlib_lemmas, key=lambda x: x.relevance_score, reverse=True)[:k]
