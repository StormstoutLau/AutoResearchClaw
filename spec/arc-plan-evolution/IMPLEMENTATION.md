---
id: arc-plan-evolution-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-plan-evolution-DESIGN]
upstream: null
---

# 实施：G8b 计划演进（P-156）

> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **状态**：实施完成；代码、测试与读数已回填。本文不宣称未验证项。
> **批次口径**：G8b 单批；G6/G7 另立批次；优先级按总纲 P2。

---

## 1. 计划变更清单

| 文件 | 动作 | 内容 |
|---|---|---|
| `researchclaw/plan/ledger.py` | 新增 | 五问账本、循环检测、下一节点、分解候选 |
| `researchclaw/plan/replan.py` | 新增 | `plan_diff`、`replan`、`apply_replan`、`request_replan` |
| `researchclaw/plan/decompose.py` | 新增 | 触发判定、懒惰分解、深度/扇出/节点上限 |
| `researchclaw/plan/search.py` | 新增 | 预算内确定性候选搜索 |
| `researchclaw/plan/store.py` | 修改 | `plan.v{n}.json` 版本化、index 指向当前版本、`plan.replanned` 事件 |
| `researchclaw/plan/__init__.py` | 修改 | 导出新 API |
| `researchclaw/pipeline/stage_impls/_analysis.py` | 修改 | Stage 15 写 ledger；REFINE/PIVOT 写 `replan_requested` |
| `researchclaw/pipeline/stage_impls/_experiment_design.py` | 修改 | Stage 9 写 `plan/search.json` 报告 |
| `tests/test_plan_ledger.py` | 新增 | T01-T06 |
| `tests/test_plan_replan.py` | 新增 | T07-T15 |
| `tests/test_plan_decompose.py` | 新增 | T16-T19 |
| `tests/test_plan_search.py` | 新增 | T20-T22 |
| `tests/test_plan_stage_hooks.py` | 新增 | T23-T25 |

## 2. 实施顺序

1. 版本化存储（`store.py`）与 `plan_diff` 纯函数；
2. `ledger.py`（先写循环/进展负向用例）；
3. `replan.py`（完成节点保护、目标审批、版本+diff）；
4. `decompose.py`（触发证据与上限）；
5. `search.py`（预算上限）；
6. Stage 15 ledger 钩子与 Stage 9 搜索报告钩子；
7. 全量回归与门禁。

## 3. 测试用例清单（TDD 定向上下文）

> 每个用例先写失败态，再写实现；正例与反例/边界各 ≥1。

### 3.1 Progress Ledger（`tests/test_plan_ledger.py`）

| # | 用例 | 夹具/输入 | 期望 | 反例/边界 | 验收 |
|---|---|---|---|---|---|
| T01 | `test_ledger_completes_when_all_done` | 全部 done/abandoned | `is_complete=true`，`next_node=null` | 一个 proposed 仍为 false | A8b-4 |
| T02 | `test_ledger_identifies_next_node` | n1 done，n2 依赖 n1 | `next_node=n2`，指令含 statement/stage | 依赖未完成 → 跳过 n2 | A8b-4 |
| T03 | `test_ledger_detects_loop_after_two_rounds` | 两次同 `next_node`、无新增 done | `is_looping=true`，`loop_rounds>=1` | 只一轮不判循环 | A8b-4 |
| T04 | `test_ledger_progress_breaks_loop` | 第二轮新增 done | `is_looping=false`，`forward_progress=true` | 无进展仍报 true → 失败 | A8b-4 |
| T05 | `test_ledger_lists_decompose_candidates` | 同一节点 2 条 `node.failed` | 候选含 `two_failures` | 1 条失败不列 | A8b-4 |
| T06 | `test_ledger_is_read_only` | 计算前后 plan 哈希 | 哈希不变 | 修改节点即失败 | J-4 |

### 3.2 版本化重规划（`tests/test_plan_replan.py`）

| # | 用例 | 夹具/输入 | 期望 | 反例/边界 | 验收 |
|---|---|---|---|---|---|
| T07 | `test_replan_preserves_done_nodes` | n1 done，新增 n3 | `preserved=["n1"]`，n1 原样 | 改 n1 状态即失败 | A8b-1 |
| T08 | `test_replan_rejects_removing_done_node` | 新节点集缺 n1 | `ReplanError` | 删除 done 仍通过 → 失败 | A8b-1 |
| T09 | `test_replan_requires_approved_goal` | 改 goal，未批准 | `ReplanError` | 未批准仍改 → 失败 | A8b-2 |
| T10 | `test_replan_with_approved_goal_bumps_version` | 改 goal，`approved_goal=True` | `version=2`，`parent_version=1` | 版本不变即失败 | A8b-2/3 |
| T11 | `test_replan_diff_has_four_buckets` | 增/删/改/保留各一 | 四键齐全且归位正确 | 少键即失败 | A8b-3 |
| T12 | `test_replan_rejects_max_versions` | `version=3`，max=3 | `ReplanError` | 超版仍写 → 失败 | A8b-3 |
| T13 | `test_apply_replan_writes_versioned_file_and_event` | v1 → v2 | `plan.v2.json`、index=2、`plan.replanned` 含 diff | 仍写 v1 即失败 | A8b-3 |
| T14 | `test_apply_replan_rejects_in_place_digest_drift` | 手改 v1 未重算 digest | `ReplanError` | 静默覆盖即失败 | A8b-3 |
| T15 | `test_apply_replan_reads_approvals_fail_closed` | 无/损坏 `approvals.json` | 改 goal 被拒 | 缺失仍放行 → 失败 | A8b-2 |

