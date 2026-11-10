---
id: arc-g1-readiness-research-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-master-roadmap, clawsgo-cleanroom-arc-reinforcement, dsh-superagent-absorption-analysis]
upstream: arc-master-roadmap
---

# 调研：G1 前置决策 Q5（事件后端）与 Q9（事件保留期）

> **Feature**：G1「运行时可恢复」开工前的两项决策闸门。
> **Spec 步骤**：Step 1-2（T1 完整管线——结论决定 G1 事件存储的**真值源与契约**，命中强制升级条款）
> **状态**：调研完成；**未改代码、未改总纲**；裁决待确认。

## 1. 调研目标

| # | 问题 | 为什么必须在 G1 开工前定 |
|---|---|---|
| Q5 | 事件后端：纯文件 + supervisor，还是 SQLite WAL？ | 决定 `EventEnvelope` 的持久化语义、崩溃恢复路径、A1-1/A1-5/A1-10 的实现形态；事后换后端要重写事件层 |
| Q9 | 事件保留期：30 天 / 永久 / 其他？ | 决定 `events.jsonl` 的滚动与压缩策略（A1-6）、审计可用窗口、单 run 磁盘上限 |

## 2. 现状实测（2026-11-10）

| # | 事实 | 证据 |
|---|---|---|
| F-1 | `checkpoint.json` 已原子写：`mkstemp` → 写 → `Path.replace` | `runner.py:90-119` |
| F-2 | `heartbeat.json` 为**非原子**直接覆写（`write_text`） | `runner.py:133-135` |
| F-3 | **无事件日志**：全仓 grep `events.jsonl` / `prev_sha256` / `Last-Event-ID` 均 0 命中 | Grep |
| F-4 | WS `ConnectionManager` **无历史缓冲、无回放**；`QueueFull` 直接丢事件并告警 | `server/websocket/manager.py:67-78` |
| F-5 | `--resume` 为**阶段级**：`read_checkpoint()` 返回下一个待执行 Stage | `runner.py:138-150` |
| F-6 | `cost_log.jsonl` 已落盘：每 LLM 调用一行，`open("a")` + `flush()`，**无 `fsync()`** | `cost_tracker.py:224-234` |
| F-7 | append-only JSONL 已是**房规**：`candidates.jsonl`、`shortlist.jsonl`、`lessons.jsonl`、`interventions.jsonl` | `_literature.py:602/868`、`evolution.py:393`、`hitl/tui/panel.py:72` |
| F-8 | **无** `lease.json` / supervisor / worker 退出码分类 | Grep `lease` 0 命中 |
| F-9 | `run_state.py` 只读消费 `checkpoint.json` + `heartbeat.json`；`RUNNING` 需 heartbeat 在 ±300s 内 | `run_state.py:232-265` |
| F-10 | 单 run 事件量级估计：23 阶段 × （阶段事件 + 工具调用 + LLM 调用）≈ **10²–10³/run**，按 0.5–2 KB/条 ≈ **0.5–2 MB/run** | 由 `cost_log.jsonl` 每调用一行外推 |

**关键结论**：ARC 已有「文件即状态」的完整肌肉记忆（checkpoint 原子写、四类 JSONL 追加），但**缺 fsync 纪律**（F-6）与**任何事件链**（F-3/F-4）。事件层是从 0 到 1，不是改造。

## 3. Q5 方案空间

| 方案 | 形态 | 关键假设 |
|---|---|---|
| **A 纯文件 + supervisor** | `<run>/events.jsonl`（append + fsync 每条）+ 段滚动；supervisor 管 worker 生命周期；租约 `lease.json` | 单 run 单写者；事件率低到可承担逐条 fsync |
| **B SQLite WAL** | `<run>/events.db`；`INSERT` 即事务；WAL 提供崩溃恢复与单写者串行 | 需要 SQL 查询/索引；接受第二份文件格式与 schema 迁移成本 |
| **C 双后端** | `DurableBackend` 接口 + A/B 两实现，默认 A | 需要抽象成本，且两实现的行为一致性需额外测试 |

### 3.1 支持 A 的证据

