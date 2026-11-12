---
id: arc-g3-m3-claim-spine-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-12
depends: [arc-g3-m3-claim-spine-DESIGN]
upstream: arc-g3-m3-claim-spine-DESIGN
---

# 实施记录：G3 M3 claim 脊柱（P-083）

> **状态**：施工完成；M3 套件读数见 §5。

## 1. 改动清单

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `researchclaw/evidence/claim_spine.py` | 新增 | `annotations_from_stage14`、`extract_claim_markers`、`export_claim_labels`、`verify_claim_trace`、`verify_claim_digests` + 两个错误码 |
| 2 | `researchclaw/evidence/claim_policy.py` | 修改 | vendor `CitationLabel` re-export、`CITATION_LABELS`、`cap_reasons`、`as_dict` |
| 3 | `researchclaw/evidence/stage_hooks.py` | 修改 | `_annotations` 三层合并；`run_stage23_consistency` 追加 `trace`/`digests` 与 `require_export` |
| 4 | `researchclaw/pipeline/stage_impls/_analysis.py` | 修改 | Stage 14 末尾生成 `claim_annotations.json` 并登记 artifact |
| 5 | `researchclaw/pipeline/stage_impls/_paper_writing.py` | 修改 | Stage 17 prompt 追加 claim 引用文法与候选清单 |
| 6 | `researchclaw/pipeline/stage_impls/_review_publish.py` | 修改 | Stage 22 导出 `claim_export.json`；Stage 23 阻断 trace/digest 错误 |
| 7 | `tests/test_claim_spine.py` | 新增 | 标注/标记/导出/trace/digest 的 12 项测试 |
| 8 | `tests/test_stage_claim_hooks.py` | 修改 | Stage 20 消费 stage-14 annotation；Stage 23 trace/digest 接线 |
| 9 | `tests/test_claim_policy.py` | 修改 | vendor 词表互检 + `cap_reasons` |
| 10 | `.github/workflows/ci.yml` | 修改 | 固定清单加入 `test_claim_spine.py` |

**不改**：C4 schema、`ar_checks.py`、`offline_audit.py`、Stage 20 的 `missing_annotation` 语义、prompt bank。

## 2. 接口与回退点

| 接口 | 签名 | 回退点 |
|---|---|---|
| `annotations_from_stage14` | `(run_dir: Path) -> dict[str, dict]` | 无 claims/无 summary → 写 `{}`；异常只 warning |
| `extract_claim_markers` | `(text: str) -> dict[str, list[str]]` | 纯函数；空文本 → `{}` |
| `export_claim_labels` | `(run_dir: Path) -> dict` | 无 decisions → `{claims:{}, errors:[]}` |
| `verify_claim_trace` | `(run_dir, *, require_export=False) -> dict` | 坏文件 → `ok=False` + 错误项，不抛 |
| `verify_claim_digests` | `(run_dir, *, annotations=None) -> dict` | 缺文件 → `skipped`，不抛 |
| `evaluate_claim` | 既有签名不变 | 新增 `cap_reasons` 键 |
| `run_stage23_consistency` | `(stage_dir, run_dir, *, require_export=False) -> dict` | 既有调用零改动 |

## 3. 关键行为

- **Stage 14**：`experiment_summary.json` 落盘后调用 `annotations_from_stage14(run_dir)`；产物加入 `artifacts`。
- **Stage 17**：在 `exp_metrics_instruction` 尾部追加 `## CLAIM CITATION GRAMMAR` 与候选清单；无 claims 时不追加。
- **Stage 20**：`_annotations` 依次合并 stage14 → 根 `annotations.json` → `annotations.external.json`；后者覆盖前者。
- **Stage 22**：`paper_final.md` 定稿后调用 `export_claim_labels`；`claim_export.json` 加入 artifacts；errors 只 warning。
- **Stage 23**：`run_stage23_consistency(..., require_export=(stage-22/ 存在))`；`trace.ok`/`digests.ok` 为 False 时返回 FAILED，错误前缀分别为 `E_CLAIM_TRACE_MISMATCH` / `E_CLAIM_DIGEST_MISMATCH`。

## 4. 版本与 API 兼容性核验（Step 6）

| 依赖 | 用法 | 下限可用性 | 状态 |
|---|---|---|---|
| `hashlib` / `json` / `os` / `re` / `pathlib` / `dataclasses` | 摘要、解析、原子写 | 3.11 全有 | ✅ |
| `researchclaw.vendor.auto_prover.datatypes.core.CitationLabel` | 词表 re-export | 仓内既有（P-049） | ✅ |
| `researchclaw.runtime.filelock` | 未使用（M3 单写者，与 Stage 顺序一致） | — | — |
| 3.12+ stdlib API | 无 | — | ✅ |

## 5. 读数（Step 9-10 回填）

| 项 | 读数 |
|---|---|
| 新增/修改测试 | 新增 18 项：`test_claim_spine.py` 14 + `test_claim_policy.py` 2 + `test_stage_claim_hooks.py` 2 |
| 双环境 | 3.13.5 **114 passed**（1.66s）；3.11.15 **114 passed**（3.21s，`uv run --python 3.11 --with pytest --with jsonschema --with referencing`） |
| 相关回归 | M1/M2/M3/M4/M5 十文件 **177 passed**；`test_rc_executor` **207 passed**（与 7 个 M1/M2 文件合计 270 passed） |
| 性能探针 | 100 claims × 20 metrics 绑定 **35.83 ms**（E2，单次测量，含原子写） |
| 门禁 | DC 0 违规；step-gate 5/5；console/repo_stats/rework 全绿；pre-commit **9/9 Passed**；`digest_bound=1` |
| 红→绿 | 红：`ModuleNotFoundError: researchclaw.evidence.claim_spine` + `ImportError: cannot import name 'CITATION_LABELS'`（2 collection errors）；初绿：77 passed；终绿：114 passed 双环境 |

## 6. 验收边界（诚实口径）

- **A3-1**：三出口同词表由 `CITATION_LABELS ⊆ STATUS_ORDER` 互检测试 + export/trace 断言覆盖。
- **A3-3**：digest 复算只覆盖本地文件型证据；pointer 计数入 `skipped`。
- **O-3**：`cap_reasons` 只增字段，不改 status。
- **O-4**：Stage 14 显式绑定；Stage 17 标记由 LLM 遵守，未标记的数值断言不在本批检出范围（U-1）。

## 7. 风险

- Stage 17 LLM 不写标记 → `paragraph_refs` 为空，trace 仍成立（U-1）。
- REFINE 后版本化 `stage-14_vN` 的 annotation 不参与 Stage 20（U-2）。
- 外部 annotation 缺 locator 时 digest 跳过（U-3）。
