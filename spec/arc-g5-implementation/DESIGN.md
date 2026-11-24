---
id: arc-g5-implementation-DESIGN
type: design
version: 1.2
status: verified
date: 2026-11-24
depends: [arc-g5-implementation-RESEARCH, arc-g5-decisions-DESIGN]
upstream: null
---

# 设计：G5 知识接入与 Grounded QA 实施（P-155）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.1 / verified）。
> **变更面**：新增 8 个知识/问答模块 + 2 个计数接入 + 1 个 Stage 20 钩子 + 7 个测试文件；不改既有写入契约。

---

## 1. 决策（吸收 P-154）

| 编号 | 决策 |
|---|---|
| D-1 | Q4 = 本批交付词面检索（子串匹配，`backend` 显式 `lexical`/`kg`）；`EmbeddingProvider`（API → SBERT → TF-IDF 256d）复用留后续批次；`retrieval_degraded` 显式 |
| D-2 | Q6 = 本地关系词表 17 类；外部 KG 只留 `KnowledgeSource` 接口 |
| D-3 | Q7 = Paper 首批 500 条；DOI/标题+年份去重；置信度 0–1 |
| D-4 | GQ 默认关闭；关闭时零文件、与基线逐字节一致 |
| D-5 | SkillPack 使用 `version + digest + HMAC-SHA256 signature`；密钥来自 `RC_SKILLPACK_KEY` |
| D-6 | GQ 矛盾默认 `warn`；`policy=block` 时 Stage 20 阻断 |
| D-7 | K4 全文未就绪：`fulltext=false`，全文引用被拒 |

## 2. 模块划分

| 模块 | 职责 |
|---|---|
| `knowledge/models.py` | `PaperRecord`、`KGNode`、`KGEdge`、`QueryResult`、`SkillPackInfo`、`Citation` |
| `knowledge/paper_index.py` | 读取/校验 `paper_entities.jsonl`；500 选择、去重、置信度归一 |
| `knowledge/textbook_kg.py` | 读取 `textbook_kg.json`；15 实体 / 17 关系；非法边拒绝 |
| `knowledge/store.py` | `KnowledgeStore.query` / `.counts`；空库与降级语义 |
| `knowledge/stats.py` | `knowledge_counts()` 单一计数源 |
| `knowledge/skillpack.py` | 5 份 pack 的 manifest、digest、HMAC 校验与拒绝 |
| `knowledge/grounded_qa.py` | `GroundedQA` / `NullGroundedQA`、citation、insufficient、降级、矛盾 |
| `knowledge/read_position.py` | 按 Source kind/instance 保存与恢复读取位置 |
| `knowledge/__init__.py` | 公共导出（store / counts / GQ / models） |
| `config.py`（`KnowledgeBaseConfig`） | `grounded_qa_policy`（默认 `warn`，合法值 `warn/block`） |
| `pipeline/stage_impls/`（Stage 20） | 读取 GQ 矛盾结果；`policy=block` 时阻断 |
| `scripts/spec/m7_stats.py` / `repo_stats.py` | 接入 `knowledge_counts`（`--knowledge`） |

## 3. 数据格式

### `paper_entities.jsonl`

```json
{"paper_id":"p-0001","title":"...","year":2024,"venue":"...","doi":"10....",
 "abstract":"...","classification_confidence":0.92,"metadata_confidence":1.0,
 "pdf_name":"0001.pdf","source":"Paper_Organized_v2"}
```

- `classification_confidence` 落库前归一到 0–1；`>1` 视为百分制。
- `metadata_confidence` 保持 0–1。
- `paper_id` 唯一；`pdf_name` 只存文件名。

### `textbook_kg.json`

```json
{"entities":[{"id":"tb-1","type":"theorem","name":"...","page":42,"attributes":{}}],
 "relations":[{"source":"tb-1","target":"tb-2","type":"prerequisite","page":43}]}
```

- 实体 15 类：`concept / definition / theorem / lemma / corollary / proof / example / exercise / chapter / section / method / model / dataset / metric / application`。
- 关系 17 类：既有 8 类 + `depends_on / proves / contains / topic_contains / generalizes / applies / prerequisite / example_of / formalized_in`。
- `applies` 仅用于 Textbook KG；研究图 `applies_method` 语义不变。
- 非法关系拒绝并计数；导入报告 `illegal_edges=0`。

### SkillPack

```json
{"packs":[{"id":"literature-search","path":"researchclaw/skills/builtin/experiment/literature-search",
           "version":"1.0.0","digest":"sha256:...","signature":"hmac-sha256:..."}]}
```

- 固定登记 **5 份** pack；manifest 路径 `researchclaw/knowledge/skillpacks.json`。
- `digest` = pack 目录内文件按相对路径排序后的 `path + bytes` 的 sha256。
- `signature` = HMAC-SHA256(`RC_SKILLPACK_KEY`, `id + version + digest`)。
- 任一字段缺失、digest 不符、签名不符 → 拒绝加载；未知 pack id 不加载。

### GQ 输出

```json
{"citations":[{"source":"paper:p-0001","locator":"abstract","quote":"...","digest":"sha256:..."}],
 "status":"answered|insufficient","retrieval_degraded":false,"backend":"lexical"}
```

