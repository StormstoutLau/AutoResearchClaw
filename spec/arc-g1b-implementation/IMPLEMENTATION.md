---
id: arc-g1b-implementation-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1b-implementation-DESIGN]
upstream: arc-g1b-implementation-DESIGN
---

# 实施记录：G1b（supervisor / exit codes / attempt / outbox）

## 1. 改动清单

| 文件 | 类型 | 内容 |
|---|---|---|
| `researchclaw/runtime/exit_codes.py` | 新增 | `ExitClass`、`classify_results`、`is_retryable`、六类退出码 |
| `researchclaw/runtime/attempt.py` | 新增 | `AttemptRecord`、`write/read/latest_attempt`、`build_resume_note`、产物清单 |
| `researchclaw/runtime/outbox.py` | 新增 | `Effect`、`pending`、`enqueue`、`run_pending`、`(kind,key)` 去重 |
| `researchclaw/runtime/supervisor.py` | 新增 | `Supervisor` 循环、full jitter、预算、残留租约清理、`default_worker_cmd` |
| `researchclaw/runtime/lease.py` | 修改 | 新增 `LeaseKeeper` 后台续期线程（R-3） |
| `researchclaw/pipeline/runner.py` | 修改 | 启动/停止 keeper；租约丢失时拒绝写事件；每 Stage 写 attempt 记录 |
| `researchclaw/cli.py` | 修改 | `cmd_run` 返回分类码；新增 `supervisor` 子命令与 dispatch |
| `tests/test_g1b_runtime.py` | 新增 | 13 用例（退出码/attempt/outbox） |
| `tests/test_supervisor.py` | 新增 | 8 用例（循环/预算/keeper） |
| `tests/test_rc_cli.py` | 修改 | 暂停断言 0 → 85（R-1 行为变更） |

## 2. 三缺口的落地

| 缺口 | 落地 | 证据 |
|---|---|---|
| **R-1** 非失败终态 | `85 PAUSED_NORMAL`；`paused/blocked_approval/rejected` → 85；失败优先于暂停 | `test_paused_is_not_success_and_not_failure`、`test_failure_wins_over_paused` |
| **R-2** 租约所有权 | supervisor 全程不 `acquire`；只在重启前释放**已过期**的残留租约 | `test_supervisor_log_and_no_lease`、`test_stale_lease_is_released_before_restart` |
| **R-3** 长任务续期 | `LeaseKeeper` 每 TTL/3 续期；`LeaseLost` → 置 `_LEASE_LOST` → `_emit` 拒绝写入 | `test_lease_keeper_renews`、`test_lease_keeper_reports_loss` |

## 3. 验收结果

| 验收 | 状态 | 依据 |
|---|---|---|
| A1-7 退出码分类 | ✅ | 六类码 + 仅 75 可重试；CLI 实际返回 |
| A1-11 三层状态 | ✅ | attempt 记录不迁移 `StageStatus`（`_record_attempt` 只写记录） |
| A1-12 resume_note | ✅ | ≤500 字，含阶段/错误/产物/恢复要求 |
| A1-10 outbox | ✅ | queued−done 去重；重复运行不重复执行；失败终态记录 |
| A1-3 supervisor | ✅（单测） | 循环、退避、预算、暂停不重启；**真实 kill -9 集成测试未在本机执行** |
| A1-9 attempt 续接 | ⚠️ 部分 | 记录 `session_id`/`context_replayed` 字段；backend 续接未接线（U-2） |
| A1-2 SSE/WS | ❌ 未纳入 | 按 RESEARCH §2 切分到 **P-031** |

## 4. 行为变更（需知悉）

| 变更 | 影响 |
|---|---|
| `cmd_run` 暂停由 `0` 改为 `85` | 依赖退出码 0 判断「成功」的外部脚本需改为「0 或 85」；CI 若以 0 为唯一成功会显式红，属预期 |
| 每个 Stage 结束写 `<run>/attempts/stage-NN/attempt-k.json` | 新增目录；不影响既有 `stage-NN/` 语义 |
| 运行时启动后台续期线程 | 进程退出时 daemon 线程自动结束；`ARC_EVENTS_DISABLED=1` 时不启动 |

## 5. 测试与机检

| # | 检查 | 结果 |
|---|---|---|
| V1 | G1b 单测 | **21 passed** |
| V2 | runner/CLI 回归 | **99 passed**（含更新后的暂停断言） |
| V3 | `pre-commit run --all-files` | 待回填 |
| V4 | `step_enforce --base HEAD` | 待回填 |
| V5 | `test_packaging` / `test_docs_and_adapters` | 待回填 |

## 6. 边界

- [x] 未引入 Temporal/Restate
- [x] outbox 不落原文（仅 kind/key/result）
- [x] supervisor 不写 `events.jsonl`（写独立 `supervisor.jsonl`）
- [x] A1-2 明确切分到 P-031，未在本批半实现
