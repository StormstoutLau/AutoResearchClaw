---
id: arc-runtime-progress-heartbeat-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-27
depends: [arc-stage10-intra-stage-checkpoint, arc-runtime-log-visibility]
upstream: arc-master-roadmap
---

# 调研：阶段内步骤级进度与心跳（B-31b / B-33 L1 扩展）

> 触发：2026-11-27 运行 I 的进度核对——`steps.jsonl` 2.5 小时只有 2 行，`heartbeat.json` 停在两天前，但进程实际存活。

## 1. 现场读数（运行 I，P-214）

| 观测面 | 读数 | 结论 |
|---|---|---|
| `stage-10/steps.jsonl` | 2 行，均为 `blueprint`（attempt 1 seq 1、attempt 2 seq 2） | CodeAgent Phase 2/2.5/对齐共 70+ 分钟无步骤记录 |
| `heartbeat.json` | `timestamp=2026-11-25T14:14:37Z`、`last_stage=11`、pid 为旧进程 | 阶段内从未更新；不能区分「运行中」与「已死」 |
| `checkpoint.json` | `in_progress_stage=10`、`in_progress_at=00:31` | 断点可恢复，但无进行时进度 |
| `lease.json` | `expires_at` 滚动到当前 +10 min | 租约续期正常（可作旁证） |
| `.inflight/token-*.json` | 每次 LLM 调用更新 | 调用级旁证存在，但不是阶段语义 |
| `p01`/`p213` 日志 | INFO 实时增长 | B-31a 已生效 |

## 2. 代码面根因

| 位置 | 现状 | 缺口 |
|---|---|---|
| [`step_journal.append_step`](../../researchclaw/pipeline/step_journal.py#L138-L179) | 追加式账本，只存摘要 | 本身可用 |
| [`CodeAgent._record_module_failure`](../../researchclaw/pipeline/code_agent.py#L580-L606) | 只在模块失败时写 `generate_file(failed)` | 成功模块不写 |
| [`CodeAgent._persist_blueprint`](../../researchclaw/pipeline/code_agent.py#L608-L644) | 蓝图写 `blueprint(done)` | 覆盖 Phase 1 |
| [`runner._write_heartbeat`](../../researchclaw/pipeline/runner.py#L255-L275) | 仅在 `result.status == DONE` 调用 | 阶段内无写入路径 |
| [`run_state.read_run_state`](../../researchclaw/run_state.py#L216-L289) | 心跳超时 → `UNKNOWN`；无 `STALLED` | 无法区分「没在跑」与「卡住」 |
| [`dashboard/collector.py`](../../researchclaw/dashboard/collector.py#L16-L19) | 固定 60s 活跃阈值 | 不读心跳自带间隔 |

## 3. 已复核的设计来源

- [长跑进度可观测调研](../../docs/arc-longrun-progress-observability-20261126.md) §6.1：`ProgressKeeper` + `STALLED` + `silence_sec`；M1 不改阶段实现。
- [异构复审](../../docs/arc-longrun-progress-review-20261126.md) D-1：`STALLED` 必须一次改齐 `run_state` / `collector` / `projects`；T-15 确认枚举变更路径。
- [B-33 DESIGN](../arc-stage10-intra-stage-checkpoint/DESIGN.md) D-4/D-5：复合键 `(step_id, variant)`、摘要 only。
- [B-31a spec](../arc-runtime-log-visibility/)：日志可见性已生效，本批只补心跳与步骤账本。

## 4. 本批范围

| 级别 | 动作 | 验收 |
|---|---|---|
| M1 | `runtime/progress.py` 的 `ProgressKeeper`：阶段内每 30s 原子写 `heartbeat.json`，投影 `steps.jsonl` 的末步 | 90s 假阶段至少刷新 2 次；载荷含 `updated_at/interval_sec/last_step` |
| M1 | `RunStatus.STALLED` + `RunState.silence_sec`；仅当 `in_progress_stage` 存在且心跳静默超阈值时判定 | 陈旧心跳 + in-progress → `stalled`；完成后仍 `unknown` |
| M2 | CodeAgent 步骤账本补全：`generate_file(done)`、`entrypoint`、`hard_validation`、`alignment`、`generate_project` | 每模块/每轮校验/每次对齐均有行；空 outputs 不可复用 |

## 5. 非目标

- 不引入 `__ARC_PROGRESS__` stdout 协议（文件账本优先，复审 D-1 已裁决）。
- 不新增事件类型、不改事件配额（A1-6）。
- 不做 supervisor 的 stall 自动重启（B-31 M3）。
- 不做 phase 级可恢复标记（B-33 L2/L3）。
- 不改 `should_skip` 的复用判据。
