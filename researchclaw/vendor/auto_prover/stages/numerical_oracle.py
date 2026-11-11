"""W5 / B-57 · S-c: `expected` 的独立复算（D1–D12 / DEV1–DEV6）。

职责:
  识别 ``np.mean(np.random.default_rng(<seed>).<dist>(<args>))`` 形态，
  用 ``scipy.stats`` 的解析矩作为**独立于 LLM** 的取值来源，按容差判据比对
  ``expected``，产出四态检查结果。

⚠ O-A (D040 / D-W5-4): 本模块只产出**可见性**数据，
  不参与 ``passed`` / ``pass_rate`` / ``verdict`` / ``citation_label``。
⚠ 口径隔离 (D046/D047): 结果由调用方写入 ``numerical_review_flags``，
  **不得**写入 ``semantic_review_flags``。
"""
from __future__ import annotations

import ast
import math
from typing import NamedTuple

from ..datatypes import TestCase
from ..sandbox import SafeEvaluator

# D2 的主路径（scipy 解析矩）**延迟导入**: `lean-real` 等精简 job 只装 pytest，
# 模块级导入会让 `import proof_pipeline` 直接 `ModuleNotFoundError`（D138 实测）。
# 缺 scipy ⇒ `OracleInvalid` ⇒ 该例计 `unrecognized`（I4 失败安全，不静默改判定）。

# D10: 舍入保护下界（相对），防「4 位小数舍入」被判成不一致。
MISMATCH_REL_FLOOR = 1e-6

# §4.2: dist -> 位置形参顺序（numpy Generator 语义；D136 实测签名）。
_DIST_PARAMS: dict[str, tuple[str, ...]] = {
    "normal": ("loc", "scale", "size"),
    "standard_normal": ("size",),
    "uniform": ("low", "high", "size"),
    "laplace": ("loc", "scale", "size"),
    "exponential": ("scale", "size"),
    "binomial": ("n", "p", "size"),
    "poisson": ("lam", "size"),
    "integers": ("low", "high", "size"),
    "lognormal": ("mean", "sigma", "size"),
}

# §4.2: dist -> 缺省形参（源码形态，交给 SafeEvaluator 求值）。
_DIST_DEFAULTS: dict[str, dict[str, str]] = {
    "normal": {"loc": "0.0", "scale": "1.0"},
    "uniform": {"low": "0.0", "high": "1.0"},
    "laplace": {"loc": "0.0", "scale": "1.0"},
    "exponential": {"scale": "1.0"},
    "poisson": {"lam": "1.0"},
    "lognormal": {"mean": "0.0", "sigma": "1.0"},
}

STATUS_MATCH = "match"
STATUS_MISMATCH = "mismatch"
STATUS_UNRECOGNIZED = "unrecognized"
STATUS_SKIPPED_DEGENERATE = "skipped_degenerate"

REASON_NO_STRUCTURE = "no_structure"
REASON_ARG_EVAL_FAILED = "arg_eval_failed"
REASON_ORACLE_INVALID = "oracle_invalid"     # DEV3: scipy 返回 nan 等


class MeanStructure(NamedTuple):
    """识别出的「样本均值」形态；``args_src`` 为形参名 → 源码文本（不含 size）。"""

    dist: str
    args_src: dict[str, str]


class OracleInvalid(ValueError):
    """参数可求值但解析矩不可得（如 ``scale=0`` ⇒ scipy 返回 nan）。"""


def parse_mean_structure(expr: str | None) -> MeanStructure | None:
    """识别样本均值形态（D4: AST，非正则）；不匹配一律 ``None``。

    目标形态: ``np.mean(np.random.default_rng(<seed>).<dist>(<args>))``
    """
    if not expr:
        return None
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None
    call = tree.body
    if not (isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "mean"
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "np"):
        return None
    if len(call.args) != 1 or call.keywords:
        return None
    inner = call.args[0]
    if not (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)):
        return None
    dist = inner.func.attr
    if dist not in _DIST_PARAMS:
        return None
    rng = inner.func.value
    if not (isinstance(rng, ast.Call)
            and isinstance(rng.func, ast.Attribute)
            and rng.func.attr == "default_rng"
            and isinstance(rng.func.value, ast.Attribute)
            and rng.func.value.attr == "random"
            and isinstance(rng.func.value.value, ast.Name)
            and rng.func.value.value.id == "np"):
        return None
    bound = _bind_args(dist, inner)
    return None if bound is None else MeanStructure(dist, bound)


