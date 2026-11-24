---
id: arc-g5-implementation-RESEARCH
type: design
version: 1.1
status: verified
date: 2026-11-24
depends: [arc-g5-decisions-DESIGN, arc-knowledge-paper-textbook]
upstream: null
---

# 调研：G5 知识接入与 Grounded QA 实施（P-155）

> **Feature**：P-155。G5 的唯一实施批：K0/K1/K2/K3/K5/GQ + A5-1..A5-9 + GQ-1..GQ-5。
> **性质**：T1 实施批。P-154 仅作为决策前序，不再拆 P-156；本批一次跑完 10 步。
> **依据**：[P-154 决策](../arc-g5-decisions/DESIGN.md)、`arc-knowledge-paper-textbook-integration.md` §0/§1/§5。

## 1. 问题

G5 的目标是「知识可查、可引用、可复算」，但现有代码只有写入与图查询骨架：

| 面 | 现状 | 缺口 |
|---|---|---|
| K0 知识库 | `knowledge/base.py` 只写 Markdown 条目 | 没有统一只读查询；空库语义未定义 |
| K1 Paper | 外部 2,487 条元数据；仓库内无索引 | 无 500 条首批、去重、置信度归一 |
| K2 Textbook KG | 外部 15 实体 / 8 关系 schema；数据含 3 类未登记关系 | 无本地适配器、合法关系集、非法边计数 |
| K3 SkillPack | 现有 `researchclaw/skills/builtin/` 无 pack 版本/摘要/签名 | 篡改无法拒绝，5 份 pack 未登记 |
| K5 计数 | `m7_stats` / `repo_stats` 不感知知识库 | 无法做到计数同源 |
| GQ Grounded QA | 不存在 | 无 citation 四字段、无 insufficient、无降级 |
| A5-9 read_position | 不存在 | 重启会重复抓取，无法续读 |

## 2. 规范回溯（SPEC_PROCESS v1.7.1）

本批按 `spec/SPEC_PROCESS.md` 的硬约束执行：

| 规范位置 | 要求 | 本批落点 |
|---|---|---|
| Step 1 调研（§工具与提示词契约表 L131） | 关键结论 ≥2 独立来源且 ≥1 个 T1；来源标 Layer + 日期 + 版本；失败必须写降级链 | §5 外部案例表 + §6 降级链 |
| Step 2 Review（L132、L153-158） | 引用 ID 可解析；不可解析只能标「未验证」；LLM 不得自任验证器 | §6 引用核验表 |
| 来源三层阶梯（L142-151） | T1 论文/标准/官方文档/源码；T3 社区只用于发现反例与工程陷阱 | §5 按 T1/T3 分层 |
| Step 5 实施文档（L135） | 每个接口写签名 + 回退点；低效排除表非空 | IMPLEMENTATION §4/§5 |
| Step 9 TDD（L139、L168-176） | 先写会失败的测试，再写实现；测试含目标形态 + 反例形态；记录红→绿 | IMPLEMENTATION §3/§6 |
| Step 3 设计（L133） | 每个关键决策写被拒绝的替代方案 + 理由 + 代价 | §7 方案对比 |

## 3. 现有代码（已核实）

- `knowledge/base.py`：`KBEntry`、`write_kb_entry`、`write_stage_to_kb`；无读取函数。
- `knowledge/graph/entities.py`：6 类实体；`relations.py`：8 类关系。
- `knowledge/graph/builder.py`：`add_entity`/`add_relation`/`save`/`load`/`get_entities_by_type`/`get_relations_for`。
- `knowledge/k5_refs.py`：`tb:` / `paper:` 引用解析与未解析阻断。
- `memory/embeddings.py`：API → sentence-transformers → TF-IDF 256d。
- `researchclaw/skills/builtin/`：现有技能目录，但无 `pack.json`/签名。

## 4. 设计输入

| 输入 | 取值 |
|---|---|
| Q4 | 复用既有 embedding 回退链；后端与降级显式 |
| Q6 | 本地关系词表 17 类；外部 KG 只留接口 |
| Q7 | Paper 首批 500 条；DOI/标题+年份去重；置信度 0–1 |
| 外部数据 | `D:\Paper`、Textbook KG 导出；**不入库**，只落导入索引 |
| 签名 | HMAC-SHA256（stdlib `hmac`），密钥来自 `RC_SKILLPACK_KEY`；非对称签名留后续 |

## 5. 外部社区案例（按来源分层）

