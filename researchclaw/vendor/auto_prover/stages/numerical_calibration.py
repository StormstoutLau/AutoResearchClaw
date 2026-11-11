"""std_err 声明校准监控 + 带宽放大复核（W12 / B-58 拆分自 `stage2_numerical.py`）。

监控口径（非生产判定行为）：阈值不落 `PipelineConfig`（避免幽灵字段）。
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

from .numerical_core import (
    effective_tolerance,
    has_random_source,
    is_degenerate,
    is_degenerate_dependent,
)


# ============================================================================
# B-19 / B-20 (D026): std_err 声明校准监控 + 带宽放大复核标记
# ============================================================================
#
# 监控口径, 非生产行为, 故阈值**不落 PipelineConfig** —— 避免制造新的幽灵字段
# (项目元级 lint: 任何 PipelineConfig 字段必须有 ≥1 代码读取点)。
#
# 为什么需要 (D026 后果节): 启用统计分支后实测 PASSED = 100%, 通过率**饱和**,
# 不再能检出假阳性; 判定正确性全部押在 std_err 的诚实性上。故闸门从"通过率"
# 换为"校准指标"。z = (actual − expected) / std_err 在声明诚实时应服从 N(0, 1):
#   std(z) ≪ 1 ⇒ std_err 被系统性**高报** ⇒ 容差带被撑宽 = 制造通过 (最危险方向)
#   std(z) ≫ 1 ⇒ std_err **低报** ⇒ 统计分支过严 (假阴性方向, 相对安全)
#   |mean(z)| 大 ⇒ 估计量有**系统偏差** —— 偏差不是抽样噪声, 放宽容差不能替代解释
#
# 口径: std(z) 用**总体标准差** (pstdev, 除以 n) 计算, 以便与 D026 回放记录
# (std(z)=1.136, n=93) 逐位对齐。

CALIBRATION_MIN_N = 20                # z 统计量最小样本量, 低于此判 INSUFFICIENT_DATA
CALIBRATION_STD_Z_BAND = (0.6, 1.6)   # std(z) 允许带
CALIBRATION_MEAN_Z_MAX = 0.4          # |mean(z)| 上界
CALIBRATION_NOMINAL_P = 0.0027        # 正态下 P(|z|>3)
CALIBRATION_OUTLIER_ALPHA = 0.01      # 离群计数的假警报率上界 (声明式, 先验选定)
BAND_WIDEN_RATIO_CAP = 30.0           # B-20 复核线: 统计分支放大倍数上限
POISSON_LAMBDA_MAX = 700.0            # exp(-λ) 不下溢上限 (λ=n×0.0027 ⇒ n ≤ 26 万)

# D034 (U-19, 方案 B): rep-cluster bootstrap 口径 —— 当调用方传入 `cluster_ids`
# (每个 test case 所属的 rep 标签) 时, 用**以 rep 为单位的 percentile bootstrap CI**
# 判定 mean(z)/std(z), 代替固定阈值 |mean|≤0.4 ∧ std∈[0.6,1.6]。
# 依据: pooled n 隐含 z 相互独立, 而 z 在 rep 内相关 (within/between ≈ 0.79/0.23)
#   ⇒ 名义与实际错误率不符 (U-19)。社区共识: 独立单位是 cluster (Cameron-Miller 2015;
#   MacKinnon-Nielsen-Webb 2022; ClusterBootstrap 2020)。
# 零新依赖: 标准库 random + 固定种子 ⇒ 可复现。
CALIBRATION_BOOTSTRAP_B = 2000        # 重抽样次数 (D034)
CALIBRATION_BOOTSTRAP_SEED = 20261003  # 固定种子 ⇒ 同一输入产生同一 CI (可复现/可审计)
CALIBRATION_MIN_CLUSTERS = 3          # 簇数下限, 低于此退回 pooled (few-clusters 下界)

# CALIBRATION_MAX_OUTLIERS 已删除 (B-24, D031): 该值曾是 **n≈100 口径的常量**
# (推导: 离群计数 ~ Poisson(λ=n×0.0027); n≈100 时 λ=0.26, P(X≥2)=0.0283 不显著、
#  P(X≥3)=0.0024 显著 ⇒ 容许 2 例)。固定值在 n 增大时**几何式偏严**:
#   n=1000 时 λ=2.7, 容许数应为 7 —— 用 2 会造成大量假警报。
# 现改为 `allowed_outliers(n)` 按 Poisson 上尾**动态导出** (零自由参数: α 已声明)。
#
# ⚠ 系统的 std_err 虚报**不会**只产生几例离群: 高报走 `std(z)≪1` 分支,
#   低报走 `std(z)≫1` 分支; 离群计数只捕获"个别例的 std_err 局部失真" (如单模板低报)。


def poisson_upper_tail(k: int, lam: float) -> float:
    """P(X ≥ k), X ~ Poisson(λ)。递推 pmf 直接求和, **不引入 scipy** (B-24)。

    数值域: λ ≤ `POISSON_LAMBDA_MAX` (≈700) 用精确递推; 超出改用正态近似
    (λ→∞ 的 Lam 极限) —— 不静默返回 0。本模块 λ = n×0.0027, 故精确域覆盖 n ≤ 26 万。
    """
    if k <= 0:
        return 1.0
    if lam <= 0.0:
        return 0.0
    if lam > POISSON_LAMBDA_MAX:   # 下溢保护: e^{-λ} 会归零, 精确递推失效
        z = (k - 0.5 - lam) / math.sqrt(lam)
        return 0.5 * math.erfc(z / math.sqrt(2.0))
    term = math.exp(-lam)          # P(X=0)
    cdf = term
    for i in range(1, k):
        term *= lam / i            # 递推: P(X=i) = P(X=i-1) × λ/i
        cdf += term
        if cdf >= 1.0:
            return 0.0
    return max(0.0, 1.0 - cdf)


def allowed_outliers(n: int, *,
                     alpha: float = CALIBRATION_OUTLIER_ALPHA,
                     nominal_p: float = CALIBRATION_NOMINAL_P) -> int:
    """在假警报率上界 α 下**容许**的 |z|>3 例数 (B-24, 随 n 定标)。

    规则 (第一原理, 零自由参数): 报警 ⟺ 观测计数在上尾显著, 即
    ``P(X ≥ obs) ≤ α``, 其中 ``X ~ Poisson(n × nominal_p)``
    ⇒ 容许数 = ``max{c : P(X ≥ c) > α}``。

    为什么必须动态: 固定阈值只在 n≈100 口径成立 (D028 记 backlog) ——
    n=1000 时 λ=2.7, 容许数应为 7, 用 2 会**大量假警报**。
    """
    if n <= 0:
        return 0
    lam = n * nominal_p
    cap = int(lam + 10.0 * math.sqrt(lam) + 10.0)
    best = 0
    for c in range(0, cap + 1):
        if poisson_upper_tail(c, lam) > alpha:
            best = c
        else:
            break                  # 上尾随 c 单调递减 ⇒ 之后必然也 ≤ α
    return best


def _pooled_mean(zs: list[float]) -> float:
    return sum(zs) / len(zs)


def _pooled_pstd(zs: list[float]) -> float:
    """总体标准差 (除以 n) —— 与生产 std(z) 同口径 (见模块常量注释)"""
    m = sum(zs) / len(zs)
    return (sum((z - m) ** 2 for z in zs) / len(zs)) ** 0.5


def cluster_bootstrap_ci(clusters: list[list[float]], stat_fn, *,
                         b: int = CALIBRATION_BOOTSTRAP_B,
                         seed: int = CALIBRATION_BOOTSTRAP_SEED,
                         alpha: float = 0.05) -> tuple[float, float]:
    """以 **cluster (rep) 为单位** 的 percentile bootstrap CI (D034)。

    每个 replicate 从 K 个簇中**有放回**抽 K 个 (整簇并入), 再算统计量。
    cluster 而非行 是独立单位 ⇒ 保留簇内相关 (Cameron-Miller 2015 口径)。
    固定种子 ⇒ 同一输入产生同一区间 (可复现/可审计)。
    """
    rng = random.Random(seed)
    k = len(clusters)
    vals: list[float] = []
    for _ in range(b):
        pooled: list[float] = []
        for _ in range(k):
            pooled.extend(clusters[rng.randrange(k)])
        vals.append(stat_fn(pooled))
    vals.sort()
    lo_i = max(0, int((alpha / 2.0) * b))
    hi_i = min(b - 1, int((1.0 - alpha / 2.0) * b))
    return (vals[lo_i], vals[hi_i])


def consecutive_verdict(history: list[str], *, rounds: int = 2) -> bool:
    """最近 `rounds` 轮是否出现**同一非 OK verdict** (D034 两轮确认策略)。

    K≈20 处于 few-clusters 下界 ⇒ 单轮 CI 有波动。此函数把"系统失效"的认定
    从单轮提升为连续 ≥`rounds` 轮, 用于区分**单轮波动**与**系统失效**并留审计线。
    注意: 运行时退出码仍反映**本轮** (fail-fast), 不据此静默转绿。
    """
    if rounds < 1 or len(history) < rounds:
        return False
    tail = history[-rounds:]
    return tail[0] not in ("OK", "INSUFFICIENT_DATA") and all(v == tail[0] for v in tail)


@dataclass
class CalibrationReport:
    """std_err 声明校准报告 (B-19) + 带宽放大复核标记 (B-20)

    verdict 取值 (优先级序): OK / INSUFFICIENT_DATA / BIASED / OUTLIERS /
    STD_ERR_INFLATED / STD_ERR_UNDERSTATED
    review_flags 不参与 verdict —— 单例带宽过宽是"该看"而非"该判死"。
    """

    n_std_err: int = 0
    mean_z: float = 0.0
    std_z: float = 0.0
    max_abs_z: float = 0.0
    n_abs_z_gt_3: int = 0
    n_wide_band: int = 0
    # D029 (U-16/B-25): 退化用例计数 —— 补上此前的**闸门盲区**。
    # 此前 only `std_err>0` 进 z 统计 ⇒ 退化用例对闸门完全不可见, 而它们仍计入
    # pass_rate 分子/分母 ⇒ "用退化用例抬高通过率"这条路径上无检测器。
    # n_degenerate: 全部退化用例 (偏差恰 0 且未声明正标准误)
    # n_degenerate_random: 其中 computed 含随机源的 (退化抽样, 如 scale=0;
    #   声明 std_err=0 属正确) —— 余下的即确定性恒等 (如 np.full, prompt 已禁)
    # ⚠ 只暴露计数, **不参与 verdict** (同 B-20 的 review_flags 哲学)。
    n_degenerate: int = 0
    n_degenerate_random: int = 0
    # B-23 (D031, 判据经 D032 重锚): tolerance 与 std_err **不自洽**的例数 ——
    # 定义 (终版): 自报 `tolerance ≥ k² × std_err`，即 ratio = tolerance/(k×std_err) ≥ k
    #   ⟺ 判定带 ≥ k 倍设计带 ⟹ 该例 P(fail) ≤ 2Φ(−k²) ≈ 2e−19 ⇒ **实际不可失败**。
    # 动机 (实测): 极端例 `tolerance=0.05`(prompt 旧规定的最小值) 配 `se=1.4e-4`
    #   ⇒ ratio ×118; 即 prompt 的绝对下限与可能极小的 std_err **自相矛盾** (D031)。
    # ⚠ 判据从 `ratio ≥ 1` 改为 `ratio ≥ k` 的依据 (D032): 新 prompt 使 ratio 中位数
    #   恰为 1.000 (模型按 tolerance≈3×se 写), 原线会命中 74% = 把健康基线判为异常,
    #   且 pre-fix 27% / post-fix 74% 单调性反向 ⇒ 无鉴别力。
    # ⚠ 只暴露计数与最大比值, **不参与 verdict** (同 B-20 的 review_flags 哲学)。
    n_loose_tolerance: int = 0
    max_loose_ratio: float = 0.0
    # B-24 (D031): 实际使用的离群容许数 (= allowed_outliers(n_std_err)), 供审计复算
    max_outliers_used: int = 0
    # D034 (U-19, 方案 B): 判定口径 —— "pooled" (固定阈值, 默认) 或
    # "cluster_bootstrap" (rep 聚类百分位 bootstrap CI, 需传 cluster_ids)。
    # ⚠ method="pooled" 时 mean_z_ci/std_z_ci 为 None, 行为与 D033 前**逐位一致**。
    method: str = "pooled"
    n_clusters: int = 0                  # 参与 bootstrap 的簇数 (rep 数); pooled 时为 0
    bootstrap_b: int = 0                 # 实际重抽样次数 (审计); pooled 时为 0
    mean_z_ci: tuple[float, float] | None = None   # mean(z) 的 95% cluster bootstrap CI
    std_z_ci: tuple[float, float] | None = None    # std(z) 的 95% cluster bootstrap CI
    z: list[float] = field(default_factory=list)   # 逐例 z (供落盘复算/审计)
    verdict: str = "INSUFFICIENT_DATA"
    reasons: list[str] = field(default_factory=list)
    review_flags: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.verdict == "OK"

    def to_dict(self) -> dict:
        return {
            "n_std_err": self.n_std_err,
            "mean_z": round(self.mean_z, 4),
            "std_z": round(self.std_z, 4),
            "max_abs_z": round(self.max_abs_z, 4),
            "n_abs_z_gt_3": self.n_abs_z_gt_3,
            "n_wide_band": self.n_wide_band,
            "n_degenerate": self.n_degenerate,
            "n_degenerate_random": self.n_degenerate_random,
            "n_loose_tolerance": self.n_loose_tolerance,
            "max_loose_ratio": round(self.max_loose_ratio, 4),
            "max_outliers_used": self.max_outliers_used,
            # D034: 判定口径 + cluster bootstrap CI (pooled 时 CI 为 None)
            "method": self.method,
            "n_clusters": self.n_clusters,
            "bootstrap_b": self.bootstrap_b,
            "mean_z_ci": [round(v, 4) for v in self.mean_z_ci] if self.mean_z_ci else None,
            "std_z_ci": [round(v, 4) for v in self.std_z_ci] if self.std_z_ci else None,
            "z": [round(v, 4) for v in self.z],
            "verdict": self.verdict,
            "reasons": list(self.reasons),
            "review_flags": list(self.review_flags),
        }

    def to_compact_dict(self) -> dict:
        """不含逐例 z 的摘要 (消息/日志用)"""
        data = self.to_dict()
        data["z"] = f"<{len(self.z)} values>" if self.z else []
        return data


def assess_std_err_calibration(test_cases: list[TestCase], *,
                              std_err_k: float = 3.0,
                              rel_tolerance_floor: float = 0.0,
                              min_n: int = CALIBRATION_MIN_N,
                              std_z_band: tuple[float, float] = CALIBRATION_STD_Z_BAND,
                              mean_z_max: float = CALIBRATION_MEAN_Z_MAX,
                              max_outliers: int | None = None,
                              band_widen_ratio_cap: float = BAND_WIDEN_RATIO_CAP,
                              cluster_ids: list[int] | None = None,
                              bootstrap_b: int = CALIBRATION_BOOTSTRAP_B,
                              bootstrap_seed: int = CALIBRATION_BOOTSTRAP_SEED,
                              ) -> CalibrationReport:
    """按 B-19/B-20 规则评估一批**已执行**用例的 std_err 声明质量。

    只用 `std_err > 0` 且无执行错误的用例做 z 统计 —— 确定性用例声明 std_err=0,
    不承载抽样误差信息, 纳入会污染分布。

    `std_err_k` / `rel_tolerance_floor` 须传**实际判定所用的值**: B-20 需据此
    判断统计分支是否为**绑定约束** (否则会把"由相对地板决定判定"的用例误标为
    "由统计分支决定")。口径与判定共用 `effective_tolerance`, 不另立一套。

    `max_outliers=None` (默认) ⇒ 容许数按 **Poisson 上尾随 n 动态导出** (B-24);
    显式传值则沿用 (向后兼容, 供测试固定场景)。

    D029 (U-16/B-25): 退化用例 (偏差恰 0 且未声明正标准误) **单独计数**并暴露在
    `n_degenerate` / `n_degenerate_random` —— 它们仍被排除在 z 统计之外 (无抽样
    误差信息), 但不再是**不可见**的; 计数口径与判定共用 `is_degenerate`。

    B-23 (D031, 判据经 D032 重锚): `n_loose_tolerance` / `max_loose_ratio` 暴露
    "自报 `tolerance ≥ k²×std_err`"（即 ratio ≥ k）的例数 —— 这类例在**自报**模型下
    偶然失败率 ≤ 2Φ(−k²) ≈ 2e−19，**实际不可失败**。**只提示不判死** (同 B-20)。

    D034 (U-19, 方案 B): 传入 `cluster_ids`（与 `test_cases` **等长**的 rep 标签）时,
    改用**以 rep 为单位的 percentile bootstrap CI** 判定 —— `mean(z)` 的 CI 含 0 才无偏,
    `std(z)` 的 CI 含 1 才一致 (代替固定阈值 `|mean|≤0.4` ∧ `std∈[0.6,1.6]`)。
    `cluster_ids=None` (默认) 或簇数 < `CALIBRATION_MIN_CLUSTERS` ⇒ 退回 pooled,
    **行为与从前逐位一致** (向后兼容)。离群规则不随口径改变 (仍按 B-24 的 pooled n)。
    """
    if cluster_ids is not None and len(cluster_ids) != len(test_cases):
        raise ValueError(
            f"cluster_ids 长度 {len(cluster_ids)} 与 test_cases 长度 {len(test_cases)} 不符")
    zs: list[float] = []
    flags: list[str] = []
    n_deg = n_deg_random = 0
    n_loose = 0
    max_loose_ratio = 0.0
    clusters_map: dict[int, list[float]] = {}   # D034: 每簇 (rep) 的 z 列表 (仅 cluster 口径用)
    for i, tc in enumerate(test_cases):
        if tc.error_message:
            continue
        if is_degenerate(tc.expected, tc.actual, tc.std_err, tc.error_message):
            n_deg += 1
            if has_random_source(tc.computed_expr):
                n_deg_random += 1
        se = tc.std_err
        if se is None or se <= 0.0:
            continue
        # B-23: 自报 tolerance 与自报统计带宽 (std_err_k × se) 的自洽性。
        # 统计分支关闭 (std_err_k=0) 时该量无定义 ⇒ 不计数 (而非记成无穷大)。
        # 临界比 = **std_err_k 本身** (D032 重锚, 原为 1.0):
        #   ratio >= k ⟺ tolerance >= k×(k×se) ⟺ 判定带 ≥ k 倍设计带
        #   ⇒ P(fail) ≤ 2Φ(−k²) = 2Φ(−9) ≈ 2e−19 ⇒ 该例**实际不可失败**。
        # 为什么改: 原线 ratio>=1 被实测证伪 —— 新 prompt 使 ratio 中位数恰为 1.000
        #   (模型按 tolerance≈3×se 写) ⇒ 74% 命中 = 把健康基线判为异常; 且
        #   pre-fix 27% < post-fix 74%, 单调性反向 ⇒ 无鉴别力。
        if std_err_k > 0.0:
            ratio = tc.tolerance / (std_err_k * se)
            if ratio >= std_err_k:
                n_loose += 1
                max_loose_ratio = max(max_loose_ratio, ratio)
        z_val = (tc.actual - tc.expected) / se
        zs.append(z_val)
        if cluster_ids is not None:
            clusters_map.setdefault(cluster_ids[i], []).append(z_val)

        # B-20: 统计分支是否**既是绑定约束、又把容差放大了 >cap 倍**。
        # 放大倍数用 se_band / tolerance 而非 band / scale: 后者在 expected≈0 处
        # 失真 (任意带宽对 ~0 的 actual 都是巨大倍数, 会把合法近零用例误标)。
        band = effective_tolerance(tc.expected, tc.actual, tc.tolerance, se,
                                   rel_tolerance_floor, std_err_k)
        se_band = std_err_k * se if std_err_k > 0.0 else 0.0
        widen = se_band / max(tc.tolerance, 1e-12)
        if se_band > 0.0 and se_band >= band and widen > band_widen_ratio_cap:
            flags.append(
                f"case#{i}: 统计分支把容差放大 ×{widen:.1f} (std_err={se:g}, "
                f"tolerance={tc.tolerance:g}, band=±{se_band:g}) "
                f"⇒ 判定由 schema 扩展而非模型自报容差决定, 需人工复核"
            )

    report = CalibrationReport(
        n_std_err=len(zs), n_wide_band=len(flags), review_flags=flags, z=list(zs),
        n_degenerate=n_deg, n_degenerate_random=n_deg_random,
        n_loose_tolerance=n_loose, max_loose_ratio=max_loose_ratio,
    )
    # B-23 汇总标记 (只提示不判死, 单条而非逐例刷屏): 临界比 = k 本身 (D032 重锚)
    if n_loose:
        report.review_flags.append(
            f"{n_loose}/{len(zs)} 例的自报 tolerance ≥ k²×std_err "
            f"(最大 ×{max_loose_ratio:.1f}) ⇒ 判定带 ≥ k 倍设计带, "
            f"偶然失败率 ≤ 2Φ(−k²) ≈ 2e−19 ⇒ 这些例**实际不可失败**, 需人工复核"
        )
    if len(zs) < min_n:
        report.verdict = "INSUFFICIENT_DATA"
        report.reasons.append(
            f"std_err>0 的样本量 {len(zs)} < {min_n}: 校准指标不可估 "
            f"(n=1 单样本陷阱见 D025)"
        )
        return report

    mean_z = _pooled_mean(zs)
    report.mean_z = mean_z
    report.std_z = _pooled_pstd(zs)
    lo, hi = std_z_band
    report.max_abs_z = max(abs(z) for z in zs)
    report.n_abs_z_gt_3 = sum(1 for z in zs if abs(z) > 3.0)
    # B-24: 容许数随 n 动态导出 (None ⇒ 不传固定值, 避免 n 增大后几何式偏严)
    if max_outliers is None:
        max_outliers = allowed_outliers(len(zs))
    report.max_outliers_used = max_outliers
    lam = len(zs) * CALIBRATION_NOMINAL_P

    # D034 (U-19, 方案 B): 口径选择 —— 簇数 (rep) 足够时用 cluster bootstrap CI,
    # 否则退回 pooled 固定阈值 (向后兼容, 行为逐位一致)。
    clusters = list(clusters_map.values())
    use_cluster = len(clusters) >= CALIBRATION_MIN_CLUSTERS
    if use_cluster:
        report.method = "cluster_bootstrap"
        report.n_clusters = len(clusters)
        report.bootstrap_b = bootstrap_b
        report.mean_z_ci = cluster_bootstrap_ci(
            clusters, _pooled_mean, b=bootstrap_b, seed=bootstrap_seed)
        report.std_z_ci = cluster_bootstrap_ci(
            clusters, _pooled_pstd, b=bootstrap_b, seed=bootstrap_seed)

    if use_cluster:
        m_lo, m_hi = report.mean_z_ci
        if m_lo > 0.0 or m_hi < 0.0:
            report.verdict = "BIASED"
            report.reasons.append(
                f"mean(z)={mean_z:.3f} 的 95% cluster bootstrap CI "
                f"[{m_lo:.3f}, {m_hi:.3f}] **不含 0** (K={report.n_clusters} reps): "
                f"估计量存在**系统偏差** —— 按 rep 聚类口径显著, 非抽样噪声; "
                f"放宽容差不能替代对偏差的解释"
            )
            return report
    elif abs(mean_z) > mean_z_max:
        report.verdict = "BIASED"
        report.reasons.append(
            f"|mean(z)|={abs(mean_z):.3f} > {mean_z_max}: 估计量存在**系统偏差** —— "
            f"偏差不是抽样噪声, 放宽容差不能替代对偏差的解释"
        )
        return report
    if report.n_abs_z_gt_3 > max_outliers:
        report.verdict = "OUTLIERS"
        report.reasons.append(
            f"|z|>3 例数={report.n_abs_z_gt_3} > {max_outliers} "
            f"(n={report.n_std_err}, λ={lam:.3f}, α={CALIBRATION_OUTLIER_ALPHA}; "
            f"max|z|={report.max_abs_z:.3f}): "
            f"超出 Poisson 上尾的容许计数 —— 或该例本身有误, 或 std_err 被低报"
        )
        return report
    if use_cluster:
        s_lo, s_hi = report.std_z_ci
        if s_hi < 1.0:
            report.verdict = "STD_ERR_INFLATED"
            report.reasons.append(
                f"std(z)={report.std_z:.3f} 的 95% cluster bootstrap CI "
                f"[{s_lo:.3f}, {s_hi:.3f}] **不含 1** (全 < 1): std_err 被系统性**高报** "
                f"⇒ 容差带被撑宽 = 制造通过"
            )
            return report
        if s_lo > 1.0:
            report.verdict = "STD_ERR_UNDERSTATED"
            report.reasons.append(
                f"std(z)={report.std_z:.3f} 的 95% cluster bootstrap CI "
                f"[{s_lo:.3f}, {s_hi:.3f}] **不含 1** (全 > 1): std_err **低报** "
                f"⇒ 统计分支过严 (假阴性方向)"
            )
            return report
    else:
        if report.std_z < lo:
            report.verdict = "STD_ERR_INFLATED"
            report.reasons.append(
                f"std(z)={report.std_z:.3f} < {lo}: std_err 被系统性**高报** "
                f"⇒ 容差带被撑宽 = 制造通过"
            )
            return report
        if report.std_z > hi:
            report.verdict = "STD_ERR_UNDERSTATED"
            report.reasons.append(
                f"std(z)={report.std_z:.3f} > {hi}: std_err **低报** "
                f"⇒ 统计分支过严 (假阴性方向)"
            )
            return report

    report.verdict = "OK"
    if use_cluster:
        report.reasons.append(
            f"z 校准 (cluster 口径, K={report.n_clusters} reps, B={report.bootstrap_b}): "
            f"mean(z) CI=[{report.mean_z_ci[0]:.3f}, {report.mean_z_ci[1]:.3f}] 含 0; "
            f"std(z) CI=[{report.std_z_ci[0]:.3f}, {report.std_z_ci[1]:.3f}] 含 1; "
            f"|z|>3 例数={report.n_abs_z_gt_3}≤{max_outliers} "
            f"(容许数按 n={report.n_std_err} 的 Poisson 上尾导出, B-24)"
        )
    else:
        report.reasons.append(
            f"z 校准在带内: std(z)={report.std_z:.3f}∈[{lo}, {hi}], "
            f"|mean(z)|={abs(mean_z):.3f}≤{mean_z_max}, "
            f"|z|>3 例数={report.n_abs_z_gt_3}≤{max_outliers} "
            f"(容许数按 n={report.n_std_err} 的 Poisson 上尾导出, B-24)"
        )
    return report


def attribute_gate_trigger(report: CalibrationReport, *,
                           mean_z_max: float = CALIBRATION_MEAN_Z_MAX,
                           std_z_band: tuple[float, float] = CALIBRATION_STD_Z_BAND) -> dict:
    """U-15 (D057): 校准闸门**触发时的机械归因** (只读 `report`, 不改 verdict/pass_rate)。

    背景: U-15 = "闸门触发时, 如何区分**判据过严**与**模型真的在虚报**"。D028 确立的
    人工程序 = ① 看 `std(z)` 是否出带 ② 离群按 Poisson 上尾核算 ③ 合成样例反证闸门
    未被削弱。其中 ①② 可**离线机械复算** ⇒ 本函数自动化之, 把"归因"从人工流程变为
    可复算的机械分类 (③ 属开发期反证, 不由本函数承担)。

    ⚠ O-A 纪律 (同 B-20/B-23/B-26): 只**暴露信号**, **不参与** verdict / pass_rate / 退出码。

    归因口径 (机械可判别部分):
      - `systematic_misreport`: 均值或带宽**系统性**出带, 且 **pooled 口径下同样触发**
        ⇒ 与聚类口径无关的稳健证据, 指向**模型虚报** (真信号)。
      - `criterion_sensitive`: 本轮 (cluster) 触发但 **pooled 口径不触发** (D034 的
        "口径反转"现象) ⇒ 触发**依赖口径/阈值** ⇒ 指向**判据过严/口径问题**侧。
      - `isolated_outliers`: 仅"离群超 Poisson 容许数", 均值/带宽均在带内 ⇒ **单例**
        性质 (或该例有误/低报), 非系统性。
      - `unattributed`: 已触发但三信号均未命中 (构造不一致时可达)。
      - `not_triggered`: verdict ∈ {OK, INSUFFICIENT_DATA}。

    Returns: dict (见上列信号 + `attribution`)。**纯函数** (无 IO, 可离线复算)。
    """
    triggered = report.verdict not in ("OK", "INSUFFICIENT_DATA")
    use_cluster = report.method == "cluster_bootstrap"

    # ① mean(z) 是否出带 (系统性偏差 = 模型虚报方向的必要条件)
    if use_cluster and report.mean_z_ci is not None:
        m_lo, m_hi = report.mean_z_ci
        mean_bias = bool(m_lo > 0.0 or m_hi < 0.0)
    else:
        mean_bias = abs(report.mean_z) > mean_z_max

    # ② std(z) 是否出带 (std_err 系统性高报/低报)
    if use_cluster and report.std_z_ci is not None:
        s_lo, s_hi = report.std_z_ci
        std_out_of_band = bool(s_hi < 1.0 or s_lo > 1.0)
    else:
        lo, hi = std_z_band
        std_out_of_band = bool(report.std_z < lo or report.std_z > hi)

    # ③ 离群是否超 Poisson 上尾容许数 (容许数由 B-24 随 n 导出, 此处只读)
    outliers_exceed = report.n_abs_z_gt_3 > report.max_outliers_used

    # ④ 口径敏感 (D034 现象): 对比 **pooled 固定阈值**是否也会触发。
    #    `report.mean_z`/`report.std_z` 恒为 **pooled** 统计量 (与 method 无关) ⇒ 可直接
    #    代入 pooled 阈值判据 (离群规则两口径共用 ⇒ 只对比均值/带宽)。
    criterion_sensitive = False
    if triggered and use_cluster:
        lo, hi = std_z_band
        pooled_fires = (abs(report.mean_z) > mean_z_max) or (report.std_z < lo) \
            or (report.std_z > hi)
        criterion_sensitive = (not pooled_fires) and (mean_bias or std_out_of_band)

    if not triggered:
        attribution = "not_triggered"
    elif criterion_sensitive:
        attribution = "criterion_sensitive"
    elif mean_bias or std_out_of_band:
        attribution = "systematic_misreport"
    elif outliers_exceed:
        attribution = "isolated_outliers"
    else:
        attribution = "unattributed"

    return {
        "verdict": report.verdict,
        "triggered": triggered,
        "method": report.method,
        "mean_bias": mean_bias,
        "std_out_of_band": std_out_of_band,
        "outliers_exceed_allowance": outliers_exceed,
        "criterion_sensitive": criterion_sensitive,
        "attribution": attribution,
    }
