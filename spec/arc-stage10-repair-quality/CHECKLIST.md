---
id: arc-stage10-repair-quality-CHECKLIST
type: design
version: 1.5
status: accepted
date: 2026-11-28
depends: [arc-stage10-repair-quality-IMPLEMENTATION]
upstream: arc-stage10-repair-quality-IMPLEMENTATION
---

> v1.1（2026-11-27，P-213 续）：C-9 扩为三个 repair 站点；新增 C-13（agent 站点两事件）；算术 11→13。
> v1.2（2026-11-27，P-214）：C-12 由运行 I（部署后首跑）现场关闭——5/6 类事件实际出现，`repair_aborted` 因第 2 次修复即被接受而未触发。
> v1.3（2026-11-27，P-216）：新增 C-14（报告写实际 repair 次数）与 C-15（失败态不写 `proceed`）；算术 13→15。
> v1.4（2026-11-27，P-220）：新增 C-16（深修计数不为负、余量单独报告）；算术 15→16。
> v1.5（2026-11-28，P-222）：新增 C-17..C-19（agent 修复三闸门）；算术 16→19。

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
| C-16 | 深修计数不为负：`fixed = max(0, 修复前 − 剩余)`，余量单独报告 | ✅ `TestDeepRepairCounts` 3 例（含运行 J 的 -14/3 形态） |
| C-17 | agent 修复回复语法错误或破坏 `main.py` 入口契约时整文件拒收，原文件保留 | ✅ `test_syntax_broken_repair_keeps_previous_file` / `test_repair_that_breaks_entrypoint_is_rejected` |
| C-18 | 修复不得减少蓝图声明符号：回退即拒收并列出丢失名，补全则接受 | ✅ `test_repair_that_drops_declared_symbols_is_rejected` / `test_repair_that_restores_symbols_is_accepted` |
| C-19 | 修复回复截断时升级一次 32768；未知模块不进入项目（`main.py` 例外需过契约） | ✅ `test_truncated_repair_retries_at_32768` / `test_unknown_module_is_not_added` / `test_missing_main_can_be_added_when_contract_holds` |

## 算术

| 段 | 通过 | 待现场 |
|---|---|---|
| 记录模块 | 8（C-1..C-8） | 0 |
| 接线与不变量 | 2（C-9、C-10） | 0 |
| 回归 | 1（C-11） | 0 |
| agent 站点 | 1（C-13） | 0 |
| 现场 | 1（C-12） | 0 |
| 状态一致性 | 3（C-14、C-15、C-16） | 0 |
| 修复验收闸门 | 3（C-17、C-18、C-19） | 0 |
| **合计** | **19 项通过** | **0** |

## 边界

- C-9 是代码审阅结论，不是逐事件单测；P1 会补链路级 fixture。
- C-12 的证据是「事件链可读」，不是「trace 能提升修复率」；后者属 P1。
- 运行 I 的代码不含 agent 站点（`agent_validation_failed` / `agent_repair`）与 `reason=truncated` 细化，两者由单测覆盖（C-13），现场验证留到下一次部署。
- 本批不验证「trace 能提升修复成功率」——那是 P1 的目标。
