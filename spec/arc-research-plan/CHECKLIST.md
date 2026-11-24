---
id: arc-research-plan-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-24
depends: [arc-research-plan-IMPLEMENTATION, arc-research-plan-DESIGN]
upstream: null
---

# 审查验收 Checklist：ResearchPlan v1 计划对象（P-152 / G8a）

> **Feature**：P-152。
> **基于实施**：[IMPLEMENTATION.md](./IMPLEMENTATION.md)（v1.0 / verified）。
> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **验收边界**：4 新模块 + 4 阶段接入 + 1 测试；不改变 23 阶段骨架与既有产物契约。

---

## 1. 文档一致性验收

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN 可追溯到 RESEARCH | ✅ | D-1..D-10 对应 RESEARCH §3/§4 |
| DESIGN ↔ IMPLEMENTATION 变更面一致 | ✅ | 均为「4 新 + 4 接入 + 1 测试」 |
| 读数在 checklist 有验收项 | ✅ | 21 + 207 + 244 ↔ §2/§7 |
| 术语一致 | ✅ | `research-plan/1`、V1–V12、`plan/` 三件套、`plan_digest` 四文档一致 |

## 2. 功能验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| Stage 2 写合法计划 | 直接调用 Stage 2 | `plan.v1.json` 存在、校验空表、`plan_meta.json` 在 artifacts | ✅ | `test_stage2_writes_valid_plan` |
| 计划 schema | `build_initial_plan` | schema/字段/节点类型齐全 | ✅ | `test_initial_plan_is_valid` |
| 缺 acceptance 拒绝 | 删除字段 | V1 | ✅ | `test_missing_acceptance_rejected` |
| 环拒绝 | n1↔n2 | V4 | ✅ | `test_cycle_rejected` |
| owner_stage 走界 | 99 | V5 | ✅ | `test_owner_stage_out_of_range` |
| experiment 字段 | 无 baseline | V6 | ✅ | `test_experiment_requires_baseline` |
| hypothesis 依赖 literature | 依赖 question | V7 | ✅ | `test_hypothesis_requires_literature` |
| writing 依赖 analysis | 依赖 question | V8 | ✅ | `test_writing_requires_analysis` |
| evidence 节点 outputs | 空 outputs | V9 | ✅ | `test_evidence_node_requires_outputs` |
| 预算/形状/重复 | 超预算、41 节点、重复 statement | V10/V11 | ✅ | 三条用例 |
| digest 复算/篡改 | 改 digest | V12 / 复算一致 | ✅ | `test_digest_tamper`、`test_roundtrip` |
| Stage 7/8/9/14 节点 | 四阶段 builder | unknown/literature/hypothesis/experiment/analysis 齐全 | ✅ | 五条 builder 用例 |

## 3. 接口验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| `validate_plan` | 任意输入 | 返回 `list[Violation]`，空表通过 | ✅ | 校验用例 |
| `seal_plan`/`plan_digest` | 写入前后 | digest 一致、排除自身 | ✅ | `test_roundtrip` |
| 存储 API | 写/读/事件 | 三件套齐全、事件类型正确 | ✅ | `test_roundtrip`、`test_update_appends_event` |
| 无 plan no-op | 既有阶段用例 | 阶段行为不变 | ✅ | `test_rc_executor` 207 passed |

## 4. 不变式验收

| 不变式 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| J-1 先校验后写入 | Stage 2 | 非法时不写/FAILED | ✅ | 集成用例 + 校验用例 |
| J-2 digest 可复算 | 写读比对 | 一致 | ✅ | `test_roundtrip` |
| J-3 每次写入一条事件 | 两次写入 | `plan.created` + `plan.updated` | ✅ | `test_update_appends_event` |
| J-4 无 plan 钩子 no-op | 既有阶段 | 全绿 | ✅ | 207 passed |
| J-5 plan/exp_plan 不一致即失败 | 3 vs 2 条件 | 返回 mismatch | ✅ | `test_stage9_consistency_detects_missing_condition` |
| J-6 非关键阶段不阻塞 | 钩子异常路径 | 阶段仍 DONE | ✅ | 钩子 `try/except` + 回归 |

## 5. 错误处理验收

| 场景 | 测试方法 | 通过条件 | 状态 | 证据 |
|------|---------|---------|------|------|
| 缺必填字段 | 删 acceptance | V1 | ✅ | 缺 acceptance 用例 |
| 依赖环 | 双向依赖 | V4 | ✅ | 环用例 |
| owner_stage=99 | 改字段 | V5 | ✅ | 走界用例 |
| 预算超限 | 3×2 USD / cap 5 | V10 | ✅ | 预算用例 |
| digest 不符 | 改 digest | V12 | ✅ | 篡改用例 |

## 6. 性能验收

纯函数校验与本地 JSON 写入，无网络调用；无性能验收项。

## 7. 兼容性验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 阶段/计划相关回归 | 207 条 | 全绿 | ✅ | IMPL §2 |
| 执行器/新颖性回归 | 244 条 | 全绿 | ✅ | IMPL §2 |
| 既有产物契约 | Stage 2 仅新增 `plan_meta.json` | 原 artifacts 不变 | ✅ | 集成用例断言 |

## 8. ADD 审计

本批无 ADD 新增或修订，故无审计项。

## 9. Review 记录（Step 8）

- RESEARCH §4 ↔ DESIGN §1/§4 ↔ IMPLEMENTATION §3 ↔ CHECKLIST §2 的 A8a-1..4 映射逐条一致。
- DESIGN §3 V1–V12 ↔ `validate_plan` 实现 ↔ 校验用例逐条对应。
- DESIGN §5 J-1..J-6 ↔ CHECKLIST §4 ↔ 测试函数对应。
- 偏离已登记：V7 收敛为 literature；计划为确定性派生；Q15 默认值冻结。

## 10. 统计与结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|------|------|------|------|------|
| 文档一致性 | 4 | 4 | 0 | 0 |
| 功能 | 12 | 12 | 0 | 0 |
| 接口 | 4 | 4 | 0 | 0 |
| 不变式 | 6 | 6 | 0 | 0 |
| 错误处理 | 5 | 5 | 0 | 0 |
| 性能 | 0 | 0 | 0 | 0 |
| 兼容性 | 3 | 3 | 0 | 0 |
| ADD 审计 | 0 | 0 | 0 | 0 |
| **总计** | **34** | **34** | **0** | **0** |

算术自洽：34 = 4+12+4+6+5+0+3+0；通过 34 = 总数 34。

### 10.2 验收结论

- [x] 验收通过：34/34；21 条新用例 + 207 条阶段/计划回归 + 244 条执行器/新颖性回归。
- [ ] 验收不通过：无阻塞项。

## 11. 行动与遗留

| 事项 | 状态 | 说明 |
|------|------|------|
| PR 合并 | 待授权 | — |
| G8b 重规划 | 未做 | 版本 diff、Progress Ledger、人工批准 |
| 计划生成率 | 未统计 | 需真实 LLM 全流程样本 |
| 语义覆盖（MECE） | 未做 | 需要 embedding，属 G5/G8b |
