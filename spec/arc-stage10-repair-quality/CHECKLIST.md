---
id: arc-stage10-repair-quality-CHECKLIST
type: design
version: 1.3
status: accepted
date: 2026-11-27
depends: [arc-stage10-repair-quality-IMPLEMENTATION]
upstream: arc-stage10-repair-quality-IMPLEMENTATION
---

> v1.1（2026-11-27，P-213 续）：C-9 扩为三个 repair 站点；新增 C-13（agent 站点两事件）；算术 11→13。
> v1.2（2026-11-27，P-214）：C-12 由运行 I（部署后首跑）现场关闭——5/6 类事件实际出现，`repair_aborted` 因第 2 次修复即被接受而未触发。
> v1.3（2026-11-27，P-216）：新增 C-14（报告写实际 repair 次数）与 C-15（失败态不写 `proceed`）；算术 13→15。

# 验收清单：B-36 P0（repair 取证）

| ID | 断言 | 结果 |
|---|---|---|
| C-1 | trace 记录只含 sha256 与长度，正文不落盘（D-2） | ✅ `test_writes_digests_instead_of_bodies` |
| C-2 | `errors[]` 保留 severity/category/line/col，message 截断到 300 | ✅ `test_errors_are_structured_and_truncated` |
| C-3 | 记录按追加顺序可读回 | ✅ `test_appends_in_order` |
| C-4 | abort 事件带 `invalid_returns` | ✅ `test_abort_carries_the_counter` |
| C-5 | 目标路径不可写时不抛异常，返回 `None`（D-5） | ✅ `test_never_raises_when_path_is_a_file` |
| C-6 | 尾部坏行被跳过，其余可读 | ✅ `test_load_skips_malformed_lines` |
| C-7 | 无 trace 文件时 `load` 返回空 | ✅ `test_missing_trace_loads_empty` |
| C-8 | 必填字段齐全，`stage` 取目录名 | ✅ `test_required_fields_present` |
| C-9 | per-file repair 五类事件 + 项目级 repair + **CodeAgent agent 级修复**均已接线 | ✅ 代码审阅（`_code_generation.py` 6 处、`code_agent.py` 2 处），由 C-11/C-13 覆盖执行路径 |
| C-10 | repair 的提示/预算/止损阈值未变 | ✅ diff 仅新增记录调用；`test_rc_stages.py` 通过 |
| C-11 | 相关回归无退化 | ✅ 195 passed（七文件）+ 110 passed（五文件） |
| C-12 | 真实 repair 运行能读出事件链 | ✅ 运行 I `repair_trace.jsonl` 7 行：`validation_failed`×2 / `repair_request`×2 / `repair_rejected` / `repair_accepted` / `project_repair`；`repair_aborted` 未触发（第 2 次即接受，属正常路径） |
| C-13 | agent 站点写出 `agent_validation_failed` 与 `agent_repair`（含 attempt/max、accepted/rejected/reason） | ✅ `test_agent_validation_and_repair_are_recorded` / `test_agent_repair_without_files_is_recorded` |
| C-14 | BLOCKED 报告写**实际执行**的 repair 次数（非每文件上限），并逐文件列出 | ✅ `TestBlockedReportCounts` 3 例 |
| C-15 | 失败阶段不把默认 `proceed` 写进 `decision.json`；显式 decision 保留 | ✅ `test_write_stage_meta_never_claims_proceed_for_failure` / `test_write_stage_meta_keeps_explicit_failure_decision` |

## 算术

| 段 | 通过 | 待现场 |
|---|---|---|
| 记录模块 | 8（C-1..C-8） | 0 |
| 接线与不变量 | 2（C-9、C-10） | 0 |
| 回归 | 1（C-11） | 0 |
| agent 站点 | 1（C-13） | 0 |
| 现场 | 1（C-12） | 0 |
| 状态一致性 | 2（C-14、C-15） | 0 |
| **合计** | **15 项通过** | **0** |

## 边界

- C-9 是代码审阅结论，不是逐事件单测；P1 会补链路级 fixture。
- C-12 的证据是「事件链可读」，不是「trace 能提升修复率」；后者属 P1。
- 运行 I 的代码不含 agent 站点（`agent_validation_failed` / `agent_repair`）与 `reason=truncated` 细化，两者由单测覆盖（C-13），现场验证留到下一次部署。
- 本批不验证「trace 能提升修复成功率」——那是 P1 的目标。
