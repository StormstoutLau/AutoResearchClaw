---
id: arc-runtime-progress-heartbeat-CHECKLIST
type: design
version: 1.1
status: accepted
date: 2026-11-27
depends: [arc-runtime-progress-heartbeat-IMPLEMENTATION]
upstream: arc-runtime-progress-heartbeat-IMPLEMENTATION
---

# 验收清单：阶段内步骤级进度与心跳（B-31b / B-33 L1 扩展）

| ID | 断言 | 结果 |
|---|---|---|
| C-1 | 阶段启动即写心跳（不等到第一个间隔） | ✅ `test_start_writes_heartbeat_immediately` |
| C-2 | 心跳按间隔刷新 | ✅ `test_heartbeat_refreshes_after_interval` |
| C-3 | 心跳投影 `steps.jsonl` 末步：`last_step` / `phase` / `steps_done` | ✅ `test_heartbeat_projects_last_journal_step` |
| C-4 | 目标路径不可写时不抛异常 | ✅ `test_write_failure_is_not_fatal` |
| C-5 | 保留 `timestamp` / `last_stage` 旧字段，新增 `updated_at` / `interval_sec` | ✅ C-1 断言 + 载荷实现 |
| C-6 | 陈旧心跳 + `in_progress_stage` → `STALLED`，带 `silence_sec` | ✅ `test_stale_heartbeat_with_in_progress_is_stalled` |
| C-7 | 陈旧心跳 + 已完成 checkpoint 仍为 `UNKNOWN` | ✅ `test_stale_heartbeat_without_in_progress_stays_unknown` |
| C-8 | 心跳 `interval_sec` 参与有效阈值（不误报 inactive） | ✅ `test_interval_extends_the_liveness_window` |
| C-9 | `silence_sec` 进入 `RunState.to_dict` / dashboard / projects | ✅ `test_to_dict_carries_silence` + collector/projects 透传 |
| C-10 | CodeAgent 每个成功模块写 `generate_file(done)`（含 outputs 摘要） | ✅ `test_each_generated_module_is_journalled` |
| C-11 | 专用入口 / 硬校验轮 / 对齐判词均有账本记录 | ✅ `test_dedicated_entrypoint_is_journalled` / `test_hard_validation_round_is_journalled` / `test_failed_hard_validation_is_journalled` |
| C-12 | 进度行（空 outputs）不可被 `should_skip` 复用 | ✅ `test_progress_rows_are_never_reusable` |
| C-13 | 相关回归无退化 | ✅ 181 + 68 + 316 passed；仅 `test_sentinel_script_is_valid_bash` 为 Windows 路径环境性失败 |
| C-14 | 重跑时新鲜 `status=running` 心跳覆盖上一轮的 `failed` summary，阶段号取 `in_progress_stage`；无 `status` 的旧心跳与 `done` 心跳语义不变 | ✅ `test_live_rerun_overrides_stale_failed_summary` / `test_heartbeat_without_status_keeps_failed_summary` / `test_finished_heartbeat_stays_completed`；B 站现场读出 `running / stage 10 / is_active True` |

## 算术

| 段 | 通过 |
|---|---|
| 心跳写入与容错 | 5（C-1..C-5） |
| 状态判定 | 4（C-6..C-9） |
| 步骤账本 | 3（C-10..C-12） |
| 回归 | 1（C-13） |
| 现场复验 | 1（C-14） |
| **合计** | **14 项通过** |

## 边界

- C-6 的 `STALLED` 只在 `in_progress_stage` 存在时成立；这是有意保留的旧 run 兼容语义。
- C-11 的对齐记录由 `_code_generation` 的判词分支覆盖，未在测试中构造完整对齐链路；以账本行存在与代码锚点为准。
- 未做告警/自动重启（B-31 M3）；未部署 B 站。
