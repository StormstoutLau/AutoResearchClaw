---
id: arc-g3-m2-stage-events-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-12
depends: [arc-g3-m0-design-DESIGN, arc-g3-m1-artifacts-DESIGN]
upstream: arc-g3-m0-design-DESIGN
---

# 调研文档：G3 M2 stage_events 循环护栏与 summary 事件链

> **Feature**：P-078，G3 M2（`stage_events.jsonl` + 循环护栏 + `events.jsonl:pipeline.summary` 三向核对）。
> **Spec 步骤**：Step 1-2。
> **输入**：M0 设计冻结 [DESIGN §4/§5/§10](../arc-g3-m0-design/DESIGN.md)；P-077 复核缺陷 D-2（事件链尾锚可被覆盖）与 O-4（坏行语义不一致）[复核报告](../../docs/arc-g3-m1-review-20261112.md)；FC-1..FC-3 与护栏背景 [failure-guards-design](../../docs/failure-guards-design.md)。

## 1. 调研目标

1. **D-2 的修法锚点**：无签名、同信任域的 append-only 事件链，能否在本地判定「尾锚被追加伪造」？行业标准给出的边界与可落地形态是什么？
2. **循环判定锚点**：文献检索「无进展」的停止规则在系统综述领域与工程韧性领域分别如何定义？「新增」应按什么口径计？
3. **取数可行性**：`plan_sig` / `new_rows` / `network_error` 能否全部来自既有产物（M0 §5.2 声称可以）？哪些字段有落盘缺口？

## 2. 调研方法

### 2.1 使用的工具与降级链

| 通道 | 用途 | 结果 |
|---|---|---|
| `WebFetch`（rfc-editor.org） | RFC 9162 原文 | ✅ 取到头部与 §1/§1.3 |
| `WebFetch`（ietf.org archive） | MVPS 审计日志草案原文 | ✅ 取到摘要与完备性断言 |
| `WebFetch`（learn.microsoft.com） | 断路器模式官方文档 | ✅ 取到 Context/Solution |
| `WebFetch`（cochrane.org） | Cochrane Handbook Ch.4 | ⚠️ 只取到目录（§4.4.11 标题可见，正文未取） |
| `mcp_paper-search.search_crossref` | 引用标识符解析 | ✅ PRISMA / Schneier-Kelsey 命中 |
| `mcp_paper-search.search_semantic` | 学术检索 | ❌ 0 结果（两轮） |
| `mcp_paper-search.search_arxiv` | 学术检索 | ❌ 0 结果 |
| `mcp_paper-search.search_papers` | 聚合检索 | ⚠️ 21 源仅 6 源有返回，命中文献与主题无关（生物医学），不可用 |
| `mcp_stackexchange.search_questions` | 社区反例 | ❌ `quota_remaining=-1`，两轮均空 |
| `WebSearch` | 通用检索（降级承接） | ✅ 6 轮，含 PRISMA 流图、饱和点、RFC 6962-bis、CLL 草案 |

**降级链记录**：学术检索（semantic/arxiv/聚合）不可用 → 降至 `WebSearch` + `Crossref` 定点解析 → 再降至仓内一手产物（读码）。未出现「工具失败静默跳过」；社区反例通道失败已如实登记，故本文**不以社区帖作为任何结论的唯一依据**。

### 2.2 调研范围

- 时间：1999-2026（审计日志→透明日志→文献停止规则→韧性模式）。
- 排除：需要签名/密钥基础设施的方案（本仓无 KMS，G7 前不引入）。

## 3. 调研发现

### 3.1 防篡改：哈希链的能力边界

#### S-1 RFC 9162（Certificate Transparency v2.0）

- **作者/年份**：Laurie, Messeri, Stradling / 2021-12（Experimental）
- **ID**：RFC 9162（obsoletes RFC 6962）
- **验证状态**：✅ 已验证（rfc-editor 原文页取到标题/作者/状态/§1 API）
- **关键结论**：append-only 由 Merkle 树实现，「任一时刻的日志实例是任一历史实例的超集」，不一致通过比较树根与一致性证明检出。超集语义原文见同族草案 draft-ietf-trans-rfc6962-bis-34（T2 引述，与 RFC 正文同源）。
- **相关性**：D-2 的判定语义应写成「锚点集合只追加、不得替换」，而不是「取最后一行」。

