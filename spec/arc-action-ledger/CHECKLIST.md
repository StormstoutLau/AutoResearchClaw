---
id: arc-action-ledger-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-24
depends: [arc-action-ledger-IMPLEMENTATION, arc-action-ledger-DESIGN]
upstream: null
---

# 审查验收 Checklist：动作级证据账本（P-143）

> **Feature**：P-143。
> **Spec 步骤**：Step 7-8。
> **基于实施**：[IMPLEMENTATION.md](./IMPLEMENTATION.md)（v1.0 / verified）。
> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **验收边界**：3 个文件；`events.jsonl` schema、23 阶段、workflow 均零改动。

---

## 1. 文档一致性验收

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN 决策可追溯到 RESEARCH | ✅ | D-1..D-7 逐条指向 RESEARCH §1/§3/§4 |
| DESIGN ↔ IMPLEMENTATION 变更面一致 | ✅ | 两文档均为「3 个文件」 |
| IMPLEMENTATION 读数在 checklist 有验收项 | ✅ | 10 + 58 读数 ↔ §2/§4 |
| 术语一致（字段名、类名、用例名） | ✅ | 四文档逐字一致 |

## 2. 功能验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 追加一条动作 | `record()` | 返回 seq=1、文件存在 | ✅ | `test_record_appends_and_verifies` |
| 链式指针 | 读第二行 | `prev_sha256` = 首行哈希 | ✅ | 同上 |
| 参数哈希 | 读记录 | `params_sha256` 以 `sha256:` 开头 | ✅ | 集成用例 |
| 输入哈希 | 构造文件 | 哈希等于 `hash_path` | ✅ | `test_input_and_output_hashes` |
| 输出哈希 | 构造文件 | 存在则记录、缺失则跳过 | ✅ | 同上 |
| env / seed | 显式传入 | 原样落盘 | ✅ | `test_env_seed_and_approver` |
| 审批人 | `grant(by=...)` | `approver == "peng"` | ✅ | `test_invoker_records_approver_identity` |

## 3. 接口验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| `ActionLedger` 公共方法 | 调用 | `record/read_all/verify_chain/last_seq/count` 可用 | ✅ | 账本用例 |
| `ToolInvoker` 向后兼容 | 不传新参数 | 行为不变、无 `actions.jsonl` | ✅ | `test_invoker_without_ledger_unchanged` |

## 4. 不变式验收

| 不变式 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| J-1 seq 连续 + 指针成链 | `verify_chain` | `ok (2 actions)` | ✅ | 账本用例 |
| J-2 摘要覆盖全字段 | 改一处字段 | 校验失败且报 `record_sha256` | ✅ | `test_tamper_is_detected` |
| J-3 输入缺失拒绝 | 传不存在路径 | 抛 `FileNotFoundError`、count 不变 | ✅ | `test_missing_input_raises` |
| J-4 撕裂尾 fail-closed | 追加坏行 | 校验失败且报 `malformed` | ✅ | `test_malformed_tail_fails_closed` |
| J-5 动作 ↔ 事件关联 | 调 invoker | `event_seq_call=1`、`event_seq_result=2` | ✅ | 集成用例 |

## 5. 错误处理验收

| 场景 | 测试方法 | 通过条件 | 状态 | 证据 |
|------|---------|---------|------|------|
| 工具失败 | handler 返回 `success=False` | 动作 `status="error"` | ✅ | `test_invoker_records_error_status` |
| 账本写入失败 | 设计审阅 | 只告警，不影响工具返回 | ✅ | DESIGN D-6 |

## 6. 性能验收

本批只在启用账本时增加一次小文件追加与 fsync；未启用时零开销，故无性能验收项。

## 7. 兼容性验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 工具子系统回归 | `pytest test_tool_*` | `58 passed` | ✅ | IMPL §2 |
| 事件流不变 | 审阅 + 用例 | `tool.call/result` 字段不变 | ✅ | IMPL §3.2 |

## 8. ADD 审计

本批无 ADD 新增或修订，故无审计项。

## 9. 审查结论

| 维度 | 结论 |
|---|---|
| 正确性 | 10 条新用例全绿；58 条工具子系统回归全绿 |
| 可逆性 | 3 个文件、单提交可回退 |
| 风险 | 账本写入为「尽力而为」，失败可静默丢一条动作；已按 D-6 接受 |
| 卫生 | 未触碰事件 schema、阶段与 workflow |

## 10. 统计与结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|------|------|------|------|------|
| 文档一致性 | 4 | 4 | 0 | 0 |
| 功能 | 7 | 7 | 0 | 0 |
| 接口 | 2 | 2 | 0 | 0 |
| 不变式 | 5 | 5 | 0 | 0 |
| 错误处理 | 2 | 2 | 0 | 0 |
| 性能 | 0 | 0 | 0 | 0 |
| 兼容性 | 2 | 2 | 0 | 0 |
| ADD 审计 | 0 | 0 | 0 | 0 |
| **总计** | **22** | **22** | **0** | **0** |

算术自洽：22 = 4+7+2+5+2+0+2+0；通过 22 = 总数 22。

### 10.2 验收结论

- [x] 验收通过：22/22 全通过；10 条新用例与 58 条回归读数齐备。
- [ ] 验收不通过：无阻塞项。

## 11. 行动与遗留

| 事项 | 状态 | 说明 |
|------|------|------|
| PR 合并 | 待授权 | 本批只推分支 |
| CLI 查询 | 未做 | P-145 候选 |
| dashboard 时间线 | 未做 | 依赖账本稳定后再做 |
| 23 阶段接入 | 未做 | 只接 `ToolInvoker` |
