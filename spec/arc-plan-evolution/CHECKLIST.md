---
id: arc-plan-evolution-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-25
depends: [arc-plan-evolution-IMPLEMENTATION, arc-plan-evolution-DESIGN]
upstream: null
---

# 审查验收 Checklist：G8b 计划演进（P-156）

> **Feature**：P-156。
> **基于实施**：[IMPLEMENTATION.md](./IMPLEMENTATION.md)（v1.0 / verified）。
> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **状态**：验收完成；33/33 通过，读数见 §10。
> **批次口径**：G8b 单批，优先级按总纲 P2。

---

## 1. 文档一致性验收

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN 可追溯到 RESEARCH | ✅ | D-1..D-8 对应 RESEARCH §5/§7 |
| DESIGN ↔ IMPLEMENTATION 变更面一致 | ✅ | 均为「4 新模块 + 存储版本化 + 2 钩子 + 5 测试文件」 |
| 读数在 checklist 有验收项 | ✅ | §10 与 IMPLEMENTATION §9 同源 |
| 术语一致 | ✅ | `ledger`、`replan`、`preserve_completed`、`max_versions`、`decompose`、`search` 四文档互查一致 |

## 2. 功能验收

> DoR：夹具与模块签名先于用例存在；DoD：通过条件成立且证据读数落到 T01-T25。

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| A8b-1 重规划保留 done | n1 done，新增 n3 | `preserved` 含 n1，n1 原样；删除/修改即拒 | ✅ | T07/T08 passed |
| A8b-2 目标变更审批 | 改 goal，未/已批准 | 未批准拒绝；已批准 version+1 | ✅ | T09/T10/T15 passed |
| A8b-3 版本+diff | v1 → v2 | `plan.v2.json`、index=2、四类 diff、原地改拒绝 | ✅ | T11-T14 passed |
| A8b-4 Ledger/分解/搜索 | 循环、失败、预算 | 循环可判；拆分需证据；搜索不超预算 | ✅ | T01-T06、T16-T25 passed |

## 3. 接口验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| `compute_ledger` | 全 done/部分 done | 13 字段齐全 | ✅ | T01/T02 passed |
| `write/read_ledger` | 写后读 | 原子写、字段回读一致 | ✅ | T23 passed |
| `plan_diff` | 增/删/改/保留 | 四键齐全 | ✅ | T11 passed |
| `replan` | 改目标/新增节点 | version+1、parent 正确 | ✅ | T10 passed |
| `apply_replan` | v1 → v2 | 新文件 + index + 事件 | ✅ | T13 passed |
| `should_decompose` | 触发/不触发 | `(bool, reason)` 正确 | ✅ | T16 passed |
| `decompose_node` | 合法/非法触发 | 证据校验 + 上限 | ✅ | T17-T19 passed |
| `search_experiment_candidates` | 预算内/超预算 | 选中集合确定 | ✅ | T20-T22 passed |

## 4. 不变式验收

| 不变式 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| J-1 done 不可改 | 删除/修改 done | `ReplanError` | ✅ | T07/T08 passed |
| J-2 目标审批 fail-closed | 缺失/损坏审批 | 拒绝 | ✅ | T15 passed |
| J-3 version+diff | 每次重规划 | version+1 且 diff 四键 | ✅ | T10/T11 passed |
| J-4 Ledger 只读 | 计算前后哈希 | 不变 | ✅ | T06 passed |
| J-5 循环判定确定 | 同输入两次 | 结果一致 | ✅ | T03/T04 passed |
| J-6 分解需证据 | 无证据触发 | `DecomposeError` | ✅ | T17 passed |
| J-7 搜索不超预算 | 超预算候选 | 跳过并标 exhausted | ✅ | T20/T21 passed |
| J-8 旧 run no-op | 无 plan/审批 | 阶段行为不变 | ✅ | T23/T25 passed |

## 5. 错误处理验收

