---
id: arc-research-plan-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-research-plan-RESEARCH]
upstream: null
---

# 设计：ResearchPlan v1 计划对象（P-152 / G8a）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **变更面**：新增 `researchclaw/plan/`（4 文件）+ 4 个阶段实现接入 + 1 个测试文件。

---

## 1. 决策

| 决策 | 内容 |
|---|---|
| D-1 | 新包 `researchclaw/plan/`：`schema.py`（校验/摘要）、`store.py`（存储/事件）、`derive.py`（阶段派生）、`__init__.py` |
| D-2 | schema 固定 `research-plan/1`；节点 7 类、状态 5 类 |
| D-3 | `validate_plan(plan, run_budget_usd=None)` 返回 `list[Violation]`，空表即通过 |
| D-4 | 存储 `<run>/plan/{plan.v1.json,index.json,plan_events.jsonl}`，原子写，每次写入追加一条事件 |
| D-5 | `plan_digest` = canonical JSON（排除自身）的 sha256；`seal_plan` 重算 |
| D-6 | Stage 2 在 `problem_tree.md` 之后派生计划；Stage 7/8/9/14 以 `update_from_stage` 追加节点 |
| D-7 | 失败策略：Stage 2（计划非法）与 Stage 9（plan ↔ exp_plan 不一致）**FAILED**；Stage 7/8/14 仅告警 |
| D-8 | experiment 绑定 literature 节点，使 question→literature→experiment→analysis 深度恰为 3 |
| D-9 | Q15 默认值冻结：`max_depth=3`、`max_fanout=8`、节点上限 40、`max_versions=3`（后者仅字段，G8b 才使用） |
| D-10 | 不实现重规划/版本 diff/Progress Ledger（G8b） |

## 2. API

```python
build_initial_plan(*, topic, goal_text, problem_tree, run_budget_usd=5.0, domains=()) -> dict
add_synthesis_gaps(plan, synthesis_md) -> dict
add_hypothesis_nodes(plan, hypotheses_md) -> dict
add_experiment_nodes(plan, experiment_plan) -> dict
check_experiment_plan_consistency(plan, experiment_plan) -> list[str]
mark_analysis_done(plan, *, metrics_present) -> dict
validate_plan(plan, run_budget_usd=None) -> list[Violation]
plan_digest(plan) -> str
seal_plan(plan) -> dict
write_plan(run_dir, plan, *, stage=2) -> dict
update_plan(run_dir, plan, *, stage) -> dict
update_from_stage(run_dir, stage, transform) -> dict | None
load_plan(run_dir) -> dict | None
read_events(run_dir) -> list[dict]
```

所有 builder 返回**已重算 digest** 的新计划，不修改入参。

## 3. 校验规则

| # | 规则 | 失败 |
|---|---|---|
| V1 | 顶层/节点必填字段、类型、枚举、budget 非负 | 拒绝 |
| V2 | 节点 id 唯一 | 拒绝 |
| V3 | `depends_on` 全部可解析 | 拒绝 |
| V4 | 依赖图无环 | 拒绝 |
| V5 | `owner_stage ∈ 1..23` | 拒绝 |
| V6 | `experiment` 必须有 metric/dataset/baseline | 拒绝 |
| V7 | `hypothesis` 必须依赖 `literature` | 拒绝 |
| V8 | `writing` 必须依赖 `analysis` | 拒绝 |
| V9 | `evidence_required=true` 必须有 outputs 与 acceptance | 拒绝 |
| V10 | 预算求和 ≤ run 预算 | 拒绝 |
| V11 | 节点 ≤40、深度 ≤3、扇出 ≤8、statement 不重复 | 拒绝 |
| V12 | `plan_digest` 可复算 | 拒绝 |

## 4. 阶段接入

| 阶段 | 动作 | 产物 | 失败策略 |
|---|---|---|---|
| 2 | 从 `problem_tree.md` 派生 question 节点 | `plan/` + `stage-02/plan_meta.json` | FAILED |
| 7 | gaps → `unknowns` + literature/question 节点 | 更新 `plan.v1.json` | 告警 |
| 8 | 每个 hypothesis 一个节点，依赖 literature | 同上 | 告警 |
| 9 | 每个 proposed_method 一个 experiment 节点，双向检查 | 同上 | FAILED |
| 14 | analysis/experiment 节点置 done/failed | 同上 | 告警 |

## 5. 不变式

| 编号 | 不变式 | 测试 |
|---|---|---|
| J-1 | Stage 2 先校验后写入 | `test_stage2_writes_valid_plan` |
| J-2 | digest 排除自身且可复算 | `test_roundtrip`、`test_digest_tamper` |
| J-3 | 每次写入产生一条 plan 事件 | `test_roundtrip`、`test_update_appends_event` |
| J-4 | 无 plan 时 Stage 7/8/9/14 钩子 no-op | `test_rc_executor` 的既有阶段用例 |
| J-5 | plan ↔ exp_plan 不一致即 Stage 9 FAILED | `test_stage9_consistency_detects_missing_condition` |
| J-6 | 非关键阶段的计划更新不阻塞阶段 | 钩子 `try/except` + 既有阶段回归 |

## 6. Review 记录（Step 6）

- `derive.py` 不导入 pipeline，避免循环依赖；阶段侧延迟导入 `researchclaw.plan`。
- `validate_plan` 只读，不做修复；修复留给后续重试策略（本批不实现）。
- V7 收敛为 literature（无 `fact` 节点类型）；DESIGN 明确记录。
- 深度上限通过「experiment 绑 literature」满足，不提高 Q15 的 3。
- `plan_meta.json` 进入 Stage 2 artifacts，使计划指针可被证据链登记；`plan/` 本身是独立真值区。

## 7. 非目标

重规划、版本 diff、人工批准、Progress Ledger、ADaPT 懒惰分解、Stage 9 树搜索、LLM 二次规划调用。