#### S-2 draft-melegassi-opsawg-mvps-logging-00（IETF Internet-Draft）

- **年份**：2026-05-28（work in progress，expires 2026-11-29）
- **验证状态**：✅ 原文取到摘要段（逐字）
- **关键结论（原文）**：「a bare hash chain cannot prove its own completeness (an anchor is REQUIRED)」；「once a head is anchored … tail truncation is exposed」。
- **相关性**：直接判定 D-2 的能力边界——`events.jsonl` 的 `prev_sha256` 链**不能**证明完备性；本仓的 `pipeline_summary.sha256` 侧车与事件锚同处一个信任域，只能**提高伪造成本**，不能证明未被重写。必须把这一条写进设计与验收口径，禁止宣称「已防篡改」。

#### S-3 Schneier & Kelsey 1999（ACM TISSEC）

- **ID**：DOI 10.1145/317087.317089
- **验证状态**：✅ Crossref 命中（标题/作者/年份/卷期页码一致）
- **关键结论**：forward integrity——被攻陷前的日志条目「不可读、不可改、不可无痕销毁」；但攻陷后的条目不在保护范围，且方案依赖密钥链 MAC。
- **相关性**：本仓无密钥 → 不能承诺 S-3 的完整性；只能在**结构一致性**上做检测。

#### S-4 PRISMA 2020（BMJ）

- **ID**：DOI 10.1136/bmj.n71（Page et al., 2021-03-29）
- **验证状态**：✅ Crossref 命中（26 作者、BMJ、n71）
- **关键结论**：PRISMA 2020 流图在「筛选前移除」框内专列 **Duplicate records removed**，即「新增」按**去重后**口径计数。
- **相关性**：`new_rows` 的语义锚点；也支撑「同计划同结果 = 无新增」的判定，而不是「本轮又写了几行」。

### 3.2 循环停止规则

#### S-5 Cochrane Handbook Ch.4 §4.4.11 "When to stop searching"

- **验证状态**：⚠️ 章节存在已验证（cochrane.org 目录逐字），正文未取（E4）
- **相关性**：文献检索停止规则是有官方成文先例的工程问题，不是本仓臆造。

#### S-6 饱和点判据（高校图书馆指南，T3）

- **验证状态**：✅ 网页取到（University of Sydney Library）
- **关键结论**：饱和度指标之一是「每组检索结果中反复出现同样的关键引文」。
- **相关性**：支持「同 `plan_sig` + 同结果集」是空转信号；仅作 T3 佐证，不与 S-4/S-5 并列作 A 类断言。

#### S-7 断路器模式（Microsoft Azure Architecture Center，T2 官方文档）

- **验证状态**：✅ 原文取到
- **关键结论**：失败达到阈值后不再重试，直接快速失败；恢复放行需成功探测。
- **相关性**：把「连续 N 次无进展 → PAUSED，任一有进展即复位」映射为断路器式阈值语义；N=3 为经验初值（failure-guards C.2 已登记）。

### 3.3 仓内一手事实（读码）

