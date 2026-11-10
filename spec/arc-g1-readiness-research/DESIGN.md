---
id: arc-g1-readiness-research-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1-readiness-research-RESEARCH]
upstream: arc-g1-readiness-research-RESEARCH
---

# 设计：Q5 文件事件后端 + Q9 三级保留策略

> 输入：[RESEARCH.md](RESEARCH.md) §6 建议。本文件把建议落成可实施契约；**裁决确认前不写代码**。

## 1. 决策

| ID | 决策 | 依据 |
|---|---|---|
| **D-1** | Q5 = **A（纯文件 + supervisor）**；`events.jsonl` 为事件真值载体，`checkpoint.json` 仍为状态权威（冲突以 checkpoint 为准并告警，I-1） | RESEARCH §3.4 |
| **D-2** | SQLite 仅作为 `DurableBackend` 的**预留实现**，第一版不写 | RESEARCH §3.4、§6.1 触发条件 |
| **D-3** | 每条事件 `write + flush + os.fsync`；**fsync 失败不重试**，run 置 FAILED 并落 `run.failed{reason:"fsync"}` | X-4/X-5 |
| **D-4** | 租约 `lease.json` 携带单调递增 `fencing`；写入侧拒绝低于已见最高值的 token | X-6 |
| **D-5** | A1-10 outbox = `effect.queued` 事件 + 消费侧 `(kind,key)` 幂等；不引入数据库事务 | RESEARCH §3.1 |
| **D-6** | Q9 = 热 30 天 + 段归档 365 天 + `events_summary.json` 永久 | RESEARCH §4.2 |
| **D-7** | 段滚动 8 MB 或 10k 条；单 run 上限 256 MB 或 200k 条，超限拒绝写入 | A1-6 |
| **D-8** | 事件只落 `digest + 摘要`，不落原文/凭据 | R0 既有纪律、GDPR |
| **D-9** | 撕裂尾行（进程死在半行）在读取时丢弃并追加 `event_log_truncated` 诊断事件 | 文件后端的必要补丁 |
| **D-10** | 保留期参数全部可配置，默认值取 Q9-A；CI 用小值（如 0/1 天）测滚动 | A1-6 可测性 |

## 2. EventEnvelope v1

```jsonc
{
  "seq": 1,                       // 单 run 单调递增，从 1 开始
  "ts": "2026-11-10T23:04:05.123+08:00",
  "run_id": "20261110-...",
  "type": "stage.started",        // 见 §2.1
  "stage": 5,                     // 可空
  "attempt": 1,                   // 可空
  "fencing": 7,                   // 写者租约代号
  "payload": { },                 // 只放摘要/digest/计数，不放原文
  "payload_sha256": "...",        // 对 payload 的规范化 JSON 求 sha256
  "prev_sha256": "..."            // 上一条事件整行（不含换行）的 sha256；seq=1 为 64 个 "0"
}
```

- 链定义：`sha256(line_n)` 写入 `line_{n+1}.prev_sha256`；校验 = 顺序重算 + 比对 + 首条 prev 为全 0。
- **规范化 JSON**：`sort_keys=True, separators=(",", ":"), ensure_ascii=False`，UTF-8。
- 文件：`<run>/events.jsonl`（当前段）；归档 `events.<first_seq>-<last_seq>.jsonl.gz`。

### 2.1 事件类型最小集

`run.started` / `run.completed` / `run.failed` / `run.paused` / `stage.started` / `stage.completed` / `stage.failed` / `stage.retried` / `tool.call` / `tool.result` / `llm.call` / `llm.result` / `approval.required` / `effect.queued` / `effect.done` / `event_log_truncated` / `event_log_rolled`

## 3. 写入协议（D-3/D-9）

```
lock(单写者，进程内 + lease 校验)
  line = json(envelope)
  if 段大小/条数超限: 滚动（见 §5）
  write(line + "\n")
  flush()
  os.fsync(fd)
  if fsync 抛 OSError:
      → 不再重试；写 run.failed{reason:"fsync"}（best-effort）
      → 进程退出码 1，状态 FAILED
```

- **为什么不重试**：X-4/X-5——fsync 失败后页可能已被标记 clean，重试会假成功并丢失已确认事件。
- **部分写**：`write` 返回短写时按剩余长度循环；仍失败按 fsync 失败处理。
- **读取**：逐行 `json.loads`；最后一行解析失败 → 丢弃并记诊断；中间行失败 → 视为日志损坏，`exit 2`（fail-closed）。

