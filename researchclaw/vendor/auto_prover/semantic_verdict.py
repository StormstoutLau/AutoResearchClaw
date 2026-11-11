"""语义级判定 (T4/D030 落地) —— Tier1 证伪力探针 + Tier2 类别矩阵

依据 DESIGN_AGENT_CLI_SEMANTIC_VERDICT.md §6 / DECISIONS D030。

**为什么需要**: 同一表达式形态在两种断言下合规性相反 ——
  - 组合断言 (`C(5,2) = 10`): `computed = comb(5,2)` 是唯一正确形态 ⇒ **合法**;
  - 统计断言 (`E[X̄] = μ`): `computed = np.mean(np.full(n, mu))` 是恒等检查 ⇒ **违规**。
⇒ 合规性 = f(断言类别, 证伪力); 机械层（Tier1）只有后者。

**防自验证 (对齐 D7 B-1 / O-92)**:
  1. 判据持有者独立于生成者: Tier2 是**静态表**, 不含 LLM 生成内容;
  2. 双盲: 生成 prompt 不暴露检验方式 (见 TESTGEN_PROMPT);
  3. 可离线复算: 给定 `params` + 表达式即可重放。

**边界 (D030)**: Tier1 的 `CONSTANT` **不能独自判合规**（组合断言会被误杀）⇒ 必须两层合用。
"""
from __future__ import annotations

from typing import Callable

from .datatypes import Falsifiability, SemanticVerdict

# 随机源键候选 (用于"受控扰动"探针)
RANDOM_SOURCE_KEYS: tuple[str, ...] = ("seed", "rng_seed", "random_state")

# Tier 2 静态矩阵的两个集合 (唯一真值表, 见 DESIGN §6.2)
_FALSIFIABILITY_FREE_KINDS = {"deterministic_identity", "combinatorial"}
_FALSIFIABILITY_REQUIRED_KINDS = {
    "expectation", "variance", "moment", "distributional", "asymptotic",
}


def probe_falsifiability(
    params: dict,
    computed_expr: str | None,
    eval_fn: Callable[[dict, str], float],
    *,
    repeats: int = 3,
) -> Falsifiability:
    """Tier 1: 证伪力探针 (机械, 零 LLM, 可离线)。

    扰动策略 (按序):
      1. 若 `params` 含随机源键 ⇒ 逐个 +1 重执行;
      2. 否则 (或扰动未变) 重复执行 `repeats` 次 (捕获表达式内 np.random 的不确定性)。
    判定: 任一结果与基准不同 ⇒ VARYING; 全同 ⇒ CONSTANT;
          `computed_expr` 为空 / 执行异常 ⇒ UNKNOWN。

    ⚠ 保守: 只证伪"恒等", **不证明"正确"** (VARYING 不是正面判定)。
    """
    if not computed_expr:
        return Falsifiability.UNKNOWN
    try:
        base = eval_fn(params, computed_expr)
    except Exception:  # broad-ok: eval_fn 为调用方注入的回调，异常类型不可枚举（探针降级 UNKNOWN）
        return Falsifiability.UNKNOWN

    # 1) 受控扰动随机源键
    for key in RANDOM_SOURCE_KEYS:
        val = params.get(key)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            perturbed = dict(params)
            perturbed[key] = val + 1
            try:
                if eval_fn(perturbed, computed_expr) != base:
                    return Falsifiability.VARYING
            except Exception:  # broad-ok: eval_fn 为调用方注入的回调，异常类型不可枚举（扰动点跳过）
                continue

    # 2) 重复执行 (捕获内部随机性)
    for _ in range(max(repeats, 1)):
        try:
            if eval_fn(params, computed_expr) != base:
                return Falsifiability.VARYING
        except Exception:  # broad-ok: eval_fn 为调用方注入的回调，异常类型不可枚举（重复点跳过）
            continue

    return Falsifiability.CONSTANT


def judge_semantic(kind: str | None,
                   falsifiability: Falsifiability) -> SemanticVerdict:
    """Tier 2: 类别 × 证伪力 匹配矩阵 (静态表, 零 LLM)。

    | kind | CONSTANT | VARYING | UNKNOWN |
    |---|---|---|---|
    | deterministic_identity / combinatorial | VALID_DETERMINISTIC | VALID_DETERMINISTIC | UNKNOWN |
    | expectation/variance/moment/distributional/asymptotic | **CIRCULAR** | UNKNOWN | UNKNOWN |
    | 缺失 / 非法 | UNKNOWN（降级） | UNKNOWN | UNKNOWN |
    """
    if kind not in _FALSIFIABILITY_FREE_KINDS and kind not in _FALSIFIABILITY_REQUIRED_KINDS:
        return SemanticVerdict.UNKNOWN           # 缺失/非法 ⇒ 降级 (现行语义不变)
    if falsifiability is Falsifiability.UNKNOWN:
        return SemanticVerdict.UNKNOWN
    if kind in _FALSIFIABILITY_FREE_KINDS:
        return SemanticVerdict.VALID_DETERMINISTIC
    # 要求证伪力的类别: 仅 CONSTANT 构成"恒等检查"
    if falsifiability is Falsifiability.CONSTANT:
        return SemanticVerdict.CIRCULAR
    return SemanticVerdict.UNKNOWN               # VARYING 不作为正面判定 (不越界)


def judge_test_case(
    tc,
    eval_fn: Callable[[dict, str], float],
) -> tuple[Falsifiability, SemanticVerdict]:
    """组合入口: 探针 + 矩阵 (供 verify() 逐例调用)。"""
    fals = probe_falsifiability(tc.params, tc.computed_expr, eval_fn)
    return fals, judge_semantic(tc.kind, fals)