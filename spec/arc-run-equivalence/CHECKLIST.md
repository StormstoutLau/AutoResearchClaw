---
id: arc-run-equivalence-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-24
depends: [arc-run-equivalence-IMPLEMENTATION, arc-run-equivalence-DESIGN]
upstream: null
---

# 审查验收 Checklist：重跑等价性对照实验（P-149）

> **Feature**：P-149。
> **基于实施**：[IMPLEMENTATION.md](./IMPLEMENTATION.md)（v1.0 / verified）。
> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **验收边界**：1 新模块 + 1 CLI 扩展 + 1 测试；P-147/P-148 行为不变。

---

## 1. 文档一致性验收

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN 可追溯到 RESEARCH | ✅ | D-1..D-8 对应 RESEARCH §2/§3 |
| DESIGN ↔ IMPLEMENTATION 变更面一致 | ✅ | 均为「1 新 + 1 扩展 + 1 测试」 |
| 读数在 checklist 有验收项 | ✅ | 16 + 57 ↔ §2/§7 |
| 术语一致（字段、命令、退出码） | ✅ | 四文档逐字一致 |

## 2. 功能验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 同构双 run 判等价 | `compare_runs` | `equivalent=True`、差异空 | ✅ | `test_identical_runs_are_equivalent` |
| 阶段序列差异 | 右侧缺 stage 23 | 记 `stage_sequence` | ✅ | `test_detects_stage_sequence_difference` |
| 阶段失败差异 | 右侧多 `stage.failed` | 记 `stage_failures` | ✅ | `test_detects_stage_failure` |
| 工具序列差异 | 右侧换工具 | 仅记 `tool_sequence` | ✅ | `test_detects_tool_sequence_difference` |
| 参数哈希差异 | 右侧换参数 | 仅记 `params_sequence` | ✅ | `test_detects_params_difference` |
| 状态差异 | 右侧 `status=error` | 仅记 `status_sequence` | ✅ | `test_detects_status_difference` |
| 产物哈希差异 | 右侧改产物 | `changed=["out.txt"]` | ✅ | `test_detects_artifact_hash_difference` |
| 易变字段忽略 | 不同 run_id/时间/绝对路径 | 判等价 | ✅ | `test_volatile_fields_are_ignored` |
| 空 run fail-closed | 两个空目录 | 仅记 `activity`、判不等价 | ✅ | `test_empty_runs_fail_closed` |

## 3. 接口验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 报告结构 | `compare_runs` | 五键齐全、`left`/`right` 摘要完整 | ✅ | 判定用例 |
| `checks` 固定 8 | 任意输入 | `checks == 8` | ✅ | `test_identical_runs_are_equivalent` |
| CLI 三态与 JSON | `runs compare` | 0/1/2；`--json` 可 `json.loads` | ✅ | 3 条 CLI 用例 |

## 4. 不变式验收

| 不变式 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| J-1 只读 | 调用前后 mtime 比对 | 完全一致 | ✅ | `test_is_read_only` |
| J-2 易变字段忽略 | 双 run 不同元数据 | 判等价 | ✅ | `test_volatile_fields_are_ignored` |
| J-3 链坏即不等价 | 篡改事件/动作记录 | 对应差异出现 | ✅ | 两条链用例 |
| J-4 空 run fail-closed | 两个空目录 | `equivalent=False` | ✅ | `test_empty_runs_fail_closed` |
| J-5 缺目录抛错 | 不存在路径 | `FileNotFoundError` | ✅ | `test_missing_run_dir_raises` |
| J-6 报告可序列化 | `--json` | `json.loads` 成功 | ✅ | `test_compare_reports_equivalent` |

## 5. 错误处理验收

| 场景 | 测试方法 | 通过条件 | 状态 | 证据 |
|------|---------|---------|------|------|
| run 目录缺失 | API | 抛 `FileNotFoundError` | ✅ | `test_missing_run_dir_raises` |
| 事件链损坏 | 篡改 payload | 记 `event_chain` | ✅ | `test_detects_broken_event_chain` |
| 动作链损坏 | 篡改 tool 字段 | 记 `action_chain` | ✅ | `test_detects_broken_action_chain` |

## 6. 性能验收

一次性读取事件与账本，无性能验收项。

## 7. 兼容性验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 既有模块零改动 | 变更清单 | `EventLog`/`ActionLedger`/`pipeline_manifest` 未修改 | ✅ | IMPL §1 |
| P-143/P-146/P-147/P-148 回归 | 57 条 | 全绿 | ✅ | IMPL §2 |

## 8. ADD 审计

本批无 ADD 新增或修订，故无审计项。

## 9. Review 记录（Step 8）

- RESEARCH §3 的 8 类判据 ↔ DESIGN §3 表 ↔ 实现 `CHECKS=8` 与六组序列 + 两链三方一致。
- DESIGN §5 的 J-1..J-6 ↔ CHECKLIST §4 ↔ 测试函数逐条对应。
- DESIGN §4 退出码 ↔ CLI 用例三态一致。
- 诚实边界：确定性双 run 对照实验已做；真实 LLM 重跑未做，登记 §11。

## 10. 统计与结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|------|------|------|------|------|
| 文档一致性 | 4 | 4 | 0 | 0 |
| 功能 | 9 | 9 | 0 | 0 |
| 接口 | 3 | 3 | 0 | 0 |
| 不变式 | 6 | 6 | 0 | 0 |
| 错误处理 | 3 | 3 | 0 | 0 |
| 性能 | 0 | 0 | 0 | 0 |
| 兼容性 | 2 | 2 | 0 | 0 |
| ADD 审计 | 0 | 0 | 0 | 0 |
| **总计** | **27** | **27** | **0** | **0** |

算术自洽：27 = 4+9+3+6+3+0+2+0；通过 27 = 总数 27。

### 10.2 验收结论

- [x] 验收通过：27/27；16 条新用例 + 57 条回归。
- [ ] 验收不通过：无阻塞项。

## 11. 行动与遗留

| 事项 | 状态 | 说明 |
|------|------|------|
| PR 合并 | 待授权 | — |
| 真实 LLM 重跑 | 未做 | 需人工执行并采集两份 run 后再判定 |
| 重试次数比较 | 未纳入 | 当前按 completed 折叠，重试不参与判定 |
| 未入账产物 | 已知边界 | 只比较 `actions.jsonl` 记录的 outputs |