def _bind_args(dist: str, call: ast.Call) -> dict[str, str] | None:
    """按 numpy 形参顺序绑定位置参数与关键字；无法确定 ⇒ ``None``。"""
    names = _DIST_PARAMS[dist]
    if len(call.args) > len(names):
        return None
    bound = {name: ast.unparse(node) for name, node in zip(names, call.args)}
    for kw in call.keywords:
        if kw.arg is None or kw.arg not in names or kw.arg in bound:
            return None
        bound[kw.arg] = ast.unparse(kw.value)
    bound.pop("size", None)                       # size 不参与均值
    for name, default in _DIST_DEFAULTS.get(dist, {}).items():
        bound.setdefault(name, default)
    required = [n for n in names if n != "size"]
    if dist == "integers":
        required = [n for n in required if n != "high"]   # high 可缺省
    if any(name not in bound for name in required):
        return None
    return bound


def _stats():
    """延迟导入 `scipy.stats`（D2）；缺依赖 ⇒ ``OracleInvalid``（不算不一致）。"""
    try:
        from scipy import stats
    except ImportError as exc:                    # pragma: no cover - CI lean-real 场景
        raise OracleInvalid("scipy unavailable: %s" % exc) from exc
    return stats


def _closed_form_mean(dist: str, values: dict[str, float]) -> float | None:
    """闭式均值（DEV7: scipy 对 ``scale=0`` 返回 nan 时的补位；语义与 numpy 一致）。"""
    if dist == "normal" or dist == "laplace":
        return values["loc"]
    if dist == "uniform":
        return (values["low"] + values["high"]) / 2.0
    if dist == "exponential":
        return values["scale"]
    if dist == "binomial":
        return values["n"] * values["p"]
    if dist == "poisson":
        return values["lam"]
    if dist == "lognormal":
        return math.exp(values["mean"] + values["sigma"] ** 2 / 2.0)
    if dist == "integers":
        low = values["low"]
        high = values.get("high")
        return (low + high - 1.0) / 2.0 if high is not None else (low - 1.0) / 2.0
    return None


def analytic_mean(structure: MeanStructure, params: dict | None,
                  evaluator: SafeEvaluator) -> float:
    """参数子表达式 → 数值（D5），再取解析矩（D2）。不可得 ⇒ ``OracleInvalid``。"""
    if structure.dist == "standard_normal":
        return 0.0
    values = {
        name: float(evaluator.evaluate(params or {}, src, 0.0, 0.0))
        for name, src in structure.args_src.items()
    }
    dist = structure.dist
    if dist == "integers":                        # scipy 无同名离散分布 ⇒ 闭式（high 右开）
        low = values["low"]
        high = values.get("high")
        mu = (low + high - 1.0) / 2.0 if high is not None else (low - 1.0) / 2.0
    elif dist == "normal":
        mu = _stats().norm.mean(loc=values["loc"], scale=values["scale"])
    elif dist == "uniform":
        mu = _stats().uniform.mean(loc=values["low"], scale=values["high"] - values["low"])
    elif dist == "laplace":
        mu = _stats().laplace.mean(loc=values["loc"], scale=values["scale"])
    elif dist == "exponential":
        mu = _stats().expon.mean(scale=values["scale"])
    elif dist == "binomial":
        mu = _stats().binom.mean(values["n"], values["p"])
    elif dist == "poisson":
        mu = _stats().poisson.mean(values["lam"])
    else:  # lognormal
        mu = _stats().lognorm.mean(s=values["sigma"], scale=math.exp(values["mean"]))
    mu = float(mu)
    if not math.isfinite(mu):                     # DEV4/DEV7: scipy 对 scale=0 返回 nan
        fallback = _closed_form_mean(dist, values)
        mu = float("nan") if fallback is None else float(fallback)
    if not math.isfinite(mu):                     # 真·不可得（参数非法）⇒ 不当作不一致
        raise OracleInvalid("non-finite analytic mean for %s" % dist)
    return mu


