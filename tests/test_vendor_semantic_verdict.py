# SPDX-License-Identifier: Apache-2.0
# Vendored from Auto_Prover tests/test_semantic_verdict.py at bd95f02.
# Modified by AutoResearchClaw on 2026-11-11: imports point at the vendored kernel.
"""T4 / D040: 语义级判定 (D030 落地) —— Tier1 证伪力探针 + Tier2 类别矩阵

依据: DESIGN_AGENT_CLI_SEMANTIC_VERDICT.md §6 / IMPL §7。
要点:
  - Tier1 **机械**探针 (零 LLM): 扰动随机源键 / 重复执行 ⇒ VARYING | CONSTANT | UNKNOWN;
  - Tier2 **静态表** (零 LLM): `kind` × 证伪力 ⇒ VALID_DETERMINISTIC | CIRCULAR | UNKNOWN;
  - 降级: `kind` 缺失/非法 或 探针不可用 ⇒ UNKNOWN ⇒ **现行判定语义不变**。

⚠ 防自验证: 判据不含 LLM 生成内容; `kind` 由 generator 声明 (判据侧不得推断)。
"""
from __future__ import annotations

import pytest

from researchclaw.vendor.auto_prover.datatypes import (
    AssertionKind,
    Falsifiability,
    LaTeXAssertion,  # noqa: F401  (集成测试预留)
    NumericalVerdict,
    SemanticVerdict,
    TestCase,
    TheoremInput,
)
from researchclaw.vendor.auto_prover.semantic_verdict import (
    RANDOM_SOURCE_KEYS,
    judge_semantic,
    judge_test_case,
    probe_falsifiability,
)


# ---------------------------------------------------------------------------
# Tier 1 — 证伪力探针
# ---------------------------------------------------------------------------

class TestTier1FalsifiabilityProbe:
    def test_deterministic_expr_is_constant(self):
        """确定性表达式 (输出与 params 无关的重复不变) ⇒ CONSTANT"""
        params = {"n": 10, "mu": 0}
        fals = probe_falsifiability(params, "mu + 0", lambda p, e: float(p["mu"]))
        assert fals is Falsifiability.CONSTANT

    def test_seed_dependent_expr_is_varying(self):
        """params 含随机源键且输出依赖它 ⇒ 扰动后变化 ⇒ VARYING"""
        params = {"seed": 1, "n": 10}
        fals = probe_falsifiability(
            params, "seed * 1.0", lambda p, e: float(p["seed"]) * 1.0)
        assert fals is Falsifiability.VARYING

    def test_repeat_detects_variability_without_seed_key(self):
        """无随机源键, 但表达式内含随机性 (重复执行结果不同) ⇒ VARYING"""
        counter = {"i": 0}

        def flaky(p, e):
            counter["i"] += 1
            return float(counter["i"])

        fals = probe_falsifiability({"n": 5}, "np.random.rand()", flaky)
        assert fals is Falsifiability.VARYING

    def test_seed_key_present_but_unused_is_constant(self):
        """有随机源键但输出不依赖它 ⇒ 仍 CONSTANT (不误判 VARYING)"""
        params = {"seed": 7, "n": 3}
        fals = probe_falsifiability(params, "n * 1.0", lambda p, e: float(p["n"]))
        assert fals is Falsifiability.CONSTANT

    def test_missing_computed_expr_is_unknown(self):
        assert probe_falsifiability({"n": 1}, None, lambda p, e: 0.0) is Falsifiability.UNKNOWN
        assert probe_falsifiability({"n": 1}, "", lambda p, e: 0.0) is Falsifiability.UNKNOWN

    def test_eval_error_is_unknown(self):
        def boom(p, e):
            raise ValueError("bad expr")

        assert probe_falsifiability({"n": 1}, "x", boom) is Falsifiability.UNKNOWN

    def test_random_source_keys_constant_present(self):
        assert "seed" in RANDOM_SOURCE_KEYS


# ---------------------------------------------------------------------------
# Tier 2 — 类别 × 证伪力 匹配矩阵 (21 格真值表, 与 DESIGN §6.2 逐格一致)
# ---------------------------------------------------------------------------

_FREE_KINDS = [AssertionKind.DETERMINISTIC_IDENTITY, AssertionKind.COMBINATORIAL]
_REQUIRED_KINDS = [
    AssertionKind.EXPECTATION, AssertionKind.VARIANCE, AssertionKind.MOMENT,
    AssertionKind.DISTRIBUTIONAL, AssertionKind.ASYMPTOTIC,
]
_ALL_FALS = [Falsifiability.CONSTANT, Falsifiability.VARYING, Falsifiability.UNKNOWN]


def _expected(kind_value: str | None, fals: Falsifiability) -> SemanticVerdict:
    """独立复述真值表 (不调用被测判据), 用于逐格交叉校验。"""
    free = {"deterministic_identity", "combinatorial"}
    required = {"expectation", "variance", "moment", "distributional", "asymptotic"}
    if kind_value not in free and kind_value not in required:
        return SemanticVerdict.UNKNOWN
    if fals is Falsifiability.UNKNOWN:
        return SemanticVerdict.UNKNOWN
    if kind_value in free:
        return SemanticVerdict.VALID_DETERMINISTIC
    return SemanticVerdict.CIRCULAR if fals is Falsifiability.CONSTANT else SemanticVerdict.UNKNOWN


