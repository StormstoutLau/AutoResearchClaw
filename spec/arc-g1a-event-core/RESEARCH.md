---
id: arc-g1a-event-core-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1-readiness-research-DESIGN, arc-q5-decision-method-RESEARCH, arc-master-roadmap]
upstream: arc-q5-decision-method-RESEARCH
---

# 调研：G1a 事件内核的实施前提

> **Feature**：把 [P-022 DESIGN](../arc-g1-readiness-research/DESIGN.md) 的 §2-§5 落成代码。本文件只记录**实施时**才发现、设计阶段未覆盖的事实。
> **Spec 步骤**：Step 1-2（T1：改 `researchclaw/` 运行时 + 新增测试）

## 1. 现状复测

| # | 事实 | 证据 |
|---|---|---|
| F-1 | `checkpoint.json` 已原子写（mkstemp→replace） | `runner.py:90-119` |
| F-2 | `heartbeat.json` 原为非原子 `write_text` | `runner.py:133-135`（本批已修） |
| F-3 | 全仓无事件日志、无 lease | grep `events.jsonl` / `lease.json` = 0 |
| F-4 | `execute_pipeline` 会**递归**调用自身处理 PIVOT/REFINE | `runner.py:730-743` |
| F-5 | `read_checkpoint` 原仅解析 JSON，损坏即返回 None | `runner.py:195-212`（本批已补重建） |
| F-6 | 无任何测试断言 run 目录的精确文件列表 | Grep `listdir(run_dir` = 0 |

## 2. 实施时新发现（设计未覆盖）

### R-1 fencing 必须在 release 后仍然单调

初版 `release()` 直接删除 `lease.json` → 下一个持有者 `fencing` 从 1 重新开始，**租约代号失去单调性**，A1-4 的「拒绝低 token 写」失效。修正：`release` 保留记录并写 `released: true`，`acquire` 对 released/expired 记录 `fencing+1`。

### R-2 哈希链无法自查尾行篡改

链的方向是「后继指向先行」，因此**最后一行被改不会被任何人发现**。这不违背设计（`prev_sha256` 的语义就是如此），但必须补一条防线：`events_summary.json` 记录 `chain_tail`，作为尾行指纹。测试也相应改为**篡改中间行**（有后继才能验证链）。

### R-3 递归调用会重复 run.started 并提前释放租约

`execute_pipeline` 递归做 PIVOT/REFINE（F-4），若每次调用都申请租约、写 `run.started`、结束时 unload，会把外层租约释放掉。修正：模块级 `_ACTIVE_EVENT_LOGS[run_id]` 守卫，嵌套调用复用外层 log 且 `owns=False`，只有最外层负责收口与释放。

## 3. 约束（来自上游，不再重议）

- Q5 = A：纯文件 + fsync；fsync 失败**不重试**，直接抛错终止（P-025 §8）。
- Q9 = A：热 30 / 归档 365 / 摘要永久；段 8 MB 或 10k 条；单 run 上限 256 MB 或 200k 条。
- `EventEnvelope` 后端中立（不出现文件路径/fsync 细节）。

## 4. 外部锚点

| # | 锚点 | 用途 | 等级 |
|---|---|---|---|
| X-1 | PostgreSQL 19.14 *Error Handling* | fsync 失败不可重试 | T1 |
| X-2 | SQLite WAL 文档（单写者） | 佐证单 run 单写者模型 | T1 |
| X-3 | Kleppmann *fencing token* | 租约代号单调递增 | T2 |
| X-4 | Kafka `log.retention` / `log.cleanup.policy` | 分段 + 按时间清理 | T1 |
| X-5 | Python `os.replace` / `os.fsync` 文档 | 原子替换与落盘 | T1 |

## 5. 未决项

- **U-1 异常路径的租约释放**：判据 = 未捕获异常时 `lease.json` 残留至 TTL（600s）；触发 = G1b supervisor；倾向 = G1b 用 `finally`/信号处理统一收口；E2。
- **U-2 事件写入的性能**：判据 = 逐条 fsync 的摊销；触发 = K-4（>5% 运行时长）；倾向 = 保持逐条；E2。
- **U-3 段文件命名与归档索引**：判据 = 段很多时 summary 是否可解析；触发 = 单 run > 20 段；倾向 = 维持 `events.<first>-<last>.jsonl`；E3。

## 6. 引用

1. PostgreSQL 17. *Error Handling*. https://www.postgresql.org/docs/17/runtime-config-error-handling.html
2. SQLite. *Write-Ahead Logging*. https://www.sqlite.org/wal.html
3. Kleppmann, M. *How to do distributed locking*.
4. Apache Kafka. *log.cleanup.policy* / *log.retention.hours*.
5. 仓内：[P-022 DESIGN](../arc-g1-readiness-research/DESIGN.md)、[P-025 §8](../arc-q5-decision-method/RESEARCH.md)
