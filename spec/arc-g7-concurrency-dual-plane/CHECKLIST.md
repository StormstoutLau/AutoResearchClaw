---
id: arc-g7-concurrency-dual-plane-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-25
depends: [arc-g7-concurrency-dual-plane-IMPLEMENTATION, arc-g7-concurrency-dual-plane-DESIGN]
upstream: arc-master-roadmap
---

# 审查验收 Checklist：G7 并发/双平面段（P-172）

> **状态**：**42/43 通过**；C-2（两轮 CI）待回填。
> **计数**：**43 项 = 文档 4 + 功能 14 + 接口 6 + 不变式 10 + 错误 6 + 兼容 3**。

## 0. DoR / DoD

- **DoR**：A7-2/A7-3/A7-5/A7-6/A7-7 的判据已冻结；`SlotRegistry`/`InflightLimiter`/`ops` 源码锚点可达；测试可在本机重复运行。
- **DoD**：逐项独立读数写入本表；不得用测试总数推算分项（RULE-2）。

## 1. 文档一致性

| 检查项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| D-1 RESEARCH E1-E10 回原文 | RESEARCH v1.0 | 每条含 URL 与要点 | ✅ | §2.1 八条工业源 + §2.2 两条学术源 |
| D-2 DESIGN D-1..D-10 覆盖实现 | 四文档 | 每条决策有落点 | ✅ | D-1..D-10 ↔ IMPLEMENTATION §1/§3 |
| D-3 IMPLEMENTATION 源码锚点 | 四文档 | ≥15 个文件/行锚点 | ✅ | §1 表 19 行锚点 |
| D-4 术语一致 | 四文档 | slot/fencing/queued/normal_capacity 同义 | ✅ | 四文档 grep 一致 |

## 2. 功能验收

| 验收项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| F-1 槽申请/释放/snapshot | T-A1 | `s1`/fencing=1/active 0-1/by_class 正确 | ✅ | `test_acquire_makes_one_slot_and_release_frees_it` |
| F-2 同 run 幂等 | T-A2 | 两次 acquire 返回同 slot_id/fencing，active=1 | ✅ | `test_same_run_is_idempotent_and_does_not_take_two_slots` |
| F-3 normal 保留 HITL | T-A3 | 第 2 个 normal 入队；hitl 立即拿槽 | ✅ | `test_normal_capacity_reserves_a_slot_for_hitl` |
| F-4 HITL 总上限 | T-A4 | 两个 hitl + 一个 normal 后第三个失败 | ✅ | `test_hitl_cannot_exceed_total_capacity` |
| F-5 释放唤醒排队 | T-A5 | 队列清空、fencing+1 | ✅ | `test_releasing_a_normal_slot_lets_the_queued_run_start` |
| F-6 过期槽回收 | T-A6 | 旧槽清除、新槽 fencing=2 | ✅ | `test_expired_slot_is_reclaimed_but_live_slot_is_not` |
| F-7 fencing 单调 | T-A7 | registry 与返回值一致 | ✅ | `test_registry_file_is_readable_and_fencing_is_monotonic` |
| F-8 预算前置拒绝 | T-A8/T-A9 | >/=/< 三态 + 无日志 | ✅ | `test_preflight_budget_rejects_at_or_over_limit`、`test_preflight_budget_without_log_is_ok` |
| F-9 inflight 上限 | T-I1/T-I2 | 峰值 ≤2；0 为 no-op | ✅ | `test_limit_is_never_exceeded`、`test_zero_limit_is_a_noop` |
| F-10 supervisor 准入 | T-S1..S4 | spawn 前持槽、超时 queued、预算拒绝、HITL 保留 | ✅ | 四个 `test_slot_*` / `test_admission_*` / `test_budget_*` / `test_hitl_*` |
| F-11 A7-2 并发隔离 | T-C1/T-C2 | 两 run 租约/事件/沙箱独立；同目录第二写者拒绝 | ✅ | `test_two_runs_have_independent_leases_events_and_sandboxes`、`test_same_run_directory_rejects_a_second_writer` |
| F-12 A7-3 双平面 | T-C3/T-C4 | 两平面 status 一致；篡改 A 不影响 B | ✅ | `test_both_claim_planes_agree_under_concurrent_runs`、`test_tampered_claim_is_detected_without_touching_the_other_run` |
| F-13 ops 看板 | T-O1/T-O4 | 重启/恢复/失败阶段/事件数；坏行容忍 | ✅ | `test_build_ops_view_reports_restarts_recovery_and_failures`、`test_build_ops_view_tolerates_a_bad_event_line` |
| F-14 归档 sweep | T-O3 | 旧段 gzip、active 不动、索引写入、run 保留 | ✅ | `test_sweep_runs_archives_old_segments_and_writes_index` |

## 3. 接口验收

