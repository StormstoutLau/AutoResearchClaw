---
id: arc-g1b-implementation-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1b-supervisor-protocol-DESIGN]
upstream: arc-g1b-review-20261110
---

# 调研：G1b 实施前的三缺口解决方案

> **Feature**：P-029 G1b 实施。本文件**先落档 P-030 复核的 R-1/R-2/R-3 解决方案**，再划定本批实施面。
> **Spec 步骤**：Step 1-2（T1：改运行时 + CLI + 测试）

## 1. 三缺口与裁决

### R-1 非失败终态无退出码映射 → 新增 `85 PAUSED_NORMAL`

| 终态 | 退出码 | supervisor 动作 |
|---|---|---|
| 全部 DONE | `0` | 结束，写 `run.completed` |
| 有 FAILED（错误可归类） | `65/77/78` | 停止，写 `run.failed{data/revoked/config}` |
| 有 FAILED（未识别） | `75` | 退避重启 |
| 有 PAUSED / BLOCKED_APPROVAL / REJECTED 且无 FAILED | **`85`** | **停止，写 `run.paused`，不写 run.failed、不重启** |
| 混合（有 FAILED 也有 PAUSED） | 按 FAILED 分类 | 失败优先，人工介入 |

**理由**：审批门是正常工作流（roadmap 三个审批门），把它当失败会触发无意义重启；当成功会让 supervisor 退出后无人续跑。独立码使两者都可表达。

### R-2 supervisor 与 worker 租约冲突 → supervisor **不持有** run 租约

- 租约语义 = 「谁在写事件」，因此**只有 worker 持有**（G1a `_runtime_begin` 已有）。
- supervisor 只做进程管理：spawn / wait / 分类 / 退避 / 预算，不碰 `lease.json`。
- 若 worker 异常退出未释放租约，下一次 spawn 的同一 owner（host:pid 不同）会 `LeaseBusy` → 因此 supervisor 在重启前**按 `lease.json` 的 pid 清理残留**（pid 不存在或已过期才清）。

### R-3 长任务租约无续期 → 后台续期线程（`LeaseKeeper`）

- runner 在 `_runtime_begin` 成功后启动 daemon 线程，每 `TTL/3`（默认 200s）`renew`。
- `renew` 抛 `LeaseLost` → 置 `cancel_event` 并记录 `run.failed{reason:"lease_lost"}`，worker 停止写入。
- `_runtime_end` 停止线程，再 `release`。
- 该线程**不写事件**（避免与主线程的 seq 竞争），只更新 `lease.json`。

## 2. 本批实施面（与 P-031 的切分）

| 项 | 本批（P-029） | 说明 |
|---|---|---|
| A1-7 退出码分类 | ✅ `runtime/exit_codes.py` + CLI `cmd_run` 返回分类码 | 可单测 |
| A1-11 三层状态 | ✅ `runtime/attempt.py`（`attempt.json` + Attempt 记录） | Stage 只由 executor 迁移 |
| A1-12 resume_note | ✅ `attempt.build_resume_note()` | 从事件 + 产物生成 |
| A1-10 outbox | ✅ `runtime/outbox.py`（queued/done 去重） | 日志即 outbox |
| A1-3 supervisor | ✅ `runtime/supervisor.py` + CLI `supervisor` 子命令 | 不持租约（R-2） |
| A1-9 attempt 续接 | ✅ attempt 记录 `session_id` + `context_replayed` 字段 | backend 续接能力按 U-2 判定 |
| A1-2 SSE/游标/WS | ❌ 留给 **P-031** | 需新增路由 + TestClient 用例；与运行时解耦，独立成批更安全 |

**理由**：A1-2 是纯传输层，与其余六项无代码耦合；混在一批会让「运行时正确性」与「HTTP 语义」互相干扰，且本批已有 5 个新模块。

## 3. 现状复测

| # | 事实 | 证据 |
|---|---|---|
| G-1 | `cmd_run` 返回 `0 if failed==0 else 1`，**暂停会返回 0** | `cli.py:472` |
| G-2 | `StageResult` 无 attempt/session_id | `_helpers.py:34-43` |
| G-3 | G1a 租约 TTL 600s，无续期 | `runtime/lease.py` |
| G-4 | `execute_pipeline` 递归 PIVOT/REFINE，已有 `_ACTIVE_EVENT_LOGS` 守卫 | `runner.py:148-191` |
| G-5 | CLI 子命令注册在 `cli.py:1246` 起 | `cli.py` |

## 4. 外部锚点（沿用 P-028，不重复检索）

X-1 crash-only、X-3 AWS 全抖动、X-4 systemd 退出状态排除、X-5 K8s 退避上限、X-7 Temporal 重试策略、X-8/X-9 outbox 与幂等键 —— 见 [P-028 RESEARCH §4](../arc-g1b-supervisor-protocol/RESEARCH.md)。

## 5. 未决项

- **U-1 退出码的业务错误细分**：判据 = 错误文本能否稳定归类到 77/78；触发 = 首批真实失败 run；倾向 = 保守落 75；E2。
- **U-2 session 续接 backend 覆盖**：判据 = CLI 代理是否暴露 resume；触发 = attempt 落地；倾向 = 不支持则 `context_replayed=true`；E2。
- **U-3 残留租约清理的判据**：判据 = pid 复用误杀风险；触发 = supervisor 实现；倾向 = pid 存在且未过期则不清理；E2。

## 6. 引用

1. [P-028 调研](../arc-g1b-supervisor-protocol/RESEARCH.md)、[P-028 设计](../arc-g1b-supervisor-protocol/DESIGN.md)
2. [P-030 复核](../../docs/arc-g1b-review-20261110.md) §4（R-1/R-2/R-3）
3. [P-027 事件内核](../arc-g1a-event-core/DESIGN.md)
