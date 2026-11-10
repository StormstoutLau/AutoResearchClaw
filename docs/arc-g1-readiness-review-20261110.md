# G1 前置调研独立复核（P-022 复核）

> **日期**：2026-11-10
> **复核对象**：[spec/arc-g1-readiness-research/](../spec/arc-g1-readiness-research/)（P-022，Q5 事件后端 / Q9 事件保留期）
> **复核方法**：①三缺陷逐项独立回源（一手读码）；②事实表 F-1..F-10 抽查（grep 复验）；③锚点回源确认；④判定矩阵权重口径复核。
> **复核人声明**：本报告为独立会话产出；读码为本机独立进行，不复用 P-022 执行路径。

---

## 1. 总体结论

P-022 的事实底座**全部属实**（行号精确、grep 复验一致）、16 项锚点**全部一手命中可回源**。三项「G1 必须带入的缺陷」**均属实**，但其中**两处定级过强需收窄**；另发现 **1 个新问题（R-4）：Q5 判定矩阵权重口径未公开，且结论在合理权重扰动下不稳健——Q5 建议应从「A 优于 B」降格为「倾向 A，B 为可辩护备选」**。Q9 结论在权重扰动下稳健，维持。

---

## 2. 机检独立重跑

| 检查 | P-022 主张 | 复核结果 |
|---|---|---|
| `pre-commit run --all-files` | 9/9 Passed | ✅ 独立重跑 exit 0 |
| `step-gate --expect` 5 步 | pass | ✅ exit 0 |
| `console_gen --check` | 一致 | ✅ |
| `step_enforce --base HEAD` | exit 0 | ✅ |
| `repo_stats --check` | 一致（P 批次=22） | ✅ |

**结论**：P-022 机检主张全部成立。

---

## 3. 事实表 F-1..F-10 抽查

| # | 抽查项 | 复核 |
|---|---|---|
| F-1 | checkpoint 原子写 `runner.py:90-119` | ✅ `mkstemp`→`replace`，行号精确 |
| F-2 | heartbeat 非原子 `runner.py:133-135` | ✅ `write_text` 直接覆写 |
| F-3 | 无事件日志 | ✅ 独立 grep `prev_sha256/events.jsonl/Last-Event-ID` = 0 命中 |
| F-4 | WS QueueFull 丢弃 `manager.py:67-78` | ✅ `put_nowait` + `except QueueFull: warning("dropping event")` |
| F-6 | cost_log 只 flush 无 fsync `cost_tracker.py:224-234` | ✅ 逐行确认，`except OSError` 仅 warning |
| F-7 | 四类 JSONL 房规 | ✅ `_literature.py:602/868`、`evolution.py:393`、`hitl/tui/panel.py:72` |
| F-8 | 无 lease/supervisor | ✅ `lease.json` = 0 命中 |

其余 F-5/F-9/F-10 为读取与推导，未见矛盾。**事实底座成立。**

---

## 4. 三缺陷独立验证（核心发现）

### 缺陷 1：cost_log 无 fsync —— **属实，但定级需收窄**

