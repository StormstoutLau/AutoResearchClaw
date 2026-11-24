---
id: arc-g5-implementation-IMPLEMENTATION
type: design
version: 1.1
status: verified
date: 2026-11-24
depends: [arc-g5-implementation-DESIGN]
upstream: null
---

# 实施：G5 知识接入与 Grounded QA（P-155）

> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.2 / verified）。
> **状态**：实施完成；代码、测试与读数已回填。本文不宣称未验证项。
> **批次口径**：P-155 是 G5 的唯一实施批；P-154 仅为决策前序，不再拆 P-156。

---

## 1. 计划变更清单

| 文件 | 动作 | 内容 |
|---|---|---|
| `researchclaw/knowledge/models.py` | 新增 | 数据类与序列化 |
| `researchclaw/knowledge/paper_index.py` | 新增 | 500 选择、去重、归一 |
| `researchclaw/knowledge/textbook_kg.py` | 新增 | 15/17、非法边拒绝 |
| `researchclaw/knowledge/store.py` | 新增 | 查询门面、空库与降级 |
| `researchclaw/knowledge/stats.py` | 新增 | `knowledge_counts` |
| `researchclaw/knowledge/skillpack.py` | 新增 | 5 份 pack、digest、HMAC 校验 |
| `researchclaw/knowledge/grounded_qa.py` | 新增 | GQ / NullGQ、citation、insufficient、降级、矛盾 |
| `researchclaw/knowledge/read_position.py` | 新增 | 读取位置保存/恢复 |
| `researchclaw/knowledge/__init__.py` | 修改 | 公共导出（store / counts / GQ / models） |
| `researchclaw/knowledge/skillpacks.json` | 新增 | 5 份 pack 登记 |
| `researchclaw/config.py` | 修改 | `KnowledgeBaseConfig.grounded_qa_policy`（默认 `warn`）+ 校验 |
| `researchclaw/pipeline/stage_impls/`（Stage 20） | 修改 | `policy=block` 时 GQ 矛盾阻断 |
| `scripts/spec/m7_stats.py` / `repo_stats.py` | 修改 | `--knowledge` 接入同一计数函数 |
| `scripts/spec/g5_acceptance.py` | 新增 | T01-T28 执行器：跑 pytest、解析 JUnit、按 A5/GQ 汇总、红/绿相位 |
| `researchclaw/knowledge/{store,skillpack,paper_index}.py` 等 | 修改 | 异构复审修复轮：backend 标注 `lexical`、manifest 路径仓库根锚定、`metadata_confidence` 0–1 fail-closed、类型错误行号、删 `load_json` |
| `tests/test_paper_index.py` | 新增 | K1 |
| `tests/test_textbook_kg.py` | 新增 | K2 |
| `tests/test_knowledge_store.py` | 新增 | K0/A5-6/A5-7 |
| `tests/test_skillpack.py` | 新增 | K3/A5-8 |
| `tests/test_grounded_qa.py` | 新增 | GQ-1..GQ-5 |
| `tests/test_read_position.py` | 新增 | A5-9 |
| `tests/test_knowledge_counts.py` | 新增 | K5 |

## 2. 实施顺序

1. 数据模型与 Paper/KG 纯函数（先写负向用例）；
2. `KnowledgeStore` 门面与降级标记；
3. SkillPack manifest、digest、HMAC 校验；
4. GroundedQA / NullGroundedQA 与 citation/insufficient/降级；
5. Stage 20 矛盾策略接线；
6. read_position；
7. `knowledge_counts` 与两个统计脚本；
8. 全量回归与门禁。

## 3. 测试用例清单（TDD 定向上下文）

> 每个用例先写失败态，再写实现；正例与反例/边界各 ≥1。

### 3.1 Paper 索引（`tests/test_paper_index.py`）

| # | 用例 | 夹具/输入 | 期望 | 反例/边界 | 验收 |
|---|---|---|---|---|---|
| T01 | `test_paper_batch_selects_500` | 600 条合成记录 | 选中 500，顺序确定 | 599/501 边界 | A5-2 |
| T02 | `test_duplicate_doi_removed` | 两条同 DOI（大小写不同） | 重复 0 | 同 DOI 不同 DOI 前缀不合并 | A5-2 |
| T03 | `test_duplicate_title_year_removed` | 无 DOI，标题标点/空白不同 | 归一后判重 | 标题相同但年份不同保留 | A5-2 |
| T04 | `test_confidence_normalized_from_percent` | 92 / 0.8 混用 | 0.92 / 0.8 | 0 / 100 边界 | A5-2 |
| T05 | `test_confidence_boundary_one` | 1 与 1.0 | 保持 1，`boundary_count` +1 | 1.01 → 0.0101 | A5-2 |
| T06 | `test_corrupt_paper_jsonl_raises` | 非法 JSONL 行 | `ValueError` | 空文件 → 空索引 | 错误处理 |

