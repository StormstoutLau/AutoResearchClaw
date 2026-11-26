---
id: arc-stage10-entrypoint-contract-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-26
depends: [arc-stage10-entrypoint-contract-IMPLEMENTATION]
upstream: arc-stage10-entrypoint-contract-IMPLEMENTATION
---

# 验收清单：B-29

| ID | 断言 | 结果 |
|---|---|---|
| C-1 | 契约判定覆盖空文件、语法错误、缺守卫、缺 `METRIC_DEF`、合规 | ✅ `TestEntrypointIssues` 6 例 |
| C-2 | 序列生成不再把首个文件改名，`config.py` 保留 | ✅ `test_sequential_generation_does_not_rename_first_file` |
| C-3 | 缺 `main.py` 时专用生成并写盘 | ✅ `test_generates_missing_main` |
| C-4 | 不合契约时用上次拒绝原因重试，2 次内成功 | ✅ `test_regenerates_invalid_main` |
| C-5 | 已合规时零 LLM 调用 | ✅ `test_noop_when_contract_already_satisfied` |
| C-6 | 两次都失败时保留原文件、不伪造 | ✅ `test_leaves_files_alone_when_generation_fails` |
| C-7 | repair 拒绝缺守卫的 `main.py`，保留合法其他文件 | ✅ `TestRepairRejectsBadEntrypoint` 2 例 |
| C-8 | CodeAgent 专用入口生成在无效输出后重试 | ✅ `test_entrypoint_generation_retries_on_invalid_output` |
| C-9 | 相关回归全绿 | ✅ 73 passed + 264 passed |
| C-10 | B 站 Stage 10 产出可运行 `main.py` 且 Stage 12 出数 | ⏳ 待现场（B-11） |
