---
id: arc-output-fallback-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-24
depends: [arc-output-fallback-IMPLEMENTATION, arc-output-fallback-DESIGN]
upstream: null
---

# 审查验收 Checklist：零产物账本的回退（P-151）

> **Feature**：P-151。
> **基于实施**：[IMPLEMENTATION.md](./IMPLEMENTATION.md)（v1.0 / verified）。
> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **验收边界**：1 条件判定 + 2 用例；API/CLI/报告结构不变。

---

## 1. 文档一致性验收

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN 可追溯到 RESEARCH | ✅ | D-1..D-5 对应 RESEARCH §2/§3 |
| DESIGN ↔ IMPLEMENTATION 变更面一致 | ✅ | 均为「1 条件 + 2 用例」 |
| 读数在 checklist 有验收项 | ✅ | 25 + 57 ↔ §2/§7 |
| 术语一致 | ✅ | `ledger`/`node_index`/`none`、`checks=9` 四文档一致 |

## 2. 功能验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 零产物账本回退 | 有动作、无 outputs、有索引 | 来源 `node_index` | ✅ | `test_node_index_fallback_when_ledger_has_no_outputs` |
| 回退识别差异 | 同上，索引内容不同 | `changed=["stage-01/goal.md"]` | ✅ | 同上 |
| 账本有产物仍优先 | 账本 outputs 非空、索引不同 | 来源 `ledger`、判等价 | ✅ | `test_ledger_preferred_over_node_index` |
| 无账本回退不回退 | 无动作、有索引 | 来源 `node_index` | ✅ | `test_node_index_fallback_equivalent` |
| 两源皆无 | 有动作、无 outputs、无索引 | 来源 `none`、产物 0 | ✅ | `test_no_artifacts_source_none` |
| 其余判据不变 | 既有 P-150 用例 | 全绿、`checks=9` | ✅ | 25 passed |

## 3. 接口验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| `artifacts_source` 取值 | 全部用例 | 仅 `ledger`/`node_index`/`none` | ✅ | 来源断言 |
| 报告与 CLI 不变 | 3 条 CLI 用例 | 0/1/2、JSON 可解析 | ✅ | CLI 用例 |

## 4. 不变式验收

| 不变式 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| J-1 只读 | 调用前后 mtime | 完全一致 | ✅ | `test_is_read_only` |
| J-2 账本有产物优先 | 两源不同 | 判等价、来源 `ledger` | ✅ | `test_ledger_preferred_over_node_index` |
| J-3 零产物回退识别差异 | 索引不同 | 记 `artifacts` | ✅ | 零产物回退用例 |
| J-4 两源皆无标 `none` | 无索引 | 来源 `none` | ✅ | `test_no_artifacts_source_none` |

## 5. 错误处理验收

| 场景 | 测试方法 | 通过条件 | 状态 | 证据 |
|------|---------|---------|------|------|
| 索引损坏 | 非法 JSON | `ValueError` | ✅ | `test_malformed_node_index_raises` |
| run 目录缺失 | 不存在路径 | `FileNotFoundError` | ✅ | `test_missing_run_dir_raises` |

## 6. 性能验收

只增加一次字典非空判断，无性能验收项。

## 7. 兼容性验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| P-150 用例回归 | 既有 23 条 | 全绿 | ✅ | 25 passed |
| P-143..P-150 模块回归 | 57 条 | 全绿 | ✅ | IMPL §2 |

## 8. ADD 审计

本批无 ADD 新增或修订，故无审计项。

## 9. Review 记录（Step 8）

- RESEARCH §3 表 ↔ DESIGN D-1..D-3 ↔ 实现三行分支逐条一致。
- J-1..J-4 ↔ CHECKLIST §4 ↔ 测试函数对应。
- P-150 的 D-7 边界在本批被显式取代；P-150 文档保持历史原样。

## 10. 统计与结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|------|------|------|------|------|
| 文档一致性 | 4 | 4 | 0 | 0 |
| 功能 | 6 | 6 | 0 | 0 |
| 接口 | 2 | 2 | 0 | 0 |
| 不变式 | 4 | 4 | 0 | 0 |
| 错误处理 | 2 | 2 | 0 | 0 |
| 性能 | 0 | 0 | 0 | 0 |
| 兼容性 | 2 | 2 | 0 | 0 |
| ADD 审计 | 0 | 0 | 0 | 0 |
| **总计** | **20** | **20** | **0** | **0** |

算术自洽：20 = 4+6+2+4+2+0+2+0；通过 20 = 总数 20。

### 10.2 验收结论

- [x] 验收通过：20/20；25 条用例 + 57 条回归。
- [ ] 验收不通过：无阻塞项。

## 11. 行动与遗留

| 事项 | 状态 | 说明 |
|------|------|------|
| PR 合并 | 待授权 | — |
| 账本部分漏记 | 已知边界 | 账本产物 ≥1 时仍整体以账本为准 |
| 真实组合复现 | 未做 | 该组合未在真实 run 中观察到，夹具覆盖 |
