---
id: arc-plan-evolution-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-plan-evolution-RESEARCH, research-plan-design]
upstream: null
---

# 设计：G8b 计划演进（P-156）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **变更面**：新增 4 个 plan 模块 + 版本化存储 + Stage 15/9 两个只读钩子 + 测试；不改变 G8a 的 schema 与阶段产物契约。
> **优先级**：按总纲记为 P2（G6/G7/G8b 均为 P2）。

---

## 1. 决策

| 编号 | 决策 |
|---|---|
| D-1 | Progress Ledger 为纯函数：`compute_ledger(plan, previous, events, spent_usd)`；五问字段对齐 Magentic-One（E1/E2），不调用 LLM |
| D-2 | 循环判定 = 连续 2 轮同一 `next_node` 且无新增 `done`；只判该组合，不做语义相似度 |
| D-3 | 重规划必须 version+1，`parent_version` 指向旧版；禁止原地改 `plan.v{n}.json`；`max_versions=3`（Q15 provisional） |
| D-4 | `done` 节点不可删除、不可修改；`replan` 在纯函数层拒绝，不依赖调用方自觉 |
| D-5 | 目标变更只认 `approvals.json` 的 `plan_goal_change.approved is True`；缺失/损坏 = 拒绝（fail-closed） |
| D-6 | 懒惰分解只在 `two_failures` / `ambiguity` / `budget_half_no_progress` 触发；`decompose_node` 校验触发证据，无证据即拒绝 |
| D-7 | Stage 9 局部搜索为确定性候选枚举 + 预算上限，只写 `plan/search.json` 报告，不删减 `exp_plan.yaml` |
| D-8 | Stage 15 只写 `ledger.json` 与 `plan.replan_requested` 事件；不自动改计划 |

## 2. 模块划分

| 模块 | 职责 |
|---|---|
| `plan/ledger.py` | 五问账本、循环检测、下一节点、分解候选；`read/write_ledger` |
| `plan/replan.py` | `plan_diff`、`replan`、`apply_replan`、`request_replan`；目标审批与完成节点保护 |
| `plan/decompose.py` | `should_decompose`、`decompose_node`；触发证据与深度/扇出/节点上限 |
| `plan/search.py` | `search_experiment_candidates`；预算上限与确定性排序 |
| `plan/store.py`（修改） | `plan.v{n}.json` 版本化；`index.json` 指向当前版本；`plan.replanned` 事件 |
| `plan/__init__.py`（修改） | 导出新 API |
| `pipeline/stage_impls/_analysis.py`（Stage 15） | 写 ledger；REFINE/PIVOT 时写 `replan_requested` |
| `pipeline/stage_impls/_experiment_design.py`（Stage 9） | 写 `plan/search.json` 报告（只读） |

## 3. 数据格式

### `plan/ledger.json`

```json
{
  "plan_version": 2,
  "completed": ["n1", "n2"],
  "active": ["n3"],
  "blocked": ["n4"],
  "abandoned": [],
  "is_complete": false,
  "is_looping": false,
  "loop_rounds": 0,
  "forward_progress": true,
  "next_node": "n3",
  "next_instruction": "Run X on Y (stage 9)",
  "decompose_candidates": [{"node_id": "n4", "reason": "two_failures"}],
  "generated_at": "2026-11-25T01:00:00+00:00"
}
```

- `completed/active/blocked/abandoned` 由节点 `status` 推导，不手填。
- `is_looping` 只在「上一账本 `next_node` 相同且无新增 `done`」时为 true；`loop_rounds` 连续累计。
- `decompose_candidates` 只列有证据的节点（失败事件 ≥2 / 歧义事件 / 预算过半且完成率 <30%）。

### `plan/index.json`

```json
{"version": 2, "digest": "sha256:...", "file": "plan.v2.json"}
```

- 旧 run 无 index → `load_plan` 回退 `plan.v1.json`。
- `update_plan` 写当前版本文件，不写死 v1。

### `plan_events.jsonl`

| type | payload |
|---|---|
| `plan.created` | `stage/version/digest` |
| `plan.updated` | `stage/version/digest` |
| `plan.replanned` | `stage/version/parent_version/reason/diff` |
| `plan.replan_requested` | `reason/trigger/next_node/is_looping/forward_progress` |

### `plan/search.json`

```json
{"selected": ["n2"], "evaluated": 3, "spent_usd": 1.0, "budget_usd": 2.0,
 "exhausted": false, "skipped_over_budget": ["n5"], "generated_at": "..."}
```

## 4. API

