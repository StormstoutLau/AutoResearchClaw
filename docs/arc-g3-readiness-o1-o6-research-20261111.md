---
id: arc-g3-readiness-RESEARCH-2
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g3-readiness-RESEARCH]
upstream: arc-g3-readiness-RESEARCH
---

# 补充调研：G3 readiness 观察项 O-1..O-6 深挖（P-073 前置）

> **Feature**：P-072 复核登记的 O-1..O-6 六项观察的深挖。
> **Spec 步骤**：T3 轻批（Layer-0：本文件 + session + PROGRESS 行；零生产代码/零门禁）。
> **结论先行**：六项全部给出可执行方案与验收映射。核心结论：**O-1 复用 vendor `CitationLabel` 枚举（wrapper 导出，不重写）**；**O-2 总纲断链是旧 §9 索引残留 + 路径基准错误，4 处改为 `spec/...`（无 `../`）**；**O-3 `cap_reason` 升 M5 gate 契约（`capped_from/capped_to/reason`）**；**O-4 Stage 14→claim_id 映射采用「Stage 14 生成时即以 claim_id 命名」**；**O-5 事件链校验以 M2 落地为准，M1 的 `--check` 先做侧车比对**；**O-6 `plan_sig` 字段冻结为 `queries+filters+sources`（全部已在 `_literature.py` 现有产物中）**。

## 1. O-1 vendor `CitationLabel` 与 G3 词表复用边界

### 现状（一手读码）

| 事实 | 位置 |
|---|---|
| vendor 枚举 7 值：`formally_verified/partially_formalized/numerically_verified/latex_verified/falsified/failed`（+`speculation` 在 C4 词表） | [`vendor/auto_prover/datatypes/core.py`](../../researchclaw/vendor/auto_prover/datatypes/core.py) `CitationLabel` |
| vendor 判定链 `decide_citation_label` 已实现全部降级原因（`tree_partial/file_sorry/evidence_incomplete/axioms_not_clean/legality_*`） | [`vendor/auto_prover/verdict/policy.py`](../../researchclaw/vendor/auto_prover/verdict/policy.py) |
| M4/M5 的 claim `status` 字段（C4）与该枚举值域**完全同构**（小写字符串） | `contracts/v1/c4_claim_record.schema.json` |
| ARC 侧唯一包装是 sidecar 返回的 claim `status`，无独立词表 | `evidence/sidecar.py` 白名单字段 |

### 方案（P-074 M3 执行）

1. **不新建枚举**：在 `researchclaw/evidence/claim_policy.py` 顶部做 vendor 枚举的**显式包装导出**：
   `CitationLabel = vendor CitationLabel`（re-export）+ `STATUS_ORDER` 与其互检（单测断言两词表集合相等）。
2. Stage 14/17/22 只消费包装导出的常量，禁止在 stage 层重新定义字符串。
3. 双词表互检测试：`set(CitationLabel) == set(STATUS_ORDER) == C4 status enum`，任一漂移即红。
4. `policy_version` 仍由 `CURRENT_POLICY_VERSION` 管理，与枚举解耦。

**验收映射**：A3-1（三出口同词表）；**消除双词表漂移面**。

## 2. O-2 总纲 4 条既有 P2 断链

### 现状（一手验证）

- 4 条违规全部位于总纲「§11 文档索引」旧表（`arc-master-roadmap.md` L788..L791），形态为 `| [spec/<feature>/...](../spec/<feature>/...) |`。
- **根因**：总纲在仓库根（`arc-master-roadmap.md`），相对基准应为 `spec/...`；这 4 行是从 `docs/` 语境复制而来，带上了 `../` 前缀。目标文件**均真实存在**（`spec/arc-cli-agent-wiring/`、`spec/arc-belief-revision-propagation/RESEARCH.md`、`spec/arc-r3-engine-impact/RESEARCH.md`、`spec/arc-g0b-governance-base/RESEARCH.md` 已验证存在）。
- stash 实证：已提交 HEAD 上即存在，非本轮引入。

### 方案（P-074 M0 执行，一行一处共 4 处）

把 L788..L791 的 `../spec/` 全部改为 `spec/`。修复后 `dc_validator arc-master-roadmap.md` 应为 0 违规。

**验收映射**：DC-4（链接可解析）；无验收 ID，属文档卫生。

## 3. O-3 `cap_reason` 与 M5 gate 契约协同

### 现状

- `ClaimDecision.capped: bool` 已存在，但**只有布尔**，无「从什么封顶到什么、为什么」。
- `claim_gate.json.decisions[claim_id]` 有 `capped` 字段，无原因。

### 方案（P-074 M3 执行）

1. `ClaimDecision` 增 `cap_reasons: tuple[str, ...] = ()`：每次 `_cap_status` 生效时记录 `f"{finding.code}:{finding.cap}"`（如 `AR-06:latex_verified`）。
2. `ClaimDecision.as_dict()` 与 `claim_gate.json` 的 decisions 增 `cap_reasons`；blocked 条目不变。
3. M5 契约升版说明：`cap_reasons` 为新增可选字段（向后兼容，消费方可忽略）。
4. 双平面一致性不受影响：`audit_claim` 重算产出相同 `cap_reasons`。

**验收映射**：A3-1（导出侧「已封顶」显示的数据源）；Q-3 的落地点。

## 4. O-4 Stage 14 → `claim_id` 映射数据源

### 现状

