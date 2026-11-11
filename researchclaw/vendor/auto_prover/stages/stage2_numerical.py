"""Stage 2: 数值推论验证（门面）。

本模块在 W12 / B-58 拆分后保留**公开 API 与导入路径**：
  - 实现: `numerical_core`（纯函数）/ `numerical_calibration`（校准监控）/
          `counterexample_search`（反例搜索）
  - 本文件保留: `TESTGEN_PROMPT` + `NumericalVerifier`
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
    COUNTEREXAMPLE_SEARCH_SEED,
    DEFAULT_CASE_SEED,
    _VALID_KINDS,
    effective_tolerance,
    has_random_source,
    is_degenerate,
    is_degenerate_dependent,
)
from .numerical_calibration import (
    BAND_WIDEN_RATIO_CAP,
    CALIBRATION_BOOTSTRAP_B,
    CALIBRATION_BOOTSTRAP_SEED,
    CALIBRATION_MEAN_Z_MAX,
    CALIBRATION_MIN_CLUSTERS,
    CALIBRATION_MIN_N,
    CALIBRATION_NOMINAL_P,
    CALIBRATION_OUTLIER_ALPHA,
    CALIBRATION_STD_Z_BAND,
    POISSON_LAMBDA_MAX,
    CalibrationReport,
    allowed_outliers,
    assess_std_err_calibration,
    attribute_gate_trigger,
    cluster_bootstrap_ci,
    consecutive_verdict,
    poisson_upper_tail,
)
from .counterexample_search import (
    MINIMAL_COUNTEREXAMPLE_PROMPT,
    CounterExampleSearcher,
)



TESTGEN_PROMPT = """【任务】为以下断言生成 Python 数值测试用例。

【断言（自然语言）】
{nl_statement}

【断言（LaTeX）】
{latex_statement}

【要求】
1. 生成 {n_cases} 个测试用例，覆盖:
   - 典型情况（常规参数）
   - 边界情况（极端参数值，但仍在断言前提成立的范围内）
2. 每个测试用例用 Python 代码表示，格式:
   # <简短描述>
   params = {{...}}          # 输入参数字典
   expected = <数字字面量>    # 断言预测值
   computed = <单行表达式>    # 实际计算值
   tolerance = <数字>         # 允许的误差
   std_err = <数字>           # computed 的标准误 (估计量的标准差)
   kind = <断言类别>          # 必填, 见下方"断言类别"
3. 使用 numpy 进行数值计算（不要 import，直接用 np.*）

【断言类别】每个用例**必须**声明 kind（裸词, 不要加引号）, 取以下之一:
   deterministic_identity | combinatorial | expectation | variance | moment | distributional | asymptotic
   说明: 按断言**本身的性质**选择, 与具体数值无关。

【硬性格式约束】(违反将导致解析失败)
- expected 必须是**数字字面量**（如 0.0 / 5.0 / 2.0 / 1e-6），禁止写 params["x"]、变量名或 np.nan
- computed 必须是**单行**表达式，只引用 params 的键名与 np.*，不要引用未定义的中间变量
- tolerance 必须是数字（如 0.01 / 1e-9），不要用 np.inf
- **std_err 必须是数字字面量**: computed 的**标准误** (估计量的标准差)。
  - computed 含随机抽样时 **必须给出** (例: 均值估计 sigma/sqrt(n*reps)、均值估计 sigma/sqrt(n))
  - computed 为确定性表达式时写 0.0
  - 在注释里写出推导 (供人工审计)
- 每个测试用例之间**必须**用单独一行 `# ---` 分隔
- **不要**使用 ``` 代码围栏

【退化情况】只生成"断言的前提成立时应当**数值通过**"的用例。
禁止生成"前提被违反故必然失败"的用例（如均值不存在的重尾分布）—— 那属于反例搜索的职责，本阶段不启用。
⚠ 若某个参数的极端取值使 computed 的输出**与数据无关**（结果恒等于 expected、不随样本变化），
必须在该用例的注释里显式标注 `# 退化: <原因>`。这类用例**不承载证伪力**；未标注视为无效用例。