### 3.3 懒惰分解（`tests/test_plan_decompose.py`）

| # | 用例 | 夹具/输入 | 期望 | 反例/边界 | 验收 |
|---|---|---|---|---|---|
| T16 | `test_should_decompose_requires_trigger` | attempts=1、不歧义 | `(False, "no_trigger")` | attempts=2 → true | A8b-4 |
| T17 | `test_decompose_node_requires_evidence` | trigger=two_failures、attempts=0 | `DecomposeError` | 无证据拆分 → 失败 | A8b-4 |
| T18 | `test_decompose_node_respects_limits` | depth=3 或 fanout=8 | `DecomposeError` | 超限仍拆 → 失败 | A8b-4 |
| T19 | `test_decompose_node_adds_children_with_deps` | 2 子节点、合法触发 | 子节点 depends_on=父，父 active | 子节点无验收 → 失败 | A8b-4 |

### 3.4 Stage 9 搜索（`tests/test_plan_search.py`）

| # | 用例 | 夹具/输入 | 期望 | 反例/边界 | 验收 |
|---|---|---|---|---|---|
| T20 | `test_search_selects_within_budget` | 3 候选、预算 2.0 | 选中高 score 且总价 ≤2.0 | 超预算仍选 → 失败 | A8b-4 |
| T21 | `test_search_exhausts_budget_deterministically` | 候选顺序打乱 | 同一结果；`exhausted=true` | 结果不稳定 → 失败 | A8b-4 |
| T22 | `test_search_empty_budget_returns_nothing` | budget=0 | 空选中 + `exhausted=true` | 仍选 → 失败 | A8b-4 |

### 3.5 阶段钩子（`tests/test_plan_stage_hooks.py`）

| # | 用例 | 夹具/输入 | 期望 | 反例/边界 | 验收 |
|---|---|---|---|---|---|
| T23 | `test_stage15_writes_ledger` | 有 plan、decision=PROCEED | `plan/ledger.json` 存在且字段齐全 | 无 plan → no-op | A8b-4 |
| T24 | `test_stage15_requests_replan_on_refine` | decision=REFINE | `plan.replan_requested` 事件 | 不改 plan 内容 | A8b-4 |
| T25 | `test_stage9_writes_search_report` | plan 有 experiment 节点 | `plan/search.json` 且预算不超 | 无 plan → no-op | A8b-4 |

## 4. 算法级证据锚点

| 设计点 | 外部锚点 | 代码落点 | 用例 |
|---|---|---|---|
| 五问 Ledger | Magentic-One E1/E2：`IsRequestSatisfied`/`IsInLoop`/`IsProgressBeingMade`/`NextSpeaker`/`InstructionOrQuestion` | `ledger.compute_ledger` 字段一一映射 | T01-T04 |
| 循环检测 | E1/E2：inner loop 的 in-loop 判定 | 连续 2 轮同 `next_node` 且无新增 done | T03/T04 |
| 懒惰分解 | ADaPT E3：执行失败才拆；能力不足才递归 | `should_decompose` 的 `two_failures`/`ambiguity` | T16-T19 |
| 预算内搜索 | AI Scientist-v2 E4：experiment manager 在预算内枚举候选 | `search_experiment_candidates` 逐候选累计 | T20-T22 |
| 确定性校验 | PlanBench E5：LLM 规划不可靠，必须机械校验 | 复用 `validate_plan`；`replan` 写前校验 | T13 |
| 版本 diff | RFC 6902 E6：add/remove/replace/test | `plan_diff` 四分类 | T11/T13 |

## 5. 接口签名与回退点

| 接口 | 签名 | 回退点 |
|---|---|---|
| `ledger.compute_ledger` | `(plan, *, previous=None, events=(), spent_usd=0.0) -> dict` | 删除 Stage 15 钩子；回到 P-152 |
| `ledger.write/read_ledger` | `(run_dir, ledger)` / `(run_dir) -> dict \| None` | 不写 `ledger.json` |
| `replan.plan_diff` | `(old, new) -> dict` | 删除 `replan.py` |
| `replan.replan` | `(plan, *, nodes=None, goal=None, approved_goal=False, reason=..., max_versions=None) -> dict` | 不调用；`update_plan` 原语义 |
| `replan.apply_replan` | `(run_dir, *, nodes=None, goal=None, approved_goal=False, reason=...) -> dict` | 不写新版本文件 |
| `replan.request_replan` | `(run_dir, *, reason, ledger) -> None` | 不写事件 |
| `decompose.should_decompose` | `(node, *, attempts=0, ambiguous=False, budget_ratio=0.0, progress_ratio=1.0, depth=0, fanout=0, max_depth=3, max_fanout=8) -> (bool, str)` | 不调用 |
| `decompose.decompose_node` | `(plan, node_id, children, *, trigger, ...) -> dict` | 不调用；节点生成仍由 `derive.py` |
| `search.search_experiment_candidates` | `(candidates, *, budget_usd, max_candidates=8) -> dict` | 不写 `search.json` |
| `store.write_replan` | `(run_dir, plan, *, stage, diff, reason) -> dict` | `update_plan` 保持原行为 |