| # | 事实 | 位置 | 对设计的影响 |
|---|---|---|---|
| R-1 | `events.jsonl` 已有 `prev_sha256` 链 + `payload_sha256` + `events_summary.chain_tail` | [`event_log.py`](../../researchclaw/runtime/event_log.py) `verify_chain` | 锚点 payload 可机械复核，无需新链 |
| R-2 | `EVENT_TYPES` 白名单与前端常量有**双向对齐测试** | [`test_event_stream.py`](../../tests/test_event_stream.py#L102-L108) | 新增 `pipeline.summary` 必须同步 `api.js` |
| R-3 | `retrieval_status.json` 由 Stage 4 无条件落盘（含 `retrieval_degraded`） | [`_literature.py`](../../researchclaw/pipeline/stage_impls/_literature.py#L382-L395) | FC-3 的 `network_error` 有稳定来源 |
| R-4 | `screen_meta.json` **只在** `model_rejected_all` PAUSED 分支写 | [`_literature.py`](../../researchclaw/pipeline/stage_impls/_literature.py#L806-L833) | M0 §5.2「Stage 5 取 screen_meta」在 DONE 路径无产物 → 必须登记派生需求 |
| R-5 | `_runtime_begin` 对嵌套调用返回 `owns=False`，`_runtime_end` 只在 `owns=True` 时发终态事件 | [`runner.py`](../../researchclaw/pipeline/runner.py#L156-L215) | 可据此实现「一次顶层执行一个锚点」 |
| R-6 | `verify_summary` 当前取**最后一条** `pipeline.summary` | [`summary_check.py`](../../researchclaw/evidence/summary_check.py) | D-2 根因 |
| R-7 | Stage 3 落 `queries.json`（非 `queries_meta.json`）+ `sources.json` + `search_plan.yaml` | `_literature.py` L358-L373 | `plan_sig` 取数改名核对（O-6 文档写 `queries_meta.json`，实际为 `queries.json`） |

## 4. 综合分析

### 4.1 关键发现

1. **裸哈希链不能证明完备性**（S-2 原文 + S-3 + S-1 的信任模型）：本地三视图同域，只能检测**不一致**，不能阻止**一致重写**。设计必须显式声明这一边界，并把「外部锚点」留为未决项。[置信度 ★★★★★]
2. **D-2 的可落地语义是 append-only 超集 + 锚点身份**（S-1）：把「取最后一行」改为「每段执行至多一个锚点，末锚必须匹配」，追加第二个锚点即判红。[★★★★★]
3. **「新增」必须按去重后口径**（S-4）：仅用行数无法识别「同计划同结果」的空转；需要加一个结果集身份（`row_ids_digest`）。[★★★★☆]
4. **停止规则应先告警再暂停**（S-7 + failure-guards C.2）：2 次同签名零新增 → WARN，3 次 → PAUSED；任一有进展/换签名/网络错误即复位。[★★★★☆]
5. **取数存在一处真实缺口**（R-4/R-7）：Stage 5 的 `screen_meta.json` 在 DONE 路径不存在；`queries_meta.json` 实际名为 `queries.json`。[E1 读码]

### 4.2 技术 landscape 与空白

- 透明日志（S-1）解决的是「多观察者 + 签名树头」场景，本仓没有签名与外部观察者 → 只能借用其**超集/一致性**语义，不能借用其安全性承诺。
- 系统综述（S-4/S-5）解决的是「人何时停止检索」，本仓要的是「机器何时停止重跑」；可复用的是**去重后新增**与**饱和判据**，不可复用的是人工判断。
- 现有仓内事件链（R-1）已解决「行内/链内篡改」，未解决「尾部追加」——正是 D-2。

### 4.3 研究空白（本批可填补）

- 无 `stage_events.jsonl`，文献段重跑无任何「进展」记录 → FC-1..3 无法判定。
- `pipeline.summary` 未进事件链 → A3-2 三向核对缺第三视图。

## 5. 幻觉抑制审查（Step 2 Review）

### 5.1 文献验证

| 引用 | ID | 验证方式 | 状态 |
|---|---|---|---|
| RFC 9162 | RFC 9162 | rfc-editor 原文页（标题/作者/状态/§1） | ✅ 已验证（T1） |
| MVPS 审计日志草案 | draft-melegassi-opsawg-mvps-logging-00 | ietf.org archive 原文摘要逐字 | ✅ 存在（T2，work in progress） |
| Schneier & Kelsey | 10.1145/317087.317089 | Crossref 解析 + 字段比对 | ✅ 已验证（T1） |
| PRISMA 2020 | 10.1136/bmj.n71 | Crossref 解析 + 字段比对 | ✅ 已验证（T1） |
| Cochrane §4.4.11 | cochrane.org Ch.4 | 目录逐字（正文未取） | ⚠️ 章节存在，正文未验证（E4） |
| 断路器模式 | learn.microsoft.com | 原文取到 | ✅ 已验证（T2） |
| 饱和点（悉尼大学指南） | 网页 | 原文取到 | ✅ 存在（T3，仅佐证） |

### 5.2 技术声明验证

| 声明 | 来源 | 状态 |
|---|---|---|
| 裸哈希链不能自证完备性，需要外部锚 | S-2 原文 + S-3 | ✅ |
| append-only 语义 = 新实例是旧实例的超集 | S-1 同族草案原文 | ✅ |
| 「新增」按去重后口径 | S-4 流图字段 | ✅ |
| 2 次告警 / 3 次暂停是经验阈值 | failure-guards C.2（本仓） | ✅ 已登记为经验值 |
| `screen_meta.json` 只在 PAUSED 分支写 | R-4 读码 | ✅ E1 |

### 5.3 待修正项

- [x] O-6 文档写 `queries_meta.json`，实际产物为 `stage-03/queries.json` — 已在 §3.3 R-7 订正，设计按实际产物取数。
- [x] 学术检索三通道失效 — 已在 §2.1 降级链登记，不以失败通道作依据。

## 6. 对设计的输入

### 6.1 可用的技术方案

1. **anchor-per-execution**：锚点只由顶层执行写入（`owns=True`），每段至多一个；验证 = 结构 + 末锚匹配。
2. **result-identity digest**：`row_ids_digest = sha256(JCS(sorted(ids)))`，用于识别同计划同结果。
3. **滑动窗口判定**：过滤网络错误轮后取最近 3 轮，同 `plan_sig` 且同 `row_ids_digest` → PAUSED；2 轮 → WARN。

### 6.2 关键约束

- 不新增错误码（M0 §9 已冻结 `E_SUMMARY_TAMPERED` / `E_SUMMARY_EVENT_MISSING` / `E_LOOP_DETECTED`）。
- 事件锚 payload 保持 M0 冻结字段 `{digest, generated}`；`stage_events` 允许在冻结字段外**增补**（`row_ids_digest`），不改变冻结字段语义。
- 新增事件类型必须同步前端常量（R-2）。
- 事件/护栏写入失败不得使 run 失败（与 M1 节点注册同策略）。

### 6.3 风险

- 同计划同结果的 `row_ids_digest` 依赖 id 稳定性；若上游 id 随机化（`candidate-1` 序号不变，稳定；API id 稳定），不会误报。
- `stage_events.jsonl` 单写者假设：与 D-1 同源，多进程并发写不在 M2 范围（登记 U-3）。

### 6.4 未决项登记（四元块）

- **U-1 外部锚点（真完备性）**
  - **判据**：存在跨信任域锚（git commit / KB 条目 / 外部公证）且 `verify_summary` 可对照
  - **触发条件**：G7 开工，或首次出现「多机共享同一 run 目录」
  - **当前倾向**：M2 只做结构一致性；G7 引入外部锚
  - **证据等级**：S-2 原文（E4 设计判断）

- **U-2 Stage 5 的 DONE 分支元数据产物**
  - **判据**：Stage 5 DONE 时也写 `screen_meta.json`（含 outcome / screened / shortlist_size）
  - **触发条件**：M3 触碰 Stage 5，或循环误判/漏判在实测中出现
  - **当前倾向**：M2 用 stage-03 计划 + `quality_threshold` 组 sig，不改 Stage 5 产物
  - **证据等级**：E1 读码（R-4）

- **U-3 `stage_events.jsonl` 并发写**
  - **判据**：并发执行同一 run 时事件不丢行
  - **触发条件**：出现并发 run 需求，或 D-1 修复批（P-079）选文件锁方案
  - **当前倾向**：单写者假设，与 runner 串行结构一致
  - **证据等级**：E2 探针（P-077 X-1 同源）

## 7. 参考文献

- Laurie B., Messeri E., Stradling R. *RFC 9162: Certificate Transparency Version 2.0*. IETF, 2021-12. https://www.rfc-editor.org/rfc/rfc9162.html
- Melegassi L. *draft-melegassi-opsawg-mvps-logging-00: The MVPS Operational Log Format*. IETF, 2026-05-28（work in progress）.
- Schneier B., Kelsey J. *Secure Audit Logs to Support Computer Forensics*. ACM TISSEC 2(2):159-176, 1999. DOI 10.1145/317087.317089
- Page M.J. et al. *The PRISMA 2020 statement: an updated guideline for reporting systematic reviews*. BMJ 2021;372:n71. DOI 10.1136/bmj.n71
- Cochrane Handbook for Systematic Reviews of Interventions, Ch.4 §4.4.11 *When to stop searching*.
- Microsoft Azure Architecture Center. *Circuit Breaker pattern*.
- University of Sydney Library. *Performing searches — saturation point*（T3）.

---

**Review 签字**: 自查（单视角）+ 机械核验 日期: 2026-11-12
