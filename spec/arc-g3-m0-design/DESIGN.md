---
id: arc-g3-m0-design-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g3-m0-design-RESEARCH]
upstream: arc-g3-m0-design-RESEARCH
---

# 设计：G3 M0 设计冻结

> 基于 [RESEARCH.md](RESEARCH.md)。本批只冻结接口与施工顺序，不写生产代码。决策依据：[G3 readiness v1.3](../arc-g3-readiness/RESEARCH.md) Q-1..Q-9；观察输入：[O-1..O-6 深挖](../../docs/arc-g3-readiness-o1-o6-research-20261111.md)。

## 1. 架构总览

```text
Stage 9/14/17/20/23 ──> ClaimRecord/CitationLabel（复用 vendor 枚举）
        │
        ├─ Stage 14 ──> claim_annotations.json（数值绑定）
        ├─ Stage 17 ──> [c-xxxxxxxx] 正文标记
        ├─ Stage 20 ──> claim_gate.json（status/cap_reasons）
        ├─ Stage 22 ──> claim_export.json（label/paragraph_refs/deliverable）
        └─ Stage 23 ──> claim_consistency.json + digest 复算
所有 DONE 阶段 ──> artifacts/nodes.jsonl（ArtifactNode v1）+ blobs/（小文本）
runner ──> pipeline_summary.json + .sha256 + events.jsonl(pipeline.summary)
literature ──> stage_events.jsonl（plan_sig/new_rows/network_error）→ 循环护栏
所有 LLM 请求 ──> prompt_version；run 启动 ──> run_mandate.json
```

## 2. 模块与接口（冻结）

| 模块 | 接口 | 归属 |
|---|---|---|
| `researchclaw/evidence/artifact_node.py` | `ArtifactNode`、`build_node()`、`verify_tree()`、`project_to_evidence()` | M1 |
| `researchclaw/evidence/summary_check.py` | `canonical_summary()`、`summary_digest()`、`verify_summary()` | M1（M2 扩事件链） |
| `researchclaw/runtime/stage_events.py` | `StageEvent`、`append_stage_event()`、`evaluate_loop()` | M2 |
| `researchclaw/evidence/claim_spine.py` | `annotations_from_stage14()`、`extract_claim_markers()`、`export_claim_labels()`、`verify_claim_trace()`、`verify_claim_digests()` | M3 |
| `researchclaw/runtime/mandate.py` | `RunMandate`、`StageHandback`、`prompt_version()` | M4 |
| `researchclaw/knowledge/k5_refs.py` | `K5Ref`、`resolve_refs()`、`check_k5_refs()` | M5 |

## 3. ArtifactNode v1

### 3.1 落盘

- `run_dir/artifacts/nodes.jsonl`：一行一节点，追加写；`node_id` 唯一。
- `run_dir/artifacts/blobs/<sha256>`：仅 `materialized=true` 的小文本（≤1 MiB）。

### 3.2 字段

```json
{
  "node_id": "an-<sha256(type+locator+content_hash)[:16]>",
  "type": "stage_artifact | claim | paper_section | experiment | figure | dataset",
  "locator": "stage-09/exp_plan.yaml",
  "content_hash": "sha256:<64>",
  "parent_ids": ["an-..."],
  "inputs_digest": "sha256:<64>",
  "producer": {"stage": 9, "stage_name": "EXPERIMENT_DESIGN", "attempt": 1},
  "materialized": true,
  "sensitive": false,
  "size_bytes": 1234,
  "created_at": "2026-11-11T00:00:00Z",
  "evidence": null
}
```

### 3.3 规则

- `inputs_digest = sha256(JCS({"parents": sorted(parent content_hash), "params": producer.params}))`。
- `parent_ids` 排序去重；必须全部可解析且无环。
- `materialized=true` ⇔ blob 存在且字节哈希等于 `content_hash`。
- `size_bytes > 1 MiB`、二进制、`sensitive=true` → `materialized=false`（只存指针）。
- `evidence` 为可选投影面；若存在，字段与旧 `EvidenceRef` 逐字段相等，`digest` 必须等于 `content_hash`（AN-4）。

### 3.4 校验

