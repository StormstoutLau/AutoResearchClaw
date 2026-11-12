---
id: arc-g3-m3-claim-spine-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-12
depends: [arc-g3-m3-claim-spine-RESEARCH, arc-g3-m0-design-DESIGN]
upstream: arc-g3-m3-claim-spine-RESEARCH
---

# 设计：G3 M3 claim 脊柱

> 基于 [RESEARCH.md](RESEARCH.md) 与 [M0 §6](../arc-g3-m0-design/DESIGN.md)。本批只做 claim 的「标注 → 引用 → 导出 → 校验」闭环，不改判定内核。

## 1. 架构总览

```text
stage-09/claims.jsonl ──┐
stage-14/experiment_summary.json ──> annotations_from_stage14()
                                      │
                                      v
                            stage-14/claim_annotations.json
                                      │
Stage 20 门禁 <── _annotations() 合并 ┘
   │
   v
stage-20/claim_gate.json（decisions + cap_reasons）
   │
   ├─ Stage 17 正文 [c-xxxxxxxx] ──> extract_claim_markers()
   │                                      │
   v                                      v
stage-22/paper_final.md ──> export_claim_labels() ──> stage-22/claim_export.json
                                      │
                                      v
Stage 23 run_stage23_consistency()
   ├─ compare_claims（既有双平面）
   ├─ verify_claim_trace（三出口）
   └─ verify_claim_digests（证据复算）
```

## 2. 词表与真值源

- `researchclaw/evidence/claim_policy.py` **显式 re-export** vendor `CitationLabel`：

```python
from researchclaw.vendor.auto_prover.datatypes.core import CitationLabel

CITATION_LABELS = frozenset(label.value for label in CitationLabel)
```

- 互检关系（按 RESEARCH R-1 订正 M0 §6.1）：`CITATION_LABELS ∪ {"speculation"} == set(STATUS_ORDER) == C4 status enum`。
- `speculation` 是 C4 的发布前状态，不在 vendor 枚举内；它是**唯一**的差集元素，新增其他差集即测试红。
- Stage 14/17/20/22/23 只消费 `STATUS_ORDER` / `CITATION_LABELS`，**禁止**在 stage 层新定义状态字符串。

## 3. 模块与接口（冻结）

| 接口 | 签名 | 归属 |
|---|---|---|
| `annotations_from_stage14` | `(run_dir: Path) -> dict[str, dict]` | `evidence/claim_spine.py` |
| `extract_claim_markers` | `(text: str) -> dict[str, list[str]]` | 同上 |
| `export_claim_labels` | `(run_dir: Path) -> dict` | 同上 |
| `verify_claim_trace` | `(run_dir: Path, *, require_export: bool = False) -> dict` | 同上 |
| `verify_claim_digests` | `(run_dir: Path, *, annotations: Mapping[str, Mapping] \| None = None) -> dict` | 同上 |

错误码：`E_CLAIM_TRACE_MISMATCH`、`E_CLAIM_DIGEST_MISMATCH`（不新增其他错误码）。

## 4. 数据形态

### 4.1 `stage-14/claim_annotations.json`

```json
{
  "c-11111111": {
    "metric": "accuracy",
    "value": 0.95,
    "n": 5,
    "ci": [0.94, 0.96],
    "condition": "baseline",
    "source": "stage14",
    "evidence_locator": "stage-14/experiment_summary.json",
    "evidence_digest": "sha256:..."
  }
}
```

- `value` 取 `metrics_summary[metric].mean`；`n` 取 `.count`。
- `ci` **仅当** `condition_summaries[condition]` 同时有 `ci95_low`/`ci95_high` 时写入；否则省略（不得用 min/max 冒充 CI）。
- `condition` 仅在 claim statement 命中某个条件名时写入；否则省略。
- `source` ∈ `{"stage14", "external"}`；external 覆盖时整条替换并改 `source`。
- `evidence_locator` 是 DR-1 增补字段：M0 样例没有它，digest 无法复算。

### 4.2 标记文法

- 正则：`\[(c-[0-9a-f]{8})\]`，与 `CLAIM_ID_RE` 同构。
- `extract_claim_markers(text)` 按空行分块；每块归属最近的 `^#{1,6}\s+` 标题：
  - 标题以数字开头（如 `## 4.2 Results`）→ `§4.2`；
  - 其余标题 → `§<标题文本>`；
  - 无标题 → `§Preamble`。
- 返回 `{claim_id: [ref, ...]}`，ref 去重且保持首次出现顺序。

### 4.3 `stage-22/claim_export.json`

```json
{
  "c-11111111": {
    "status": "numerically_verified",
    "citation_label": "numerically_verified",
    "paragraph_refs": ["§4.2"],
    "deliverable": true,
    "cap_reasons": ["AR-06:latex_verified"]
  }
}
```