## 6. 低效排除表

| 排除项 | 理由 |
|---|---|
| LLM 自评计划进展 | 不可复算；纯函数可测 |
| embedding 相似度做循环检测 | 新增依赖与阈值校准；与「同节点无新增 done」相比收益低 |
| 全量树搜索（AI Scientist-v2 规模） | 成本与时间不可控；G8b 只做预算内候选枚举 |
| JSON Patch 运行时 | 只需四分类 diff，不引入依赖 |
| 自动 LLM 重规划节点生成 | 本批只交付可校验的演进原语；生成留后续 |
| 修改 `exp_plan.yaml` 条件 | 会破坏 G8a 双向一致性；搜索只产出报告 |

## 7. 版本核验表（Step 6）

| 依赖/工具 | 版本 | 核验方式 | 用途 |
|---|---|---|---|
| Python | 3.11–3.14 | CI 矩阵 | 运行时 |
| `hashlib`/`json`/`os` | stdlib | Python 文档 | digest/存储 |
| `researchclaw.plan`（G8a） | P-152 已合并 `db4ad47` | 本仓代码 | 复用 schema/store |
| `tools/approvals.py` | P-106 已合并 | 本仓代码 | 目标变更审批 |
| RFC 6902 | 2013-04 | rfc-editor.org | diff 四分类口径 |
| Magentic-One | arXiv 2411.04468 | arXiv/官方文档 | Ledger 字段 |
| ADaPT | arXiv 2311.05772 | NAACL 2024 Findings | 懒惰分解 |
| AI Scientist-v2 | arXiv 2504.08066 | arXiv | 预算内搜索 |
| PlanBench | arXiv 2206.10498 | arXiv | 确定性校验动机 |

## 8. 红→绿记录

| 阶段 | 预期失败态 | 实际读数 |
|---|---|---|
| 初版测试（模块未建） | 新模块 `ImportError`；T01/T07/T16/T20/T23 失败 | `4 errors in 0.34s`（`ModuleNotFoundError: researchclaw.plan.{ledger,replan,decompose,search}`） |
| 实现后 | 负向用例（T03/T08/T09/T12/T14/T15/T17/T18/T22）先红后绿 | 27 passed in 0.63s；首轮 1 failed（T07 期望漏了未变的 n2，属测试缺陷，修正后全绿） |
| 回归 | `test_research_plan.py`、`test_rc_executor.py` | 228 passed（含 Stage 15/9 执行器用例）；另有 113 passed（plan/stage guards 子集） |

## 9. 读数

```text
$ python -m pytest tests/test_plan_ledger.py tests/test_plan_replan.py \
    tests/test_plan_decompose.py tests/test_plan_search.py tests/test_plan_stage_hooks.py -q
27 passed in 0.63s

$ python -m pytest tests/test_research_plan.py tests/test_rc_executor.py -q
228 passed in 274.12s

$ python -m pytest tests/test_research_plan.py tests/test_stage_claim_hooks.py \
    tests/test_simulated_guard.py tests/test_fabrication_guards.py tests/test_offline_audit.py -q
113 passed in 3.39s

ledger_40_nodes_ms=0.224
```

- 27 = T01-T25 中 25 条 + T23/T25 各多一条 no-op 用例（T23 拆为 ledger/refine/no-plan，T25 拆为 report/no-plan）。
- 首轮唯一失败是 T07 测试期望（`preserved` 漏计未变的 n2），修正测试后全绿；实现逻辑未改。
- 40 节点账本耗时 0.224 ms，无性能门槛。

## 10. 门禁

| 门禁 | 读数 |
|---|---|
| dc_validator | 本批 0 违规（全仓 148 存量：P1=62/P2=86） |
| grandfather_gate | grandfathered=0 expired=0 violations=0 |
| step-gate | 5/5（research/design/implement/verify/finalize） |
| verify-anchor | 10 真实 / 0 缺失 / 0 漂移 |
| step_enforce | `digest_bound=1` |
| pre-commit | 全绿 |
| PR CI | 8/8（Packaging/Extras/Tests 3.11-3.14/Roadmap/Spec gates） |

## 11. 未做与边界

- 不含 LLM 自动生成重规划节点、全流程树搜索、G6/G7。
- Q15/Q16 仍为 provisional；常量可在后续裁决后调整。
- Stage 15 只请求重规划，不自动改计划。
- Stage 9 只写搜索报告，不删减实验条件。
