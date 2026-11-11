"""数值验证核心纯函数（W12 / B-58 拆分自 `stage2_numerical.py`）。

容差口径 / 退化判定 / 可复现随机判定 —— 判定与校准共用，**不含任何 I/O**。
"""

from __future__ import annotations
import asyncio
import math
import random
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from ..datatypes import (
    TheoremInput, LaTeXAssertion, NumericalVerification,
    TestCase, NumericalVerdict,
    CounterExample, CounterExampleSearchResult,
    AssertionKind, SemanticVerdict,
)
from ..semantic_verdict import judge_test_case
from ..model_gateway import ModelGateway
from ..sandbox import (
    DEFAULT_BATCH_BUDGET_S,
    DEFAULT_MEMORY_LIMIT_MB,
    DEFAULT_SEARCH_BUDGET_S,
    DEFAULT_TIMEOUT_S,
    SafeEvaluator,
)
# W5/B-57 S-c (D135): expected 独立复算（纯函数模块；只产出可见性）。
from .numerical_oracle import check_case as _oracle_check_case
from .numerical_oracle import flags as _oracle_flags
from .numerical_oracle import summarize as _oracle_summarize



# T4/D030 (D040): 合法的断言类别集合 (用于解析校验; 缺失/非法 ⇒ 降级)
_VALID_KINDS = frozenset(k.value for k in AssertionKind)

# W4/B-57 (D129, D3/D4): 可复现随机 —— 本仓注入的默认用例种子与反例搜索种子。
#   ⚠ 默认常量而非 config 字段 (D13): 不新增 PipelineConfig 字段, 回退靠 git revert。
DEFAULT_CASE_SEED = 0
COUNTEREXAMPLE_SEARCH_SEED = 0




def effective_tolerance(expected: float, actual: float, tolerance: float,
                        std_err: float | None = None,
                        rel_tolerance_floor: float = 0.0,
                        std_err_k: float = 0.0) -> float:
    """统一容差口径 (D025 方案 C + D026 统计分支)。

    `max(tolerance, rel_floor × max(|expected|, |actual|), std_err_k × std_err)`

    为什么抽成函数: 判定 (`_run_test_cases`) 与校准监控
    (`assess_std_err_calibration`, B-19/B-20 的放大倍数) **必须同一口径**,
    否则监控到的带宽与真实带宽不一致 ⇒ 闸门失真。
    """
    eff = tolerance
    if rel_tolerance_floor > 0.0:
        eff = max(eff, rel_tolerance_floor * max(abs(expected), abs(actual)))
    if std_err_k > 0.0 and std_err is not None and std_err > 0.0:
        eff = max(eff, std_err_k * std_err)
    return eff


def is_degenerate(expected: float, actual: float, std_err: float | None,
                  error_message: str | None = None) -> bool:
    """退化用例判据 (D029 / U-16 / B-25)。

    退化 = 执行无错 ∧ 偏差**恰为** 0 ∧ 未声明正的标准误
      ⇒ computed 的输出与数据无关 ⇒ 用例**不承载证伪力**
      (形态有二: 确定性恒等, 如 ``np.mean(np.full(n, mu))``;
        或退化抽样, 如 ``scale=0`` 的正态 —— 后者声明 std_err=0 是**正确**的)。

    为什么抽成函数: 判定 (`_run_test_cases` 置位) 与监控
    (`assess_std_err_calibration` 计数) **必须同一口径** —— 同 `effective_tolerance`
    的理由, 否则"报告的退化数与真实的退化数"不一致 ⇒ 可见性失真。

    ⚠ 本判据**只测"是否依赖数据", 不判"该不该依赖数据"**。后者取决于断言类别
    (组合断言下确定性表达式是唯一正确形态; 统计断言下同样形态才是恒等检查),
    属语义级判定, 归 B-12 harness 侧 (见 DECISIONS D030)。
    """
    if error_message:
        return False
    if std_err is not None and std_err > 0.0:
        return False
    return actual == expected


def has_random_source(computed_expr: str | None) -> bool:
    """computed_expr 是否含随机源 (D029)。

    用于把退化用例**二分**, 便于归因与审计:
      含随机源 ⇒ 退化抽样 (如 ``scale=0``); 不含 ⇒ 确定性恒等 (如 ``np.full``)。
    仅做字符串判定, 是**计数维度**而非合规判定 (合规归 B-12)。
    """
    if not computed_expr:
        return False
    return ("np.random" in computed_expr) or ("default_rng" in computed_expr)


def is_degenerate_dependent(
    passed: Sequence[bool],
    degenerate: Sequence[bool],
    pass_threshold: float,
) -> bool:
    """「剔除退化用例 ⇒ 该轮 verdict 不再 PASSED」= 判定依赖退化用例 (T6/B-26)。

    退化用例恒 `passed` (dev==0 ∧ std_err≤0 ⇒ ``|Δ|=0 ≤ 容差带``) ⇒ 它**总在分子里**，
    因而抬高 `pass_rate`。本判据问的是: 若把退化用例移出分子/分母，
    `pass_rate` 是否**跌破阈值**? 是 ⇒ 该轮 PASSED **依赖不承载证伪力的用例**。

    这是 B-26「退化占比」升级路径的**第一原理锚**: 复用既有 `pass_threshold`，
    **零新常量**（避开 D029(c) 否决的"经验阈值"）；并把 D029 的"0/40 轮翻转"依据
    泛化为**可判定的检测器**，而非事后统计。

    ⚠ 边界 (诚实): 只覆盖"退化对判定有**决定作用**"的形态；对"退化很多但未翻转"
      不报警（占比而不决定）。且本判据**不改** verdict/pass_rate (O-A 兼容)。

    边界语义:
      - 空输入 ⇒ False
      - 无退化用例 (n_deg==0) ⇒ False (退化不决定)
      - 本就未达阈值 ⇒ False (退化不决定"通过")
      - 全退化 (n_nondeg==0) 且达阈值 ⇒ True (判定完全无证伪力)
    """
    n_total = len(passed)
    if n_total == 0:
        return False
    n_deg = sum(1 for d in degenerate if d)
    if n_deg == 0:
        return False
    if sum(1 for p in passed if p) / n_total < pass_threshold:
        return False                       # 未 PASSED ⇒ 退化不决定
    n_nondeg = n_total - n_deg
    if n_nondeg == 0:
        return True                        # 全退化 ⇒ 判定完全无证伪力
    n_pass_nondeg = sum(1 for p, d in zip(passed, degenerate) if p and not d)
    return (n_pass_nondeg / n_nondeg) < pass_threshold