`verify_tree(nodes)`：逐节点重算哈希、解析父节点、检查环、重算 `inputs_digest`。错误：
`E_ARTIFACT_HASH` / `E_ARTIFACT_PARENT` / `E_ARTIFACT_CYCLE` / `E_ARTIFACT_INPUTS`。

## 4. pipeline_summary 校验

- `pipeline_summary.json` 按 RFC 8785 JCS 生成 canonical bytes；`generated` 参与摘要。
- 同目录 `pipeline_summary.sha256`：`sha256:<64>\n`，原子写。
- M2 起在 `events.jsonl` 追加 `pipeline.summary` 事件（`{digest, generated}`）。
- `verify_summary(run_dir, require_event=False)`：
  1. 从持久化 stage 结果重算 summary（复用既有 `_build_pipeline_summary`，`generated` 取文件内值）；
  2. 比对侧车 digest；
  3. `require_event=true` 时比对事件链中最后一个 `pipeline.summary`。
- 错误：`E_SUMMARY_TAMPERED`、`E_SUMMARY_EVENT_MISSING`。
- M1 只做 1+2；M2 增加 3（O-5）。

## 5. stage_events 与循环护栏

### 5.1 事件

`run_dir/stage_events.jsonl`，一行一事件，`seq` 单调：

```json
{"seq": 12, "ts": "...", "stage": 5, "stage_name": "LITERATURE_SCREEN",
 "attempt": 2, "plan_sig": "sha256:...", "new_rows": 0,
 "network_error": false, "status": "done"}
```

### 5.2 取数（O-6，全部来自既有产物）

- `plan_sig = sha256(JCS({"stage": int, "queries": sorted(queries), "year_min": int, "sources": sorted(ids), "filters": filters}))`；Stage 4 取 `queries_meta.json` + search plan，Stage 5 取 `screen_meta.json` 的筛选口径。
- `new_rows`：Stage 4 = `candidates.jsonl` 去重后行数；Stage 5 = `shortlist.jsonl` 行数。
- `network_error`：`retrieval_status.json.retrieval_degraded`（true → 豁免本轮）。

### 5.3 规则

- 同一 stage 最近 3 条事件：`plan_sig` 相同、`new_rows==0`、均无 `network_error` → `PAUSED`，`E_LOOP_DETECTED`。
- 任一轮 `new_rows>0` 或 `network_error=true` → 重置计数/放行。
- `network_error=true` 同时置 `retrieval_degraded`，供 M5 使用。

## 6. Claim 脊柱（Stage 14/17/22）

### 6.1 词表（O-1）

`claim_policy` 显式 re-export vendor `CitationLabel`；单测断言
`set(CitationLabel) == set(STATUS_ORDER) == C4 status enum`。Stage 层禁止新定义字符串。

### 6.2 Stage 14 annotation

`stage-14/claim_annotations.json`：

```json
{"c-11111111": {"metric": "accuracy", "value": 0.95, "n": 5,
  "ci": [0.94, 0.96], "condition": "baseline", "source": "stage14",
  "evidence_digest": "sha256:..."}}
```

- 绑定：claim statement 的指标/条件与 `experiment_summary.json.metrics_summary` 确定性匹配；未匹配不生成。
- 外部 `annotations.external.json` 覆盖，`source` 标注。
- Stage 20 对 `numerically_verified` 缺 annotation 继续 `missing_annotation` 阻断。

### 6.3 Stage 17 标记

- 正文 claim 使用 `[c-xxxxxxxx]`（与 C4 `claim_id` 同模式）。
- `extract_claim_markers(text)` 返回 `{claim_id: [paragraph_refs]}`；未标记的数值断言不得进入导出。

### 6.4 Stage 22 导出

`stage-22/claim_export.json`：

```json
{"c-11111111": {"status": "numerically_verified",
  "citation_label": "numerically_verified", "paragraph_refs": ["§4.2"],
  "deliverable": true, "cap_reasons": []}}
```

- 标签映射：复用 vendor `CitationLabel`；`partially_formalized` 显示「部分形式化」，不得显示「形式化已验证」。
- 不可发布 claim（`failed/falsified`）不得出现在导出；任一未发布 claim 被引用 → `E_CLAIM_TRACE_MISMATCH`。
- `cap_reasons` 来自 `ClaimDecision`（O-3：`AR-06:latex_verified` 形式）。

