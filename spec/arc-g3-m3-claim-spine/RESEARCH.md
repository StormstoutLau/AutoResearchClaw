---
id: arc-g3-m3-claim-spine-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-12
depends: [arc-g3-m0-design-DESIGN]
upstream: arc-g3-m0-design-DESIGN
---

# 调研文档：G3 M3 claim 脊柱（Stage 14/17/22/23）

> **Feature**：P-083，G3 M3（`claim_annotations.json` + `[c-xxxxxxxx]` 正文标记 + `claim_export.json` + 三出口一致性与 digest 复算）。
> **Spec 步骤**：Step 1-2。
> **输入**：M0 设计冻结 [DESIGN §6/§9/§10](../arc-g3-m0-design/DESIGN.md)；O-1/O-3/O-4 深挖 [O-1..O-6 调研](../../docs/arc-g3-readiness-o1-o6-research-20261111.md)；M2 复核 [P-079 报告](../../docs/arc-g3-m2-review-20261112.md)。

## 1. 调研目标

1. **claim 与数值证据的绑定语义**：在「claim 语句 → 实验指标」没有显式 id 关联的现状下，学术界的 claim verification 如何定义「claim + evidence」的最小充分绑定？
2. **provenance 与 digest 的边界**：标注条目上的 `evidence_digest` 能证明什么、不能证明什么？应绑定到哪一层实体？
3. **标记文法与段落定位**：`[c-xxxxxxxx]` 正文标记如何映射到可复核的段落引用（`paragraph_refs`）？
4. **三出口一致性**：Stage 20 决定 / Stage 22 导出 / Stage 23 校验三者最小一致条件是什么？

## 2. 调研方法

### 2.1 使用的工具与降级链

| 通道 | 用途 | 结果 |
|---|---|---|
| `WebFetch`（w3.org） | W3C PROV-O 原文 | ✅ 取到 Recommendation 头、实体/活动/代理定义与 `wasDerivedFrom` 关系 |
| `WebFetch`（csrc.nist.gov） | FIPS 180-4 原文页 | ✅ 取到摘要「digests are used to detect whether messages have been changed」与 DOI |
| `WebFetch`（api.crossref.org） | SciFact 标识符解析 | ✅ DOI 命中，标题/作者/年份/页码一致 |
| 仓内读码（`Read` / `Grep`） | 现状边界与取数可行性 | ✅ 见 §3.3 |

**降级链记录**：外部标准用 WebFetch 直取原文（T1）；文献用 Crossref 定点解析（T1）；外部检索未命中时全部降级到仓内一手读码，**未出现「工具失败静默跳过」**。

### 2.2 调研范围

- 时间：2013-2026（PROV-O → SciFact → 本仓 G2/G3 落地）。
- 排除：需要训练模型或外部标注集的 claim 抽取（本批不引入 NLP 依赖）。

## 3. 调研发现

### 3.1 claim 与证据绑定

#### S-1 SciFact：Fact or Fiction: Verifying Scientific Claims

- **作者/年份**：Wadden, Lin, Lo, Wang, van Zuylen, Cohan, Hajishirzi / EMNLP 2020, pp. 7534-7550
- **ID**：DOI 10.18653/v1/2020.emnlp-main.609
- **验证状态**：✅ Crossref 命中（标题/作者/年份/页码一致，is-referenced-by-count=241）
- **关键结论**：科学 claim 验证的最小输入是「claim + 证据摘要」，输出是 label（SUPPORT/REFUTE/NOT_ENOUGH_INFO）；claim 与证据必须显式配对，不能只靠同一段文本共现。
- **相关性**：支撑 M0 §6.2「显式绑定表」而非隐式文本匹配；本仓的 `claim_annotations.json` 就是 claim ↔ 数值证据的显式配对表。

#### S-2 W3C PROV-O（Provenance Ontology）