一手确认：[cost_tracker.py:230-232](../researchclaw/cost_tracker.py#L230-L232) 只有 `flush()`。

**P-022 表述**：「『已记录』承诺不成立」。
**复核修正**：`flush()` 把 Python 缓冲推到 **OS 页缓存**。故障模式分两层：

| 故障 | flush 后是否丢 |
|---|---|
| 进程崩溃（`kill -9`，OS 存活） | **不丢**——OS 页缓存仍在 |
| OS 崩溃 / 断电 | **可能丢** |

因此：对 **A1-3（kill -9 → supervisor 拉起）**，`cost_log.jsonl` 现状够用；缺口只对 **OS 崩溃/断电** 存在。事件层必须 fsync 的理由不是 kill -9，而是**链完整性跨断电**——A1-1 的 `prev_sha256` 链一旦断在丢失行上，重放（A1-5）即失效。**定级：P1（事件层必须），P3（cost_log 现状）**，而非笼统的「承诺不成立」。

### 缺陷 2：WS QueueFull 丢弃 —— **属实，但与 A1-2 无关**

一手确认：[manager.py:67-78](../researchclaw/server/websocket/manager.py#L67-L78) 丢弃的是**内存广播队列**中的事件。

**P-022 表述**：列为「A1-2 无缺口必须先解决该丢弃路径」。
**复核修正**：P-022 自己的 DESIGN（§6）规定「事件**先落盘**再广播；重连用 `Last-Event-ID` 从磁盘补拉」——在该设计下，WS 队列丢弃只影响**实时推送体验**，不影响事件持久化与补拉。A1-2 的「无缺口、无重复」以**磁盘事件流**为准。**缺陷属实（现状确实丢），但修复动作 = 事件层落地本身，不需要单独修 WS 队列**。P-022 将其列为独立修复项有误导，应从「G1 必须带入」降为「随事件层自然消解」。

### 缺陷 3：heartbeat 非原子 —— **属实，影响有限，维持修复建议**

一手确认：[runner.py:133-135](../researchclaw/pipeline/runner.py#L133-L135) `write_text` 直接覆写。
**影响面核查**：消费者 = [run_state.py:233](../researchclaw/run_state.py#L233)，其 `_read_json`（L78-86）捕获 `JSONDecodeError/OSError/UnicodeDecodeError` → 返回 `None` → `is_active=False` → 状态降级 `UNKNOWN`。即：撕裂写最多导致**状态短暂误报 inactive**，不损坏数据、不崩溃。`acp_client.py`/`server/app.py` 的 heartbeat 是无关同名概念。
**定级：P2**——修复成本低（与 checkpoint 同构 tmp+replace），维持建议，但不应表述为高风险。

---

## 5. R-4（新发现）：Q5 判定矩阵权重口径不可复算，结论非稳健

RESEARCH §3.4 给出 A=4.2 / B=3.6 的加权分，但**未公开权重数值口径**。复核以 高=3/中=2/低=1 重算：

- A = 74/18 ≈ **4.11**（原文 4.2）
- B = 68/18 ≈ **3.78**（原文 3.6）

轻微偏差尚可归因舍入；但**权重敏感性测试**显示结论不稳：若把权重集中在 B 的强项（崩溃恢复、A1-10 原子性 = 高），则 **B = 84 > A = 80，排序反转**。

**含义**：A 优于 B 的结论**依赖权重选择**——A 的优势集中在 I-1 一致性与迁移成本；若裁决者更看重「成熟崩溃恢复机制」，B 是**可辩护的选择**。

**处置建议**：
1. Q5 建议从「A 优于 B」**降格**为「**倾向 A（I-1 一致性 + 迁移成本 + 房规延续），B 为可辩护备选**」；
2. 实施批在 RESEARCH 补权重口径（或改为序数判定），并保留 §6.1 的四项「切换 B 触发条件」；
3. **Q9 无此问题**：A 在三个维度均 ≥4，B 的磁盘（1）与合规（2）、C 的复现（2）是任何合理权重都翻不掉的硬伤——**Q9 = A 稳健维持**。

---

## 6. 锚点回源确认

16 项锚点全部在本轮独立检索中一手命中，等级标注复核：

| 等级 | 锚点 | 判定 |
|---|---|---|
| T1（9） | X-1 SQLite WAL（「only one writer at a time」原文）、X-2、X-4（「the only way to avoid data loss is to recover from the WAL」原文）、X-7、X-10（168h 原文）、X-11、X-12（「at least one year; three months immediately available」原文）、X-13、X-14（EUR-Lex Art.5(1)(e) 原文） | 全部成立 |
| T1（1） | X-15 Azure Event Sourcing（snapshots every N events 原文） | 成立 |
| T2（3） | X-5 TigerBeetle（页标记 clean → 二次 fsync 假成功，原文命中）、X-6 Kleppmann、X-8 WBL 论文 | 成立 |
| T2（1） | X-3 SQLite 论坛 | 成立 |
| T3（2） | X-9 队列压测 14 jobs/sec、X-16 快照实践 | 已标注「仅作反例」，使用合规 |

**无虚标、无 T4 混入。**

---

## 7. 复核结论与登记

| # | 结论 | 类型 |
|---|---|---|
| C-1 | 三缺陷**全部属实**（一手读码确认） | 确认 |
| C-2 | 缺陷 1 定级收窄：kill -9 不丢，断电/OS 崩溃才丢；事件层 fsync 的理由 = 链完整性跨断电 | **定级修正** |
| C-3 | 缺陷 2 定级修正：与 A1-2 无关，随事件层落地自然消解，撤销「单独修复项」 | **定级修正** |
| C-4 | 缺陷 3 维持 P2（读侧有容错，仅状态误报） | 定级确认 |
| C-5 | **Q5 建议降格**为「倾向 A，B 可辩护备选」（权重敏感性披露，R-4） | **建议强度修正** |
| C-6 | Q9 = A 稳健维持 | 确认 |
| C-7 | 事实表与锚点全部成立 | 确认 |
| C-8 | **R-5（新，治理工具观察）**：`step_enforce` 两分支门槛不一致——`_resolve_declared`（docs_features 路径）对 batch 声明的**全部** P 要求 spec/ 链接，而 `batch-registration` 分支（L478）有 `BATCH_BINDING_MIN_P=129` 豁免。T3 复核批（无 feature）与 T1 批同提交时必然红。**不在本批修**（T3 禁改门禁）；修复 = 对齐两分支门槛，走独立 T1 小批 | **登记待修** |

**登记**：本报告 + `specwf-p023` session 已落盘；PROGRESS P-023 行**延后登记**——因 C-8 的 batch 语义（P-022/P-023 同提交会红），P-023 行将在 P-022 提交后立即补登（先例 = P-019/P-020 两笔提交）。P-022 四文档保持原样（复核不修改被复核对象）；C-2..C-5 作为 **G1 实施批的设计输入**（其 DESIGN 引用时以本报告为准）。

## 8. 复核清单

- [x] 机检独立重跑（5/5 通过）
- [x] 三缺陷一手读码（三处行号全部命中）
- [x] F 表抽查（7 项精确复验）
- [x] 锚点 16 项回源确认
- [x] 判定矩阵权重复算与敏感性测试（Q5 不稳健、Q9 稳健）
- [x] 未修改 P-022 归档文档（本报告为追加证据）