### 6.5 校验

- `verify_claim_trace(run_dir)`：Stage 20 decisions ↔ Stage 23 consistency ↔ Stage 22 export 三出口逐条一致；错误 `E_CLAIM_TRACE_MISMATCH`。
- `verify_claim_digests(run_dir)`：从 evidence `locator` / blob 重算 `digest`；错误 `E_CLAIM_DIGEST_MISMATCH`（A3-3）。

## 7. 治理

### 7.1 RunMandate

`run_dir/run_mandate.json`，run 启动写一次，不可变：

```json
{"policy_version": 2, "scope": ["stage:1-23", "tool:literature"],
 "strength": "write", "requester": "user:...", "created_at": "...", "run_id": "..."}
```

配置变更只影响新 run；已接受 run 的 mandate 不变。

### 7.2 StageHandback

`stage-NN/handback.json`：`{reason, evidence: [...], requested_scope: [...]}`。
runner 只允许「暂停/交回」，不得静默扩大 scope；越界 → `E_HANDBACK_SCOPE`。

### 7.3 prompt_version

`prompt_version = sha256(JCS({system, user_template, model_role, prompt_bank_version}))`；
每次 LLM 请求写入请求日志/事件，claim 可追溯到生成版本。

## 8. K5 与 retrieval_degraded

- 文法：`^(tb|paper):[A-Za-z0-9][A-Za-z0-9._-]*$`；`tb:` → 知识库节点，`paper:` → 文献 key。
- `check_k5_refs(text, kb, bib)` 返回 `[{file, line, ref}]`；未解析 → `E_K5_UNRESOLVED_REF`；Stage 22 预检 + Stage 23 终检，默认严格。
- `retrieval_degraded=true`：`pipeline_summary.retrieval_degraded` 置 true，论文显式标注（A3-5）；不阻断，但不得静默。

## 9. 错误码

| 错误 | 含义 |
|---|---|
| `E_ARTIFACT_HASH` | 节点内容哈希不符 |
| `E_ARTIFACT_PARENT` | 父节点缺失 |
| `E_ARTIFACT_CYCLE` | 节点图有环 |
| `E_ARTIFACT_INPUTS` | `inputs_digest` 不符 |
| `E_SUMMARY_TAMPERED` | summary 与侧车/重算不符 |
| `E_SUMMARY_EVENT_MISSING` | 事件链缺少 summary 锚点 |
| `E_LOOP_DETECTED` | 连续空转触发 PAUSE |
| `E_CLAIM_TRACE_MISMATCH` | 三出口 claim 状态不一致 |
| `E_CLAIM_DIGEST_MISMATCH` | evidence digest 复算不符 |
| `E_HANDBACK_SCOPE` | StageHandback 越界扩 scope |
| `E_K5_UNRESOLVED_REF` | K5 引用无法解析 |

## 10. 验收映射

| 批次 | 验收 ID | 关键落盘 |
|---|---|---|
| M1 P-075 | AN-1..AN-6、A3-2、A3-3（digest 复算基础） | `artifacts/nodes.jsonl`、`pipeline_summary.sha256` |
| M2 P-076 | FC-1..FC-3、A3-2 事件链 | `stage_events.jsonl`、`events.jsonl:pipeline.summary` |
| M3 P-077 | A3-1、A3-3 | `claim_annotations.json`、`claim_export.json` |
| M4 P-078 | A3-6、A3-7、A3-8 | `run_mandate.json`、`handback.json`、请求日志 |
| M5 P-079 | A3-4、A3-5 | `k5_refs` 报告、`retrieval_degraded` 标注 |

## 11. 不变式

- 不修改 C4 schema 与判定内核；`cap_reasons` 仅进 gate payload。
- 所有落盘原子写（`tmp + os.replace`）；审计/校验只读。
- 词表单一真值源：vendor `CitationLabel` + `CURRENT_POLICY_VERSION`。
- 正常 1:1 claim/decision 不触发新增错误；续跑语义不变。

## 12. 非目标

- 不实现多 run 并发/双平面长期审计（G7）。
- 不实现工具注册表/沙箱（G4）。
- 不做 knowledge Grounded QA（G5）。