- **作者/年份**：Lebo, Sahoo, McGuinness 等 / W3C Recommendation 30 April 2013
- **ID**：https://www.w3.org/TR/prov-o/
- **验证状态**：✅ 原文取到 Recommendation 头与核心关系（`Entity` / `Activity` / `Agent`；`wasDerivedFrom` / `wasGeneratedBy` / `used`）
- **关键结论**：provenance 的核心是「实体由哪个活动、使用哪些实体生成」；派生关系必须显式记录，不能从内容相同反推。
- **相关性**：claim annotation 是「由 Stage 14 活动生成、派生自 `experiment_summary.json` 实体」的实体；`source` + `evidence_locator` 对应 `wasGeneratedBy` + `wasDerivedFrom`，digest 只是派生关系的完整性校验，不是来源本身。

### 3.2 digest 的能力边界

#### S-3 NIST FIPS 180-4（Secure Hash Standard）

- **发布者/年份**：NIST / 2015-08（DOI 10.6028/NIST.FIPS.180-4）
- **验证状态**：✅ 原文页取到摘要与 DOI
- **关键结论（原文）**：「The digests are used to detect whether messages have been changed since the digests were generated.」
- **相关性**：`evidence_digest` 只能在「生成时记录、校验时复算」的假设下检出**事后改动**；它不能证明生成者身份，也不能阻止生成时即写入错误值。设计必须把这一条写成边界，不得宣称「防篡改」。

### 3.3 仓内一手事实（读码）

| # | 事实 | 位置 | 对设计的影响 |
|---|---|---|---|
| R-1 | `STATUS_ORDER` 7 值；vendor `CitationLabel` **6 值**（无 `speculation`）；C4 status enum 7 值 | [`claim_policy.py`](../../researchclaw/evidence/claim_policy.py)、[`core.py`](../../researchclaw/vendor/auto_prover/datatypes/core.py)、[`c4_claim_record.schema.json`](../../contracts/v1/c4_claim_record.schema.json) | M0 §6.1 的「`set(CitationLabel) == set(STATUS_ORDER)`」字面不成立；正确关系是 `CitationLabel ∪ {speculation} == STATUS_ORDER == C4 enum`。本批按**实际关系**写互检测试 |
| R-2 | `ClaimDecision` 只有 `capped: bool`，无原因；`_cap_status` 丢弃 `Finding.cap` | `claim_policy.py` L64-L87、L136-L144 | O-3 的 `cap_reasons` 必须在 `evaluate_claim` 内累计，才能进 gate/export |
| R-3 | Stage 20 `_annotations` 只读 run 根 `annotations.json`（`dict[str, str]`），不读 Stage 14 产物 | [`stage_hooks.py`](../../researchclaw/evidence/stage_hooks.py) L107-L116 | M3 必须把 `stage-14/claim_annotations.json` 并入 Stage 20，否则 Stage 14 生成的值永远不被消费 |
| R-4 | Stage 14 写 `experiment_summary.json`，`metrics_summary` 为 `{metric: {min,max,mean,count}}`；`condition_summaries` 可带 `ci95_low/high`、`n_seeds` | [`_analysis.py`](../../researchclaw/pipeline/stage_impls/_analysis.py) L506-L554 | annotation 的 `value/n/ci/condition` 有真实取数来源；无 CI 时不得伪造 `ci` |
| R-5 | Stage 17 写 `paper_draft.md`；prompt 汇总块为 `exp_metrics_instruction` | [`_paper_writing.py`](../../researchclaw/pipeline/stage_impls/_paper_writing.py) L2182-L2195 | 候选 `claim_id` 清单可追加到该块，无需改 prompt bank |
| R-6 | Stage 22 在 L1794 写 `paper_final.md`，L1875 初始化 artifacts | [`_review_publish.py`](../../researchclaw/pipeline/stage_impls/_review_publish.py) | 导出钩子应插在 `paper_final.md` 定稿之后、artifacts 返回之前 |
| R-7 | Stage 23 只做双平面一致性；无 export trace / digest 复算 | `_review_publish.py` L2793-L2816 | M3 在 `run_stage23_consistency` 内增 `trace` 与 `digests` 两段，由 Stage 23 决定是否阻断 |
| R-8 | `CLAIM_ID_RE = ^c-[0-9a-f]{8}$`；vendor label 小写 | `claim_policy.py` L43 | 标记文法 `\[(c-[0-9a-f]{8})\]` 与既有 id 完全同构 |
| R-9 | `run_offline_audit` 与 Stage 23 共享 `compare_claims`；无测试断言 Stage 23 payload 与离线报告全等 | [`offline_audit.py`](../../researchclaw/evidence/offline_audit.py)、`tests/test_offline_audit.py` | 扩展 Stage 23 payload 新增键不破坏 M5 的「共享比对」声明 |
| R-10 | 既有 claims 的 `evidence` 为空；测试 fixture 的 pointer 证据 `locator="Table 3"` 不是文件 | `tests/test_offline_audit.py` L41-L53 | digest 复算只对**本地文件型** evidence 生效；pointer/表号必须跳过，否则误红 |