- claim 由 Stage 9 从 hypotheses 抽取，`claim_id = sha256(statement)[:8]`；Stage 14 输出 `experiment_summary.json`（`metrics_summary`/`best_run`）与 VerifiedRegistry（数值白名单），**两者之间目前没有 id 关联**。
- LLM 不会自发使用 `claim_id` 写作。

### 方案（P-074 M3 执行）

1. **Stage 14 生成 annotation 时不做文本匹配**，而是按「claim ↔ 数值证据」的**显式绑定表**落盘：`stage-14/claim_annotations.json`，条目 `{claim_id, metric, value, n, ci?, source: "stage14", evidence_digest}`。
2. 绑定来源：Stage 9 的 claim 已含 statement；Stage 14 从 `experiment_summary.json` 提取数值条目后，由**确定性启发式**（claim statement 中的指标名/条件名与 `metrics_summary` key 匹配）建立绑定；未匹配的 claim 不生成 annotation（Stage 20 对 numeric 缺标注 fail-closed）。
3. LLM 生成 claim 时（Stage 8/17）在 prompt 中携带候选 claim_id 清单，要求正文中以 `[c-xxxxxxxx]` 引用（Stage 14 由此直接对齐）；无法对齐的正文 claim 保持 speculation。
4. 外部覆盖：`annotations.external.json` 优先级高于 Stage 14 产物（`source` 字段区分）。

**验收映射**：A3-1（数值 claim 三出口一致）、A2-5；**Q-4 的落地点**。

## 5. O-5 事件链校验排期

### 现状

- G1a 已有 `events.jsonl`（append-only + `prev_sha256` 链 + `verify_chain`），事件类型表 `EVENT_TYPES` 为白名单。
- Q-5 要求 `pipeline_summary` 摘要写入事件链锚定——**依赖 M2 的 `stage_events.jsonl` 与 `EVENT_TYPES` 扩展**。

### 方案

1. **M1（P-074）**：`pipeline_summary --check` 只做「重算 vs 侧车 `pipeline_summary.sha256`」双向核对（不依赖事件链）。
2. **M2（P-075）**：`EVENT_TYPES` 扩 `pipeline.summary`；写摘要事件（含 digest）；`--check` 升级为「重算 vs 侧车 vs 事件链」三向核对。
3. M0 冻结两步接口：事件字段 `{digest, generated}`，避免 M1/M2 返工。

**验收映射**：A3-2 两阶段达标；O-5 排期关闭。

## 6. O-6 `plan_sig` 取数字段冻结

### 现状（一手读码）

- Stage 4 已落 `stage-04/queries_meta.json`：`{queries, year_min, model_queries_extracted, fallback_reason}`（[`_literature.py`](../../researchclaw/pipeline/stage_impls/_literature.py)）。
- Stage 5 已落 `stage-05/screen_meta.json`：`{outcome, candidates_screened, shortlist_size}`。
- 检索源与过滤：search plan `sources/filters/deduplication`（`title_doi_hash, fuzzy_threshold: 0.9`）在 `_literature.py` L160..L171；去重实现在 [`literature/search.py`](../../researchclaw/literature/search.py) `_deduplicate`（DOI > arXiv ID > fuzzy title）。
- **网络错误信号**：`retrieval_status.json` 的 `retrieval_degraded/real_search_succeeded`（FC-3 豁免的直接数据源）。

### 方案（P-075 M2 执行）

1. `plan_sig = sha256(JCS({stage, queries, year_min, sources, filters}))`：
   - Stage 4 取 `queries_meta.json` + search plan `sources/filters`；
   - Stage 5 取 `screen_meta.json.outcome + candidates_screened + shortlist_size`（口径：筛选轮签名）。
2. `new_rows`：Stage 4 = `candidates.jsonl` 行数；Stage 5 = `shortlist.jsonl` 行数；两轮均按 `_deduplicate` 后口径。
3. `network_error`：读 `retrieval_status.json.retrieval_degraded`（true → 豁免本轮）。
4. 文法冻结进 M0：上述字段名即契约，改动需升版。

**验收映射**：FC-1..3 全部字段闭环；O-6 关闭。

## 7. 对 P-073 G3 M0 的输入清单（汇总）

| 观察 | 落点 | 约束 |
|---|---|---|
| O-1 | M3 词表 | 复用 vendor `CitationLabel`（wrapper 导出 + 双词表互检测试） |
| O-2 | M0 文档卫生 | 总纲 L788..L791 共 4 处 `../spec/` → `spec/` |
| O-3 | M5 契约升版 | `cap_reasons` 进 `ClaimDecision`/gate JSON（可选字段，向后兼容） |
| O-4 | M3 数据绑定 | Stage 14 `claim_annotations.json` 显式绑定表 + Stage 8/17 `[c-xxx]` 引用文法 |
| O-5 | M1/M2 排期 | M1 侧车双向核对；M2 升级三向核对；接口先冻结 |
| O-6 | M2 字段冻结 | `plan_sig`/`new_rows`/`network_error` 取数全部来自既有产物 |

## 8. 结论

- 六项观察全部有可执行方案，且**全部依赖的既有产物/接口已存在**（无新建基础设施需求）；O-4 的 `[c-xxxxxxxx]` 正文引用文法是唯一新增约定。
- P-073 G3 M0 应将本文件 §7 清单并入设计冻结范围；本文件不改总纲 106 计数。