### 3.2 Textbook KG（`tests/test_textbook_kg.py`）

| # | 用例 | 夹具/输入 | 期望 | 反例/边界 | 验收 |
|---|---|---|---|---|---|
| T07 | `test_textbook_kg_counts_15_17` | 15 实体 / 17 关系夹具 | 计数一致 | 少一类关系 → 失败 | A5-3 |
| T08 | `test_illegal_relation_rejected` | 未登记 relation | 不落库，`illegal_edges=1` | 大小写不同视为非法 | A5-3 |
| T09 | `test_sample_queries_return_three_with_page` | 3 条抽样查询 | 各 ≥3 实体且带 page | 空查询 → 空结果 | A5-3 |
| T10 | `test_corrupt_kg_json_raises` | 非法 JSON | `ValueError` | 缺 entities/relations 键 | 错误处理 |

### 3.3 KnowledgeStore（`tests/test_knowledge_store.py`）

| # | 用例 | 夹具/输入 | 期望 | 反例/边界 | 验收 |
|---|---|---|---|---|---|
| T11 | `test_empty_kb_returns_empty` | 空目录 | `[]` + `empty=true` | 不得返回占位条目 | A5-1 |
| T12 | `test_missing_index_marks_degraded` | 无 paper/KG 索引 | `retrieval_degraded=true` | 后端不可用同样标记 | A5-6 |
| T13 | `test_unknown_kind_raises` | `kind="unknown"` | `ValueError` | `kb/paper/kg` 三值合法 | 错误处理 |
| T14 | `test_query_is_read_only` | 查询前后文件哈希 | 哈希不变 | 并发只读 | J-6 |
| T15 | `test_fulltext_false_and_citation_rejected` | 全文查询/引用 | `fulltext=false`，引用被拒 | 不得静默返回摘要冒充全文 | A5-7 |

### 3.4 SkillPack（`tests/test_skillpack.py`）

| # | 用例 | 夹具/输入 | 期望 | 反例/边界 | 验收 |
|---|---|---|---|---|---|
| T16 | `test_load_five_packs` | 5 份 pack manifest | 5 份可加载；单 run 注入 ≤5 | 第 6 份不加载 | A5-4 |
| T17 | `test_tampered_pack_rejected` | 修改 pack 文件 | digest 不符 → 拒绝 | 只改 mtime 不拒绝 | A5-8 |
| T18 | `test_bad_signature_rejected` | 改 signature | HMAC 不符 → 拒绝 | 空签名拒绝 | A5-8 |
| T19 | `test_missing_key_fails_closed` | 无 `RC_SKILLPACK_KEY` | 签名模式拒绝加载 | 非签名模式可显式关闭 | A5-8 |

### 3.5 Grounded QA（`tests/test_grounded_qa.py`）

| # | 用例 | 夹具/输入 | 期望 | 反例/边界 | 验收 |
|---|---|---|---|---|---|
| T20 | `test_gq_disabled_writes_nothing` | `enabled=false` | 无 `grounded_qa/`，产物与基线一致 | 关闭仍写文件 → 失败 | GQ-1 |
| T21 | `test_citation_four_fields_digest_recomputes` | 有证据回答 | source/locator/quote/digest 齐全且复算一致 | 缺字段 → 失败 | GQ-2 |
| T22 | `test_insufficient_without_evidence` | 空检索 | `status=insufficient` | 不得输出「已证实」 | GQ-3 |
| T23 | `test_dependency_failure_degrades_not_fails` | 后端超时/缺失 | `retrieval_degraded=true`，stage DONE | 抛异常 → 失败 | GQ-4 |
| T24 | `test_contradiction_warn_and_block` | 矛盾证据 | 默认 warn；`policy=block` 时 `E20_GQ_CONTRADICTION` | 未阻断 → 失败 | GQ-5 |

### 3.6 read_position（`tests/test_read_position.py`）

| # | 用例 | 夹具/输入 | 期望 | 反例/边界 | 验收 |
|---|---|---|---|---|---|
| T25 | `test_position_roundtrip` | 保存 (paper,p-1,3) | 读回 3 | 不同 instance 隔离 | A5-9 |
| T26 | `test_restart_does_not_refetch` | 重启后读取 | 抓取计数器不增加 | 缺失位置从 0 开始 | A5-9 |

### 3.7 计数同源（`tests/test_knowledge_counts.py`）

| # | 用例 | 夹具/输入 | 期望 | 反例/边界 | 验收 |
|---|---|---|---|---|---|
| T27 | `test_knowledge_counts_single_source` | 索引重算 | m7/repo 与重算一致 | 手改文档数字 → 失败 | A5-5 |
| T28 | `test_counts_mismatch_detected` | 文档与索引差 1 | 检测失败 | 空索引 → 0 计数 | A5-5 |

