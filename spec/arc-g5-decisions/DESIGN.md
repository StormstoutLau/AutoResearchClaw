---
id: arc-g5-decisions-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-g5-decisions-RESEARCH, arc-master-roadmap]
upstream: null
---

# 设计：G5 三问裁决与实施契约（P-154）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **变更面**：零代码；冻结 Q4/Q6/Q7 与 G5 实施契约，供后续实施批按此执行。

---

## 1. D-1 / Q4：embedding 后端

- 复用 `researchclaw/memory/embeddings.py` 的 `EmbeddingProvider`：
  1. 显式配置 API（base_url + key）→ `api`；
  2. 否则 sentence-transformers 可用 → `sbert`；
  3. 否则 TF-IDF 256d → `tfidf`。
- 检索结果必须携带 `embedding_backend`；发生降级时 `retrieval_degraded=true`（A5-6 / GQ-4），不得静默。
- 不新增依赖；API 不是默认路径。

## 2. D-2 / Q6：KG 词表

- `RelationType` 扩为 17 类：现有 8 类 + `depends_on` / `proves` / `contains` / `topic_contains` / `generalizes` / `applies` / `prerequisite` / `example_of` / `formalized_in`。
- Textbook 数据导入时只接受合法集内关系；非法边计数必须为 0（A5-3）。
- 外部 KG 只留 `KnowledgeSource` 协议与 `NullKnowledgeSource`；G5 不发起网络请求。

## 3. D-3 / Q7：Paper 首批

- 首批 **500** 条，选择顺序：
  1. `metadata_confidence == 1.0` 优先；
  2. `classification_confidence` 归一后从高到低；
  3. 有已整理 PDF 优先；
  4. `paper_id` 升序作为确定性 tie-break。
- 去重键：DOI（存在时）否则 `normalized_title + year`；重复键必须为 0。
- `classification_confidence` 由 0–100 归一到 0–1，`metadata_confidence` 保持 0–1；量纲混用即失败。
- 全量 2,487 条导入登记为后续批次；本阶段 A5-2 的读数为 **500/500**。

## 4. G5 实施契约（供下一批）

| 交付 | 契约 |
|---|---|
| K0 `KnowledgeStore` | 只读查询接口；空库返回 `[]` + `empty=true`，禁止占位数据 |
| K1 Paper 索引 | 500 条首批；`paper_id` 唯一；两级置信度归一；查询返回 title/year/venue/doi |
| K2 Textbook KG | 15 实体 / 17 关系；节点与边计数与源一致；非法边 0；查询带 page |
| K3 SkillPack | 5 份 pack；`version + digest + signature`；篡改拒绝加载 |
| K5 计数 | `m7_stats` / `repo_stats` 与索引同源重算 |
| GQ `GroundedQA` | 默认关闭；关闭时零文件（GQ-1）；citation 四字段 + 可复算 digest；无证据 `insufficient`；依赖失败 `retrieval_degraded=true` 且 stage 仍 DONE |
| A5-9 read_position | 按 Source kind/instance 保存；重启不重复抓取 |
| K4 全文 | 仍被 Paper Phase 2 硬前置阻断；未就绪时 `fulltext=false` |

## 5. 验收映射调整

| ID | 本阶段读数 |
|---|---|
| A5-2 | 首批 **500** 条，重复键 0，置信度 0–1；全量 2,487 后续批次 |
| A5-3 | 合法关系集 **17 类**；非法边 0；3 条抽样查询各 ≥3 实体且带 page |
| A5-1 / A5-4..A5-9 / GQ-1..GQ-5 | 不变 |

## 6. 实施不变式

| 编号 | 不变式 |
|---|---|
| J-1 | 空库查询返回空 + `empty=true`，无伪造条目 |
| J-2 | 置信度只以 0–1 落库 |
| J-3 | 非法 relation 拒绝入库（A5-3） |
| J-4 | 每条 citation 四字段齐全且 digest 可离线复算（GQ-2） |
| J-5 | 任何降级必须显式 `retrieval_degraded=true` |
| J-6 | GQ 默认关闭时产物与基线逐字节一致（GQ-1） |

## 7. Review 记录（Step 6）

- 三问裁决与 RESEARCH §4 一一对应；没有新增未决项。
- Q7 的 500 条不改变 A5-2 的断言结构，只改本阶段读数；全量验收显式推迟，避免「静默降级验收」。
- 关系词表扩展只增不改，现有 8 类语义不变，`Relation.from_dict` 的旧数据仍可加载。
- embedding 后端仍由既有 `EmbeddingProvider` 探测，避免 G5 自建第二套回退链。

## 8. 非目标

K0..K5/GQ 的代码实现、外部 KG 服务、Paper Phase 2、全量 2,487 导入、SkillPack 签名算法选型（由实施批决定具体签名方案）。
