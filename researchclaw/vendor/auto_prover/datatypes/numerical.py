"""数据类型 — 数值验证/断言/可复现构件"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time

from .retrieval import DependencyCheck, DependencyGraph, LaTeXStatus
from .hypothesis import HypothesisMiningResult, PreconditionAnalysis

# ============================================================================

@dataclass
class CounterExample:
    """系统化搜索发现的反例"""
    params: dict                            # 使断言失效的参数组合
    expected: float                         # 断言预测值
    actual: float                           # 实际计算值
    deviation: float                        # 偏差 = |actual - expected|
    relative_deviation: float = 0.0         # 相对偏差
    search_method: str = ""                 # "llm_sampling" | "optimization" | "smt" | "grid_search"
    is_minimal: bool = False                # 是否是最小反例
    minimality_evidence: str = ""           # 最小性证明说明
    precondition_violated: str = ""         # 哪个前提条件被违反
    discovery_iteration: int = 0

@dataclass
class CounterExampleSearchResult:
    """反例搜索的完整结果"""
    counterexamples: list[CounterExample] = field(default_factory=list)
    total_searched: int = 0                 # 总搜索次数
    search_methods_used: list[str] = field(default_factory=list)
    minimal_counterexample: Optional[CounterExample] = None
    falsification_confidence: float = 0.0   # 证伪置信度（发现反例后）
    search_time_seconds: float = 0.0
    # B-34 (D047): boundary_search 调用的**传输归因** (原始事实, 供离线复算)
    #   来源: ModelResponse.finish_reason / reasoning_chars / diagnosis (D045/B-32)
    #   ⚠ 口径隔离: 与语义字段正交; ⚠ O-A (D040): 不参与任何判定。
    #   未走 boundary 分支 (有 failed_cases / 有符号反例) ⇒ 保持默认。
    boundary_search_finish_reason: Optional[str] = None
    boundary_search_reasoning_chars: int = 0
    boundary_search_diagnosis: Optional[str] = None
    # W4/B-57 (D129, D5): 本次搜索实际使用的种子（None = 未播种/未走搜索）
    search_seed: Optional[int] = None


@dataclass
class LaTeXAssertion:
    """Stage 1 输出：多 LLM 验证后的 LaTeX 数学断言

    多个 LLM 独立将 NL 断言翻译为 LaTeX，交叉验证后选最优。
    依赖检查确保所有符号有定义，所有前提条件被显式列出。
    """
    latex_statement: str               # 最终 LaTeX 语句
    candidates: list[str] = field(default_factory=list)        # 所有 LLM 的候选翻译
    consensus_score: float = 0.0       # 多 LLM 共识度 (0.0~1.0)
    status: LaTeXStatus = LaTeXStatus.SUCCESS

    # 依赖检查
    dependency_check: Optional[DependencyCheck] = None

    # 提取的结构化信息
    extracted_hypotheses: list[str] = field(default_factory=list)  # 从 LaTeX 中提取的前提
    extracted_conclusion: str = ""                                  # 从 LaTeX 中提取的结论

    # 知识检索结果
    knowledge_sources: list[str] = field(default_factory=list)     # 检索到的知识源
    kg_nodes_used: list[str] = field(default_factory=list)         # 使用的 KG 节点

    # 迭代信息
    iterations: int = 0
    errors: list[str] = field(default_factory=list)
    llm_names_used: list[str] = field(default_factory=list)        # 参与验证的 LLM 名称

    # 注意事项
    hallucination_warning: str = ""    # 无法完全排除 LLM 幻觉的警告

    # 新增: 假设挖掘 + 前提条件分析 + 依赖图
    hypothesis_mining: Optional[HypothesisMiningResult] = None
    precondition_analysis: Optional[PreconditionAnalysis] = None
    dependency_graph: Optional[DependencyGraph] = None
# Stage 2: 数值推论验证
# ============================================================================

class AssertionKind(Enum):
    """断言类别 (T4/D030: 由 generator 随用例声明, 判据侧**不得**事后推断)"""
    DETERMINISTIC_IDENTITY = "deterministic_identity"
    COMBINATORIAL = "combinatorial"
    EXPECTATION = "expectation"
    VARIANCE = "variance"
    MOMENT = "moment"
    DISTRIBUTIONAL = "distributional"
    ASYMPTOTIC = "asymptotic"


class Falsifiability(Enum):
    """Tier 1 证伪力探针输出 (T4/D030): 机械, 零 LLM, 可离线"""
    VARYING = "varying"      # 输出随数据变化 ⇒ 承载抽样证伪力
    CONSTANT = "constant"    # 输出与数据无关 (恒等检查 / 退化抽样 / 确定性表达式)
    UNKNOWN = "unknown"      # 探针不可用 (无 computed_expr / 执行异常)


class SemanticVerdict(Enum):
    """Tier 2 类别 × 证伪力 判定输出 (T4/D030): 静态表, 零 LLM"""
    VALID_DETERMINISTIC = "valid_deterministic"  # 组合/恒等断言下的确定性表达式 ⇒ 合法
    CIRCULAR = "circular"                        # 统计断言下的恒等检查 ⇒ 无效用例
    UNKNOWN = "unknown"                          # kind 缺失/非法 或 探针不可用 ⇒ 降级


@dataclass
class TestCase:
    """数值测试用例"""
    params: dict                    # {"n": 100, "mu": 0, "sigma": 1}
    expected: float
    actual: float
    tolerance: float
    passed: bool
    computed_expr: Optional[str] = None  # 计算表达式, 由 LLM 生成
    error_message: Optional[str] = None
    # B-17/B-18 (D026): computed 的**标准误** (估计量的标准差), 由 LLM 声明。
    # 用途: 判定新增统计分支 tolerance_stat = std_err_k × std_err。
    # 为什么需要: ① 相对容差在 expected=0 处**结构性失效** (任意偏差对 0 都是 100%);
    #   ② 蒙特卡洛噪声随 σ/√N 变化, 固定的绝对/相对容差不是统计检验。
    std_err: Optional[float] = None
    # D029 (U-16/B-25): 退化用例标记 —— 由 _run_test_cases 执行后置位, 判据见
    # stage2_numerical.is_degenerate (判定与监控**共用同一口径**)。
    # 定义: 执行无错 ∧ 偏差恰为 0 ∧ 未声明正的标准误
    #   ⇒ computed 的输出与数据无关 (恒等检查或退化抽样) ⇒ **不承载证伪力**。
    # 用途: 让这类用例在报告与校准闸门中**可见**。此前 assess_std_err_calibration
    #   对 std_err<=0 直接 continue ⇒ 退化用例对闸门完全不可见, 存在"用退化用例
    #   抬高 pass_rate"的盲区 (U-16/B-25)。
    # ⚠ **不改变判定语义**: pass_rate / verdict 仍照原口径, 本字段只增可见性。
    degenerate: bool = False
    # T4/D030 (D040): 语义级判定 —— 断言类别 (generator 声明; 缺失 ⇒ 降级不判)。
    kind: Optional[str] = None
    # 以下两字段由 semantic_verdict.judge_test_case 在执行后置位 (同 degenerate 范式)
    falsifiability: Optional[str] = None     # Falsifiability.value
    semantic_verdict: Optional[str] = None   # SemanticVerdict.value
    # ⚠ 同样**不改变判定语义** (O-A): pass_rate / verdict 不消费本字段。
    # W4/B-57 (D129, D2/D6): 种子与证据来源可见性（均为附加字段, 默认值 ⇒ 旧构造零改动）
    #   seed: 用例实际使用的种子（LLM 声明或本仓注入; None = 未经过注入点）
    #   seed_source: "llm" | "injected" | ""（旧式构造）
    #   evidence_source: "llm_declared" | "recomputed" | "machine_checked"
    # ⚠ O-A: 三字段均**不参与** pass_rate / verdict。
    seed: Optional[int] = None
    seed_source: str = ""
    evidence_source: str = "llm_declared"


class NumericalVerdict(Enum):
    PASSED = "passed"
    PARTIAL = "partial"
    FAILED = "failed"

@dataclass
class NumericalVerification:
    """Stage 2 输出"""
    test_cases: list[TestCase] = field(default_factory=list)
    pass_rate: float = 0.0
    verdict: NumericalVerdict = NumericalVerdict.FAILED
    failure_analysis: str = ""
    # 新增: 系统化反例搜索
    counterexample_search: Optional[CounterExampleSearchResult] = None
    # T4/D030 (D040): 语义级判定**可见性**汇总 (不参与 verdict / pass_rate, 见 O-A)
    n_circular: int = 0
    semantic_review_flags: list[str] = field(default_factory=list)
    # B-33 (D046): Stage2 生产可见性 —— testgen 调用的**传输归因** (原始事实, 供离线复算)
    #   来源: ModelResponse.finish_reason / reasoning_chars / diagnosis (D045/B-32)
    #   ⚠ 口径隔离: 与 semantic_review_flags (**语义**) 正交, 非同族 —— 不写入该字段
    #     (B-23/B-24/D034 的"口径混淆"缺陷族)。
    #   ⚠ O-A (D040): 在 verdict / pass_rate 定值**之后**写入 ⇒ 不参与判定。
    testgen_finish_reason: Optional[str] = None   # 引擎原样; 不可得 ⇒ None
    testgen_reasoning_chars: int = 0              # message.reasoning_content 字符数; 不可得 ⇒ 0
    testgen_diagnosis: Optional[str] = None       # 归因标签; 正常/未知 ⇒ None
    # W4/B-57 (D129, D6/D7): 证据来源聚合 + 数值侧 review flags
    #   ⚠ 口径隔离 (D046/D047): 数值 flags **不写入** semantic_review_flags。
    #   ⚠ O-A (D040): 在 verdict / pass_rate 定值**之后**写入 ⇒ 不参与判定。
    evidence_source_counts: dict[str, int] = field(default_factory=dict)
    numerical_review_flags: list[str] = field(default_factory=list)
    # W5/B-57 S-c (D135, D1/D7): expected 独立复算的**汇总可见性**（§4.5 形状）。
    #   ⚠ O-A (D040): 在 verdict / pass_rate 定值之后写入 ⇒ 不参与判定。
    #   ⚠ 只做可见性: 不改 passed / evidence_source (D-W5-4 / D9)。
    oracle_summary: dict = field(default_factory=dict)


@dataclass
class NumericalArtifact:
    """机读数值构件 (T4/D040: 阶段 II 跨机交换契约; 本轮只定义 + 序列化原语)

    交付物 = **可执行构件** + **执行证据** (D024 结论: 迁移把失败面从"格式合规"移到"判据质量")。
    ⚠ ASCII 安全由调用方 `json.dumps(..., ensure_ascii=True)` 保证 (D027)。
    """
    params: dict
    expected: float
    computed_expr: str
    tolerance: float
    kind: Optional[str] = None
    std_err: Optional[float] = None
    # 执行证据 (回填)
    actual: Optional[float] = None
    passed: Optional[bool] = None
    error_message: Optional[str] = None
    falsifiability: Optional[str] = None
    semantic_verdict: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "params": self.params,
            "expected": self.expected,
            "computed_expr": self.computed_expr,
            "tolerance": self.tolerance,
            "kind": self.kind,
            "std_err": self.std_err,
            "actual": self.actual,
            "passed": self.passed,
            "error_message": self.error_message,
            "falsifiability": self.falsifiability,
            "semantic_verdict": self.semantic_verdict,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "NumericalArtifact":
        return cls(
            params=d["params"],
            expected=d["expected"],
            computed_expr=d["computed_expr"],
            tolerance=d["tolerance"],
            kind=d.get("kind"),
            std_err=d.get("std_err"),
            actual=d.get("actual"),
            passed=d.get("passed"),
            error_message=d.get("error_message"),
            falsifiability=d.get("falsifiability"),
            semantic_verdict=d.get("semantic_verdict"),
        )

    @classmethod
    def from_test_case(cls, tc: "TestCase") -> "NumericalArtifact":
        return cls(
            params=tc.params,
            expected=tc.expected,
            computed_expr=tc.computed_expr or "",
            tolerance=tc.tolerance,
            kind=tc.kind,
            std_err=tc.std_err,
            actual=tc.actual,
            passed=tc.passed,
            error_message=tc.error_message,
            falsifiability=tc.falsifiability,
            semantic_verdict=tc.semantic_verdict,
        )
