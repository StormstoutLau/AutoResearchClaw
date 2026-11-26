---
id: arc-stage10-entrypoint-budget-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-26
depends: [arc-stage10-entrypoint-budget-IMPLEMENTATION]
upstream: arc-stage10-entrypoint-budget-IMPLEMENTATION
---

# 验收清单：B-30

| ID | 断言 | 结果 |
|---|---|---|
| C-1 | 截断后第二次调用预算为 65536 | ✅ `test_truncation_escalates_to_65536`（calls == [32768, 65536]） |
| C-2 | 提示含 `≤150 行` 与 `Do NOT re-implement` | ✅ `test_prompt_caps_file_length` |
| C-3 | 兜底驱动满足入口契约（守卫 + METRIC_DEF） | ✅ `test_builds_driver_over_entry_function` |
| C-4 | 候选优先级 main > train | ✅ `test_prefers_main_over_train` |
| C-5 | 无入口函数时返回 None，不造假 | ✅ `test_returns_none_without_entry_function` |
| C-6 | 跳过 main.py 与语法错误模块 | ✅ `test_skips_main_and_syntax_errors` |
| C-7 | 生成失败时 `_ensure_entrypoint` 使用兜底并写盘 | ✅ `test_falls_back_to_synthesized_driver` |
| C-8 | repair 连续 2 次不可用即停止 | ⏳ 代码审查确认（无独立单测，需完整 stage 上下文） |
| C-9 | 相关回归全绿 | ✅ 35 / 80 / 3 passed |
| C-10 | B 站 Stage 10 通过并进入 Stage 12 | ⏳ 待现场 |