- 只导出 `claim_gate.decisions` 中 `deliverable=true` 的 claim。
- `citation_label` 直接取 `status`（同词表）；`partially_formalized` 的显示文案由消费方按「部分形式化」渲染，不得写「形式化已验证」。
- `cap_reasons` 来自 `ClaimDecision.cap_reasons`；无封顶时为 `[]`。
- 文件是**裸映射**（与 M0 §6.4 一致）；trace 错误不写进该文件，由 `export_claim_labels` 返回值携带并交 Stage 23。

## 5. 绑定启发式（Stage 14）

确定性规则，按顺序：

1. 读 `stage-09/claims.jsonl`（live 优先，缺失则空）。
2. 读 live `stage-14/experiment_summary.json`；缺失则写 `{}`。
3. 对每个 claim：
   - 把 statement 小写化；
   - 候选指标 = `metrics_summary` 的 key 及 key 最后一段（`ppo/accuracy` → `accuracy`）；
   - 仅保留「指标名作为完整 token 出现在 statement 中」的候选（词边界匹配，避免 `accuracy` 命中 `balanced_accuracy`）；
   - 取最长匹配；长度相同取字典序最小 key；
   - 条件名（`condition_summaries` key）同样按 token 匹配 statement，命中则优先用该条件的 `metrics[metric]`，并用其 `n_seeds`/CI。
4. 无匹配 → 不生成该 claim 的 annotation。
5. 外部覆盖：读 run 根 `annotations.external.json`，存在则逐条整条覆盖并置 `source="external"`。
6. 原子写 `stage-14/claim_annotations.json`。

## 6. Stage 20 消费

`stage_hooks._annotations(run_dir)` 合并顺序（后者覆盖前者）：

1. `stage-14/claim_annotations.json`（dict → JSON 字符串）；
2. run 根 `annotations.json`（既有 `dict[str, str]` 兼容层）；
3. run 根 `annotations.external.json`（dict → JSON 字符串）。

只保留标量/可序列化值；非 dict 根或坏文件仍按既有语义 `ClaimStreamError`（fail-closed）。

## 7. Stage 17 引用

- 在 `exp_metrics_instruction` 尾部追加「可引用 claim 清单」块：

```text
## CLAIM CITATION GRAMMAR
When a sentence asserts a quantitative claim from the experiment, append its id in square
brackets, e.g. [c-1a2b3c4d]. Only use ids from this list:
- c-1a2b3c4d: <statement 前 120 字>
```

- 清单来源：`stage-09/claims.jsonl`；无 claims 时不追加。
- 不修改 prompt bank、不新增 prompt 版本号（属于运行时上下文）。

## 8. Stage 22 导出

`export_claim_labels(run_dir)`：

1. 读 `stage-20/claim_gate.json.decisions`；缺失 → `{claims: {}, errors: []}`。
2. 读论文文本：`stage-22/paper_final.md` → `stage-17/paper_draft.md` → `stage-19/paper_revised.md`。
3. `markers = extract_claim_markers(text)`。
4. 对每个 decision：
   - `deliverable=false`：不导出；若 `claim_id in markers` → error `unpublished_claim_cited`。
   - `deliverable=true`：导出条目；`paragraph_refs = markers.get(id, [])`。
5. `markers` 中存在但 decisions 未覆盖的 id → error `unknown_claim_marker`。
6. 写 `stage-22/claim_export.json`；返回 `{"claims": ..., "errors": [...]}`。

Stage 22 只记录 `errors` 并 warning；**不**在本阶段失败（阻断点在 Stage 23），保持既有发布路径的失败语义。

## 9. Stage 23 校验

### 9.1 `verify_claim_trace(run_dir, *, require_export=False)`

逐条比对：

| 视图 | 来源 |
|---|---|
| 生产决定 | `stage-20/claim_gate.json.decisions` |
| 导出 | `stage-22/claim_export.json` |
| 审计 | `stage-23/claim_consistency.json.audit` |

规则：

- 每个 `deliverable=true` 的 claim 必须在 export 中且 `status`/`cap_reasons` 相等；
- export 中每个 claim 必须在 decisions 中且 `deliverable=true`；
- 论文标记只能引用 export 中的 claim；
- `audit[claim_id].status` 必须等于 `decisions[claim_id].status`（若 audit 存在）；
- `require_export=true` 且存在 decisions 但无 export → 判红；默认 `False` 用于既有单测 fixture。

返回：`{"ok": bool, "checked": N, "errors": [{"code", "claim_id", "field", "detail"}]}`，`code` 固定为 `E_CLAIM_TRACE_MISMATCH`。

### 9.2 `verify_claim_digests(run_dir, *, annotations=None)`

- 复算 annotation 的 `evidence_digest`：locator 取 `evidence_locator`；`source=stage14` 且缺 locator 时回退 `stage-14/experiment_summary.json`；external 且缺 locator → 计入 `skipped`，不判红。
- 复算 claim `evidence` 条目：仅当 `kind != "pointer"` 且 `locator` 是 run 内真实文件时复算；pointer / 表号 / 非文件 locator 跳过。
- 返回：`{"ok": bool, "checked": N, "skipped": N, "errors": [{"code", "claim_id", "field", "detail"}]}`，`code` 固定为 `E_CLAIM_DIGEST_MISMATCH`。
- 边界（S-3）：只能检出「记录后被改」，不能证明生成时正确。

