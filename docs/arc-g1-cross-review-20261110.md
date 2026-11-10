# G1 异基座独立复审报告（2026-11-10）

> **性质**：Layer-0 独立复核（T3，零代码/零门禁）。复审基座与实施基座不同（GLM 复审前一模型产出的 P-027..P-038），复审人不采信既有文档结论，所有主张均以机检、探针或读码一手重验。
> **范围**：G1 全链 12 批——P-027（G1a 事件内核）、P-028/P-030（G1b 调研与复核）、P-029（G1b 实施）、P-031（A1-2 协议面）、P-032/P-034/P-038（总纲同步）、P-033（遗留收口）、P-035（遗留分析）、P-036（前端闭环）、P-037（A1-9 接线）。
> **重点**：P-036 / P-037 从未经过独立 pass，本轮补上。

## 1. 复审方法

| 手段 | 内容 |
|---|---|
| 机检 | G1 范围 7 个测试文件 + 4 个 G1a 测试文件实跑（不采信 IMPLEMENTATION 里的数字） |
| 探针 | P1 链篡改（read_all 面）、P4 末行篡改（verify_chain 面）、bogus session（复跑）、fencing 接管 |
| 读码 | `event_log.py`、`lease.py`、`supervisor.py`、`outbox.py`、`event_stream.py`、`routes/events.py`、`api.js`、`attempt.py`、`code_agent.py`、`runner.py` 全文 |
| 锚点回源 | P-030 复核报告的 R-1/R-2/R-3 → 代码落点逐条对照 |

## 2. 事实复验（T 表，全部一手）

| # | 主张 | 复验方式 | 结果 |
|---|---|---|---|
| T-1 | G1 相关测试全绿 | 实跑 `test_g1b_runtime/g1_closeout/supervisor/events_api/event_stream/cli_agent_wiring/stage_retries`（64）+ `test_event_log/lease/runner_events/rc_checkpoint`（43） | **107 passed** |
| T-2 | A1-1 中间行篡改必失败 | 测试 + 链语义读码（`verify_chain` 校验 seq 连续 + `prev_sha256` 指针） | ✅ 成立 |
| T-3 | A1-4 租约互斥/fencing 单调/release 保留记录 | 读码 `lease.py` + 测试 | ✅ 成立 |
| T-4 | R-2：supervisor 不持租约 | 读码 `supervisor.py`（无 acquire 调用，`_clear_stale_lease` 只释放已死 worker 的租约） | ✅ 成立 |
| T-5 | R-1/R-3：退出码 85 独立成类、LeaseKeeper 续期 | 读码 `exit_codes.py`/`lease.py:265-306` + `runner._emit` 在租约丢失后拒写（L255-257） | ✅ 成立 |
| T-6 | A1-10 outbox `queued−(kind,key) 去重−done`，失败终态 | 读码 `outbox.py` + 测试（含 poisoned effect 终态用例） | ✅ 成立 |
| T-7 | A1-2 `Last-Event-ID` 优先（HTTP+流双端）、gap 显式、终态关流、单 run 流上限 5 | 读码 `event_stream.py`/`routes/events.py` + 测试 | ✅ 成立 |
| T-8 | A1-9 bogus session → exit 1 + `No conversation found`（不烧配额） | 本基座复跑探针 | ✅ 成立（round-trip 见 O-4） |
| T-9 | A1-9 attempt 真值：`session_id`/`context_replayed` 读 stage 自写日志、`since` 过滤旧日志 | 读码 `attempt.read_session_telemetry` + `runner._record_attempt` + 测试 | ✅ 成立 |
| T-10 | P-036 修复「JSON 端点忽略 Last-Event-ID」 | 读码 `list_events`（读 header）+ HTTP 测试 | ✅ 成立 |

## 3. 新发现缺陷（D 表）

### D-1（中）：A1-1「篡改任一条即校验失败」在**末行场景假通过**

- **一手证据（探针 P4）**：篡改最后一行 payload（`payload_sha256` 字段不动）后，`verify_chain()` 返回 **True**（`ok (2 events)`）；`read_all()` 同样通过。
- **根因**：`verify_chain`（event_log.py:324-336）只校验 seq 连续与 `prev_sha256` 指针，**不校验 `payload_sha256` 与实际 payload 的一致性**；链条方向是「后继指向先行」，末行无后继，payload 篡改不可检。
- **「兜底」未接线**：P-027 文档称「尾行由 summary `chain_tail` 兜底」，但全仓检索显示 `chain_tail` 的唯一消费者是测试断言（非零检查）——**没有任何运行时路径把 summary 指纹与当前日志比对**。指纹已生成（探针 P4 证实指纹不一致可证篡改事实），但没人看。
- **影响**：A1-1 负向用例的测试只篡改中间行，末行场景假通过；总纲 v1.3 据此宣布的 12/12 在 A1-1 上语义不完整。
- **建议修法**（小修批，约两处改动）：① `verify_chain` 增加一行校验 `_sha256(canonical_json(e.get("payload"))) == e.get("payload_sha256")`——单点修复同时覆盖末行与中间行，比 chain_tail 比对更根本；② 测试补「末行 payload 篡改必失败」负向用例。