| # | 来源 | Layer | 日期/版本 | 机制/事实 | 本批借用 | 不借用 |
|---|---|---|---|---|---|---|
| E1 | [SQLite FTS5 Extension（官方文档）](https://www.sqlite.org/fts5.html) | T1 | 访问 2026-11-24；FTS5 文档 | 内置 `bm25()` 排序；`k1=1.2`、`b=0.75` 硬编码 | 作为「关键词检索基线」的对照口径 | 不引入 SQLite 依赖；知识库仍是 JSONL/Markdown |
| E2 | [rank-bm25（PyPI 官方包页）](https://pypi.org/project/rank-bm25/) | T1 | 0.2.2 / 2022-02-16 | `BM25Okapi`；README 明确「不做任何预处理」，示例用 `doc.split(" ")` | 说明 BM25 的 tokenization 责任在调用方 | 不采用空白分词作为默认；中文/混合文本会漏召回 |
| E3 | [SentenceTransformer（官方文档）](https://www.sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html) | T1 | 访问 2026-11-24 | 构造参数含 `local_files_only`；模型可本地路径加载 | 离线优先：本地模型缺失时回退 TF-IDF | 不强制下载模型；不在 CI 里触发网络 |
| E4 | [HF discussion #47：模型下载失败](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/discussions/47) | T3 | 未标日期（线索） | 社区报告下载失败/路径拼写问题 | 作为「下载不可用」工程陷阱的证据 | 不作为最佳实践唯一依据 |
| E5 | [Python hmac 官方文档](https://docs.python.org/3/library/hmac.html) | T1 | Python 3.15.2；页面更新 2026-08-05 | 验证外部 digest 时应使用 `compare_digest()`，避免时序攻击 | SkillPack 签名用 `hmac.compare_digest` | 不用 `==` 比较签名 |
| E6 | [ALCE（arXiv:2305.14627，EMNLP 2023）](https://arxiv.org/abs/2305.14627) | T1 | v2 / 2023-10-31 | citation recall / precision；ELI5 上最佳模型仍有 50% 缺少完整引用支持 | citation 四字段 + `insufficient` 的动机 | 不引入 LLM 自动评判；不做端到端生成评测 |
| E7 | [W3C PROV-O](https://www.w3.org/TR/prov-o/) | T1 | Recommendation 2013-04-30 | Entity / Activity / Agent 的 provenance 模型 | citation 记录 source/locator/digest 的溯源形态 | 不引入 RDF/OWL 运行时 |
| E8 | [Crossref REST API（官方文档）](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) | T1 | 页面更新 2020-04-08 | `/works/{doi}` 可取 DOI 元数据；无需注册 | DOI 作为去重首键；离线导入时不发请求 | 不在查询路径调用网络 |
| E9 | [LinkML（官方文档）](https://linkml.io/linkml/) | T1 | 访问 2026-11-24 | YAML schema + 多格式校验/生成 | 15 实体 / 17 关系的 schema 表达方式 | 不新增 LinkML 运行时依赖；本批手写校验 |

### 5.1 源码锚点（社区案例源码）

| 项目 | 源码 | 核验状态 | 用途 |
|---|---|---|---|
| rank_bm25 | [rank_bm25/__init__.py](https://github.com/dorianbrown/rank_bm25/blob/master/rank_bm25/__init__.py) | 未验证（raw 抓取返回空；以 PyPI README 替代） | `BM25Okapi` 的 tokenization 责任 |
| sentence-transformers | [sentence_transformer/model.py](https://github.com/huggingface/sentence-transformers/blob/main/sentence_transformers/sentence_transformer/model.py) | 未逐行抓取（文档页链接到该源码） | `local_files_only` / `encode` |
| CPython hmac | [Lib/hmac.py](https://github.com/python/cpython/blob/3.14/Lib/hmac.py) | 未逐行抓取（文档页链接到该源码） | `compare_digest` |
| SQLite FTS5 | [ext/fts5/fts5.c](https://github.com/sqlite/sqlite/blob/master/ext/fts5/fts5.c) | 未验证（仅作对照，不引入依赖） | `bm25()` 实现 |
| ALCE | [princeton-nlp/ALCE](https://github.com/princeton-nlp/ALCE) | 未逐行抓取（摘要页给出代码链接） | citation recall/precision 指标 |

## 6. 引用核验与降级链

### 6.1 引用核验（Step 2 四步）

| 引用 | ID | 验证方式 | 状态 |
|---|---|---|---|
| SQLite FTS5 | https://www.sqlite.org/fts5.html | WebFetch 命中官方页面 | 已验证（T1 命中） |
| rank-bm25 | https://pypi.org/project/rank-bm25/ | WebFetch 命中 0.2.2 包页，含 README 与发布日期 | 已验证（T1 命中） |
| SentenceTransformer | https://www.sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html | WebFetch 命中官方文档，签名含 `local_files_only` | 已验证（T1 命中） |
| Python hmac | https://docs.python.org/3/library/hmac.html | WebFetch 命中官方文档，含 `compare_digest` 警告 | 已验证（T1 命中） |
| ALCE | https://arxiv.org/abs/2305.14627 | WebFetch 命中摘要页，作者/年份/结论一致 | 已验证（T1 命中） |
| PROV-O | https://www.w3.org/TR/prov-o/ | WebFetch 命中 W3C Recommendation 页面 | 已验证（T1 命中） |
| Crossref REST | https://www.crossref.org/documentation/retrieve-metadata/rest-api/ | WebFetch 命中官方文档，含 `/works/{doi}` | 已验证（T1 命中） |
| LinkML | https://linkml.io/linkml/ | WebFetch 命中官方文档，含 YAML schema 说明 | 已验证（T1 命中） |
| HF discussion #47 | https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/discussions/47 | 仅检索命中，未逐页抓取 | 未验证（T3 线索，不单独支撑结论） |

### 6.2 降级链（按 SPEC_PROCESS 反模式 ③）

- `raw.githubusercontent.com/dorianbrown/rank_bm25/.../__init__.py` 抓取返回空 → 降级到 PyPI 官方包页（T1），用 README 的 `doc.split(" ")` 与「不做预处理」说明替代源码逐行核对。
- GitHub issue 搜索（rank_bm25 中文分词）无结果 → 不写「社区共识」，改用 PyPI README 的明确声明作为 T1 依据。
- SQLite FTS5 官方页抓取成功，但 bm25 公式段未进入预览 → 以官方 URL 作为页面存在性验证，`k1=1.2 / b=0.75` 由 SQLite 文档镜像页（sources.debian.org）逐字命中作为数值锚点。

## 7. 方案对比

| 方案 | 做法 | 问题 |
|---|---|---|
| A 运行时直读外部数据 | 每次查询访问 `D:\Paper` / Textbook 目录 | CI 不可复现，路径私有 |
| **B 本地索引 + 夹具 + 可选导入（采用）** | 导入为 `paper_entities.jsonl` / `textbook_kg.json`；测试用夹具 | 需要导入步骤，但可复算 |
| C 外包 KG/向量服务 | 查询外部服务 | 网络、鉴权、可用性；A5-3 不可机械判定 |
| D 引入 BM25/SQLite FTS5 作为默认检索 | 直接用 BM25 排名 | 需额外依赖与 tokenizer 维护；Q4 已裁决复用现有回退链 |

拒绝 D 的代价：TF-IDF 语义召回弱于 BM25/embedding，但可通过 SBERT 回退缓解；收益是零新依赖与确定性。

## 8. 风险与边界

| 风险 | 处理 |
|---|---|
| 500 条选择偏差 | 选择规则确定性；导入报告记录入选/淘汰/量纲修正 |
| 外部 schema 与本地实体类型不一致 | 独立 `TextbookEntityType`（15 类），不并入 6 类研究图 |
| 关系词表扩展破坏旧数据 | 只增不改；`applies` 与 `applies_method` 语义分离 |
| 缺失索引 | 空结果 + `empty=true`；不伪造条目 |
| 索引损坏 | `ValueError` fail-closed |
| SkillPack 签名密钥缺失 | 签名模式 fail-closed；测试用显式密钥 |
| GQ 默认关闭仍产生文件 | `NullGroundedQA` 不写任何文件（GQ-1） |
| GQ 依赖失败阻塞阶段 | 降级 `retrieval_degraded=true`，stage 仍 DONE（GQ-4） |
| 引用不可解析 | 标「未验证」，不得写「已验证」 |

## 9. Review 记录（Step 4）

- 外部案例全部按 T1/T3 分层；T3 只用于陷阱（E4），不单独支撑方法学结论。
- 关键结论「BM25 需要调用方 tokenization」有 T1（E2 README）与 T1（E1 参数）两个独立来源。
- 拒绝 D（BM25 默认）已写代价；与 Q4 裁决一致。
- 未重新清点外部 Paper/Textbook 数据；计数以导入报告为准。
- 本批吸收 P-154 的三问裁决，不再单独开决策批；决策写入 DESIGN §1。

## 10. 范围

- 做：K0/K1/K2/K3/K5/GQ、A5-1..A5-9、GQ-1..GQ-5，7 个测试文件覆盖 14 项验收。
- 不做：全量 2,487、外部 KG 服务、PDF→Markdown、非对称签名、GQ 的 LLM 生成质量评估。

## 11. 诚实边界

- 外部数据在仓库外，本批不重新清点；计数以导入报告为准。
- Textbook 15 实体类型是适配层定义，不代表上游 schema 的全部字段。
- SkillPack 签名是 HMAC（对称），密钥管理是本地/CI 责任；不等同于供应链公钥签名。
- K4 全文仍被 Paper Phase 2 阻断，`fulltext` 固定 false。
- BM25/SQLite 仅作对照口径，不进入运行时依赖。