```python
compute_ledger(plan, *, previous=None, events=(), spent_usd=0.0) -> dict
read_ledger(run_dir) -> dict | None
write_ledger(run_dir, ledger) -> None

plan_diff(old, new) -> dict            # added/removed/changed/preserved
replan(plan, *, nodes=None, goal=None, approved_goal=False,
       reason="human_request", max_versions=None) -> dict
apply_replan(run_dir, *, nodes=None, goal=None, approved_goal=False,
             reason="human_request") -> dict
request_replan(run_dir, *, reason, ledger) -> None

should_decompose(node, *, attempts=0, ambiguous=False, budget_ratio=0.0,
                 progress_ratio=1.0, depth=0, fanout=0,
                 max_depth=3, max_fanout=8) -> tuple[bool, str]
decompose_node(plan, node_id, children, *, trigger, attempts=0, ambiguous=False,
               budget_ratio=0.0, progress_ratio=1.0) -> dict

search_experiment_candidates(candidates, *, budget_usd,
                             max_candidates=8) -> dict
```

回退点：

| 接口 | 回退点 |
|---|---|
| `compute_ledger` / `write_ledger` | 删除钩子；Stage 15 行为回到 P-152 |
| `replan` / `apply_replan` | 不调用即无版本化；`update_plan` 保持原语义 |
| `decompose_node` | 不调用即无懒惰分解；不影响既有节点生成 |
| `search_experiment_candidates` | 不写 `search.json`；Stage 9 产物不变 |

## 5. 重规划规则

1. 读取当前 plan（index 版本优先，回退 v1）。
2. `goal` 变更：必须 `approved_goal=True` 且对应审批来自 `approvals.json`（由 `apply_replan` 读取）；纯函数 `replan` 只接受显式布尔值。
3. `version >= max_versions` → 拒绝（`ReplanError`）。
4. 新节点集合：
   - 旧 `done` 节点必须原样存在（canonical JSON 全等），否则拒绝；
   - 允许新增节点、修改 `proposed/active` 节点、删除未完成节点；
   - 新节点必须能通过 `validate_plan`（调用方或 `apply_replan` 校验）。
5. 新 plan：`version+1`、`parent_version=old.version`、`replan.last_reason/reason_trigger`、重新 `seal_plan`。
6. `apply_replan` 写 `plan.v{n+1}.json` + `index.json` + `plan.replanned` 事件（含 diff）。
7. 拒绝原地改：`apply_replan` 在写前重算旧文件 digest；与 index 不一致即拒绝。

## 6. 懒惰分解规则

| 触发 | 条件 | 常量 |
|---|---|---|
| `two_failures` | 同一节点失败事件 ≥2 | Q16 provisional |
| `ambiguity` | 最近事件 payload `reason == "ambiguous"` | Q16 provisional |
| `budget_half_no_progress` | `spent/budget >= 0.5` 且 `done/total < 0.3` | Q16 provisional |

- `should_decompose` 先检查深度/扇出上限；超限返回 `(False, "limits")`。
- `decompose_node` 必须传入 `trigger`，并验证 `should_decompose` 返回同一原因；否则 `DecomposeError`。
- 子节点 2..`max_fanout`；深度 ≤3；全 plan ≤40 节点；父节点转 `active`。

## 7. 验收映射

| ID | 落点 | 负向 |
|---|---|---|
| A8b-1 | `replan` 保留 `done` 节点；`plan_diff.preserved` 含之 | 删除/修改 done → `ReplanError` |
| A8b-2 | `replan(goal=...)` 需 `approved_goal=True`；`apply_replan` 读 `approvals.json` | 未批准改 goal → 拒绝 |
| A8b-3 | `replan` 总是 version+1 且返回 added/removed/changed/preserved | 原地改文件/digest 不符 → 拒绝 |
| A8b-4 | `compute_ledger` 循环检测；`should_decompose` 触发证据；`search...` 预算上限 | 空转仍报进展 / 无证据拆分 / 超预算 → 失败 |

## 8. 不变式

| 编号 | 不变式 |
|---|---|
| J-1 | `done` 节点在重规划中永不被删除或修改 |
| J-2 | 目标变更必须人工批准；审批源缺失/损坏即拒绝 |
| J-3 | 每次重规划 version+1 且有 diff；原地改计划被拒绝 |
| J-4 | Ledger 只读 plan，不修改节点状态 |
| J-5 | 循环判定确定性，不用 LLM/embedding |
| J-6 | 懒惰分解必须带触发证据，且受深度/扇出/节点上限 |
| J-7 | 搜索不超预算，结果顺序确定 |
| J-8 | 无 plan / 无审批 / 旧 run：no-op 或 fail-closed，不破坏既有阶段 |

## 9. Review 记录（Step 6）

- 与 G8a 的 `validate_plan`/`seal_plan` 复用，不复制校验逻辑。
- 版本化只改 `store.py` 的文件名与 index，不改 schema 字段。
- Stage 15/9 钩子全部包在 `try/except` 内，规划失败不阻断阶段（沿用 P-152 语义）。
- Q15/Q16 以 provisional 常量落地，文档显式标注，不宣称正式裁决。

## 10. 非目标

LLM 自动生成重规划节点、全流程树搜索、G6 模型分层、G7 72h soak、计划语义覆盖的自动判定。
