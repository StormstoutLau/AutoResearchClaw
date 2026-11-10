---
id: arc-g1b-supervisor-protocol-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1a-event-core-DESIGN, arc-g1-readiness-research-DESIGN, arc-master-roadmap]
upstream: arc-g1a-event-core-DESIGN
---

# 调研：G1b 自愈与协议面

> **Feature**：G1b 七项验收（A1-2/3/7/9/10/11/12）。本文件只做**调研与方案对比**，不动代码。
> **Spec 步骤**：Step 1-2（T1：结论将定义 supervisor 退出码契约、attempt 状态模型与公开事件接口）

## 1. 目标与问题分解

| 子问题 | 覆盖验收 |
|---|---|
| **P-1 进程守护**：谁看守 worker、崩溃后如何重启、哪些错误不该重启 | A1-3、A1-7 |
| **P-2 状态分层**：Run / Stage / Attempt 如何分离，重试如何续接上下文 | A1-9、A1-11、A1-12 |
| **P-3 协议面**：断线补拉（SSE `Last-Event-ID` / WS 首帧 subscribe）与游标分页 | A1-2 |
| **P-4 副作用**：入队与状态同源、崩溃后不重复执行 | A1-10 |

## 2. 现状实测（2026-11-10）

| # | 事实 | 证据 |
|---|---|---|
| F-1 | CLI 无 `supervisor` / `worker` 子命令；只有 `run` / `serve` / `dashboard` 等 | `python -m researchclaw --help` |
| F-2 | 重试是**进程内**：`_call_with_retries` 按 `contract.max_retries` 循环，无进程重启 | `executor.py:613-630` |
| F-3 | `StageResult` 只有 `stage/status/artifacts/error/decision/evidence_refs`，**无 attempt / session_id** | `_helpers.py:34-43` |
| F-4 | `StageStatus` 九态（pending/running/blocked_approval/approved/rejected/paused/retrying/failed/done），**无 Attempt 概念** | `stages.py:65-74` |
| F-5 | 已有目录级版本化先例：`stage-NN_v{attempt}/`（PIVOT/REFINE 回滚时） | `runner.py:1365-1397` |
| F-6 | 无 `/events` / `/events/stream` 路由；现有路由只到 `/runs/{id}/metrics` | `server/routes/pipeline.py` |
| F-7 | WS 仅 `/ws/chat`；dashboard 广播无历史缓冲、无补拉 | `routes/chat.py:34`、`dashboard/broadcaster.py` |
| F-8 | G1a 已提供 `EventLog.read_after(seq)` 与 `events_summary.json` | `runtime/event_log.py` |
| F-9 | 退出码未分类：任何失败都走 `break`，由人工 `--resume` | `runner.py:790-794` |

**结论**：G1b 的四个子问题**全部从零开始**，唯一可复用的是 G1a 的事件流与 F-5 的版本目录先例。

## 3. 方案空间

### 3.1 P-1 进程守护

| 方案 | 做法 | 评价 |
|---|---|---|
| **A 自带 supervisor 子进程** | `supervisor` 以子进程方式拉起 `run --resume`，按退出码决定重启/停止 | 与 file-as-state 一致；Windows 可用；无新依赖 |
| B 交给 systemd/容器 | 只写 unit/容器配置 | 跨平台差；本地开发不可用；无法感知 stage 级状态 |
| C 引入 Temporal/Restate | 换编排引擎 | 违背「第一版不引入」约束（roadmap §4 G1） |

**建议 A**，并把退出码契约作为 supervisor 与 worker 之间的**唯一接口**（可单测）。

### 3.2 P-2 状态分层

| 方案 | 做法 | 评价 |
|---|---|---|
| **A 三层 + 目录承载** | Run=`run/`、Stage=`stage-NN/`、Attempt=`stage-NN/attempt-<k>/` + `attempt.json` | 与 file-as-state、F-5 先例一致；可审计 |
| B 单层 + 字段 | 只加 `attempt` 字段到 checkpoint | 无法保留每次尝试的产物差异 |
| C 事件即状态 | 只靠事件流推导 | 与 I-1「checkpoint 权威」冲突 |

**建议 A**：`attempt.json` 记录 `{attempt, started_at, ended_at, exit_code, exit_class, session_id, resume_note}`；Stage 状态由 executor 在**收到 attempt 结果后**统一迁移，attempt 退出码不直接写 Stage。

### 3.3 P-3 协议面

| 方案 | 做法 | 评价 |
|---|---|---|
| **A SSE + 游标 API** | `GET /events?after=&limit=`；`GET /events/stream` 用 `Last-Event-ID` | 符合 WHATWG；浏览器原生重连 |
| B 仅 WS | 扩展 `/ws/chat` | 断线补拉要自定义语义，易与 SSE 漂移 |
| C 仅轮询 | 前端定时拉 | 简单但延迟高、重复读放大 |

**建议 A + WS 首帧 subscribe 复用同一序列化器**（roadmap 实现约束已规定）。

### 3.4 P-4 副作用

| 方案 | 做法 | 评价 |
|---|---|---|
| **A 日志即 outbox** | `effect.queued` 事件 + 消费侧 `(kind,key)` 去重 + `effect.done` | 无数据库事务；与 G1a 天然衔接 |
| B 独立 outbox 文件 | 单独 outbox.jsonl | 又一份真值源，需额外一致性 |
| C 直接执行 | 不登记，失败重跑 | 崩溃后重复副作用 |

**建议 A**。

## 4. 外部锚点