def effective_production_tolerance(expected: float, actual: float | None,
                                   tolerance: float, std_err: float | None,
                                   rel_tolerance_floor: float = 0.0,
                                   std_err_k: float = 0.0) -> float:
    """生产带宽（W7/D2）: 与 `stage2_numerical.effective_tolerance` **逐字同公式**。

    `max(tolerance, rel_floor × max(|expected|, |actual|), k × std_err)`

    `actual is None` ⇒ 退化为 `|expected|`（§4.3；由调用方在块内计 `actual_missing`）。
    为什么复写: D7 排除了反向 import（stage2 已 import oracle，循环导入）；
    漂移由测试侧跨模块一致性锚（B1）每次 CI 钉住（D8）。
    """
    scale = max(abs(expected), abs(actual if actual is not None else expected))
    band = float(tolerance)
    if rel_tolerance_floor > 0.0:
        band = max(band, rel_tolerance_floor * scale)
    if std_err_k > 0.0 and std_err is not None and std_err > 0.0:
        band = max(band, std_err_k * std_err)
    return band


def _result(index: int, status: str, *, dist=None, reason=None,
            expected=None, mu=None, delta=None, tolerance_used=None,
            tolerance_ratio=None, production_ratio=None) -> dict:
    return {
        "index": index,
        "status": status,
        "dist": dist,
        "reason": reason,
        "expected": expected,
        "mu": mu,
        "delta": delta,
        "tolerance_used": tolerance_used,
        # W6/D9: 键恒存在（unrecognized / skipped_degenerate ⇒ None，**不写 0**）。
        "tolerance_ratio": tolerance_ratio,
        # W7/D1 (D147): 生产口径带宽（第 10 键）；同样恒存在、未识别/退化 ⇒ None。
        "production_ratio": production_ratio,
    }


def check_case(index: int, tc: TestCase, evaluator: SafeEvaluator,
               rel_tolerance_floor: float = 0.0,
               std_err_k: float = 0.0) -> dict:
    """单例四态判定（§4.3）；**不抛异常**（I4）。

    W7/D7: 新增两个关键字默认参数（默认 0 ⇒ 旧调用逐值等价）；生产由
    `stage2._check_expected_oracle` 注入 config 值。
    """
    if tc.degenerate:
        return _result(index, STATUS_SKIPPED_DEGENERATE, expected=tc.expected)
    structure = parse_mean_structure(tc.computed_expr)
    if structure is None:
        return _result(index, STATUS_UNRECOGNIZED, reason=REASON_NO_STRUCTURE,
                       expected=tc.expected)
    try:
        mu = analytic_mean(structure, tc.params, evaluator)
    except OracleInvalid:
        return _result(index, STATUS_UNRECOGNIZED, dist=structure.dist,
                       reason=REASON_ORACLE_INVALID, expected=tc.expected)
    except Exception:  # broad-ok: 解析/求值回调异常不可枚举（I4 失败安全，返回 unrecognized）
        return _result(index, STATUS_UNRECOGNIZED, dist=structure.dist,
                       reason=REASON_ARG_EVAL_FAILED, expected=tc.expected)
    tolerance_used = max(float(tc.tolerance or 0.0),
                         MISMATCH_REL_FLOOR * max(1.0, abs(mu)))
    delta = abs(float(tc.expected) - mu)
    status = STATUS_MISMATCH if delta > tolerance_used else STATUS_MATCH
    # W6/D2: 分辨力的尺度读数；**只读**，不进任何 if（O-A / D5）。
    tolerance_ratio = tolerance_used / max(1.0, abs(mu))
    # W7/D1/D2: 生产口径读数（与生产判定同公式）；**只读**，不进任何 if（O-A / D10）。
    production_ratio = effective_production_tolerance(
        float(tc.expected), tc.actual, float(tc.tolerance or 0.0), tc.std_err,
        rel_tolerance_floor, std_err_k,
    ) / max(1.0, abs(mu))
    return _result(index, status, dist=structure.dist, expected=tc.expected,
                   mu=mu, delta=delta, tolerance_used=tolerance_used,
                   tolerance_ratio=tolerance_ratio,
                   production_ratio=production_ratio)