- **房规一致性**：F-1/F-7 显示「run 目录 = 状态载体」是既有不变量（§2 全局不变量 I-1）；SQLite 会引入第二种状态容器，`checkpoint.json` 与 `events.db` 的一致性成为新问题。
- **事件率低**：10²–10³ 事件/run、历时数十分钟至数小时 → 逐条 fsync 的摊销成本可忽略（对比 Kafka 级吞吐场景才有意义）。
- **事件日志可兼任 outbox**（A1-10）：把「待执行副作用」写成 `effect.queued` 事件，消费侧按 `(kind,key)` 幂等重放；无需数据库事务即可获得 at-least-once + 幂等，避免为 A1-10 专门引入 B。
- **恢复路径短**（A1-5）：从 `events.jsonl` 顺序重放重建 checkpoint，逻辑与 `run_state.py` 同构，无 SQL 依赖。
- **只读工具友好**：`jq`/`tail -f` 即可诊断；SQLite 需要额外客户端。

### 3.2 支持 B 的证据

- **单写者模型天然匹配**：WAL 明确「同一时刻只能有一个 writer」——与 A1-4 的 lease 模型（一 run 一 worker）完全一致，不构成瓶颈（X-1）。
- **崩溃恢复成熟**：WAL + checkpoint 是经过数十年验证的机制（X-7）；自研 append+fsync 需要自己处理部分写、撕裂尾行、fsync 错误（X-4/X-5）。
- **原子多行写**：A1-10 的「入队与 checkpoint 同事务」在 SQLite 中是一条 `BEGIN IMMEDIATE ... COMMIT`。
- **SQLite 定位本身支持**（X-2）：官方把「application file format」列为推荐用法，恰是 ARC 的形态。

### 3.3 反向证据（两条对 B 不利、对 A 有利的硬事实）

- **fsync 失败不可重试**：PostgreSQL 官方明确「报告失败后唯一的避免数据丢失方式是从事 WAL 恢复」，重试 fsync 可能假成功（X-4）；TigerBeetle 的分析指出内核会把页标记为 clean 导致第二次 fsync 成功（X-5）。→ **无论 A/B，fsync 错误必须 fail-closed，不得重试**。这条对 A 的要求更高（自研需自己实现），对 B 由 SQLite 承担。
- **SQLite 队列的吞吐天花板**：社区实测「零基础设施 SQLite 队列」约 14 jobs/sec（X-9，T3 单源）；SQLite 论坛亦指出写锁是整库级（X-3）。ARC 事件率远低于此，但**若未来把 ARC 当多 run 并发平台**，B 的写锁会成为单点。

### 3.4 Q5 判定矩阵

| 维度 | A 纯文件 | B SQLite WAL | 权重 |
|---|---|---|---|
| 与 I-1「file-as-state」一致 | 5 | 3 | 高 |
| 崩溃恢复正确性（现成机制） | 3 | 5 | 高 |
| fsync 错误可控性 | 3（自研） | 4（库内，但仍需处理） | 高 |
| 单写者/租约适配（A1-4） | 5 | 5 | 中 |
| A1-10 outbox 原子性 | 4（日志即 outbox） | 5（同事务） | 中 |
| 运维/诊断成本 | 5 | 3 | 中 |
| 迁移与依赖成本 | 5 | 2 | 中 |
| 多 run 并发扩展 | 3 | 2 | 低 |
| **加权** | **4.2** | **3.6** | — |

## 4. Q9 方案空间

| 方案 | 策略 | 依据 |
|---|---|---|
| **A 热 30 天 + 段归档 365 天 + 摘要永久** | 热日志 30 天后 gzip 段归档；`events_summary.json`（链头尾 digest、计数、关键节点、体积）永久 | Kafka 默认 7 天为下限（X-10）；PCI 审计类 ≥1 年为上限参考（X-12） |
| B 永久保留全量 | 不删除 | 磁盘无界增长；与 A1-6「单 run 体积上限」直接冲突 |
| C 7 天热 + 无归档 | 只保 7 天 | 复现窗口过短；G7 长时程（72h）跨周复现会失效 |

### 4.1 判定依据

- **下限**：Kafka `log.retention.hours` 默认 **168h（7 天）**（X-10，T1 官方），说明「7 天」是流式日志的通用起点；ARC 需要覆盖「一次 run 从失败到人工复核」的周期，30 天更稳妥。
- **上限**：PCI DSS 10.7 要求审计日志**保留 ≥1 年、其中最近 3 个月可即时分析**（X-12，T1 标准）。ARC 不处理支付卡数据，但该条给出了「热/冷分层」的成熟比例（3/12 ≈ 25%）。
- **合规边界**：GDPR Art. 5(1)(e) 要求个人数据「不超过必要期限」保存，科研归档属例外（Art. 89(1)）（X-14，T1 法规）。→ 事件若含个人数据（工具入参摘要可能含），不能承诺永久全量。
- **可复算性**：I-4 要求「任何主张引用的证据可复算」。摘要永久 + 段归档 1 年，足以覆盖论文产出周期；超过 1 年时以 `artifacts_digest` + checkpoint 为准（证据不依赖事件日志）。
- **成本**：按 F-10 估计 0.5–2 MB/run，30 天 × 100 run ≈ 0.05–0.2 GB，可忽略；gzip 后约 10–20%。