## 4. 综合分析

### 4.1 关键发现

1. **显式绑定优先**（S-1）：claim ↔ 数值证据必须是落盘配对，不能靠「同一段落里出现同一个数字」反推。[置信度 ★★★★★]
2. **provenance 不是 digest**（S-2 + S-3）：`source` + `evidence_locator` 是派生关系，`evidence_digest` 只是完整性校验；两者缺一不可。[★★★★★]
3. **M0 §6.1 的等式需订正**（R-1）：vendor 词表 6 值、C4 7 值，差异恰为 `speculation`；互检测试必须写成「vendor ⊆ STATUS_ORDER 且差集 = {speculation}」。[E1 读码]
4. **Stage 20 消费面是 M3 的真实缺口**（R-3）：只产不消的 annotation 等于零；合并顺序必须显式（external > legacy root > stage14）。[★★★★☆]
5. **digest 复算必须限定本地文件**（R-10）：跨仓 pointer / 表号 locator 无法在本地复算，必须跳过并登记边界。[★★★★☆]

### 4.2 技术 landscape 与空白

- claim verification（S-1）解决的是「给定 claim 与证据，判断支持/反驳」；本批不训练判定模型，只做**证据配对与可追溯**，判定仍由既有 AR/C4 内核。
- provenance（S-2）解决的是「实体如何派生」；本批用最小字段 `source` + `evidence_locator` + `evidence_digest` 表达，不引入 RDF/OWL。
- 现有 Stage 20/23（R-7/R-9）已解决「生产/审计同内核」；未解决「导出侧标签与正文引用是否一致」。

### 4.3 研究空白（本批可填补）

- Stage 14 无 claim ↔ 数值绑定产物 → Stage 20 的 `missing_annotation` 只能靠人工根文件补。
- Stage 22 无 claim 导出产物 → 论文中的 claim 状态无法逐条复核。
- Stage 23 无 export trace / digest 复算 → A3-3 只剩声明。

## 5. 幻觉抑制审查（Step 2 Review）

### 5.1 文献验证

| 引用 | ID | 验证方式 | 状态 |
|---|---|---|---|
| SciFact | 10.18653/v1/2020.emnlp-main.609 | Crossref 解析 + 字段比对 | ✅ 已验证（T1） |
| W3C PROV-O | https://www.w3.org/TR/prov-o/ | 原文页头 + 核心术语 | ✅ 已验证（T1） |
| NIST FIPS 180-4 | 10.6028/NIST.FIPS.180-4 | 原文页摘要 + DOI | ✅ 已验证（T1） |

### 5.2 技术声明验证

| 声明 | 来源 | 状态 |
|---|---|---|
| claim 与证据必须显式配对 | S-1 | ✅ |
| provenance 需记录派生关系，不能从内容反推 | S-2 | ✅ |
| digest 只能检出「生成后被改动」 | S-3 原文 | ✅ |
| vendor 词表 6 值、C4 7 值、差集为 speculation | R-1 读码 | ✅ E1 |
| Stage 20 只读根 annotations.json | R-3 读码 | ✅ E1 |
| Stage 23 payload 扩展不破坏离线审计 | R-9 读码 + 测试检索 | ✅ E1 |

### 5.3 待修正项