class TestTier2Matrix:
    @pytest.mark.parametrize("kind", _FREE_KINDS)
    @pytest.mark.parametrize("fals", _ALL_FALS)
    def test_free_kinds(self, kind, fals):
        assert judge_semantic(kind.value, fals) is _expected(kind.value, fals)

    @pytest.mark.parametrize("kind", _REQUIRED_KINDS)
    @pytest.mark.parametrize("fals", _ALL_FALS)
    def test_required_kinds(self, kind, fals):
        assert judge_semantic(kind.value, fals) is _expected(kind.value, fals)

    def test_circular_is_the_核心_定案(self):
        """统计断言下的恒等检查 ⇒ CIRCULAR (本设计的核心判定)"""
        assert judge_semantic("expectation", Falsifiability.CONSTANT) is SemanticVerdict.CIRCULAR

    def test_free_kind_constant_is_valid(self):
        """组合断言下的确定性表达式是唯一正确形态 ⇒ 合法 (D030 反例)"""
        assert (judge_semantic("combinatorial", Falsifiability.CONSTANT)
                is SemanticVerdict.VALID_DETERMINISTIC)


class TestDegradation:
    @pytest.mark.parametrize("bad_kind", [None, "", "bogus", "EXPECTATION"])
    def test_bad_kind_degrades_to_unknown(self, bad_kind):
        assert judge_semantic(bad_kind, Falsifiability.CONSTANT) is SemanticVerdict.UNKNOWN


# ---------------------------------------------------------------------------
# 组合入口
# ---------------------------------------------------------------------------

def _tc(**kw) -> TestCase:
    base = dict(params={"n": 10}, expected=1.0, actual=1.0, tolerance=0.01, passed=True)
    base.update(kw)
    return TestCase(**base)


class TestJudgeTestCase:
    def test_combines_probe_and_matrix(self):
        tc = _tc(kind="expectation", computed_expr="mu + 0", params={"mu": 0})
        fals, sem = judge_test_case(tc, lambda p, e: float(p["mu"]))
        assert fals is Falsifiability.CONSTANT
        assert sem is SemanticVerdict.CIRCULAR

    def test_no_kind_degrades(self):
        tc = _tc(kind=None, computed_expr="n + 0")
        fals, sem = judge_test_case(tc, lambda p, e: float(p["n"]))
        assert fals is Falsifiability.CONSTANT
        assert sem is SemanticVerdict.UNKNOWN

    def test_varying_statistical_is_not_positive(self):
        """VARYING 只证伪"恒等", 不构成"正确" ⇒ UNKNOWN (不越界, DESIGN Review #2 注②)"""
        tc = _tc(kind="expectation", params={"seed": 1}, computed_expr="seed * 1.0")
        fals, sem = judge_test_case(tc, lambda p, e: float(p["seed"]))
        assert fals is Falsifiability.VARYING
        assert sem is SemanticVerdict.UNKNOWN


# ---------------------------------------------------------------------------
# 集成: 可见性只增不减 (verdict / pass_rate 不受影响)
# ---------------------------------------------------------------------------

class TestVisibilityOnlyNoVerdictChange:
    def test_run_test_cases_backfills_and_keeps_passed(self):
        import asyncio

        from researchclaw.vendor.auto_prover.stages.stage2_numerical import NumericalVerifier

        v = NumericalVerifier.__new__(NumericalVerifier)
        tcs = [_tc(kind="expectation", computed_expr="mu + 0", params={"mu": 0},
                   expected=0.0, actual=0.0, tolerance=0.5, passed=False)]
        out = asyncio.new_event_loop().run_until_complete(v._run_test_cases(tcs))
        assert out[0].falsifiability == Falsifiability.CONSTANT.value
        assert out[0].semantic_verdict == SemanticVerdict.CIRCULAR.value
        # 判定本身不变: expected==actual ⇒ deviation 0 <= tol ⇒ passed=True (由容差口径决定, 非语义判定)
        assert out[0].passed is True

    def test_verify_aggregates_n_circular_without_changing_verdict(self):
        """反证: 即使全为 CIRCULAR, verdict 仍按 pass_rate 决定 (可见性 ≠ 拦截, O-A)"""
        import asyncio

        from researchclaw.vendor.auto_prover.stages.stage2_numerical import NumericalVerifier

        v = NumericalVerifier.__new__(NumericalVerifier)
        v.gateway = _MockGateway()

        async def fake_run(tcs, rel_tolerance_floor=0.0, std_err_k=0.0):
            for t in tcs:
                t.passed = True
                t.falsifiability = Falsifiability.CONSTANT.value
                t.semantic_verdict = SemanticVerdict.CIRCULAR.value
            return tcs

        def fake_parse(text, expected_count):
            n = max(expected_count, 1)
            return [_tc(kind="expectation", computed_expr="mu + 0", params={"mu": 0},
                        expected=1.0, actual=1.0, tolerance=0.01, passed=False)
                    for _ in range(n)]

        v._parse_test_cases = fake_parse
        v._run_test_cases = fake_run
        res = asyncio.new_event_loop().run_until_complete(
            v.verify(TheoremInput(nl_statement="t"), _latex(), n_cases=3,
                     pass_threshold=0.8, counterexample_search_enabled=False))
        assert res.verdict == NumericalVerdict.PASSED   # 100% 通过 ⇒ PASSED (语义判定未拦截)
        assert res.n_circular == 3
        assert res.semantic_review_flags


class _MockGateway:
    kind = "mock"

    async def call_reasoner(self, prompt, task, temperature=0.0):
        return type("R", (), {"text": "# ---\n# tc", "success": True})


def _latex():
    from researchclaw.vendor.auto_prover.datatypes import LaTeXAssertion
    return LaTeXAssertion(latex_statement="1+1=2")