| # | 锚点 | 可复用结论 | 等级 |
|---|---|---|---|
| X-1 | Candea & Fox, *Crash-Only Software*（HotOS 2003） | 只保留「崩溃 + 恢复」一条路径，恢复逻辑即启动逻辑 | T1 论文 |
| X-2 | Candea et al., *Microreboot*（arXiv cs/0406005） | 组件级重启可恢复大部分故障，成本远低于整机 | T1 论文 |
| X-3 | AWS, *Exponential Backoff And Jitter* | 全抖动（full jitter）避免重试同步；SDK 已内置 | T1 官方 |
| X-4 | systemd `Restart=` / `RestartPreventExitStatus=` | 按退出状态**显式**排除不重启的错误 | T1 手册 |
| X-5 | Kubernetes *Pod Lifecycle* | 重启退避 10s→20s→40s…，上限 **5 分钟**；稳定运行 10 分钟后重置 | T1 官方 |
| X-6 | WHATWG HTML §9.2 *Server-sent events* | `id:` / `retry:` / `Last-Event-ID` 语义；UTF-8、CRLF 或 LF | T1 标准 |
| X-7 | Temporal *Retry Policy* | `InitialInterval` / `BackoffCoefficient` / `MaximumInterval` / `MaximumAttempts` / 非重试错误 | T1 官方 |
| X-8 | Transactional outbox + idempotent consumer（Spring / Azure 架构中心） | 至少一次投递 + 消费端按稳定 id 去重 | T1 官方文档 |
| X-9 | Stripe *Idempotent requests* | 幂等键保存首次结果，重试返回同一响应 | T1 官方 |
| X-10 | Google SRE（重试预算） | 重试占流量比例设上限（约 10%），超限 fail-closed | T1 书/官方 |

## 5. 建议（供 DESIGN 落地）

1. **退出码契约**（P-1）：`0` 成功；`75 TEMPFAIL`（OOM/NET/超时）可重启；`77 NOPERM` / `78 CONFIG` / `65 DATA`（版本不兼容、凭据撤销、配置错误）**不重启**。对齐 systemd 的 `RestartPreventExitStatus` 语义（X-4）与 sysexits 习惯。
2. **退避**（P-1）：full jitter，`base=2s`，`cap=300s`（X-3/X-5），连续成功 10 分钟后重置计数（X-5），`max_restarts` 默认 5（X-7）。
3. **三层状态**（P-2）：Run/Stage/Attempt；`attempt.json` 为每尝试真值；Stage 只由 executor 迁移。
4. **续接**（P-2）：`session_id` 随 attempt 保存；仅当上次失败可重试且 backend 支持时传给下一次 attempt；否则重放上下文（受 A1-9 约束）。
5. **resume_note**（P-2）：新 attempt 携带「上次失败阶段/错误/已存在产物清单」，要求先查产物再重复付费调用。
6. **协议**（P-3）：SSE `id=<seq>`；`Last-Event-ID` 优先于 `after` 查询参数；`after` 早于最旧段 → 返回 `stream.gap` 事件（含 `oldest_seq`）而非静默跳号。
7. **outbox**（P-4）：`effect.queued{kind,key,payload}`；消费者只处理无 `effect.done{key}` 的项；key = `sha256(kind + canonical(payload))`。
8. **重试预算**（P-1，交叉约束）：单 run 重试次数与总时长设上限（X-10 的本地化），超限即 `supervisor_exhausted`。

## 6. 未决项

- **U-1 退出码的具体映射**：判据 = 各 backend 的错误是否可稳定归类；触发 = 实现首个 supervisor；倾向 = 先覆盖 OOM/超时/配置/凭据四类；E2。
- **U-2 session 续接的 backend 覆盖面**：判据 = CLI 代理是否暴露 resume 能力；触发 = 实现 attempt；倾向 = 支持则用、不支持则标注 `context_replayed`；E2。
- **U-3 SSE 与 WS 的序列化统一**：判据 = 两端字段是否完全一致；触发 = 协议实现；倾向 = 共用 `EventEnvelope` 投影；E1。
- **U-4 旧 run 的兼容**：判据 = 无 `attempt.json` 的历史 run 如何处理；触发 = 首个历史 run 恢复；倾向 = 视为 attempt=1 的只读视图；E2。
- **U-5 重试预算的具体数值**：判据 = 单 run 合理重试次数；触发 = 压测；倾向 = 5 次 / 30 分钟；E3。

## 7. 引用

1. Candea, G., Fox, A. *Crash-Only Software*. HotOS IX, 2003. https://www.usenix.org/conference/hotos-ix/crash-only-software
2. Candea, G. et al. *Microreboot — A Technique for Cheap Recovery*. https://arxiv.org/abs/cs/0406005
3. AWS Architecture Blog. *Exponential Backoff And Jitter*. https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
4. systemd. *systemd.service* — `Restart=`, `RestartPreventExitStatus=`.
5. Kubernetes. *Pod Lifecycle* — container restart backoff.
6. WHATWG. *HTML Standard* §9.2 Server-sent events.
7. Temporal. *Retry Policy* — https://docs.temporal.io/encyclopedia/retry-policies
8. Azure Architecture Center. *Idempotent Consumer Pattern*.
9. Stripe. *Idempotent requests*.
10. Google SRE. *Handling Overload* / retry budget.
11. 仓内：[P-027 事件内核](../arc-g1a-event-core/DESIGN.md)、[P-025 §8](../arc-q5-decision-method/RESEARCH.md)