### D-2（低）：`effect.started` 事件类型未登记

`outbox.mark_started` 写 `effect.started`，但 `EVENT_TYPES` 白名单（17 类）与前端 `api.js` 的 17 个常量都**不含**它。`append` 不校验类型所以能写入，但「前端常量与 EVENT_TYPES 17/17 对齐」的验收声明漏了这个真实会产生的事件类型。建议：登记进 `EVENT_TYPES` 与前端常量（第 18 类），或 outbox 改用已有类型。

### D-3（低）：SSE/WS 对不存在的 run 缺存在性预检，且有 mkdir 副作用

- `list_events` 有 404 预检（`_page` 检查 events 文件存在）；`stream_events` 与 `ws_events` **没有**——直接 `read_page` → `EventLog.__init__` 执行 `mkdir(parents=True, exist_ok=True)`，为不存在的 run **创建空目录**。
- 后果：SSE 先返回 200 再进入无限空轮询（客户端 EventSource 每 3s 空转，永不终止也不报 404）；WS 同样挂死且产生垃圾目录。
- 建议修法：流端点在 acquire 之前复用 `_page` 的存在性检查（或 `_validated_run_dir` 增加 `events.jsonl` 存在性断言），WS 同样预检。

## 4. 观察项（O 表，不构成本轮修正对象）

| # | 内容 | 定级 |
|---|---|---|
| O-1 | `read_session_telemetry` 的 `since` 用字符串比较，「同秒重试」边界会误收上一 attempt 日志；实际 attempt 执行必然跨秒，不可触发 | 观察 |
| O-2 | SSE 每秒全量重读 `events.jsonl`（上限 256MB/200k 条），5 流并发下 O(n)/s；G1 规模内可接受，G7 长时程前建议改增量读 | 观察 |
| O-3 | A1-10 验收表述「入队与 checkpoint 同事务」与实现（event-log-as-outbox，无跨文件事务）措辞不符；崩溃语义（不丢不重）由 pending 派生达成，建议总纲改措辞或登记等价说明 | 措辞 |
| O-4 | A1-9 三端 round-trip 实测由前一基座执行；本基座仅复跑 bogus-session 探针（不烧配额）。resume 语义回忆正确性未在本基座复测 | 证据基座 |
| O-5 | supervisor 的 `max_wall_seconds` 只在两次重启之间检查，单个挂死 worker 不受其约束（依赖 worker 自身 timeout） | 观察 |
| O-6 | `lease.renew` 不检查 `released` 标志：release 后同 owner 同 fencing 再 renew 会成功；实际调用序（release 在进程收尾）不可触发 | 观察 |

## 5. 对总纲 v1.3 的影响

- v1.3「G1 正式收口（12/12）」**维持，但附条件**：D-1 使 A1-1 的末行负向场景未闭合，属验收语义缺口而非功能缺失（中间行场景已闭合、指纹已生成）。建议开一个小修批（D-1+D-2+D-3，改动面小）后再让 12/12 无保留成立；总纲可在该批完成后加一行 v1.3a 修订说明。
- D-1/D-3 均不阻塞 G2（学术证据内核，依赖的是 G-1/G0b 而非事件面）。

## 6. 引用

1. 仓内：[P-027 实施](../spec/arc-g1a-event-core/IMPLEMENTATION.md)（D-2 自认尾行兜底）、[P-030 复核](arc-g1b-review-20261110.md)（R-1/R-2/R-3）、[P-037 实施](../spec/arc-a1-9-session-resume/IMPLEMENTATION.md)。
2. 代码：`researchclaw/runtime/{event_log,lease,supervisor,outbox,event_stream,attempt,exit_codes}.py`、`researchclaw/server/routes/events.py`、`researchclaw/pipeline/runner.py`、`researchclaw/experiment/code_agent.py`、`frontend-legacy/src/services/api.js`。
3. 探针：本报告 §2-T8（bogus session 复跑）、§3-D-1（末行篡改 + 指纹不一致，均为本基座一手执行）。
