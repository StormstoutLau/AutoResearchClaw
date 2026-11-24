---
id: arc-g5-decisions-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-knowledge-paper-textbook, arc-master-roadmap]
upstream: null
---

# 调研：G5 三问裁决（P-154）

> **Feature**：P-154。G5（知识接入 + Grounded QA）是剩余唯一的 P1，但开工前必须裁决 Q4 / Q6 / Q7。本批是 T3 决策批：零代码，只落裁决与实施契约。
> **结论先行**：Q4 = 复用现有 embedding 回退链；Q6 = 本地扩词表 + 外部 KG 留接口；Q7 = Paper 首批 500 条高置信度。

## 1. 问题

G5 有 14 项验收、6 个交付物（K0/K1/K2/K3/K5/GQ），三处口径未定：

| 问题 | 未定内容 | 不裁决的后果 |
|---|---|---|
| Q4 | embedding 后端（API / sentence-transformers / TF-IDF） | 检索层无法开工，`retrieval_degraded` 语义悬空 |
| Q6 | KG 扩词表 vs 外包外部 KG | A5-3 的「非法边 = 0」没有合法集 |
| Q7 | Paper 首批范围（2,487 / 500 / 100） | K1 的导入量与验收读数无法冻结 |

## 2. 现状（已核实）

| 面 | 现状 | 位置 |
|---|---|---|
| 知识库 | 只有 Markdown 写入，**没有读/查 API** | `researchclaw/knowledge/base.py` |
| 关系词表 | 8 类：cites / extends / outperforms / uses_dataset / applies_method / evaluates_with / authored_by / related_to | `researchclaw/knowledge/graph/relations.py` |
| 嵌入 | API → sentence-transformers → TF-IDF 256d 三级回退 | `researchclaw/memory/embeddings.py` |
| Paper | 2,487 条整理记录、2,463 个 PDF；Phase 2（PDF→Markdown）未完成 | 外部 `D:\Paper`（报告口径） |
| Textbook KG | 15 实体 / 8 关系 schema；数据含 prerequisite 906、example_of 252、formalized_in 未登记 | 外部 Textbook 项目（报告口径） |
| K5 引用 | `tb:` / `paper:` 引用可解析，未解析即阻断 | `researchclaw/knowledge/k5_refs.py` |

来源：`arc-knowledge-paper-textbook-integration.md` §0/§1/§5（该文件在 `.gitignore` 中，故用行内引用；本批不重新清点外部数据）。

## 3. 三问分析

### Q4 embedding 后端

| 选项 | 优点 | 缺点 |
|---|---|---|
| A 复用现有回退链（API → SBERT → TF-IDF） | 零新依赖；离线可用；已有实现与降级语义 | 语义质量随后端漂移，需要显式记录 |
| B 固定 sentence-transformers | 语义稳定 | 新增依赖与模型下载；离线首跑成本 |
| C 纯 TF-IDF | 确定性最强 | 语义召回弱，GQ 质量受限 |
| D 固定 API | 质量最好 | 网络/密钥/成本，CI 不可用 |

**裁决：A**。默认不配置 API 时走 SBERT → TF-IDF；实际后端写入 `embedding_backend`，降级时 `retrieval_degraded=true`。

### Q6 KG 接入

| 选项 | 优点 | 缺点 |
|---|---|---|
| A 本地扩词表 + 外部 KG 留接口 | 数据已在本地；A5-3 可机械判定；无网络依赖 | 需要维护关系映射 |
| B 外包外部 KG 服务 | 复用外部能力 | 网络、鉴权、可用性、成本；验收面变大 |
| C 只保留现有 8 类 | 最小改动 | 无法吸收 prerequisite / example_of / formalized_in，A5-3 需降级 |

**裁决：A**。新增 9 类关系（depends_on / proves / contains / topic_contains / generalizes / applies / prerequisite / example_of / formalized_in），总数 17；外部 KG 只留 `KnowledgeSource` 适配器接口，G5 不接入。

### Q7 Paper 首批范围

| 选项 | 优点 | 缺点 |
|---|---|---|
| A 500 条高置信度 | 可做去重/量纲/查询闭环；审阅成本可控 | 覆盖率约 20%，需后续扩批 |
| B 全量 2,487 | 一次覆盖 | 11 条 needs_manual 与重复键需先处理，验收面最大 |
| C 100 条最小闭环 | 最快 | 覆盖率低，统计意义弱 |

**裁决：A**。选择规则：`classification_confidence` 归一到 0–1 后取高置信度；`metadata_confidence=1` 优先；有已整理 PDF 优先；按 `paper_id` 确定性排序。去重键：DOI 优先，否则规范化 title+year。

## 4. 裁决结果

| 编号 | 裁决 | 写入 |
|---|---|---|
| D-1 | Q4 = A：复用 API → SBERT → TF-IDF 回退链，后端与降级显式记录 | DESIGN §1 |
| D-2 | Q6 = A：本地词表扩到 17 类，外部 KG 只留接口 | DESIGN §2 |
| D-3 | Q7 = A：首批 500 条高置信度，全量 2,487 登记为后续批次 | DESIGN §3 |

## 5. Review 记录（Step 4）

- 三问均有代码/报告一手依据，未凭印象裁决。
- Q4 不新增依赖：复用 `memory/embeddings.py` 的既有三级回退，避免 G5 引入新的安装面。
- Q6 拒绝外包：A5-3 要求「非法边 = 0」，外部服务的边类型不可控，无法机械保证。
- Q7 选择 500 而非全量：先把量纲归一与去重闭环做对，再扩量；全量验收推迟到后续批次并显式登记。
- 风险：500 条的选择偏差；Textbook schema 与 ARC 词表的映射需要一对一表。

## 6. 范围

- 做：三问裁决、G5 实施契约、A5/GQ 验收映射调整。
- 不做：任何 G5 代码（K0..K5/GQ 由后续实施批交付）、外部数据清点、Textbook schema 修改。

## 7. 诚实边界

- Paper/Textbook 的实际数据在仓库外（`D:\Paper`、Textbook 项目），本批计数来自既有报告，未重新清点。
- 500 条首批意味着 A5-2 的「2,487 条全量」在本阶段改为「500 条首批 + 全量后续」。
- Q4 的 SBERT 是否可用取决于目标环境；不可用时按设计降级为 TF-IDF，并标 `retrieval_degraded`。
- Phase 2（PDF→Markdown）未完成，K4 全文升级仍被硬前置阻断。