| 场景 | 测试方法 | 通过条件 | 状态 | 证据 |
|------|---------|---------|------|------|
| 无 plan | Stage 15/9 钩子 | no-op | ✅ | T23/T25 passed |
| index 损坏 | 非法 JSON | 回退 v1 或 None | ✅ | T13（回退路径读码 + 用例） |
| v1 手改未重算 digest | 写前校验 | `ReplanError` | ✅ | T14 passed |
| 目标未批准 | 改 goal | `ReplanError` | ✅ | T09/T15 passed |
| 无触发证据 | 拆分 | `DecomposeError` | ✅ | T17 passed |
| 超预算搜索 | budget=0/不足 | 空选中 + exhausted | ✅ | T22 passed |

## 6. 性能验收

本批无性能门槛；Ledger 与搜索均为 O(节点数) 纯函数。一次读数：

```text
ledger_40_nodes_ms=0.224
```

## 7. 兼容性验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| G8a schema 不变 | `test_research_plan.py` 回归 | 21 条全绿 | ✅ | 228 passed（含 executor） |
| 阶段产物契约不变 | Stage 15/9 回归 | 既有 artifacts 不变 | ✅ | 228 passed；新增仅 `plan/ledger.json`、`plan/search.json` |
| 旧 run 兼容 | 无 plan 目录 | 钩子 no-op | ✅ | T23/T25 passed |

## 8. ADD 审计

本批无 ADD 新增或修订。

## 9. Review 记录（Step 8）

- RESEARCH §5 的 E1-E7 ↔ DESIGN §1 的 D-1..D-8 ↔ CHECKLIST §2 的 4 项映射一一对应。
- 外部证据 T1：E1-E6；T3：E7（仅陷阱对照）。
- 算法锚点见 IMPLEMENTATION §4；测试清单 T01-T25 见 §3。
- 实施完成：27 passed（T01-T25 + 2 条 no-op 拆分）；首轮 T07 期望缺陷已修正并记录（IMPLEMENTATION §8）。
- 红→绿读数见 IMPLEMENTATION §8；门禁读数见 §10。

## 10. 统计与结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|------|------|------|------|------|
| 文档一致性 | 4 | 4 | 0 | 0 |
| 功能 | 4 | 4 | 0 | 0 |
| 接口 | 8 | 8 | 0 | 0 |
| 不变式 | 8 | 8 | 0 | 0 |
| 错误处理 | 6 | 6 | 0 | 0 |
| 性能 | 0 | 0 | 0 | 0 |
| 兼容性 | 3 | 3 | 0 | 0 |
| ADD 审计 | 0 | 0 | 0 | 0 |
| **总计** | **33** | **33** | **0** | **0** |

算术自洽：33 = 4+4+8+8+6+0+3+0；通过 33 = 总数 33。

### 10.2 验收结论

- [x] 验收通过：27 passed（T01-T25 + 2 条 no-op）；相关回归 228 + 113 passed。
- [ ] 验收不通过：无。

### 10.3 全量回归（本机环境说明）

本批未改动 G8a 之外的阶段内核；定向回归 228（plan + executor）与 113（guards 子集）全绿。本机全量 pytest 仍受 P-155 已记录的两处环境限制（Windows 无法执行 `.sh`；Keras 3/tf-keras 缺失），与本批无关。

## 11. 行动与遗留

| 事项 | 状态 | 说明 |
|------|------|------|
| 代码实施 | 已完成 | 4 模块 + 存储版本化 + Stage 15/9 钩子 |
| 测试与验收 | 已完成 | 27 passed；33/33 通过 |
| 异构复审 | 待做 | 合并前按约定执行 |
| Q15/Q16 | provisional | 本批采用建议值，不宣称正式裁决 |
| LLM 自动重规划 | 未做 | 本批只交付演进原语 |
| G6/G7 | 未开始 | 另立批次，均 P2 |