- citation 四字段：`source / locator / quote / digest`；`digest` 可离线复算。
- 无证据 → `status=insufficient`，不输出「已证实」。
- 依赖缺失/超时 → `retrieval_degraded=true`，stage 仍 DONE。
- 矛盾列表 `contradictions`；默认 `warn`，`knowledge_base.grounded_qa_policy: block` 时 Stage 20 返回 `E20_GQ_CONTRADICTION`。

### read_position

```json
{"source_kind":"paper","source_instance":"p-0001","position":3,"updated_at":"..."}
```

- 存储 `knowledge/read_positions.json`；按 `(kind, instance)` 唯一。
- 重启读取同一位置，不重复抓取；缺失即从 0 开始。

## 4. API

```python
KnowledgeStore(kb_root, paper_index_path=None, kg_path=None).query(kind, text="", limit=10) -> QueryResult
KnowledgeStore.counts() -> dict
load_paper_index(path) -> list[PaperRecord]
select_first_batch(records, limit=500) -> list[PaperRecord]
normalize_confidence(value) -> float
load_textbook_kg(path) -> tuple[list[KGNode], list[KGEdge], list[dict]]
query_entities(nodes, text, limit=10) -> list[KGNode]
load_skillpacks(manifest, key_env="RC_SKILLPACK_KEY") -> list[SkillPackInfo]
GroundedQA(store, enabled=False).answer(question, policy="warn") -> dict
NullGroundedQA().answer(...) -> dict
save_position(path, kind, instance, position) -> None
load_position(path, kind, instance) -> int
knowledge_counts(kb_root) -> dict
```

`QueryResult`：

```json
{"results": [], "empty": true, "retrieval_degraded": false,
 "backend": "none", "fulltext": false, "count": 0}
```

- `kind ∈ {kb, paper, kg}`；未知 `kind` 抛 `ValueError`。
- 空库：`results=[]`、`empty=true`。
- 索引缺失：`empty=true`、`retrieval_degraded=true`。
- `fulltext` 固定 `false`。

## 5. Paper 首批规则

1. `metadata_confidence == 1.0` 优先；
2. `classification_confidence` 归一后降序；
3. 有 `pdf_name` 优先；
4. `paper_id` 升序 tie-break；
5. 去重：`doi.lower()`，否则 `normalize_title(title)+year`；
6. 取前 500；导入报告记录入选/重复/淘汰/量纲修正/边界计数。

补充：
- `normalize_title`：lowercase、去标点、压缩空白。
- `value > 1` 视为百分制并除以 100；`value == 1` 视为归一满值（上游百分制 1 分计入 `boundary_count`）。

## 6. KG 查询

- name 包含匹配（大小写不敏感），返回节点带 `page`；
- 3 条抽样查询各返回 ≥3 实体；
- 非法边在加载阶段拒绝并计数。

## 7. 验收映射

| ID | 落点 |
|---|---|
| A5-1 | K0 空库返回空 + `empty=true` |
| A5-2 | K1 500 条、重复 0、置信度 0–1 |
| A5-3 | K2 15/17、非法边 0、3 条抽样查询 |
| A5-4 | K3 5 份 pack 可加载；单 run 注入 ≤5 |
| A5-5 | K5 计数与文档同源 |
| A5-6 | 降级显式 `retrieval_degraded` |
| A5-7 | `fulltext=false`，全文引用被拒 |
| A5-8 | pack 版本/摘要/签名；篡改拒绝 |
| A5-9 | read_position 保存/恢复；重启不重抓 |
| GQ-1 | 默认关闭零文件 |
| GQ-2 | citation 四字段 + digest 复算 |
| GQ-3 | 无证据 `insufficient` |
| GQ-4 | 依赖失败降级且 stage DONE |
| GQ-5 | 矛盾默认 warn；`policy=block` 时 Stage 20 阻断 |

## 8. 不变式

| 编号 | 不变式 |
|---|---|
| J-1 | 空库/缺失索引不产生伪造条目 |
| J-2 | 置信度只以 0–1 落库 |
| J-3 | 非法 relation 永不入库 |
| J-4 | 任何降级必须显式 `retrieval_degraded=true` |
| J-5 | 计数只有一个来源函数 |
| J-6 | 查询只读，不修改索引与知识库 |
| J-7 | SkillPack 校验失败拒绝加载 |
| J-8 | GQ 关闭时零文件、与基线逐字节一致 |

## 9. Review 记录（Step 6）

- 15 实体类型独立于既有 6 类研究图，避免破坏 `EntityType` 调用方。
- 关系词表只增不改；`applies`/`applies_method` 明确分离。
- SkillPack 使用 stdlib HMAC，避免新增密码学依赖；密钥缺失 fail-closed。
- GQ 与 Stage 20 只做最小接线；默认 warn，不改变既有门禁行为。
- 单批覆盖 G5 全部 14 项；不再拆 P-156。
- 异构复审（跨模型，2026-11-25）5 项修复：paper 查询 `backend` 由失实的 `tfidf` 改为 `lexical` 并修订本决策（embedding 链留后续）；manifest 相对路径锚定仓库根（消除 CWD 依赖）；`metadata_confidence` 落库 0–1 fail-closed；`year`/`metadata_confidence` 类型错误补行号上下文；删除 `store.load_json` 死代码。修复轮 CI 8/8。

## 10. 非目标

全量 2,487、外部 KG 服务、PDF→Markdown、非对称签名、GQ 生成质量评估、重规划。