【容差纪律】若 computed 含随机抽样（如 np.random.*），其结果是**点估计**，tolerance 必须覆盖抽样误差：
**tolerance 必须与 std_err 匹配**：取 `tolerance ≈ 1–3 × std_err`，且**必须给出 std_err**（判定用 k=3 的统计带 k×std_err，二者同量级即可）。
⚠ 不要写与 std_err 无关的**固定值**当 tolerance（例如一律写 0.05 / 0.1）——当 std_err 很小时，
判定带会比抽样误差宽上百倍，该用例将**不可能失败**，验证失去意义。
⚠ 不要为了绕开容差而把 computed 改成与 expected 同源的**确定性表达式**（如 np.full(n, mu)、np.linspace 对称数组）——
那会退化成恒等检查（均值恒等于自身），验证不了任何命题，属于无效用例。
判定依据是「computed 是否**依赖数据**」：断言涉及期望/分布时，用与数据无关的常量表达式代替抽样即为绕开。

【完整示例】
# 典型: 标准正态, n=1000, 标准误 = sigma/sqrt(n) = 2.0/31.62 = 0.0632
params = {{"mu": 5.0, "sigma": 2.0, "n": 1000, "seed": 1}}
expected = 5.0
computed = np.mean(np.random.default_rng(params["seed"]).normal(loc=params["mu"], scale=params["sigma"], size=params["n"]))
tolerance = 0.1
std_err = 0.0632
# ---
# 边界: 单样本 (n=1), 标准误 = sigma/sqrt(1) = 1.0
params = {{"mu": 0.0, "sigma": 1.0, "n": 1, "seed": 2}}
expected = 0.0
computed = np.mean(np.random.default_rng(params["seed"]).normal(loc=params["mu"], scale=params["sigma"], size=params["n"]))
tolerance = 1.0
std_err = 1.0