- [x] M0 §6.1 的「set 相等」表述按 R-1 订正为「vendor ∪ {speculation} = STATUS_ORDER」；M0 文档不在本批改动范围，订正写入 DESIGN §2 与本文件 R-1。
- [x] M0 §6.2 的 annotation 样例缺 `evidence_locator`；本批增补该字段作为派生需求 DR-1（否则 digest 不可复算）。

## 6. 对设计的输入

### 6.1 可用的技术方案

1. **显式 annotation 表**：Stage 14 用确定性启发式（指标名/条件名 token 出现在 claim statement）建立绑定；未匹配不生成，Stage 20 fail-closed。
2. **标记文法**：正文 `[c-xxxxxxxx]`；`extract_claim_markers` 按 Markdown 段落归属最近标题，输出 `§<heading>`。
3. **三出口一致性**：Stage 20 decisions → Stage 22 export → Stage 23 trace；任一缺失/状态不一致即 `E_CLAIM_TRACE_MISMATCH`。
4. **digest 复算**：annotation 绑定 `evidence_locator` + `evidence_digest`；`verify_claim_digests` 复算本地文件型证据，pointer 跳过。

### 6.2 关键约束

- 不新建词表：`claim_policy` 显式 re-export vendor `CitationLabel`；Stage 层不得新定义状态字符串。
- 不改 C4 schema 与判定内核；`cap_reasons` 只作为 `ClaimDecision` 的可选附加字段。
- Stage 22 不因 trace 错误提前失败（保持既有发布路径）；Stage 23 是阻断点。
- `run_stage23_consistency` 的新增检查默认不要求 export（保护既有单测 fixture）；生产 Stage 23 在 `stage-22/` 存在时传 `require_export=True`。

### 6.3 风险

- Stage 17 LLM 可能不写 `[c-xxxxxxxx]`；导出仍成立但 `paragraph_refs` 为空，trace 无法发现「未标记的数值断言」。登记 U-1。
- Stage 14 重跑会生成版本化 `stage-14_vN/`；Stage 20 只读 live `stage-14`。登记 U-2。
- 外部 annotation 若无 `evidence_locator`，digest 不可复算。登记 U-3。

### 6.4 未决项登记（四元块）

- **U-1 未标记数值断言的检出**
  - **判据**：出现首个真实 run 的论文含数值断言但无 `[c-xxxxxxxx]`，且 Stage 23 未判红
  - **触发条件**：首次真实论文导出，或用户报告「导出漏 claim」
  - **当前倾向**：本批只保证「被标记的 claim 可追溯」；不做 NLP 抽取
  - **证据等级**：S-1（claim 抽取需模型）+ R-5 读码

- **U-2 版本化 Stage 14 的 annotation 归属**
  - **判据**：REFINE 后 Stage 20 能消费最新 Stage 14 的 annotation
  - **触发条件**：首次 REFINE/PIVOT 后重跑 Stage 14-20
  - **当前倾向**：live `stage-14` 优先；版本化目录只作历史
  - **证据等级**：R-4 读码（同 D-1 版本选择语义）

- **U-3 外部 annotation 的 digest 复算**
  - **判据**：`annotations.external.json` 条目带 `evidence_locator` 时 digest 可复算
  - **触发条件**：首次使用外部 annotation
  - **当前倾向**：无 locator 时跳过 digest 校验并计入 `skipped`
  - **证据等级**：S-3 + R-3

## 7. 参考文献

- Wadden D., Lin S., Lo K., Wang L.L., van Zuylen M., Cohan A., Hajishirzi H. *Fact or Fiction: Verifying Scientific Claims*. EMNLP 2020, pp. 7534-7550. DOI 10.18653/v1/2020.emnlp-main.609
- Lebo T., Sahoo S., McGuinness D. et al. *PROV-O: The PROV Ontology*. W3C Recommendation, 2013-04-30. https://www.w3.org/TR/prov-o/
- National Institute of Standards and Technology. *FIPS 180-4: Secure Hash Standard (SHS)*. 2015-08. DOI 10.6028/NIST.FIPS.180-4

---

**Review 签字**: 自查（单视角）+ 机械核验 日期: 2026-11-12