### 4.2 Q9 判定矩阵

| 维度 | A 30+365+摘要 | B 永久全量 | C 7 天 |
|---|---|---|---|
| 复现/审计覆盖 | 5 | 5 | 2 |
| 磁盘可控（A1-6） | 5 | 1 | 5 |
| 合规风险（数据最小化） | 5 | 2 | 4 |
| 实现复杂度 | 4 | 5 | 5 |
| 与链校验兼容（A1-1） | 4（摘要存首尾） | 5 | 3 |
| **加权** | **4.6** | **3.5** | **3.7** |

## 5. 外部锚点

| # | 锚点 | 结论 | 等级 |
|---|---|---|---|
| X-1 | SQLite *Write-Ahead Logging* | WAL 下**仍只有一个 writer**；读写可并发 | T1 官方 |
| X-2 | SQLite *Appropriate Uses* / *As An Application File Format* | 嵌入式、无服务器；「应用文件格式」是推荐用法 | T1 官方 |
| X-3 | SQLite User Forum：*Building a queue based on SQLite* | 写锁是**整库级**；多队列表需索引 | T2 维护者论坛 |
| X-4 | PostgreSQL 19.14 *Error Handling* | fsync 失败后**唯一**免丢失路径是从 WAL 恢复；重试不安全 | T1 官方 |
| X-5 | TigerBeetle（InfoQ）/ SREcon 讲稿 | 内核可把失败页标记 clean → 第二次 fsync **假成功** | T2 会议讲稿 |
| X-6 | Kleppmann *How to do distributed locking* | 租约必须配 **fencing token**；被保护资源拒绝低 token 写 | T2 权威博客（原文可回源） |
| X-7 | PostgreSQL *WAL Configuration* | checkpoint + WAL 的崩溃恢复语义 | T1 官方 |
| X-8 | *Write-Behind Logging*（CS839 论文） | WAL 变体的恢复协议与持久化边界 | T2 学术 |
| X-9 | 社区 SQLite 任务队列压测 | 约 14 jobs/sec；WAL + `UPDATE...RETURNING` 原子认领 | T3 单源（仅作反例） |
| X-10 | Kafka *log.retention.hours* | 默认 **168h（7 天）** | T1 官方 |
| X-11 | Kafka *log.cleanup.policy* | `delete`（按时间/大小）vs `compact`（按键保留最新） | T1 官方 |
| X-12 | PCI DSS v3.2.1 §10.7 | 审计日志保留 **≥1 年**，最近 **3 个月**可即时分析 | T1 标准 |
| X-13 | NIST SP 800-92 | 日志管理需定义「保留期限 + 归档 + 处置」流程 | T1 标准 |
| X-14 | GDPR Art. 5(1)(e) + Art. 89(1) | 存储限制原则；科研归档为例外 | T1 法规 |
| X-15 | Azure Architecture Center *Event Sourcing* | 长事件流必须用快照 + 重放窗口控制成本 | T1 官方文档 |
| X-16 | 事件溯源快照实践（社区） | 「过早删事件会破坏审计，永久全量会耗尽磁盘」→ 自动保留/压缩策略 | T3 单源 |

## 6. 建议

### 6.1 Q5 = **A（纯文件 + supervisor）**，B 作为 `DurableBackend` 预留

- 事件层：`<run>/events.jsonl`，每条 `write + flush + os.fsync`；**fsync 失败 → 立即将 run 置 FAILED 并写 `run.failed{reason:fsync}`，不重试**（X-4/X-5 的直接推论）。
- 崩溃安全：写入前先写长度前缀或采用「整行 JSON + 尾行撕裂检测」；恢复时丢弃不可解析的尾行并记 `event_log_truncated`。
- 租约：`lease.json{owner,pid,expires_at,fencing}`；所有写事件带 `fencing`，写入侧拒绝低于已见最高值的 token（X-6）。
- A1-10 outbox：以 `effect.queued` 事件入日志，消费侧按 `(kind,key)` 幂等；不引入数据库事务。
- **切换 B 的触发条件**（任一满足即重审）：① 单 run 事件 > 10⁵；② 需要多 worker 并发写同一 run；③ 需要跨 run 查询/索引；④ fsync 摊销 > 运行时长 5%。