## 4. 算法级证据锚点

| 算法/规则 | 外部锚点（T1） | 本地落点 | 测试 |
|---|---|---|---|
| BM25 对照口径（不默认采用） | SQLite FTS5 `bm25()`，`k1=1.2`、`b=0.75`；rank-bm25 README 明确不做预处理、示例 `doc.split(" ")` | DESIGN §7（拒绝 D） | T07-T09 的抽样检索对照 |
| DOI/标题去重 | Crossref REST `/works/{doi}` 元数据；DOI 作为首键 | DESIGN §5 | T02/T03 |
| 置信度归一 | 百分制 `>1` 除以 100；`==1` 视为满值 | DESIGN §5 补充规则 | T04/T05 |
| Embedding 回退 | SentenceTransformer 构造参数 `local_files_only`；模型下载可能失败 | DESIGN D-1 | T12/T23 |
| 常量时间签名校验 | Python `hmac.compare_digest()`，避免时序攻击 | DESIGN D-5 | T18 |
| Citation 四字段/insufficient | ALCE 的 citation recall/precision；无支持证据时不可称「已证实」 | DESIGN §3/§7 | T21-T23 |
| Provenance 形态 | W3C PROV-O 的 Entity/Activity/Agent | DESIGN §3（source/locator/digest） | T21 |
| Schema 校验 | LinkML 的 YAML schema 与多格式校验思路 | DESIGN §2/§6 | T07/T08 |

## 5. 接口签名与回退点

| 接口 | 签名 | 回退点 |
|---|---|---|
| `KnowledgeStore.query` | `(kind: str, text: str = "", limit: int = 10) -> QueryResult` | 删除 `store.py`；无既有调用方 |
| `paper_index.load_paper_index` | `(path) -> list[PaperRecord]` | 不提供索引文件；查询返回空 |
| `textbook_kg.load_textbook_kg` | `(path) -> (nodes, edges, errors)` | 不提供 KG 文件；查询返回空 |
| `skillpack.load_skillpacks` | `(manifest, key_env="RC_SKILLPACK_KEY") -> list[SkillPackInfo]` | 不登记 manifest；默认无 pack |
| `grounded_qa.GroundedQA.answer` | `(question, policy="warn") -> dict` | `enabled=false` → `NullGroundedQA` |
| `read_position.save/load` | `(path, kind, instance, position)` / `(path, kind, instance)` | 删除 position 文件；从 0 开始 |
| `stats.knowledge_counts` | `(kb_root) -> dict` | 回退两个统计脚本的旧计数 |

## 6. 低效排除表

| 排除项 | 理由 |
|---|---|
| 每次查询扫描 `D:\Paper` | 私有路径、CI 不可复现、延迟高 |
| LLM 作为 citation 评判器 | ALCE 类指标需可复算；LLM 自评不可靠且成本高 |
| 引入 SQLite FTS5/BM25 作为运行时依赖 | 增加依赖与 tokenizer 维护；Q4 已裁决复用现有回退链 |
| RDF/OWL 运行时 | PROV-O 只借形态；引入 RDF 栈超出 G5 范围 |
| 强制下载 SBERT 模型 | CI 无网络；用 `local_files_only` + TF-IDF 回退 |
| 全量 2,487 首导入 | Q7 裁决首批 500；先闭环去重/量纲 |

## 7. 版本核验表（Step 6）

| 依赖/工具 | 版本 | 核验方式 | 用途 |
|---|---|---|---|
| Python | 3.11 / 3.12 / 3.13 / 3.14 | CI 矩阵 | 运行时 |
| `sqlite3` | stdlib | Python 文档 | 仅对照口径，不作依赖 |
| `rank-bm25` | 0.2.2（2022-02-16） | PyPI 页面 | 仅参考算法，不引入依赖 |
| `sentence-transformers` | 可选，未 pin | 官方文档签名 | 可选后端；缺失回退 TF-IDF |
| `hmac` | stdlib | Python 文档 | 签名校验 |
| LinkML | 参考 | 官方文档 | schema 形态参考，不引入运行时 |

## 8. 红→绿记录

| 阶段 | 预期失败态 | 实际读数 |
|---|---|---|
| 初版测试（文件未建） | 新模块 `ImportError`；T01/T07/T11/T16/T20/T25 失败 | 红相位 `RED-PENDING (tests missing)`（28 missing）；绿相位 `NOT OK` |
| 实现后 | 负向用例（T06/T10/T13/T17/T18/T22/T24）先红后绿 | `--phase green`：`total=28 passed=28 failed=0 missing=0`，`report: GREEN` |
| 全量回归 | `knowledge/base.py`、`knowledge/graph` 既有用例 | 定向回归 261 passed（KB/graph/K5 56 + Stage 20 guards 92 + config/templates 113）；本机全量见 CHECKLIST §10.3（两处环境失败与本批无关） |

