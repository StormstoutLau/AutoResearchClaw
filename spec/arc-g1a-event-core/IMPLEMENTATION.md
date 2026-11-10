---
id: arc-g1a-event-core-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1a-event-core-DESIGN]
upstream: arc-g1a-event-core-DESIGN
---

# 实施记录：G1a 事件内核

## 1. 改动清单

| 文件 | 类型 | 内容 |
|---|---|---|
| `researchclaw/runtime/__init__.py` | 新增 | 包声明 |
| `researchclaw/runtime/event_log.py` | 新增 | 信封/链/fsync/滚动/配额/保留/摘要/重放/重建 |
| `researchclaw/runtime/lease.py` | 新增 | 租约 + fencing 单调 |
| `researchclaw/pipeline/runner.py` | 修改 | `_runtime_begin/_emit/_runtime_end`、原子 heartbeat、`read_checkpoint` 恢复 |
| `tests/test_event_log.py` | 新增 | 12 用例 |
| `tests/test_lease.py` | 新增 | 7 用例 |
| `tests/test_runner_events.py` | 新增 | 5 用例（含 A1-5 恢复） |

## 2. 关键实现

- **链**：`prev_sha256 = sha256(上一行规范化 JSON)`；`seq=1` 用 64 个 `0`。
- **fsync**：`write`→`flush`→`os.fsync`；`OSError` → `EventDurabilityError`，**不重试**。
- **滚动**：达阈值把 `events.jsonl` 改名为 `events.<first>-<last>.jsonl`，新文件续链。
- **保留**：滚动段按 mtime 归档为 `.gz`（30 天）或删除（365 天）；活动日志永不移动。
- **租约**：`O_EXCL` 锁文件串行化；`release` 保留 `released:true` 以维持 fencing 单调。
- **恢复**：`read_checkpoint` 在 checkpoint 缺失/损坏时读事件日志重建并原子写回。

## 3. 测试结果

```
tests/test_event_log.py     12 passed
tests/test_lease.py          7 passed
tests/test_runner_events.py  5 passed
回归：test_rc_runner / test_rc_checkpoint / test_run_state / G1a → 106 passed
```

| 验收 | 用例 |
|---|---|
| A1-1 | `test_append_chain_and_payload_digest`、`test_tamper_breaks_chain`（中间行） |
| A1-4 | `test_second_owner_is_rejected`、`test_expired_lease_can_be_taken_over_with_higher_fencing`、`test_release_then_reacquire_bumps_fencing`、`check_fencing` |
| A1-5 | `test_read_checkpoint_recovers_from_event_log`、`test_rebuild_checkpoint_from_stage_completed` |
| A1-6 | `test_run_quota_is_enforced`、`test_segment_rolling_keeps_chain`、`test_retention_archives_then_deletes` |
| 撕裂尾行 | `test_torn_tail_is_dropped_and_appends_continue` |
| fsync 失败 | `test_fsync_failure_raises_durability_error` |
| 递归守卫 | `test_nested_call_reuses_outer_log` |

## 4. 与设计的偏差

| # | 偏差 | 原因 |
|---|---|---|
| D-1 | `Lease` 增加 `released` 字段，`release` 不再删除文件 | 删除会重置 fencing（RESEARCH R-1） |
| D-2 | 链校验测试改为篡改**中间行** | 尾行篡改在链语义下不可检，改由 summary `chain_tail` 兜底（R-2） |
| D-3 | 新增 `_ACTIVE_EVENT_LOGS` 守卫 | 递归 PIVOT/REFINE 会重复收口（R-3） |
| D-4 | 新增 `ARC_EVENTS_DISABLED` 环境开关 | 为极端/测试环境留可逆通道；默认开启 |

## 5. 机检

| # | 检查 | 结果 |
|---|---|---|
| V1 | G1a 单测 + 回归 | **106 passed** |
| V2 | `pre-commit run --all-files` | **9/9 Passed** |
| V3 | `step_enforce --base HEAD` | exit 0 |
| V4 | `test_packaging` / `test_docs_and_adapters` / `test_cli_agent_wiring` | **36 passed** |
| V5 | `roadmap_coverage_check --check` | accept=106 missing=0 |

## 6. 边界

- [x] 未改 `checkpoint.json` 的权威语义（事件仍是投影）
- [x] 未引入 Temporal/Restate；无新第三方依赖（`sqlite3` 未使用）
- [x] 未实现 supervisor / attempts / outbox / SSE（G1b）
- [x] 事件 payload 不含原文与凭据
