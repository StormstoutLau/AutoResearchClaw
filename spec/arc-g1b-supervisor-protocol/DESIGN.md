---
id: arc-g1b-supervisor-protocol-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1b-supervisor-protocol-RESEARCH]
upstream: arc-g1b-supervisor-protocol-RESEARCH
---

# 设计：G1b supervisor / attempt / 协议面

> 输入：[RESEARCH.md](RESEARCH.md) §5 建议。本文件定义**待实施契约**；实现批次按此执行。

## 1. 决策

| ID | 决策 |
|---|---|
| D-1 | 新增 `researchclaw supervisor --run-id <id>`，以子进程拉起 worker（`python -m researchclaw run --resume`） |
| D-2 | **退出码契约**是 supervisor 与 worker 的唯一接口：`0` 成功；`75` 可重试；`65/77/78` 不可重试 |
| D-3 | 退避 = full jitter，`base 2s`、`cap 300s`、`max_restarts 5`、连续稳定 10 分钟重置 |
| D-4 | Run / Stage / Attempt 三层；`attempt.json` 为每尝试真值，Stage 状态只由 executor 迁移 |
| D-5 | `session_id` 与 `resume_note` 写入 `attempt.json`；可重试且 backend 支持时续接 |
| D-6 | SSE `id=<seq>` + `Last-Event-ID` 优先；缺口返回 `stream.gap`，不静默跳号 |
| D-7 | WS 首帧 `{type:"subscribe", run_id, after}`，与 SSE 共用同一投影 |
| D-8 | outbox = `effect.queued` 事件 + `(kind,key)` 去重 + `effect.done` |
| D-9 | 单 run 重试预算：`max_restarts 5` 或总时长 30 分钟，先到即 `supervisor_exhausted` |

## 2. 退出码契约（D-2）

| 码 | 含义 | supervisor 动作 | 典型来源 |
|---|---|---|---|
| `0` | 正常结束 | 退出，写 `run.completed` | — |
| `75` | 暂时性失败 | **重启**（退避） | OOM(137)、网络超时、沙箱短暂不可用 |
| `65` | 数据/输入错误 | 停止，`run.failed{data}` | 输入不可解析、产物缺失 |
| `77` | 权限/凭据失效 | 停止，`run.failed{revoked}` | 401/403、token 撤销 |
| `78` | 配置/版本不兼容 | 停止，`run.failed{config}` | schema 版本不符、参数非法 |

- worker 侧新增 `ExitClass` 枚举与 `classify_exit(stage_status, error) -> int`；**分类表可单测**。
- 未识别错误 → `75`（保守，交给退避与上限兜底）。

## 3. supervisor 循环

```
acquire lease(run)                 # G1a，fencing 单调
restarts = 0
while True:
    rc = spawn_worker(run_id, resume=True).wait()
    if rc == 0: break
    cls = classify(rc)
    if cls != RETRYABLE: record run.failed; break
    restarts += 1
    if restarts > MAX_RESTARTS or elapsed > MAX_WALL: record supervisor_exhausted; break
    sleep(full_jitter(attempt=restarts, base=2, cap=300))
renew/release lease
```

- 每次重启前写 `stage.retried{attempt, reason, delay}` 事件。
- **只重启，不修补**：恢复逻辑全部复用既有 `--resume` + `read_checkpoint`（含 G1a 的事件重建）。

## 4. Attempt 模型（D-4/D-5）

```
<run>/
  checkpoint.json            # Run 级：最后完成 stage（权威，I-1）
  events.jsonl               # 投影 + outbox
  stage-05/
    attempt-1/               # 本次尝试的产物快照/日志
      attempt.json
    attempt-2/
```

`attempt.json`：

```jsonc
{
  "attempt": 2,
  "started_at": "...", "ended_at": "...",
  "exit_code": 75, "exit_class": "retryable",
  "session_id": "acp-abc123",        // 可空
  "resume_note": "上次在 Stage 12 超时；已存在 stage-12/results.json（md5=…），先校验再重跑",
  "context_replayed": false
}
```