| 验收项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| I-1 `SlotRegistry.acquire` | DESIGN §3.1 | 签名/超时异常/幂等齐备 | ✅ | [admission.py L272](../../researchclaw/runtime/admission.py#L272) |
| I-2 `release` 幂等 | DESIGN §3.3 | 二次释放返回 False，不误删他槽 | ✅ | F-1 用例 + [L302](../../researchclaw/runtime/admission.py#L302) |
| I-3 `preflight_budget` | DESIGN §3.4 | 返回三键；超限抛 `BudgetRejected` | ✅ | F-8 用例 |
| I-4 `InflightLimiter.slot` | DESIGN §5 | 上下文管理器，finally 释放 | ✅ | F-9 + `test_timeout_when_all_tokens_are_held` |
| I-5 `build_ops_view`/`sweep_runs` | DESIGN §6 | 返回 `runs/totals` 与 `ok/runs` | ✅ | F-13/F-14 |
| I-6 CLI/配置 | DESIGN §7 | `ops`、`--hitl-priority`、五个新字段可解析 | ✅ | 配置探针（IMPLEMENTATION §4）+ [cli.py L536](../../researchclaw/cli.py#L536) |

## 4. 不变式

| 不变式 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| J-1 无槽不 spawn | DESIGN §8 | spawn 回调看到本 run 槽 | ✅ | F-10 `test_slot_is_held_before_spawn_and_released_after` |
| J-2 退出必释放 | DESIGN §8 | 正常退出后 active=0 | ✅ | 同上 + `try/finally` |
| J-3 同 run 不占两槽 | DESIGN §8 | active 恒 1 | ✅ | F-2 |
| J-4 活槽不夺/死槽可回收 | DESIGN §8 | 过期回收；活槽拒绝新 normal | ✅ | F-6 + F-3 |
| J-5 normal 不吞保留容量 | DESIGN §8 | 1 normal 后 normal 入队、hitl 拿槽 | ✅ | F-3/F-4 |
| J-6 预算拒绝先于 spawn | DESIGN §8 | spawn 未被调用 | ✅ | F-10 `test_budget_is_rejected_before_spawn` |
| J-7 inflight ≤ limit | DESIGN §8 | 3 线程峰值 ≤2 | ✅ | F-9 |
| J-8 ops 视图只读 | DESIGN §8 | 前后目录哈希一致 | ✅ | `test_build_ops_view_is_read_only` |
| J-9 双平面一致且审计只读 | DESIGN §8 | status 相等；B 目录哈希不变 | ✅ | F-12 |
| J-10 跨 run 零写入 | DESIGN §8 | 两 run 各写各目录 | ✅ | F-11 |

## 5. 错误处理

| 场景 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| E-1 registry 损坏 | DESIGN §9 | 视为空状态，不崩 | ✅ | `test_corrupt_registry_fails_open_to_empty_state` |
| E-2 容量满 | DESIGN §9 | `AdmissionTimeout` + queue 行 | ✅ | F-3/F-4 |
| E-3 预算恰好等于上限 | DESIGN §9 | 拒绝 | ✅ | `test_preflight_budget_rejects_at_or_over_limit` |
| E-4 inflight 超时 | DESIGN §9 | `InflightTimeout` | ✅ | `test_timeout_when_all_tokens_are_held` |
| E-5 残留 token | DESIGN §9 | 过期 token 被清理 | ✅ | `test_expired_token_is_pruned` |
| E-6 ops 坏行 | DESIGN §9 | 跳过坏行继续 | ✅ | `test_build_ops_view_tolerates_a_bad_event_line` |

## 6. 兼容性与演练

| 环境/项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| C-1 本机 3.13 | 本机 3.13.5 | 新增面全绿 | ✅ | 39 passed（新增面）、215 passed（相关面） |
| C-2 CI 3.11–3.14 | CI 矩阵 | 两轮 8/8 | ⏳ | 待推送后回填 |
| C-3 默认行为不变 | 默认关闭/0 | 全量无新增失败 | ✅ | 3945 passed / 6 环境态失败 / 108 skipped（同 P-171 基线） |
| A7-5 演练 | Runbook §1-§4 | 合成 run 恢复 + 三项验证 | ✅ | supervisor `elapsed=0.34s restarts=1`；`verify ok/converged`；`recovery_seconds=0.08s`；`ops last_stage=4 status=completed` |

## 7. 诚实边界

1. **A7-5 不是独立新人盲测**：演练由作者按 Runbook 执行，worker 为合成脚本（本机无真实 LLM 凭据）；恢复代码路径与生产一致。登记 **U-172-1**。
2. **裸 `researchclaw run` 不经过准入**：只在 supervisor 的 spawn 边界强制；登记 **U-172-2**。
3. **registry 损坏时 fail-open**：可用性优先，极端情况下可能暂时超过容量；下一次成功写入即修复。已在 DESIGN §9 声明。
4. **`recovery_seconds` 对旧 run 为空**：supervisor 的 `worker_started` 日志是本批新增；历史 run 无该行，不回溯补齐。
5. **双平面不是 N-version**：两平面共用 `evaluate_claim`/`compare_claims`，只能证明同 oracle 重放一致与篡改可检（RESEARCH §3.5）。

## 8. 批次自审（ADD）

| 项 | 级别 | 内容 | 处置 |
|---|---|---|---|
| P3-1 | low | A7-5 无独立新人盲测 | 登记 U-172-1，Runbook §6 明示 |
| P3-2 | low | 旧 run 的 `recovery_seconds` 为空 | 设计声明，不回溯 |
| P3-3 | medium | registry 损坏 fail-open 可能短暂超容 | DESIGN §9 声明；可用性优先 |
| P2-1 | medium | 裸 `run` 绕过准入 | 登记 U-172-2；生产入口为 supervisor |

## 9. 门禁读数

| 门禁 | 读数 |
|---|---|
| `dc_validator` | 4 文件 / 0 结果 / **0 违规**（P1=0 P2=0） |
| `step-gate` | `research → design → implement → verify → finalize` **5/5 pass** |
| `verify-anchor` | **10 真实 / 0 硬性 / 0 软性** |
| `step_enforce` | `mode=batch pid=P-172 digest_bound=1` |
| `pre-commit` | **10/10 Passed**（dc/m7/repo-stats/step-enforce/console/blackbox/private/wiring/rework/ci-coverage） |
| 两轮 CI | 待推送后回填 |
