"""反例搜索器（W12 / B-58 拆分自 `stage2_numerical.py`）。

搜索策略：Mathematica 符号 → 失败用例邻域 → 优化驱动 → 网格 → 最小反例。
"""

from __future__ import annotations
import asyncio
import logging
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
    EvaluationError,
    SafeEvaluator,
)
# W5/B-57 S-c (D135): expected 独立复算（纯函数模块；只产出可见性）。
from .numerical_oracle import check_case as _oracle_check_case
from .numerical_oracle import flags as _oracle_flags
from .numerical_oracle import summarize as _oracle_summarize

from .numerical_core import COUNTEREXAMPLE_SEARCH_SEED

logger = logging.getLogger(__name__)


MINIMAL_COUNTEREXAMPLE_PROMPT = """【任务】从以下反例中找到最小反例（参数值最接近"正常"情况但仍使断言失效）。

【反例列表】
{counterexamples}

【要求】
1. 识别哪个反例的参数最小程度偏离典型值
2. 说明为什么它是最小反例
3. 输出最小反例的参数

【输出格式】
MINIMAL_INDEX: <反例编号>
MINIMALITY_REASON: <说明>
"""



class CounterExampleSearcher:
    """系统化反例搜索器

    搜索策略优先级:
      1. Mathematica 符号搜索 (FindInstance/Reduce/Resolve) — 精确
      2. 从失败用例出发，梯度引导搜索相邻参数空间 — 半精确
      3. 优化驱动搜索 (scipy.optimize) — 数值
      4. 网格搜索 (grid search) — 数值
      5. 最小反例识别
    """

    # W4/B-57 (D129, D4): 类级默认种子 —— 兼容 `__new__` 构造的测试替身
    #   （实例赋值仍走 __init__; 该默认值只兜住未初始化路径）。
    _search_seed: int = COUNTEREXAMPLE_SEARCH_SEED

    def __init__(self, gateway: ModelGateway,
                 mathematica_timeout: float | None = None,
                 mathematica_use_wolframclient: bool | None = None,
                 eval_timeout: float = DEFAULT_TIMEOUT_S,
                 search_budget: float = DEFAULT_SEARCH_BUDGET_S,
                 search_seed: int = COUNTEREXAMPLE_SEARCH_SEED,
                 memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB):
        self.gateway = gateway
        # 懒导入（W12 / B-58 D3）: 门面 -> 本模块 为模块级单行道; 本模块 -> 门面 只在实例化时发生。
        from .stage2_numerical import NumericalVerifier
        self._verifier = NumericalVerifier(gateway)  # 复用 _parse_test_cases / _run_test_cases
        self._bridge = None
        # W4/B-57 (D129, D4/D5): 反例搜索种子 —— 局部生成器, 不污染全局 RNG。
        self._search_seed = search_seed
        # T5/B-11 (D039): 供 bridge 单例首建消费 (None = 用 bridge 默认值)
        self._mm_timeout = mathematica_timeout
        self._mm_use_wolframclient = mathematica_use_wolframclient
        # W2 / B-53: 搜索路径会话级 worker 的单次超时与总预算（D3 / D-W2-2）
        self._eval_timeout = eval_timeout
        self._search_budget = search_budget
        # W8 / B-60: 搜索路径 worker 的提交内存上限（0 = 关闭）
        self._memory_limit_mb = memory_limit_mb

    @property
    def bridge(self):
        """延迟加载 Mathematica 桥接器"""
        if self._bridge is None:
            try:
                from ..mathematica_bridge import get_bridge
                self._bridge = get_bridge(
                    timeout=self._mm_timeout,
                    use_wolframclient=self._mm_use_wolframclient,
                )
            except ImportError:
                self._bridge = None
        return self._bridge

    async def search(self, theorem: TheoremInput,
                     latex_assertion: LaTeXAssertion,
                     existing_test_cases: list[TestCase],
                     optimization_enabled: bool = True,
                     mathematica_enabled: bool = True,
                     max_iterations: int = 100,
                     minimal_search: bool = True,
                     grid_search_enabled: bool = True,  # D042: 接线 counterexample_grid_search_enabled
                     ) -> CounterExampleSearchResult:
        """执行系统化反例搜索"""

        counterexamples = []
        methods_used = []
        total_searched = 0
        # B-34 (D047): boundary 归因默认 (未走该分支 ⇒ 保持默认)
        boundary_finish_reason = None
        boundary_reasoning_chars = 0
        boundary_diagnosis = None

        # Step 0 (新增): Mathematica 符号搜索 — 最优先
        if mathematica_enabled and self.bridge and self.bridge.available:
            symbolic_results = await self._symbolic_counterexample_search(
                theorem, latex_assertion
            )
            if symbolic_results:
                counterexamples.extend(symbolic_results)
                methods_used.append("mathematica_symbolic")
                total_searched += 1  # 一次精确搜索

        # 收集已有的失败用例
        failed_cases = [t for t in existing_test_cases if not t.passed]

        if not failed_cases and not counterexamples:
            # 没有失败用例，尝试从边界条件搜索
            counterexamples, boundary_resp = await self._boundary_search_call(
                theorem, latex_assertion, max_iterations
            )
            methods_used.append("boundary_search")
            total_searched += max_iterations
            # B-34 (D047): 提取 boundary 调用的传输归因 (getattr 防护无属性响应)
            boundary_finish_reason = getattr(boundary_resp, "finish_reason", None)
            boundary_reasoning_chars = getattr(boundary_resp, "reasoning_chars", 0)
            boundary_diagnosis = getattr(boundary_resp, "diagnosis", None)
        else:
            # 从失败用例出发，数值搜索
            # B-35 (D048): 原 "Step 1: LLM 生成搜索方向" 为**死调用**（resp 从不被读、
            #   不产出任何反例却记 llm_directed）⇒ 已删除（含孤立的 COUNTEREXAMPLE_SEARCH_PROMPT）。

            # Step 2: 优化驱动搜索
            if optimization_enabled:
                opt_results = await self._optimization_search(
                    failed_cases[0], max_iterations
                )
                counterexamples.extend(opt_results)
                methods_used.append("optimization")
                total_searched += max_iterations

            # Step 3: 网格搜索（在失败用例附近）— D042: 由 counterexample_grid_search_enabled 开关控制
            if grid_search_enabled:
                grid_results = await self._grid_search(
                    failed_cases[0], grid_size=5
                )
                counterexamples.extend(grid_results)
                methods_used.append("grid_search")
                total_searched += 25  # 5x5 grid

        # Step 4: 寻找最小反例
        minimal = None
        if minimal_search and counterexamples:
            minimal = await self._find_minimal_counterexample(counterexamples)

        # 计算证伪置信度
        confidence = min(1.0, len(counterexamples) / 10.0) if counterexamples else 0.0

        return CounterExampleSearchResult(
            counterexamples=counterexamples,
            total_searched=total_searched,
            search_methods_used=methods_used,
            minimal_counterexample=minimal,
            falsification_confidence=confidence,
            # B-34 (D047): boundary_search 传输归因可见性 (不参与判定, 见 O-A)
            boundary_search_finish_reason=boundary_finish_reason,
            boundary_search_reasoning_chars=boundary_reasoning_chars,
            boundary_search_diagnosis=boundary_diagnosis,
            # W4/B-57 (D129, D5): 记录实际使用的种子（供事后核对）
            search_seed=self._search_seed,
        )

    async def _symbolic_counterexample_search(self, theorem: TheoremInput,
                                               latex_assertion: LaTeXAssertion) -> list[CounterExample]:
        """使用 Mathematica 进行符号反例搜索

        三阶段策略:
          1. FindInstance → 直接搜索反例
          2. Reduce → 判定不等式是否恒成立
          3. Resolve (量词消去) → 确定性判定
        """
        from ..mathematica_bridge import get_bridge
        bridge = get_bridge(
            timeout=self._mm_timeout,
            use_wolframclient=self._mm_use_wolframclient,
        )
        if not bridge.available:
            return []

        results = []
        assertion = latex_assertion.latex_statement
        # 提取变量名
        variables = self._extract_variables(assertion)

        # 提取假设条件
        hypotheses = latex_assertion.extracted_hypotheses

        # Phase 1: FindInstance — 直接搜索反例
        find_result = bridge.find_counterexample(
            assertion, variables, domain="Reals", n=5
        )
        if find_result.success and not find_result.is_true:
            # 找到反例 — 断言被证伪
            parsed = self._parse_mathematica_counterexamples(
                find_result.raw_output, assertion, "mathematica_findinstance"
            )
            results.extend(parsed)

        # Phase 2: Reduce — 判定不等式
        if not results:
            reduce_result = bridge.check_inequality(
                assertion, variables, domain="Reals"
            )
            if reduce_result.success and reduce_result.is_true == False:
                # Reduce 返回 False — 恒不成立
                # 尝试找具体反例
                find_result2 = bridge.find_counterexample(
                    assertion, variables, domain="Reals", n=1
                )
                if find_result2.success and not find_result2.is_true:
                    parsed = self._parse_mathematica_counterexamples(
                        find_result2.raw_output, assertion, "mathematica_reduce"
                    )
                    results.extend(parsed)

        # Phase 3: Resolve — 量词消去 (仅多项式)
        if not results and len(variables) <= 3:
            try:
                resolve_result = bridge.quantifier_elimination(
                    assertion, variables, domain="Reals"
                )
                if resolve_result.success and resolve_result.is_true == False:
                    results.append(CounterExample(
                        params={"verdict": "universally_false"},
                        expected=0.0, actual=1.0, deviation=1.0,
                        search_method="mathematica_resolve",
                        precondition_violated="all",
                    ))
            except (OSError, RuntimeError, ValueError, AttributeError) as exc:
                logger.debug("mathematica resolve search skipped: %s", exc)

        return results

    def _parse_mathematica_counterexamples(self, raw: str, assertion: str,
                                            method: str) -> list[CounterExample]:
        """解析 Mathematica FindInstance 返回的反例

        格式:
          {True, {{x -> 1, y -> 2}, {x -> -1, y -> 3}}}  ← 找到反例
          {False, {}}                                       ← 未找到反例
        """
        import re
        results = []
        if not raw:
            return results
        try:
            # 判断是否找到反例 (FindInstance 返回 True 表示找到反例)
            if not raw.strip().startswith("{True"):
                return results

            # 提取所有 {x -> val, y -> val} 分组 (不含嵌套大括号)
            group_pattern = r'\{[^{}]*\}'
            # 跳过外层 {True, 找到内层 {{x -> ...}, ...} 部分
            comma_idx = raw.index(",")
            inner_start = raw.index("{", comma_idx + 1)
            inner = raw[inner_start:]
            groups = re.findall(group_pattern, inner)

            for group in groups:
                params = {}
                for m in re.finditer(r'(\w+)\s*->\s*([\d.eE+\-]+)', group):
                    try:
                        params[m.group(1)] = float(m.group(2))
                    except ValueError:
                        continue
                if params:
                    results.append(CounterExample(
                        params=params,
                        expected=0.0,  # Mathematica 反例不需要 expected/actual
                        actual=1.0,
                        deviation=1.0,
                        search_method=method,
                        precondition_violated="assertion_falsified_by_mathematica",
                    ))
        except (ValueError, IndexError):
            pass
        return results

    @staticmethod
    def _extract_variables(assertion: str) -> list[str]:
        """从 LaTeX 断言中提取变量名"""
        import re
        # 匹配常见变量模式: 单个字母或带下标的字母
        # 排除常见函数名和希腊字母
        reserved = {"sin", "cos", "tan", "log", "exp", "sqrt", "sum", "prod",
                     "int", "lim", "max", "min", "infty", "partial", "nabla",
                     "alpha", "beta", "gamma", "delta", "epsilon", "theta",
                     "lambda", "mu", "sigma", "omega", "Phi", "Psi", "Omega"}
        vars_found = set()
        # 匹配 \mathbf{X}, \boldsymbol{\beta}, x_i, X, Y 等
        for pattern in [r'\\mathbf\{([A-Za-z]+)\}', r'\\boldsymbol\{\\([a-z]+)\}',
                         r'([A-Za-z])_\{[^}]+\}', r'(?<!\\)([A-Za-z])(?![\w\{])']:
            for m in re.finditer(pattern, assertion):
                v = m.group(1)
                if v.lower() not in reserved and len(v) <= 3:
                    vars_found.add(v)
        return sorted(vars_found) if vars_found else ["x", "y"]

    async def _optimization_search(self, seed_case: TestCase,
                                    max_iter: int) -> list[CounterExample]:
        """优化驱动的反例搜索 — 使用 scipy.optimize.minimize

        构造目标函数 objective(x) = |computed(params) - expected|,
        用 Nelder-Mead 在种子反例附近搜索最小偏差点.
        若最小偏差 > tolerance, 该点为反例.
        无 computed_expr 时返回空列表 (不再用随机 actual).
        """
        if seed_case.computed_expr is None:
            return []

        try:
            import numpy as np
            from scipy.optimize import minimize
        except ImportError:
            return []

        param_names = list(seed_case.params.keys())
        if not param_names:
            return []

        seed_values = np.array([float(seed_case.params[k]) for k in param_names])

        # W2 / B-53 (D3): 搜索路径 = **会话级 worker**（一次搜索一个进程），
        # 单次超时 + 搜索总预算；表达式违规/超时/崩溃均走 objective 的惩罚分支。
        results = []
        # W4/B-57 (D129, D4): 局部生成器（固定种子）⇒ 反例集可复现。
        #   ⚠ 不用 np.random.seed / np.random.normal（全局 RNG, 与 W2 逐例隔离冲突）。
        rng = np.random.default_rng(self._search_seed)
        with SafeEvaluator(timeout_s=self._eval_timeout,
                           total_budget_s=self._search_budget,
                           memory_limit_mb=self._memory_limit_mb) as ev:
            def objective(x):
                params = dict(zip(param_names, x))
                try:
                    computed = ev.evaluate(params, seed_case.computed_expr)
                    return abs(float(computed) - seed_case.expected)
                except (EvaluationError, ArithmeticError, TypeError, ValueError):
                    return 1e10  # 惩罚不可行点

            for i in range(min(max_iter, 10)):
                if ev.budget_exhausted():
                    break
                x0 = seed_values + rng.normal(0.0, 0.1, len(seed_values))
                res = minimize(objective, x0, method="Nelder-Mead",
                              options={"maxiter": 100, "xatol": 1e-6})
                if res.fun > seed_case.tolerance:
                    params = dict(zip(param_names, res.x))
                    # actual 用 computed_expr 在最优点的真实值 (非随机)
                    try:
                        actual = ev.evaluate(params, seed_case.computed_expr)
                    except (EvaluationError, ArithmeticError, TypeError, ValueError):
                        actual = float(seed_case.expected + res.fun)
                    results.append(CounterExample(
                        params={k: float(v) for k, v in params.items()},
                        expected=seed_case.expected,
                        actual=actual,
                        deviation=float(res.fun),
                        relative_deviation=float(res.fun / max(abs(seed_case.expected), 1e-10)),
                        search_method="optimization",
                        discovery_iteration=i,
                    ))
        return results

    async def _grid_search(self, seed_case: TestCase,
                            grid_size: int = 5) -> list[CounterExample]:
        """在种子反例附近进行网格搜索

        D5 修复: actual 用 computed_expr 真实计算 (非随机).
        无 computed_expr 时回退到 seed_case.actual.
        """
        results = []
        try:
            import numpy as np
        except ImportError:
            return results

        seed_params = seed_case.params
        param_names = list(seed_params.keys())
        if not param_names:
            return results

        base_values = np.array([float(seed_params[k]) for k in param_names])
        ranges = []
        for v in base_values:
            if abs(v) < 1e-10:
                ranges.append(np.linspace(-1, 1, grid_size))
            else:
                ranges.append(np.linspace(0.5 * v, 1.5 * v, grid_size))

        import itertools
        sampled = 0
        # W2 / B-53 (D3): 会话级 worker + 搜索预算（同 `_optimization_search`）
        with SafeEvaluator(timeout_s=self._eval_timeout,
                           total_budget_s=self._search_budget,
                           memory_limit_mb=self._memory_limit_mb) as ev:
            for combo in itertools.product(*ranges):
                if sampled >= 25 or ev.budget_exhausted():
                    break
                new_params = {k: float(v) for k, v in zip(param_names, combo)}

                # D5 修复: actual 来自 computed_expr (非随机)
                if seed_case.computed_expr:
                    try:
                        actual = ev.evaluate(new_params, seed_case.computed_expr)
                    except (EvaluationError, ArithmeticError, TypeError, ValueError):
                        actual = seed_case.actual
                else:
                    actual = seed_case.actual  # 回退到已知值

                deviation = abs(actual - seed_case.expected)

                if deviation > seed_case.tolerance:
                    results.append(CounterExample(
                        params=new_params,
                        expected=seed_case.expected,
                        actual=float(actual),
                        deviation=float(deviation),
                        relative_deviation=float(deviation / max(abs(seed_case.expected), 1e-10)),
                        search_method="grid_search",
                    ))
                sampled += 1

        return results

    async def _search_from_boundary(self, theorem: TheoremInput,
                                     latex_assertion: LaTeXAssertion,
                                     max_iter: int) -> list[CounterExample]:
        """从边界条件搜索反例（无已知失败用例时）

        让 LLM 生成极端参数组合, 复用 _parse_test_cases / _run_test_cases 流水线.
        失败用例转为 CounterExample (search_method="boundary").

        B-34 (D047): **薄包装** —— 保持既有签名/返回类型 (D6 回归 7 处直调依赖);
        实际调用与传输归因提取在 `_boundary_search_call`。
        """
        counterexamples, _resp = await self._boundary_search_call(
            theorem, latex_assertion, max_iter)
        return counterexamples

    async def _boundary_search_call(self, theorem: TheoremInput,
                                    latex_assertion: LaTeXAssertion,
                                    max_iter: int):
        """B-34 (D047): 原 `_search_from_boundary` 逻辑; 额外返回 ModelResponse
        (供上层用 getattr 提取传输归因 finish_reason/reasoning_chars/diagnosis)。
        """
        n_cases = min(max_iter, 10)
        prompt = f"""Generate {n_cases} extreme parameter combinations
to test the assertion: {theorem.nl_statement}
LaTeX: {latex_assertion.latex_statement}
Focus on boundary conditions where the assertion might fail.

Output format (Python code, each case separated by '# ---'):
# Test case: <description>
params = {{"x": value, ...}}
expected = <value>
computed = <expression using params variables>
tolerance = 0.01
"""
        resp = await self.gateway.call_reasoner(
            prompt, "boundary_search", temperature=0.3
        )
        test_cases = self._verifier._parse_test_cases(resp.text, n_cases)
        test_cases = await self._verifier._run_test_cases(test_cases)

        counterexamples = [
            CounterExample(
                params=tc.params,
                expected=tc.expected,
                actual=tc.actual,
                deviation=abs(tc.actual - tc.expected),
                search_method="boundary",
            )
            for tc in test_cases if not tc.passed
        ]
        # B-34 (D047): 上抛 resp 供 `search()` 提取传输归因
        return counterexamples, resp

    async def _find_minimal_counterexample(self,
                                            counterexamples: list[CounterExample]) -> CounterExample | None:
        """从反例列表中识别最小反例"""
        if not counterexamples:
            return None
        if len(counterexamples) == 1:
            ce = counterexamples[0]
            ce.is_minimal = True
            ce.minimality_evidence = "Only one counterexample found."
            return ce

        # 使用 LLM 判断最小反例
        ce_str = "\n".join(
            f"  [{i}] params={ce.params}, deviation={ce.deviation:.4f}"
            for i, ce in enumerate(counterexamples[:10])
        )

        prompt = MINIMAL_COUNTEREXAMPLE_PROMPT.format(
            counterexamples=ce_str,
        )

        resp = await self.gateway.call_auxiliary(
            prompt, "minimal_counterexample", temperature=0.05
        )

        # 解析最小反例索引
        minimal_idx = 0
        reason = ""
        for line in resp.text.split("\n"):
            line = line.strip()
            if line.upper().startswith("MINIMAL_INDEX:"):
                try:
                    minimal_idx = int(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif line.upper().startswith("MINIMALITY_REASON:"):
                reason = line.split(":", 1)[1].strip()

        if 0 <= minimal_idx < len(counterexamples):
            ce = counterexamples[minimal_idx]
            ce.is_minimal = True
            ce.minimality_evidence = reason
            return ce

        # 启发式：选择偏差最小的反例
        best = min(counterexamples, key=lambda c: c.deviation)
        best.is_minimal = True
        best.minimality_evidence = "Heuristic: smallest deviation from expected."
        return best