- **Stage 状态迁移只发生在 executor**：attempt 的 `exit_code` 不直接写 `StageStatus`。
- 历史 run（无 attempt 目录）按 `attempt=1` 只读视图处理（U-4）。
- 与既有 `stage-NN_v{k}/` 并存：`_v{k}` 是 PIVOT/REFINE 的**语义回滚**快照，`attempt-<k>/` 是**执行重试**记录，不复用同一目录。

## 5. resume_note 生成规则（A1-12）

输入：最后一次 `stage.failed` 事件、`stage-NN/` 现存产物清单（名称 + 大小 + digest）。

输出模板（≤ 500 字）：

```
[attempt N] 上次失败：Stage 12 (EXPERIMENT_RUN) 超时（exit 75）。
已存在产物：stage-12/results.json (12KB)、stage-12/code/main.py (3KB)。
恢复要求：先校验上述产物与 Stage 10 的 experiment_spec 是否一致；一致则跳过付费重跑，
         不一致再重跑。禁止无条件重复外部付费调用。
```

## 6. 协议面（D-6/D-7）

| 接口 | 语义 |
|---|---|
| `GET /api/runs/{id}/events?after=<seq>&limit=500` | 游标分页；`limit` 上限 2000 |
| `GET /api/runs/{id}/events/stream` | SSE；首帧 `retry: 3000`；每事件 `id: <seq>` + `event: <type>` + `data: <json>`；15s 心跳注释 `: ping` |
| `Last-Event-ID` | 优先于 `after`；两者都缺省 = 从 `oldest_seq` 开始 |
| 缺口 | 请求 `after` < 最旧段首 seq → 先发 `event: stream.gap`，`data: {oldest_seq}`，再从 `oldest_seq` 续 |
| WS | 首帧 `{type:"subscribe", run_id, after}`；后续帧与 SSE `data` 同构 |

## 7. Outbox（D-8）

```jsonc
// 入队（与 stage 事件同一次 append 序列，先 queued 后 completed）
{"type":"effect.queued","payload":{"kind":"overleaf_sync","key":"sha256:…","args_digest":"…"}}
// 完成
{"type":"effect.done","payload":{"key":"sha256:…","result":"ok"}}
```

- 消费者启动时扫描全量事件，构建 `queued - done` 集合；同一 `key` 只执行一次。
- 执行前先写 `effect.started{key}`（便于崩溃定位）；执行结果只记 digest/状态，不落原文。
- 幂等键 = `sha256(kind + canonical(payload))`，与 Stripe 的客户端幂等键同构（X-9）。

## 8. 验收映射

| 验收 | 落点 |
|---|---|
| A1-2 | §6 SSE + `Last-Event-ID` + `stream.gap`；`EventLog.read_after` 已有 |
| A1-3 | §3 supervisor 循环；kill -9 后 `--resume` + 事件重建 |
| A1-7 | §2 退出码契约（四类 + 保守默认） |
| A1-9 | §4 attempt + `session_id` 续接；`context_replayed` 显式标注 |
| A1-10 | §7 outbox + `(kind,key)` 去重 |
| A1-11 | §4 三层状态，attempt 不直写 Stage |
| A1-12 | §5 `resume_note` 模板 |

## 9. 风险与回滚

| 风险 | 缓解 |
|---|---|
| Windows 无 POSIX 信号，kill -9 等价性 | supervisor 用 `subprocess` + `terminate/kill`；测试用 `taskkill /F` 或 `proc.kill()` |
| 子进程孤儿 | 父进程退出时 `kill` 子进程组；启动时按 `lease.json` 的 pid 清理残留 |
| attempt 目录膨胀 | 每 stage 最多保留最近 2 个 attempt（可配置），其余归档到 `attempts_archive/` |
| SSE 长连接占用 | 单 run 连接数上限 + 心跳超时断开 |

回滚：`supervisor` 为新增入口，`run` 原路径不变；SSE 路由为新增，不影响既有 API。
