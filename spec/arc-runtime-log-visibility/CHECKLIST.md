---
id: arc-runtime-log-visibility-CHECKLIST
type: design
version: 1.1
status: accepted
date: 2026-11-26
depends: [arc-runtime-log-visibility-IMPLEMENTATION]
upstream: arc-runtime-log-visibility-IMPLEMENTATION
---

# 验收清单：B-31a

> v1.1（2026-11-26，P-198）：C-15 由 ⚠️ 转 ✅（剥离实现后重跑得到 ModuleNotFoundError + CLI 参数 MISSING 的真实红态）。

| ID | 断言 | 结果 |
|---|---|---|
| C-1 | 级别名大小写不敏感（`info` / `INFO`） | ✅ `test_case_insensitive` |
| C-2 | 缺省级别为 INFO | ✅ `test_default_is_info` |
| C-3 | 非法级别抛 `ValueError` | ✅ `test_invalid_raises` |
| C-4 | INFO 写入日志文件（默认级别可见） | ✅ `test_info_reaches_file` |
| C-5 | WARNING 级别下 INFO 被过滤、WARNING 保留 | ✅ `test_warning_level_drops_info` |
| C-6 | 重复配置不叠加 handler（D-4 `force=True`） | ✅ `test_repeated_calls_do_not_duplicate_handlers` |
| C-7 | root 级别被实际应用 | ✅ `test_root_level_is_applied` |
| C-8 | 真实 `TextIOWrapper` 被切到行缓冲（D-5） | ✅ `test_real_text_stream_is_switched` |
| C-9 | 无 `reconfigure` 的流降级返回 `False` | ✅ `test_stream_without_reconfigure_is_ignored` |
| C-10 | 阶段进行中日志文件持续增长 | ✅ `test_log_file_grows_while_stage_runs`（单测级模拟，非真实 Stage 10） |
| C-11 | `run --log-level` 默认 INFO、大小写归一 | ✅ `test_defaults`、`test_level_is_uppercased` |
| C-12 | `run --log-file` 被解析 | ✅ `test_log_file_accepted` |
| C-13 | 相关回归无退化 | ✅ 88 passed（cli / rc_cli / rc_runner / runner_events / blueprint_persistence） |
| C-14 | B 站 Stage 10 重跑期间重定向日志持续增长且含 INFO 行 | ⏳ 待现场（未部署） |
| C-15 | TDD 红→绿记录 | ✅ 剥离实现后 `ModuleNotFoundError: researchclaw.runtime.logging_setup`（exit 2）+ CLI 探针 `MISSING MISSING`；恢复后 13 passed + `INFO None`（见 IMPLEMENTATION §4） |

## 算术

14 项本地通过（C-1..C-13、C-15）+ 1 项现场待验（C-14）。通过 14，待验证 1。

## 边界

- 心跳与 `STALLED` 不在本批（B-31b），验收不以「阶段内有无心跳」为条件。
- C-10 是两次日志调用之间的文件增长，不等价于真实长阶段的持续增长。
- `--log-file` 无轮转，属已登记未决项。
