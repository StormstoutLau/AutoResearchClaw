---
id: arc-g3-m2-stage-events-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-12
depends: [arc-g3-m2-stage-events-DESIGN]
upstream: arc-g3-m2-stage-events-DESIGN
---

# 实施记录：G3 M2 stage_events 与 summary 事件链（P-078）

> **状态**：施工完成；M2 套件 30 passed（双环境），读数见 §5。

## 1. 改动清单

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `researchclaw/runtime/stage_events.py` | 新增 | `StageEvent`、`plan_signature`、`plan_payload`、`collect_progress`、`append_stage_event`、`load_stage_events`、`evaluate_loop`、`record_stage_progress` |
| 2 | `researchclaw/evidence/summary_check.py` | 修改 | `append_summary_event` 增 `generated`；`verify_summary(require_event)` 三关（结构/身份/末锚） |
| 3 | `researchclaw/runtime/event_log.py` | 修改 | `EVENT_TYPES` 增 `pipeline.summary` |
| 4 | `frontend-legacy/src/services/api.js` | 修改 | 前端常量同步（对齐测试 R-2） |
| 5 | `researchclaw/pipeline/runner.py` | 修改 | Stage 4/5 循环护栏；顶层 summary 锚定 |
| 6 | `tests/test_stage_events.py` | 新增 | 循环护栏与事件文件测试 |
| 7 | `tests/test_pipeline_summary_check.py` | 修改 | 锚点 fixture 升级 + D-2 回归 |
| 8 | `.github/workflows/ci.yml` | 修改 | 固定清单加入新测试文件 |

**不改**：Stage 4/5 的业务产物与判定、C4 schema、`pipeline_summary` 字段集、`events.jsonl` 既有链格式。

## 2. 接口与回退点

| 接口 | 签名 | 回退点 |
|---|---|---|
| `plan_signature` | `(payload: Mapping[str, object]) -> str` | 纯函数；无 IO |
| `plan_payload` | `(run_dir: Path, stage: int, *, quality_threshold: float = 0.6, min_shortlist: int = 15) -> dict \| None` | 产物缺失返回 `None` |
| `collect_progress` | `(run_dir, stage, *, quality_threshold=0.6, min_shortlist=15) -> dict` | `plan_sig=None` 时调用方跳过 |
| `append_stage_event` | `(run_dir, *, stage, stage_name, attempt, plan_sig, new_rows, row_ids_digest, network_error, status="done", ts=None) -> StageEvent` | 追加单行 + flush + fsync |
| `load_stage_events` | `(run_dir) -> list[StageEvent]` | 末行坏容忍；中间坏抛 `StageEventError` |
| `evaluate_loop` | `(events, *, stage, window=3) -> dict` | 纯函数 |
| `record_stage_progress` | `(run_dir, stage, stage_name, *, config=None) -> dict` | 读写事件文件；异常上抛由 runner 兜底 |
| `append_summary_event` | `(run_dir, summary, event_log=None) -> None` | 写一条锚事件 |
| `verify_summary` | `(run_dir, *, require_event=False) -> dict` | 只读；坏输入不抛 |

## 3. 关键行为

- **循环护栏**：Stage 4/5 DONE → 取既有产物算签名/行数/结果集 digest → 追加事件 → 滑动窗口判定；`pause` 时用 PAUSED 覆盖结果，走既有停机分支。
- **锚点写入**：仅顶层执行（`owns=True`）在 summary 写后追加 `pipeline.summary`（`{digest, generated}`），位置在终态事件之前。
- **锚点验证**：结构（payload 可解析、`payload_sha256` 匹配）→ 身份（同执行段至多一锚）→ 末锚（最后一段 digest = 当前 digest）。
- **失败隔离**：护栏与锚点异常只写 warning，不影响 run 结果。

## 4. 版本与 API 兼容性核验（Step 6）

| 依赖 | 用法 | 下限可用性 | 状态 |
|---|---|---|---|
| `hashlib` / `json` / `os` / `tempfile` / `pathlib` / `dataclasses` | 摘要在事件与锚点 | 3.11 全有 | ✅ |
| `yaml`（PyYAML） | 读 `search_plan.yaml` | 既有依赖（`_literature.py` 已用） | ✅ |
| `researchclaw.runtime.event_log.EventLog` | 读全段事件 | 仓内既有 | ✅ |
| `researchclaw.runtime.attempt` | **不使用**（避免计数耦合） | — | — |
| 3.12+ stdlib API | 无 | — | ✅ |

## 5. 读数（Step 9-10 回填）

| 项 | 读数 |
|---|---|
| 新增/修改测试 | **30 passed**（`test_stage_events.py` 18 + `test_pipeline_summary_check.py` 12） |
| 双环境 | 3.13.5 **30 passed**；3.11.15 **30 passed** |
| 相关回归 | `rc_runner + event_stream + artifact_node + retrieval_degraded + M2` **99 passed**；3.11 四文件 **49 passed** |
| 性能探针 | `evaluate_loop` 200 事件 **0.032 ms**（E2，单次测量） |
| 门禁 | DC 0 违规；step-gate 5/5；console 一致；rework PASS；pre-commit **9/9 Passed**；`test_rc_executor` **207 passed** |
| 红→绿 | 红：`ModuleNotFoundError: stage_events`；`test_second_anchor_in_same_segment_is_rejected` FAILED（1 failed / 11 passed）。绿：30 passed |

## 5.1 测试升级说明

- `test_require_event_with_matching_anchor` / `test_require_event_with_mismatched_anchor` 的 fixture 升级为**运行时形态**（含 `payload_sha256`），因为 M2 起锚点结构校验严格匹配写入端编码；断言强度不降。
- 新增 D-2 回归 3 项：同段重复锚判红、payload 篡改判红、跨段锚点放行。

## 6. 验收边界（诚实口径）

- **FC-1..FC-3**：由事件级单测 + runner 集成测试覆盖。
- **A3-2**：三向核对的第三视图由事件锚提供；**不承诺**抗一致重写（DESIGN §4.2 边界、RESEARCH U-1）。
- **O-4**：坏行语义闭合（中间 fail-closed、末行容忍）。
- **D-2**：同段重复锚与末锚不匹配均判红；完整执行段伪造不在本批能力内。
- **M0 §5.2 偏移**：Stage 5 签名不用 `screen_meta.json`（DONE 路径无产物），登记 DR-2 / U-2。

## 7. 风险

- `row_ids_digest` 依赖上游 id 稳定；id 缺失时退化到 title，仍可比。
- 事件文件单写者假设；并发写与 D-1 同源，登记 U-3。
- 既有 M1 锚点测试的 fixture 需要升级为带 `payload_sha256` 的运行时形态（严格化，不弱化断言）。