### 6.2 Q9 = **A（热 30 天 + 段归档 365 天 + 摘要永久）**

| 参数 | 默认 | 说明 |
|---|---|---|
| `events.retention_days` | 30 | 热日志；到期 gzip 为 `events.<seq>.jsonl.gz` |
| `events.archive_days` | 365 | 归档保留；到期删除段文件 |
| `events_summary.json` | 永久 | `{first_seq,last_seq,count,chain_head,chain_tail,bytes,key_events[]}` |
| 段大小 | 8 MB 或 10k 条 | 触发滚动（A1-6） |
| 单 run 上限 | 256 MB 或 200k 条 | 超限即拒绝写入并 `run.failed{reason:event_log_quota}` |

- **链校验跨越归档**：摘要保存首尾 sha256，归档段头尾也记 digest → 归档后仍可验证「未整体替换」。
- **纯文本事件不落原文**：只落 `digest + 摘要`（沿用 R0 既有纪律），降低 GDPR 面（X-14）。

## 7. 对 G1 验收项的影响

| 验收 | 影响 |
|---|---|
| A1-1 链哈希 | 文件后端：`prev_sha256` 逐条链；需定义撕裂尾行处理 |
| A1-2 Last-Event-ID | 与后端无关；事件 `seq` 单调即可 |
| A1-3 kill -9 恢复 | supervisor 拉起 + 从最后完整行续写 |
| A1-4 租约 | `lease.json` + fencing token（X-6） |
| A1-5 重建 checkpoint | 顺序重放 `events.jsonl`；损坏 checkpoint 仍可恢复 |
| A1-6 滚动/上限 | Q9 参数表直接落地 |
| A1-10 outbox | 日志即 outbox，`effect.queued` 幂等消费 |

## 8. 未决项

- **U-1 fencing 粒度**：判据 = 每次写事件带 token 是否可接受；触发 = A1-4 实现；倾向 = 事件级；E2。
- **U-2 摘要 `key_events` 选取规则**：判据 = 能否覆盖「为何失败」；触发 = 首批真实 run；倾向 = 阶段起止 + 失败 + 审批；E3。
- **U-3 归档是否加密**：判据 = 事件是否可能含敏感入参；触发 = 首次含外部数据；倾向 = 否（仅摘要）；E2。
- **U-4 SQLite 后端触发条件复核周期**：判据 = 四项触发是否出现；触发 = G7 长时程前；倾向 = G7 前复核一次；E2。

## 9. 引用

1. SQLite. *Write-Ahead Logging*. https://www.sqlite.org/wal.html
2. SQLite. *Appropriate Uses For SQLite*. https://www.sqlite.org/whentouse.html
3. SQLite. *SQLite As An Application File Format*. https://www.sqlite.org/appfileformat.html
4. SQLite User Forum. *Building a queue based on SQLite*. https://www.sqlite.org/forum/forumpost/4fa389bdfdc9bc0f
5. PostgreSQL 17. *Error Handling*. https://www.postgresql.org/docs/17/runtime-config-error-handling.html
6. PostgreSQL 17. *Write Ahead Log*. https://www.postgresql.org/docs/17/runtime-config-wal.html
7. InfoQ. *A New Era for Database Design with TigerBeetle*. https://www.infoq.com/presentations/tigerbeetle/
8. Kleppmann, M. *How to do distributed locking*. https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html
9. Apache Kafka. *log.retention.hours*. https://kafka.apache.org/0100/generated/kafka_config.html
10. Apache Kafka. *Topic Configs / log.cleanup.policy*. https://kafka.apache.org/31/generated/topic_config.html
11. PCI Security Standards Council. *PCI DSS Quick Reference Guide v3.2.1* §10.7.
12. NIST. *SP 800-92 Guide to Computer Security Log Management*. https://csrc.nist.gov/pubs/itlb/2006/10/log-management-using-computer-and-network-records/final
13. EUR-Lex. *Regulation (EU) 2016/679* Art. 5(1)(e), Art. 89(1).
14. Microsoft. *Event Sourcing Pattern — Azure Architecture Center*. https://learn.microsoft.com/en-us/Azure/Architecture/patterns/event-sourcing
15. 仓内：[clawsgo-cleanroom-arc-reinforcement.md](../../clawsgo-cleanroom-arc-reinforcement.md) R0/R1；[dsh-superagent-absorption-analysis.md](../../dsh-superagent-absorption-analysis.md)
