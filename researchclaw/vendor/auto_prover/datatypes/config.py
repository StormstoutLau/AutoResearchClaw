# Modified by AutoResearchClaw on 2026-11-11: added CompileReport.timed_out for M3 timeout evidence.
"""数据类型 — 流水线配置与编译报告"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time

from .core import StopStage

# 配置
# ============================================================================

@dataclass
class PipelineConfig:
    """流水线运行配置"""
    orchestrator_model: str = "DeepSeekV4Pro"
    reasoner_model: str = "GPT120B"
    tactician_model: str = "Oprover32B"
    auxiliary_model: str = "aux"

    # LLM 网关 (M1 e2e): 空 base_url = Mock 模式; 非空 = 真实 LM Studio/Ollama 兼容端点
    llm_base_url: str = ""            # "" = Mock; 合规范示例 http://127.0.0.1:18080 (SSH 隧道回环; 直连已失效 · D062)
    llm_timeout_seconds: float = 120.0
    llm_max_tokens: int = 4096
    # U-20 (D044): 端点特定请求参数透传 (合并进 chat/completions payload)。
    #   用途: 推理型模型 (MiniMax/Qwen3.8 等) 把预算烧在 `reasoning_content` ⇒
    #   `content` 为空 ⇒ 生成用例解析 0 例; "关思维链"的开关是各家私有的 JSON 字段
    #   (如 {"chat_template_kwargs":{"enable_thinking":false}}), 无透传则换模型即失效。
    #   None = 零变化 (默认路径 payload 与既有逐位一致)。
    llm_extra_body: dict | None = None
    # W9 / B-58 切片: True ⇒ `base_url` 为空时**构造失败**（fail-fast），
    # 而非静默走 Mock。默认 False = 零变化（Mock 仍可离线跑通）。
    llm_require_endpoint: bool = False

    # 流水线控制
    stop_at: StopStage = StopStage.STAGE3  # 默认在形式化证明后停止

    # Stage 1: NL → LaTeX (多 LLM 验证)
    latex_llm_count: int = 3               # 参与翻译的 LLM 数量
    latex_consensus_threshold: float = 0.7  # 多 LLM 共识阈值
    latex_max_retries: int = 3
    latex_temperature: float = 0.1
    dependency_check_enabled: bool = True   # 是否检查依赖完整性
    paper_search_enabled: bool = True       # 是否使用 MCP 论文检索
    kg_search_enabled: bool = True          # 是否查询本地知识库

    # Stage 1 增强: 假设挖掘 + 前提条件分析 + 依赖链追踪
    hypothesis_mining_enabled: bool = True      # 是否主动挖掘隐含假设
    hypothesis_mining_llm_count: int = 2        # 挖掘假设的 LLM 数量
    precondition_analysis_enabled: bool = True   # 是否分析前提条件复杂性
    dependency_graph_enabled: bool = True        # 是否构建依赖图
    dependency_max_depth: int = 5                # 依赖图最大深度

    # Stage 1.5: Proof Sketching
    sketching_enabled: bool = True
    sketching_temperature: float = 0.3
    max_sketch_steps: int = 15

    # Stage 2: 数值验证
    numerical_enabled: bool = True
    max_test_cases: int = 15
    numerical_pass_threshold: float = 0.8
    # 尺度感知相对容差下限 (D025 方案 C)。0.0 = 关闭 = 现行语义 (零变化)。
    # 规则: passed = |actual-expected| <= max(tolerance, floor × max(|expected|,|actual|))
    # 单调性: floor ≥ 0 时只会把 fail 翻为 pass, 不新增 fail ⇒ 阈值须显式且保守。
    # 用途: 吸收"模型对蒙特卡洛点估计设了小于抽样误差的绝对容差"造成的假阴性;
    #       同时修复大量级下绝对容差的尺度失配 (如 exp=1e6, tol=0.2)。
    numerical_rel_tolerance_floor: float = 0.0
    # B-17/B-18 (D026) 统计容差分支: 判定取 tol_stat = numerical_std_err_k × std_err。
    # 0.0 = 关闭 = 现行语义 (零变化)。k 为置信乘子 (k=3 ≈ 3σ, 正态下 ~99.7%)。
    # 单调性同 C: 只会把 fail 翻为 pass (取 max), 不新增 fail ⇒ k 须显式且保守。
    # 闭合 C 的 `expected=0` 盲区: 相对容差对 0 无定义, 但标准误有定义。
    # ⚠ 依赖 LLM 声明 std_err: 未声明则该分支不生效 (不劣于现状), 声明值可被人工审计。
    numerical_std_err_k: float = 0.0

    # Stage 2 增强: 系统化反例搜索
    counterexample_search_enabled: bool = True
    counterexample_optimization_enabled: bool = True  # 优化驱动反例搜索
    counterexample_grid_search_enabled: bool = False   # 网格搜索
    counterexample_max_iterations: int = 100
    counterexample_minimal_search: bool = True         # 寻找最小反例

    # Mathematica 符号计算
    mathematica_enabled: bool = True        # 是否启用 Mathematica 桥接
    mathematica_timeout: float = 30.0       # Mathematica 查询超时 (秒)
    mathematica_use_wolframclient: bool = True  # 使用 wolframclient 库 (否则 wolframscript 子进程)

    # Stage 3: LaTeX → Lean4 + 形式化证明
    lean4_translation_max_retries: int = 3
    lean4_translation_temperature: float = 0.1
    lean4_translation_candidates: int = 3
    semantic_similarity_threshold: float = 0.85
    pass_k: int = 12
    tactic_temperature: float = 0.7
    beam_width: int = 4
    max_beam_depth: int = 10
    max_iterations_per_goal: int = 5
    reflection_enabled: bool = True

    # Context compression (miniCTX)
    context_compression_enabled: bool = True
    max_context_tokens: int = 2000

    # Error repair
    max_repair_attempts: int = 3

    # Sorry tolerance
    tier1_sorry_allowed: bool = False
    tier2_max_sorry: int = 5
    tier3_max_sorry: int = 20

    # Stage 3.5
    legality_check_enabled: bool = True

    # Timeouts
    tactic_timeout_seconds: float = 30.0

    # W2 / B-53 · B-55: 求值隔离与 Lean/REPL 沙箱（D6 / D-W2-2 用户裁决）
    # 单次求值墙钟上限（判定 + 搜索路径的 worker；非法值回落 2.0）
    sandbox_eval_timeout_seconds: float = 2.0
    # 判定路径整批预算（`_run_test_cases`；超预算 ⇒ 剩余用例 fail-closed）
    sandbox_batch_budget_seconds: float = 10.0
    # 反例搜索会话预算（`CounterExampleSearcher`；超预算 ⇒ 该次搜索中止）
    sandbox_search_budget_seconds: float = 30.0
    # W8 / B-60: worker 提交内存上限（MiB；0 = 关闭）。
    #   Windows 用 Job Object；POSIX 由 worker 自设 RLIMIT_AS（8× + 2 GiB 下界）。
    #   实测合法用例峰值 18.43 MiB ⇒ 256 的余量 ≥ 13.8×（RESEARCH §3.4）。
    sandbox_memory_limit_mb: int = 256
    # Lean LLM 代码危险构造过滤（B-55 / D11；False 仅供对照实验与排障）
    lean_dangerous_filter_enabled: bool = True

    # Lean4 项目目录 (lake build 所需)
    lean4_project_dir: str = ""  # 空 = 未配置, compile_check 会返回 False
    # G05 / B-08 接线: Lean4 REPL tactic 逐步执行 (D2-2)。
    # False (默认) = 保持 LeanSimRuntime (阶段一, execute 恒失败, 零行为变化);
    # True  = 构造 Lean4ReplRuntime 接管 tactic execute (需 lean4_project_dir 指向
    #         含 `.lake/packages/repl` 且可 `lake exe repl` 的项目)。compile_check
    #         仍走 LeanSimRuntime (REPL 无此接口)。
    lean4_repl_enabled: bool = False
    # D103 / F1: per-run 临时 Lean 项目。
    # False (默认) = 既有行为：Stage3 直接使用 `lean4_project_dir`；
    # True  = 从 `lean4_project_dir`（源项目）派生独立临时项目（含 Main 目标 +
    #         预生成 manifest + mathlib/REPL path 复用），Stage3 结束后删除。
    lean4_per_run_project_enabled: bool = False
    # 空 = `proof_pipeline/output/lean_runs`（已 gitignore）
    lean4_run_root: str = ""
    # prewarm（import Mathlib + trivial）超时；冷依赖首次构建实测 87s（D102 C2）
    lean4_prewarm_timeout: float = 300.0
    # D072 / G13 Phase 5c-A5 接线: Stage 3 tactic prompt 注入 D:\Textbook skills。
    # False (默认) = 不注入, 提示词与既有行为**逐字相同**;
    # True  = 初始化时一次性组合 skills(cached), 注入 `_prove_single_goal` 的 tactic prompt。
    atlas_skills_enabled: bool = False
    # 空 = 使用 `skill_bridge.DEFAULT_SKILLS_DIR` (D:\Textbook\lean_src\skills)
    atlas_skills_dir: str = ""
    # T14 Stage 3 接线: 进程内证明准备（Planner + Sketch → tactic prompt 蓝图）。
    # False (默认) = 不构造/不注入 ⇒ 提示词与既有行为逐字相同;
    # True  = 每次 prove() 对根目标生成一次蓝图段（模板，不可编译；失败 fail-open）。
    atlas_proof_prep_enabled: bool = False
    # T14 接 synthesizer_merge（D090）：MISSING_LEMMA 提议子目标 + 多节点块级合成。
    # True（用户裁定默认开）⇒ 仅在 MISSING_LEMMA / 多节点树触发时才改变行为。
    atlas_synthesizer_enabled: bool = True
    atlas_subgoal_max: int = 2
    atlas_parent_retry_max: int = 1
    # D093 / F7: Stage 3 指标 JSONL（默认开；写入失败 fail-open）。
    # False ⇒ 不构造 writer / 不写盘；True ⇒ 每次 Stage 3 追加一行到
    # atlas_metrics_dir（空 = proof_pipeline/output/metrics，已 gitignore）。
    atlas_metrics_enabled: bool = True
    atlas_metrics_dir: str = ""
    # D076 / T13: 真值判定 → KG 写回（**本仓 staging**；不写 D:\Textbook）。
    # False (默认) = 不创建 writer / 不写盘 ⇒ 零行为变化。
    kg_writeback_enabled: bool = False
    # 空 = `proof_pipeline/output/kg`
    kg_writeback_dir: str = ""

    @property
    def stop_after_stage1(self) -> bool:
        return self.stop_at == StopStage.STAGE1

    @property
    def stop_after_stage2(self) -> bool:
        return self.stop_at in (StopStage.STAGE1, StopStage.STAGE2)

    @property
    def stop_after_stage3(self) -> bool:
        return self.stop_at in (StopStage.STAGE1, StopStage.STAGE2, StopStage.STAGE3)


# ============================================================================
# 最终输出
# ============================================================================

@dataclass
class CompileReport:
    """W1 / B-54: 结构化编译证据（compile_status 的唯一来源）

    status 三态:
      - failed              编译失败（rc 非 0 / 无构建物 / 超时）
      - success_with_sorry  编译成功但文件含 `declaration uses 'sorry'`
      - success             编译成功且无 sorry 警告

    axiom_check:
      - passed        `#print axioms` 只含标准公理（或明确无公理）
      - failed        `sorryAx` / 自定义公理 / `_native`
      - skipped       有 theorem_name 但未解析到公理输出（fail-closed）
      - not_requested 未请求（无 theorem_name 或 legacy 包装）
    """
    success: bool = False
    status: str = "failed"
    diagnostics: str = ""
    errors: list[str] = field(default_factory=list)
    sorry_warnings: list[str] = field(default_factory=list)
    axioms: list[str] = field(default_factory=list)
    axiom_check: str = "not_requested"
    theorem_name: str = ""
    evidence_complete: bool = True
    returncode: Optional[int] = None
    artifact_present: bool = False
    # M3 (ARC P-060): 超时证据。`failed` 无法区分超时与普通编译失败，
    # sidecar 需要据此返回可重试的 75，而不是业务失败 0。
    timed_out: bool = False

    @property
    def formally_clean(self) -> bool:
        """是否足以支撑 FORMALLY_VERIFIED 的编译证据。"""
        return (
            self.success
            and self.status == "success"
            and not self.sorry_warnings
            and self.evidence_complete
            and self.axiom_check == "passed"
        )

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "status": self.status,
            "errors": list(self.errors),
            "sorry_warnings": list(self.sorry_warnings),
            "axioms": list(self.axioms),
            "axiom_check": self.axiom_check,
            "theorem_name": self.theorem_name,
            "evidence_complete": self.evidence_complete,
            "returncode": self.returncode,
            "artifact_present": self.artifact_present,
        }

    @classmethod
    def from_legacy(cls, ok: bool, message: str = "",
                    theorem_name: str = "") -> "CompileReport":
        """旧 `compile_check` 的 (bool, str) 包装；不声称完整证据。"""
        return cls(
            success=bool(ok),
            status="success" if ok else "failed",
            diagnostics=message or "",
            errors=[] if ok else ([message] if message else []),
            theorem_name=theorem_name,
            evidence_complete=False,
            axiom_check="not_requested",
        )