【输出格式】只输出上述用例块，每个测试用例之间用单独一行 `# ---` 分隔。
"""



class NumericalVerifier:
    """Stage 2: 数值推论验证"""

    def __init__(self, gateway: ModelGateway,
                 eval_timeout: float = DEFAULT_TIMEOUT_S,
                 batch_budget: float = DEFAULT_BATCH_BUDGET_S,
                 search_budget: float = DEFAULT_SEARCH_BUDGET_S,
                 memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB):
        self.gateway = gateway
        # W2 / B-53 (D6 / D-W2-2): 求值超时与预算（pipeline 由 config 注入；
        # 直接构造的测试/调用方取默认值 2.0 / 10.0 / 30.0）。
        self._eval_timeout = eval_timeout
        self._batch_budget = batch_budget
        self._search_budget = search_budget
        # W8 / B-60: worker 提交内存上限（0 = 关闭）
        self._memory_limit_mb = memory_limit_mb

    async def verify(self,
                     theorem: TheoremInput,
                     latex_assertion: LaTeXAssertion,
                     n_cases: int = 10,
                     pass_threshold: float = 0.8,
                     rel_tolerance_floor: float = 0.0,
                     std_err_k: float = 0.0,
                     counterexample_search_enabled: bool = True,
                     mathematica_enabled: bool = True,
                     mathematica_timeout: float | None = None,
                     mathematica_use_wolframclient: bool | None = None,
                     optimization_enabled: bool = True,
                     max_iterations: int = 100,
                     minimal_search: bool = True,
                     grid_search_enabled: bool = True,  # D042: 接线 counterexample_grid_search_enabled
                     ) -> NumericalVerification:
        """运行数值验证"""

        # Step 1: 生成测试用例
        prompt = TESTGEN_PROMPT.format(
            nl_statement=theorem.nl_statement,
            latex_statement=latex_assertion.latex_statement,
            n_cases=n_cases,
        )
        resp = await self.gateway.call_reasoner(
            prompt, "testgen", temperature=0.3
        )
        # B-33 (D046): 承接 gateway 传输归因 (D045); getattr 防护旧 Mock (无此属性 ⇒ 默认值)
        testgen_finish_reason = getattr(resp, "finish_reason", None)
        testgen_reasoning_chars = getattr(resp, "reasoning_chars", 0)
        testgen_diagnosis = getattr(resp, "diagnosis", None)

        # Step 2: 解析测试用例
        test_cases = self._parse_test_cases(resp.text, n_cases)

        # Step 3: 执行数值计算 (W2 / B-53: 逐例 worker + 单例/整批双超时)
        # ⚠ 保持**原调用形态**（只传两个旧关键字）: `_run_test_cases` 是既有
        #   10 个测试文件的 monkeypatch 点，超时经实例属性解析（见该方法）。
        test_cases = await self._run_test_cases(
            test_cases, rel_tolerance_floor=rel_tolerance_floor,
            std_err_k=std_err_k)

        # Step 4: 判定 (G03: 阈值由 config 注入, 不再硬编码)
        pass_count = sum(1 for t in test_cases if t.passed)
        pass_rate = pass_count / max(len(test_cases), 1)

        if pass_rate >= pass_threshold:
            verdict = NumericalVerdict.PASSED
        elif pass_rate >= 0.5:
            verdict = NumericalVerdict.PARTIAL
        else:
            verdict = NumericalVerdict.FAILED

        failure_analysis = self._analyze_failures(test_cases)

        # Step 5 (新增): 系统化反例搜索
        counterexample_result = None
        if counterexample_search_enabled and verdict != NumericalVerdict.PASSED:
            searcher = CounterExampleSearcher(
                self.gateway,
                mathematica_timeout=mathematica_timeout,
                mathematica_use_wolframclient=mathematica_use_wolframclient,
                eval_timeout=getattr(self, "_eval_timeout", DEFAULT_TIMEOUT_S),
                search_budget=getattr(self, "_search_budget", DEFAULT_SEARCH_BUDGET_S),
                memory_limit_mb=getattr(
                    self, "_memory_limit_mb", DEFAULT_MEMORY_LIMIT_MB),
            )
            counterexample_result = await searcher.search(
                theorem, latex_assertion, test_cases,
                optimization_enabled=optimization_enabled,
                mathematica_enabled=mathematica_enabled,
                max_iterations=max_iterations,
                minimal_search=minimal_search,
                grid_search_enabled=grid_search_enabled,
            )
            if counterexample_result.counterexamples:
                verdict = NumericalVerdict.FAILED
                failure_analysis += (
                    f"\n\n[Counterexample Search] Found {len(counterexample_result.counterexamples)} "
                    f"counterexamples via {counterexample_result.search_methods_used}."
                )

        # T4/D030 (D040): 语义级判定可见性汇总 (⚠ 不参与 verdict/pass_rate, 见 O-A)
        n_circular = sum(
            1 for t in test_cases
            if t.semantic_verdict == SemanticVerdict.CIRCULAR.value)
        semantic_review_flags = (
            [f"{n_circular} circular (恒等检查) case(s) detected"] if n_circular else [])

        # W4/B-57 (D129, D6/D7): 证据来源聚合 + 数值侧 flags
        #   ⚠ 在 verdict / pass_rate 定值**之后**写入 (O-A, 镜像 D046)。
        #   ⚠ 新建 numerical_review_flags, **不写** semantic_review_flags (口径隔离)。
        evidence_source_counts: dict[str, int] = {}
        for t in test_cases:
            evidence_source_counts[t.evidence_source] = (
                evidence_source_counts.get(t.evidence_source, 0) + 1)
        numerical_review_flags: list[str] = []
        for i, t in enumerate(test_cases):
            if t.seed_source == "injected":
                numerical_review_flags.append(f"case#{i}:no_seed")
            if has_random_source(t.computed_expr) and (t.std_err is None or t.std_err <= 0):
                numerical_review_flags.append(f"case#{i}:no_std_err")

        # W5/B-57 S-c (D135, D1/D7): expected 独立复算
        #   ⚠ 同样在 verdict / pass_rate 定值之后；只写可见性 (O-A / D-W5-4)。
        #   ⚠ flags 段序: W4 段在前、oracle 段在后 (CHECKLIST D3)。
        oracle_summary, oracle_flags = self._check_expected_oracle(
            test_cases, rel_tolerance_floor=rel_tolerance_floor,
            std_err_k=std_err_k)
        numerical_review_flags.extend(oracle_flags)

        return NumericalVerification(
            test_cases=test_cases,
            pass_rate=pass_rate,
            verdict=verdict,
            failure_analysis=failure_analysis,
            counterexample_search=counterexample_result,
            n_circular=n_circular,
            semantic_review_flags=semantic_review_flags,
            # B-33 (D046): Stage2 传输归因可见性 (不参与 verdict/pass_rate, 见 O-A)
            testgen_finish_reason=testgen_finish_reason,
            testgen_reasoning_chars=testgen_reasoning_chars,
            testgen_diagnosis=testgen_diagnosis,
            evidence_source_counts=evidence_source_counts,
            numerical_review_flags=numerical_review_flags,
            oracle_summary=oracle_summary,
        )

    def _check_expected_oracle(
            self, test_cases: list[TestCase],
            rel_tolerance_floor: float = 0.0,
            std_err_k: float = 0.0) -> tuple[dict, list[str]]:
        """W5/B-57 S-c (D1/D6/I4): expected 独立复算（四态 + flags）。

        W7/D7: 两个关键字默认参数透传给 `check_case` / `summarize`
        （默认 0.0 ⇒ 旧调用逐值等价；生产由 `verify()` 注入 config 值）。
        ⚠ O-A: 调用点在 verdict / pass_rate 定值之后；返回值只写可见性。
        ⚠ I4 失败安全: 会话级异常 ⇒ 未完成的用例一律 ``unrecognized(oracle_invalid)``，
          不抛给上游、不影响判定。
        """
        results: list[dict] = []
        try:
            with SafeEvaluator(
                    timeout_s=getattr(self, "_eval_timeout", DEFAULT_TIMEOUT_S),
                    memory_limit_mb=getattr(
                        self, "_memory_limit_mb", DEFAULT_MEMORY_LIMIT_MB)) as ev:
                for i, tc in enumerate(test_cases):
                    results.append(_oracle_check_case(
                        i, tc, ev, rel_tolerance_floor=rel_tolerance_floor,
                        std_err_k=std_err_k))
        except Exception:  # broad-ok: SafeEvaluator/worker 外部异常不可枚举（I4 失败安全，补齐 unrecognized）
            done = {r["index"] for r in results}
            for i, tc in enumerate(test_cases):
                if i in done:
                    continue
                results.append({
                    "index": i,
                    "status": "unrecognized",
                    "dist": None,
                    "reason": "oracle_invalid",
                    "expected": tc.expected,
                    "mu": None,
                    "delta": None,
                    "tolerance_used": None,
                    # W6/D9 (DEV1): 与 `_result` 同一键集（该路径手工构造 dict）。
                    "tolerance_ratio": None,
                    # W7/D1 (DEV14): 同键集 +1（未识别 ⇒ 生产读数 None，不写 0）。
                    "production_ratio": None,
                })
        results.sort(key=lambda r: r["index"])
        # W7/§4.3 (DEV14): actual 缺失近似须落在汇总块（逐例键集不变）。
        actual_missing = sum(
            1 for r, tc in zip(results, test_cases)
            if r["status"] in ("match", "mismatch") and tc.actual is None)
        return (_oracle_summarize(
            results, rel_tolerance_floor=rel_tolerance_floor,
            std_err_k=std_err_k, actual_missing=actual_missing), _oracle_flags(results))

    def _parse_test_cases(self, text: str, expected_count: int) -> list[TestCase]:
        """
        解析 LLM 生成的 Python 测试用例

        提取 params, expected, computed_expr, tolerance
        """
        test_cases = []
        blocks = text.split("# ---")

        for block in blocks:
            if not block.strip():
                continue

            # 提取 Python 变量
            params = self._extract_dict(block, "params")
            expected = self._extract_number(block, "expected")
            tolerance = self._extract_number(block, "tolerance") or 0.01
            std_err = self._extract_number(block, "std_err")   # B-17/B-18: 可选
            computed_expr = self._extract_expr(block, "computed")
            kind = self._extract_kind(block)                   # T4/D030: 可选 (缺失降级)

            if params is not None and expected is not None:
                # W4/B-57 (D129, D2/D3): 种子治理 —— 单一构造点注入。
                #   ⚠ 必须**写回 params**: computed 表达式读的是 params["seed"],
                #     只记 TestCase.seed 而不写回 ⇒ 种子对执行无效 (D128 ①)。
                #   LLM 显式声明的 seed 优先（不改写）。
                if "seed" in params:
                    seed, seed_source = params["seed"], "llm"
                else:
                    seed, seed_source = DEFAULT_CASE_SEED, "injected"
                    params["seed"] = seed
                test_cases.append(TestCase(
                    params=params,
                    expected=expected,
                    actual=0.0,  # 将在 _run_test_cases 中填充
                    tolerance=tolerance,
                    passed=False,
                    computed_expr=computed_expr,
                    std_err=std_err,
                    kind=kind,
                    seed=seed,
                    seed_source=seed_source,
                ))

        return test_cases[:expected_count]

    @staticmethod
    def _extract_kind(text: str) -> str | None:
        """提取断言类别 `kind = <值>` (T4/D030)。

        缺失或非法值 ⇒ `None`（**降级**: 语义判定不生效, 现行语义不变）。
        合法集合 = `AssertionKind` 的 `.value`（小写, 与枚举约定一致）。
        """
        import re
        m = re.search(r"^\s*kind\s*=\s*([A-Za-z_]+)", text, re.MULTILINE)
        if not m:
            return None
        val = m.group(1)
        return val if val in _VALID_KINDS else None

    async def _run_test_cases(self, test_cases: list[TestCase],
                              rel_tolerance_floor: float = 0.0,
                              std_err_k: float = 0.0,
                              *,
                              eval_timeout: float | None = None,
                              batch_budget: float | None = None,
                              ) -> list[TestCase]:
        """
        执行数值计算

        使用 LLM 生成的 computed_expr 计算实际值。
        缺失 computed_expr 时标记为失败 (不产生假成功)。

        W2 / B-53 (D-W2-1 = S2): **逐例 worker** —— 每个 TestCase 一个子进程，
        主求值与 `judge_test_case` 的探针**共用**该 worker（同一求值口径）。
        逐例而非整批: 防止前例的进程内状态（如 `np.seterr`）污染后例判定。

        rel_tolerance_floor (D025 方案 C, 默认 0.0 = 关闭):
          判定改用尺度感知容差 ``max(tolerance, floor × max(|expected|, |actual|))``。
          动机 (实测证据): 模型常对蒙特卡洛点估计给出小于抽样误差的绝对容差
          (如 exp=-10 配 tol=1e-9), 且绝对容差在大量级下尺度失配
          (如 exp=1e6 配 tol=0.2 而偏差 4831 → 相对仅 0.48%)。
          单调性: 因 effective_tol ≥ tolerance 恒成立, 该参数只会把 fail 翻为 pass,
          **不会新增失败** ⇒ 不产生新假阴性, 但可产生假阳性 ⇒ 阈值须显式且保守。
          expected=0 时 scale 取自 |actual|, 相对容差仍有定义。

        std_err_k (B-17/B-18, 默认 0.0 = 关闭):
          追加统计分支 ``tol_stat = std_err_k × tc.std_err`` (std_err 由 LLM 声明)。
          动机: 相对容差在 ``expected=0`` 处**结构性失效** (任意偏差对 0 都是 100%),
          而标准误在 0 处仍有定义; 且 MC 噪声随 σ/√N 变化, 固定容差不是统计检验。
          同样单调 (取 max)。std_err 未声明或 ≤0 时该分支不生效 (不劣于现状)。

        eval_timeout / batch_budget (W2 / D6 / D-W2-2):
          单例墙钟上限与整批预算（默认 2.0 s / 10.0 s，由 `NumericalVerifier`
          构造参数注入）。批预算耗尽后**剩余用例一律 fail-closed** 记为
          ``batch budget exceeded``（不假通过、不重试）。
        """
        if eval_timeout is None:
            eval_timeout = getattr(self, "_eval_timeout", DEFAULT_TIMEOUT_S)
        if batch_budget is None:
            batch_budget = getattr(self, "_batch_budget", DEFAULT_BATCH_BUDGET_S)
        deadline = time.monotonic() + batch_budget
        for tc in test_cases:
            if tc.computed_expr is None:
                tc.passed = False
                tc.error_message = "No computed_expr provided by LLM"
                continue
            if time.monotonic() > deadline:
                tc.passed = False
                tc.error_message = "batch budget exceeded"
                continue
            try:
                # 逐例 worker（D-W2-1 S2）: 用例间零状态共享。
                with SafeEvaluator(
                        timeout_s=eval_timeout,
                        memory_limit_mb=getattr(
                            self, "_memory_limit_mb", DEFAULT_MEMORY_LIMIT_MB)) as ev:
                    tc.actual = ev.evaluate(
                        tc.params, tc.computed_expr, tc.expected, tc.tolerance)
                    deviation = abs(tc.actual - tc.expected)
                    # 容差口径统一在 effective_tolerance (判定与 B-19/B-20 监控共用)
                    effective_tol = effective_tolerance(
                        tc.expected, tc.actual, tc.tolerance, tc.std_err,
                        rel_tolerance_floor, std_err_k,
                    )
                    tc.passed = deviation <= effective_tol
                    # D029: 标记退化用例 (与监控共用 is_degenerate 口径)。只标记, 不影响判定。
                    tc.degenerate = is_degenerate(
                        tc.expected, tc.actual, tc.std_err, tc.error_message)
                    # T4/D030 (D040): 语义级判定 (Tier1 探针 + Tier2 静态表)。
                    # ⚠ 仅写可见性字段, **不改** passed / verdict (O-A)。
                    fals, sem = judge_test_case(
                        tc, lambda p, e, _tc=tc: ev.evaluate(
                            p, e, _tc.expected, _tc.tolerance))
                    tc.falsifiability = fals.value
                    tc.semantic_verdict = sem.value
            except Exception as e:  # broad-ok: 单例求值/语义探针外部异常不可枚举（记为 exec failed）
                tc.error_message = f"exec failed: {e}"
                tc.passed = False

        return test_cases

    @staticmethod
    def _eval_computed(params: dict, computed_expr: str,
                       expected: float = 0.0, tolerance: float = 0.0,
                       *, evaluator: SafeEvaluator | None = None) -> float:
        """受限求值 (T4/D040 抽出; W2/B-53 改为委托 :class:`SafeEvaluator`)。

        兼容契约 (D10): 签名与返回值不变；`evaluator=None` ⇒ 临时 worker
        （逐例语义，`with` 结束即销毁）。传入 `evaluator` 时复用会话 worker
        （判定路径逐例复用 = 主求值与语义探针同一口径）。

        既有语义保留: 局部名展开 `params` 的键 + `expected`/`tolerance`，
        globals 仅 `np` 且 `__builtins__` 置空。
        """
        if evaluator is None:
            with SafeEvaluator(
                    timeout_s=DEFAULT_TIMEOUT_S,
                    memory_limit_mb=DEFAULT_MEMORY_LIMIT_MB) as ev:
                return ev.evaluate(params, computed_expr, expected, tolerance)
        return evaluator.evaluate(params, computed_expr, expected, tolerance)

    def _analyze_failures(self, test_cases: list[TestCase]) -> str:
        """分析失败原因"""
        failures = [t for t in test_cases if not t.passed]
        if not failures:
            return "All tests passed."

        lines = [f"{len(failures)}/{len(test_cases)} tests failed:"]
        for tc in failures:
            lines.append(
                f"  - params={tc.params}: expected={tc.expected}, "
                f"actual={tc.actual}, tolerance={tc.tolerance}"
            )
            if tc.error_message:
                lines.append(f"    error: {tc.error_message}")
        return "\n".join(lines)

    @staticmethod
    def _extract_dict(text: str, var_name: str) -> dict | None:
        """从文本中提取字典变量

        使用括号深度匹配 + ast.literal_eval, 正确处理嵌套结构
        (列表、元组、嵌套字典)。ast.literal_eval 只解析字面量,
        不执行代码, 安全可靠。
        """
        import re
        import ast

        # 定位 var_name = { 的位置
        pattern = rf'{var_name}\s*=\s*\{{'
        match = re.search(pattern, text)
        if not match:
            return None

        # 从 { 开始, 用括号深度匹配找到完整的字典字面量
        start = match.end() - 1  # 指向 {
        depth = 0
        end = -1
        for i in range(start, len(text)):
            c = text[i]
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        if end == -1:
            return None  # 括号不匹配

        try:
            result = ast.literal_eval(text[start:end])
            if isinstance(result, dict) and result:
                return result
            return None
        except (ValueError, SyntaxError):
            return None

    @staticmethod
    def _extract_number(text: str, var_name: str) -> float | None:
        """从文本中提取数值"""
        import re
        pattern = rf'{var_name}\s*=\s*([\d.e+\-]+)'
        match = re.search(pattern, text)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        return None

    @staticmethod
    def _extract_expr(text: str, var_name: str) -> str | None:
        """提取 var_name = <表达式> 行

        跳过注释行和 Mock 占位 (computed = expected)。
        只返回第一个匹配的表达式。
        """
        import re
        pattern = rf'^{var_name}\s*=\s*(.+?)\s*(?:#.*)?$'
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("#"):
                continue
            m = re.match(pattern, line)
            if m:
                expr = m.group(1).strip()
                # 排除 Mock 占位: computed = expected
                if expr == "expected":
                    continue
                return expr
        return None
