---
id: arc-node-equivalence-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-24
depends: [arc-node-equivalence-IMPLEMENTATION, arc-node-equivalence-DESIGN]
upstream: null
---

# 审查验收 Checklist：产物节点等价性与 summary digest（P-150）

> **Feature**：P-150。
> **基于实施**：[IMPLEMENTATION.md](./IMPLEMENTATION.md)（v1.0 / verified）。
> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **验收边界**：1 模块扩展 + 1 测试扩展；CLI、命令与退出码不变。

---

## 1. 文档一致性验收

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN 可追溯到 RESEARCH | ✅ | D-1..D-8 对应 RESEARCH §2/§3/§4 |
| DESIGN ↔ IMPLEMENTATION 变更面一致 | ✅ | 均为「1 扩展 + 1 测试」 |
| 读数在 checklist 有验收项 | ✅ | 23 + 57 + 真实复判 ↔ §2/§7 |
| 术语一致（来源、字段、检查数） | ✅ | `ledger`/`node_index`/`none`、`run_summary`、`checks=9` 四文档一致 |

## 2. 功能验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 节点索引回退可用 | 无账本、同内容 | 判等价、来源 `node_index` | ✅ | `test_node_index_fallback_equivalent` |
| 节点索引差异识别 | 同 locator 不同内容 | `changed=["stage-01/goal.md"]` | ✅ | `test_node_index_fallback_detects_change` |
| 账本优先 | 有动作 + 索引不同 | 判等价、来源 `ledger` | ✅ | `test_ledger_preferred_over_node_index` |
| summary 差异识别 | 两份 summary 不同 | 仅记 `run_summary` | ✅ | `test_detects_summary_difference` |
| summary 单侧缺失 | 删除文件 | 记 `run_summary`、右侧 `null` | ✅ | `test_detects_missing_summary` |
| 节点索引损坏 | 非法 JSON | 抛 `ValueError` | ✅ | `test_malformed_node_index_raises` |
| summary 损坏 | 非法 JSON | 抛 `ValueError` | ✅ | `test_malformed_summary_raises` |
| P-149 八类判据不回退 | 既有 13 条判定用例 | 全部通过 | ✅ | 23 passed |
| 易变字段仍被忽略 | 不同 run_id/时间/路径 | 判等价 | ✅ | `test_volatile_fields_are_ignored` |
| 空 run 仍 fail-closed | 两个空目录 | `activity` 差异 | ✅ | `test_empty_runs_fail_closed` |

## 3. 接口验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 报告新增字段 | `compare_runs` | `artifacts_source`、`summary_digest` 齐全 | ✅ | 判定用例 |
| `checks` 固定 9 | 任意输入 | `checks == 9` | ✅ | `test_identical_runs_are_equivalent` |
| CLI 三态不变 | `runs compare` | 0/1/2；`--json` 可解析 | ✅ | 3 条 CLI 用例 + 真实复判 exit 1 |

## 4. 不变式验收

| 不变式 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| J-1 只读 | 调用前后 mtime | 完全一致 | ✅ | `test_is_read_only` |
| J-2 账本优先 | 两侧索引不同、账本同 | 判等价 | ✅ | `test_ledger_preferred_over_node_index` |
| J-3 回退可识别差异 | 索引不同 | 记 `artifacts` | ✅ | `test_node_index_fallback_detects_change` |
| J-4 回退可判等价 | 索引相同 | 判等价 | ✅ | `test_node_index_fallback_equivalent` |
| J-5 summary 差异/缺失 | 改内容、删文件 | 判不等价 | ✅ | 两条 summary 用例 |
| J-6 损坏输入抛错 | 非法 JSON | `ValueError` | ✅ | 两条损坏用例 |

## 5. 错误处理验收

| 场景 | 测试方法 | 通过条件 | 状态 | 证据 |
|------|---------|---------|------|------|
| 节点索引不可解析 | 非法 JSON | `ValueError` | ✅ | `test_malformed_node_index_raises` |
| summary 不可解析 | 非法 JSON | `ValueError` | ✅ | `test_malformed_summary_raises` |
| run 目录缺失 | 不存在路径 | `FileNotFoundError` | ✅ | `test_missing_run_dir_raises` |

## 6. 性能验收

一次性读取事件、账本、节点索引与 summary，无性能验收项。

## 7. 兼容性验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| P-143/P-146/P-147/P-148 回归 | 57 条 | 全绿 | ✅ | IMPL §2 |
| 账本路径行为不变 | P-149 既有判定用例 | 全绿 | ✅ | 23 passed |

## 8. ADD 审计

本批无 ADD 新增或修订，故无审计项。

## 9. Review 记录（Step 8）

- RESEARCH §3 方案 C ↔ DESIGN D-1/D-2/D-3 ↔ 实现来源分支与 `run_summary` 三方一致。
- DESIGN §5 J-1..J-6 ↔ CHECKLIST §4 ↔ 测试函数逐条对应。
- `checks` 8→9 在 RESEARCH §4、DESIGN D-4、IMPLEMENTATION §2、CHECKLIST §3 四处显式登记。
- 真实数据复判：P-149 同一对 run 由 `true` 变为 `false`，差异定位到 5 个产物文件 + summary。

## 10. 统计与结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|------|------|------|------|------|
| 文档一致性 | 4 | 4 | 0 | 0 |
| 功能 | 10 | 10 | 0 | 0 |
| 接口 | 3 | 3 | 0 | 0 |
| 不变式 | 6 | 6 | 0 | 0 |
| 错误处理 | 3 | 3 | 0 | 0 |
| 性能 | 0 | 0 | 0 | 0 |
| 兼容性 | 2 | 2 | 0 | 0 |
| ADD 审计 | 0 | 0 | 0 | 0 |
| **总计** | **28** | **28** | **0** | **0** |

算术自洽：28 = 4+10+3+6+3+0+2+0；通过 28 = 总数 28。

### 10.2 验收结论

- [x] 验收通过：28/28；23 条新/改用例 + 57 条回归 + 真实双 run 复判。
- [ ] 验收不通过：无阻塞项。

## 11. 行动与遗留

| 事项 | 状态 | 说明 |
|------|------|------|
| PR 合并 | 待授权 | — |
| 账本非空但 outputs 为空 | 已知边界 | 仍标 `ledger`，不回退 |
| 节点树完整性 | 未纳入 | 由 `verify_tree` 负责，避免职责重叠 |
| 真实 LLM 再跑 | 未做 | 复用 P-149 两份真实 run 复判 |