## 4. 租约与 fencing（D-4）

```jsonc
// <run>/lease.json
{
  "owner": "host-a:pid-1234",
  "pid": 1234,
  "acquired_at": "...",
  "expires_at": "...",     // 默认 now + 60s，心跳续期
  "fencing": 7             // 单调递增；每次成功获取 +1
}
```

- 获取：`O_EXCL` 创建临时租约 → `os.replace` 原子生效；已存在且未过期 → 拒绝启动（A1-4）。
- 续期：仅 owner 可续；续期失败 → worker 自停，不写事件。
- 写入校验：事件 `fencing` < 已见最高值 → 拒绝并记 `stale_writer_rejected`。

## 5. 保留与滚动（D-6/D-7）

| 阶段 | 触发 | 动作 |
|---|---|---|
| 段滚动 | 当前段 ≥ 8 MB 或 ≥ 10k 条 | 关闭当前段 → 新段；写 `event_log_rolled{prev_first,prev_last,digest}` |
| 热→归档 | `now - ts > retention_days`（默认 30） | gzip 为 `events.<f>-<l>.jsonl.gz`，删除明文段 |
| 归档删除 | `now - ts > archive_days`（默认 365） | 删除 `.gz`；摘要保留 |
| 摘要 | 每段滚动与 run 结束时更新 | `events_summary.json` 永久 |

`events_summary.json` 形态：

```jsonc
{
  "run_id": "...",
  "first_seq": 1, "last_seq": 5234, "count": 5234,
  "chain_head": "sha256(line_1)", "chain_tail": "sha256(line_5234)",
  "bytes": 1234567,
  "segments": [{"first":1,"last":900,"file":"events.1-900.jsonl.gz","digest":"..."}],
  "key_events": [{"seq":1,"type":"run.started"},{"seq":5234,"type":"run.completed"}]
}
```

- 校验能力：`chain_head`/`chain_tail` + 每段 digest → 归档后仍可判「未整体替换」。
- `key_events` 选取：阶段起止、失败、审批（U-2）。

## 6. 与既有机制的接缝

| 既有 | 变化 |
|---|---|
| `checkpoint.json` | 不变；写 checkpoint 后追加 `stage.completed` 事件 |
| `heartbeat.json` | 改为同样原子写（tmp + replace）；heartbeat 同时续租 |
| `run_state.py` | 只读接口不变；新增可选 `events` 计数读取（缺失即 0） |
| `--resume` | 先校验事件链；损坏 checkpoint 时从事件重建（A1-5） |
| `cost_log.jsonl` | 保留；`llm.result` 事件只记 digest 与费用摘要，不重复落原文 |
| WS 广播 | 事件先落盘再广播；重连用 `Last-Event-ID` 补拉（A1-2） |

## 7. 失败模式与处置

| 失败 | 处置 | 验收 |
|---|---|---|
| fsync EIO | run FAILED，不重试 | A1-1 负向 |
| 尾行撕裂 | 丢弃 + `event_log_truncated` | A1-5 |
| 双 worker | 租约拒绝第二个；fencing 兜底 | A1-4 |
| 事件超限 | 拒绝写入 + `run.failed{reason:"event_log_quota"}` | A1-6 |
| checkpoint 损坏 | 事件重放重建 | A1-5 |
| 归档段缺失 | `chain_head/tail` 不匹配 → 报警，不静默通过 | A1-1 |

## 8. 回滚

| 变更 | 回滚 |
|---|---|
| 事件层上线 | 关闭写入开关（`events.enabled=false`），checkpoint 路径回到当前形态 |
| 租约 | 删除 `lease.json` 逻辑，回到单进程 `--resume` |
| 保留策略 | `retention_days`/`archive_days` 设为极大值，等价于不删 |

## 9. 验收映射（供 G1 批次引用）

| G1 验收 | 本设计的落点 |
|---|---|
| A1-1 | §2 链定义 + §3 fsync 失败处置 |
| A1-2 | §6 WS 补拉 + `seq` 单调 |
| A1-3 | §4 租约 + supervisor 拉起 |
| A1-4 | §4 fencing |
| A1-5 | §6 重放重建 + §7 撕裂尾行 |
| A1-6 | §5 滚动/上限 |
| A1-10 | §1 D-5 outbox |