### 9.3 接线

`run_stage23_consistency(stage_dir, run_dir, *, require_export=False)`：

- 写完 `claim_consistency.json` 后追加 `trace` 与 `digests` 两段（均为上述返回值）；
- 返回 `{"consistent": bool, "payload": {...}}`；`consistent` 仍只由 `diffs` 决定（离线审计/既有语义不变）。
- `_execute_citation_verify` 在 **`stage-22/` 目录存在**时传 `require_export=True`（发布阶段确已运行），并在 `trace.ok == False` / `digests.ok == False` 时返回 FAILED，错误字符串分别以 `E_CLAIM_TRACE_MISMATCH` / `E_CLAIM_DIGEST_MISMATCH` 开头。续跑/局部运行未经过 Stage 22 时不强制 export，避免历史 run 误红。

## 10. `cap_reasons`

- `ClaimDecision` 增 `cap_reasons: tuple[str, ...] = ()`。
- `evaluate_claim` 在 `_cap_status` 生效时追加 `f"{finding.code}:{finding.cap}"`；同一原因只记一次，保持发现顺序。
- `as_dict()` 增 `cap_reasons` 键；M5 消费方忽略未知键，向后兼容。
- 格式冻结为 `AR-NN:<status>`；判定内核本身不改。

## 11. 决策表（含拒绝的替代方案）

| # | 决策 | 依据 | 拒绝的方案与理由 |
|---|---|---|---|
| D-1 | 显式 annotation 表 + 确定性 token 匹配 | S-1；O-4 | 拒绝「让 LLM 自报数值」：不可机械复核，且引入模型依赖 |
| D-2 | `evidence_locator` 增补进 annotation | S-2 + DR-1 | 拒绝「用 source 反推路径」：版本化目录下会指错 |
| D-3 | Stage 22 只记录、Stage 23 阻断 | R-7；既有失败语义 | 拒绝「Stage 22 直接 FAILED」：会改变既有导出路径的非致命告警语义 |
| D-4 | `require_export` 默认 False | R-9；既有单测 fixture | 拒绝「默认 True」：所有 Stage 23 单测需重建 stage-22，违背零回归 |
| D-5 | digest 只复算本地文件型证据 | S-3；R-10 | 拒绝「pointer 也强制复算」：跨仓 pointer 无本地字节，必然误红 |
| D-6 | `cap_reasons` 为可选附加字段 | O-3；M5 契约 | 拒绝「改 C4 schema」：越出 M3 边界且破坏双平面契约 |

## 12. 派生需求（DR）

| # | 派生需求 | 理由 | 验收 |
|---|---|---|---|
| DR-1 | annotation 增 `evidence_locator` | M0 样例无该字段，digest 不可复算（RESEARCH R-3/S-3） | F-2、F-10 |
| DR-2 | `paragraph_ref` 文法 `§<heading>` | M0 只给示例 `§4.2`，未定义无编号标题 | F-5/F-6 |
| DR-3 | Stage 20 合并顺序 external > legacy > stage14 | M0 只写「外部覆盖」，未定义根 `annotations.json` 的优先级 | F-8 |
| DR-4 | `require_export` 生产按 `stage-22/` 存在判定 | 阻断点必须在 Stage 23；既有 fixture 无 Stage 22，续跑也不应误红 | F-12、E-1 |

## 13. 不变式

- I-1 不修改 C4 schema、AR 判定与 `evaluate_claim` 的 status 结果；`cap_reasons` 只增字段。
- I-2 词表单一真值源：vendor `CitationLabel` + `STATUS_ORDER`；Stage 层零新字符串。
- I-3 所有落盘原子写（复用 `stage_hooks._write_json` / `_atomic_write_text`）。
- I-4 校验只读；`verify_*` 不写文件。
- I-5 正常 1:1 claim/decision 不触发新增错误；续跑语义不变。
- I-6 无 claims / 无 decisions / 无 export 时三函数均返回 `ok=True, checked=0`（`require_export=true` 且有 decisions 除外）。

## 14. 验收映射

| 验收 ID | 落点 |
|---|---|
| A3-1（三出口同词表） | §2、§4.3、F-11/F-13 |
| A3-3（evidence digest 复算） | §9.2、F-10 |
| O-3（`cap_reasons`） | §10、F-9 |
| O-4（Stage 14 绑定 + Stage 17 标记） | §5、§7、F-1..F-7 |

## 15. 非目标

- 不做 claim 的 NLP 抽取或自动生成（U-1）。
- 不做跨仓 pointer 的 digest 复算（§9.2）。
- 不改 Stage 20 的 `missing_annotation` 判定语义。
- 不实现多 run 并发/外部锚点（G7）。
