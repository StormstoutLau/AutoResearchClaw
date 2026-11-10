---
id: arc-g1a-event-core-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1a-event-core-RESEARCH]
upstream: arc-g1a-event-core-RESEARCH
---

# 设计：G1a 事件内核 + 租约

> 基于 [RESEARCH.md](RESEARCH.md)。覆盖 A1-1、A1-4、A1-5、A1-6 与 Q9 全部参数。

## 1. 模块

| 文件 | 职责 |
|---|---|
| `researchclaw/runtime/__init__.py` | 包声明 |
| `researchclaw/runtime/event_log.py` | `EventEnvelope`、`EventLog`（append/fsync/链/滚动/配额/保留/摘要/重放/重建）、`rebuild_checkpoint` |
| `researchclaw/runtime/lease.py` | `Lease`、`acquire/renew/release/read_lease`、fencing 单调 |
| `runner.py` | 接入：`_runtime_begin/_emit/_runtime_end`、原子 heartbeat、`read_checkpoint` 恢复路径 |

## 2. EventEnvelope v1

```json
{"seq":1,"ts":"...","run_id":"...","type":"stage.started","stage":1,
 "attempt":null,"fencing":1,"payload":{},
 "payload_sha256":"...","prev_sha256":"000...0"}
```

- 规范化：`json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False)`。
- 链：`prev_sha256 = sha256(上一行规范化文本)`；`seq=1` 时全 0。
- `payload` 只放摘要/计数/digest，不放原文与凭据。

## 3. 写入协议

```
append(type, payload, stage, attempt)
  → 配额检查（bytes/events）
  → 段滚动检查（8 MB 或 10k 条）
  → write + flush + os.fsync
  → OSError ⇒ EventDurabilityError（不重试，向上抛）
```

- 撕裂尾行：读取时丢弃并置 `truncated=True`；追加基于最后**完整**行续写（R-2）。
- `verify_chain()`：逐条校验 seq 连续与 prev 指针；归档段异常超过 1 行视为损坏并报错。

## 4. 租约与 fencing

| 场景 | 行为 |
|---|---|
| 无租约 | 获取，`fencing=1` |
| 同 owner 且未过期 | 续期，**fencing 不变**（支持递归） |
| 异 owner 且未过期 | `LeaseBusy` |
| 已释放 / 已过期 | 接管，`fencing = 旧值 + 1` |
| `renew` 非 owner | `LeaseLost` |

`release` 保留记录（`released: true`）以保证代号单调（R-1）。

## 5. 保留策略（Q9）

| 参数 | 默认 |
|---|---|
| 段大小 / 条数 | 8 MB / 10k |
| 单 run 上限 | 256 MB / 200k（超限 `EventQuotaExceeded`） |
| 热保留 | 30 天（滚动段 → gzip） |
| 归档保留 | 365 天（到期删除） |
| 摘要 | `events_summary.json` 永久，含 `chain_head`/`chain_tail`/段 digest |

## 6. runner 接入

| 位置 | 行为 |
|---|---|
| `execute_pipeline` 入口 | `_runtime_begin`：取租约 → 建 log → `run.started`；递归调用复用外层（R-3） |
| 每阶段开始 | `stage.started` |
| 阶段结束 | DONE → 写 checkpoint + `stage.completed`；否则 `stage.failed` |
| 流水线收口 | `run.completed` / `run.failed` → 写 summary → 释放租约 |
| `_write_heartbeat` | tmp + `os.replace`（原子） |
| `read_checkpoint` | checkpoint 缺失/损坏 → 从事件重建并持久化 `recovered:true`（A1-5） |

**开关**：`ARC_EVENTS_DISABLED=1` 可整体关闭（兼容极端环境）；默认开启。

## 7. 验收映射

| 验收 | 落点 |
|---|---|
| A1-1 | `verify_chain` + 中间行篡改测试；尾行由 summary `chain_tail` 兜底 |
| A1-4 | `lease.acquire` 异 owner 拒绝；fencing 单调（含 release/expire） |
| A1-5 | `read_checkpoint` 恢复路径 + `rebuild_checkpoint` |
| A1-6 | 段滚动 + 配额 + 保留归档 |
| Q9 | 30/365/摘要永久参数与 `apply_retention` |

## 8. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 逐条 fsync 拖慢测试 | 实测 23 阶段模拟流水 +12s 内；必要时 `fsync=False` 仅测试用 |
| 递归重复收口 | `_ACTIVE_EVENT_LOGS` 守卫 + 嵌套测试 |
| 未捕获异常残留租约 | TTL 600s 自愈；G1b 统一收口（U-1） |

回滚：`ARC_EVENTS_DISABLED=1` 或回退本批 commit；`checkpoint.json` 语义不变，`--resume` 仍可用。