def _percentile(values: list[float], p: int) -> float | None:
    """最近秩（W6/D6）: ``idx = min(n-1, max(0, ceil(p/100*n) - 1))``；空 ⇒ None。"""
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    idx = min(n - 1, max(0, math.ceil(p / 100.0 * n) - 1))
    return ordered[idx]


def summarize(checks: list[dict], rel_tolerance_floor: float = 0.0,
              std_err_k: float = 0.0, actual_missing: int = 0) -> dict:
    """§4.5 汇总；不变式 ``recognized + unrecognized + skipped_degenerate == checked``。

    W7/D7: `rel_tolerance_floor` / `std_err_k` 落**调用方实际传入值**（默认 0.0 ⇒
    如实标注「未启用生产口径」，不伪装成 0.05）。`actual_missing` 为 DEV14：
    由调用方统计「recognized 且 `tc.actual is None`」的例数（不新增逐例键）。
    """
    summary = {
        "checked": len(checks),
        "recognized": 0,
        "unrecognized": 0,
        "mismatch": 0,
        "skipped_degenerate": 0,
        "distributions": {},
        "unrecognized_reasons": {
            REASON_NO_STRUCTURE: 0,
            REASON_ARG_EVAL_FAILED: 0,
            REASON_ORACLE_INVALID: 0,
        },
    }
    ratios: list[float] = []
    production_ratios: list[float] = []
    for check in checks:
        status = check["status"]
        if status == STATUS_SKIPPED_DEGENERATE:
            summary["skipped_degenerate"] += 1
        elif status == STATUS_UNRECOGNIZED:
            summary["unrecognized"] += 1
            reason = check.get("reason") or REASON_ORACLE_INVALID
            reasons = summary["unrecognized_reasons"]
            reasons[reason] = reasons.get(reason, 0) + 1
        else:
            summary["recognized"] += 1
            if status == STATUS_MISMATCH:
                summary["mismatch"] += 1
            dist = check.get("dist")
            if dist:
                dists = summary["distributions"]
                dists[dist] = dists.get(dist, 0) + 1
            # W6/D1: 只有 recognized 的用例进分母（count == recognized）。
            ratio = check.get("tolerance_ratio")
            if ratio is not None:
                ratios.append(float(ratio))
            # W7/D1/D5: 生产口径分位（与 W6 同一最近秩算法 ⇒ 两列可逐值比较）。
            prod = check.get("production_ratio")
            if prod is not None:
                production_ratios.append(float(prod))
    summary["tolerance_ratio"] = {
        "count": len(ratios),
        "p50": _percentile(ratios, 50),
        "p90": _percentile(ratios, 90),
        "max": max(ratios) if ratios else None,
    }
    summary["production_band"] = {
        "count": len(production_ratios),
        "p50": _percentile(production_ratios, 50),
        "p90": _percentile(production_ratios, 90),
        "max": max(production_ratios) if production_ratios else None,
        # W7/D4: 读数自带生效参数（否则读者不知口径）。
        "rel_tolerance_floor": float(rel_tolerance_floor),
        "std_err_k": float(std_err_k),
        # W7/§4.3: `actual` 缺失近似**不静默**。
        "actual_missing": int(actual_missing),
    }
    return summary


def flags(checks: list[dict]) -> list[str]:
    """§4.4 flag 词表；输入按 index 升序 ⇒ 输出同序。"""
    out: list[str] = []
    for check in checks:
        if check["status"] == STATUS_MISMATCH:
            out.append(f"case#{check['index']}:expected_mismatch")
        elif check["status"] == STATUS_UNRECOGNIZED:
            out.append(f"case#{check['index']}:oracle_unrecognized")
    return out
