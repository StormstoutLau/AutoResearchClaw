"""数据类型 — 假设挖掘与前提条件"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time

# 假设挖掘 (Hypothesis Mining) — 主动发现论文中隐含的未声明假设
# ============================================================================

class HypothesisClass(Enum):
    """假设分类"""
    EXPLICIT = "explicit"          # 论文中明确声明的假设
    IMPLICIT = "implicit"          # 隐含的、未声明的假设（被挖掘发现）
    STRONG = "strong"              # 强假设（限制性强，如正态分布）
    WEAK = "weak"                  # 弱假设（易满足，如有限二阶矩）
    VERIFIABLE = "verifiable"      # 可通过数据验证的假设
    UNVERIFIABLE = "unverifiable"  # 无法验证的假设（如"市场有效"）
    CONTROVERSIAL = "controversial" # 有争议的假设（文献中意见不一致）

@dataclass
class HypothesisProfile:
    """单个假设的完整画像"""
    statement: str                          # 假设内容
    hypothesis_class: HypothesisClass       # 分类
    source: str = ""                        # 来源：explicit_in_paper / mined_by_llm / kg_inferred
    confidence: float = 0.0                 # 假设成立的置信度 (0.0~1.0)
    kg_standardized: bool = False           # 是否在 KG 中有标准定义
    kg_node_name: str = ""                  # KG 中对应的概念节点
    dependent_theorems: list[str] = field(default_factory=list)  # 依赖此假设的定理
    counterexample_risk: float = 0.0        # 此假设被违反时断言失效的风险 (0.0~1.0)
    mining_llm: str = ""                    # 哪个 LLM 发现了这个假设

@dataclass
class HypothesisMiningResult:
    """假设挖掘的完整结果"""
    profiles: list[HypothesisProfile] = field(default_factory=list)
    total_explicit: int = 0
    total_implicit: int = 0
    total_strong: int = 0
    total_weak: int = 0
    total_controversial: int = 0
    risk_score: float = 0.0                 # 综合风险评分：假设越多越强，风险越高
    mining_iterations: int = 0
    llm_agreement: float = 0.0              # 多 LLM 对隐含假设的一致性


# ============================================================================
# 前提条件复杂性分析 (Precondition Complexity Analysis)
# ============================================================================

@dataclass
class ComplexityScore:
    """前提条件复杂性评分"""
    hypothesis_count: int = 0               # 前提条件数量
    implicit_ratio: float = 0.0             # 隐含假设占比
    strong_ratio: float = 0.0               # 强假设占比
    unverifiable_ratio: float = 0.0         # 不可验证假设占比
    kg_coverage: float = 0.0                # KG 覆盖率（标准定义的比例）
    dependency_depth: int = 0               # 依赖链最大深度
    external_dependency_count: int = 0      # 外部（非 KG）依赖数量
    overall_score: float = 0.0              # 综合复杂度 (0.0~1.0, 越高越复杂)
    risk_level: str = "low"                 # "low" | "medium" | "high" | "critical"

@dataclass
class PreconditionAnalysis:
    """前提条件复杂性分析报告"""
    complexity: ComplexityScore = field(default_factory=ComplexityScore)
    weakest_link: str = ""                  # 最脆弱的前提条件
    missing_from_kg: list[str] = field(default_factory=list)  # KG 中缺失的定义
    suggested_verification: list[str] = field(default_factory=list)  # 建议的验证方法
    paper_ready_statement: str = ""         # 论文中可直接使用的复杂度说明