## 9. 读数

### 9.1 执行器自检与当前相位

```text
$ python scripts/spec/g5_acceptance.py --selftest
selftest: ok (28 cases parsed)

$ python scripts/spec/g5_acceptance.py --phase red --allow-missing
report: RED-PENDING (tests missing)

$ python scripts/spec/g5_acceptance.py --phase green
report: NOT OK
```

执行器 `scripts/spec/g5_acceptance.py` 已按 T01-T28 建立映射；实现前测试文件不存在，故绿相位失败、红相位在显式 `--allow-missing` 下为 RED-PENDING。

### 9.2 实施后回填

```text
$ python scripts/spec/g5_acceptance.py --phase green --json-out artifacts/p155-acceptance-green.json
phase=green total=28 passed=28 failed=0 missing=0 skipped=0
report: GREEN

$ python -m pytest tests/test_paper_index.py tests/test_textbook_kg.py \
    tests/test_knowledge_store.py tests/test_skillpack.py \
    tests/test_grounded_qa.py tests/test_read_position.py \
    tests/test_knowledge_counts.py -q
30 passed in 0.87s

$ python scripts/spec/m7_stats.py --knowledge
m7_stats: knowledge paper_count=0 paper_duplicates=0 kg_nodes=0 kg_edges=0 illegal_edges=0 consistent=True

$ python scripts/spec/repo_stats.py --knowledge
repo_stats: knowledge paper_count=0 paper_duplicates=0 kg_nodes=0 kg_edges=0 illegal_edges=0 consistent=True
```

- 30 = 28 条 T01-T28 + 2 条 GQ-5 Stage 20 接线（`test_stage20_blocks_on_gq_contradiction`、`test_stage20_warn_policy_does_not_block`）。
- 知识库为空（`docs/kb` 无索引）时计数为 0，`consistent=True`；这是 A5-1 的空库语义，不是伪造数据。
- 回归读数见 §10。

### 9.3 异构复审修复轮（2026-11-25）

跨模型复审（GLM）发现 5 项（1 major + 4 minor），全部修复并新增 3 条定向用例：

| # | 修复 | 用例 |
|---|---|---|
| 1 | paper 查询 `backend` 由失实的 `tfidf` 改为 `lexical`；DESIGN D-1 修订为词面检索交付 | stub 同步 |
| 2 | manifest 相对路径以仓库根锚定（`_resolve_pack_path`），消除 CWD 依赖 | `test_shipped_manifest_loads_from_any_cwd` |
| 3 | `metadata_confidence` 落库 0–1 fail-closed（越界 `ValueError`） | `test_metadata_confidence_out_of_range_rejected` |
| 4 | `year`/`metadata_confidence` 类型错误补行号上下文 | `test_invalid_year_reports_line` |
| 5 | 删除 `store.load_json` 死代码及 `import json` | —（全仓 grep 零调用） |

```text
$ python -m pytest <7 个 G5 测试文件> -q
33 passed in 0.67s        # 28 T + 2 接线 + 3 复审新增

$ python scripts/spec/g5_acceptance.py --phase green
report: GREEN             # 28/28

$ python -m pytest tests/test_rc_kb.py tests/test_knowledge_graph.py tests/test_k5_refs.py \
    tests/test_stage_claim_hooks.py tests/test_simulated_guard.py tests/test_fabrication_guards.py \
    tests/test_offline_audit.py tests/test_rc_config.py tests/test_rc_templates.py -q
261 passed
```

## 10. 门禁

| 门禁 | 读数 |
|---|---|
| dc_validator | 本批 0 违规（全仓 148 存量：P1=62/P2=86） |
| grandfather_gate | grandfathered=0 expired=0 violations=0 |
| step-gate | 5/5（research/design/implement/verify/finalize） |
| verify-anchor | 10 真实 / 0 缺失 / 0 漂移 |
| step_enforce | `digest_bound=1` |
| pre-commit | 全绿 |
| PR CI | 8/8（Packaging/Extras/Tests 3.11-3.14/Roadmap/Spec gates） |
| PR CI（复审修复轮） | 待 CI |

## 11. 未做与边界

- 不含全量 2,487、外部 KG 服务、PDF→Markdown。
- SkillPack 为非对称签名的后续扩展留接口，但本批只用 HMAC。
- GQ 生成质量不在本批评估；只验证契约、降级与阻断。
- 外部数据路径只在导入脚本参数中出现，不写入索引。
