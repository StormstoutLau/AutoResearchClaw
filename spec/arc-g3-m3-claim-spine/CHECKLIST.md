---
id: arc-g3-m3-claim-spine-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-12
depends: [arc-g3-m3-claim-spine-IMPLEMENTATION, arc-g3-m3-claim-spine-DESIGN]
upstream: arc-g3-m3-claim-spine-IMPLEMENTATION
---

# 验收清单：G3 M3 claim 脊柱（P-083）

> **Spec 步骤**：Step 7-8, 10。
> **基于实施**：[IMPLEMENTATION.md](IMPLEMENTATION.md)　**基于设计**：[DESIGN.md](DESIGN.md)

## 1. 文档一致性验收（Step 8）

| # | 检查项 | 状态 | 说明 |
|---|---|---|---|
| DC-1 | RESEARCH 的结论在 DESIGN 中被使用（S-1→D-1、S-2→D-2、S-3→D-5、R-1→§2、R-3→§6） | ✅ | DESIGN §11 决策表逐条挂来源 |
| DC-2 | DESIGN 的模块在 IMPLEMENTATION 中有对应实施 | ✅ | DESIGN §3 ↔ IMPL §1/§2 |
| DC-3 | IMPLEMENTATION 的功能点在 CHECKLIST 有验收项 | ✅ | F-1..F-14 / API-1..API-7 |
| DC-4 | 无文档间矛盾（错误码、字段名、合并顺序、`require_export` 口径） | ✅ | 四文档 grep `E_CLAIM_TRACE_MISMATCH`/`evidence_locator`/`cap_reasons`/`stage-22/` 一致 |
| DC-5 | 术语一致（annotation / marker / export / trace / digest） | ✅ | 四文档互查 |
| DC-6 | 派生需求 DR-1..DR-4 已登记且单独验收 | ✅ | DESIGN §12 + F-2/F-5/F-8/F-12 |

## 2. 功能验收

| # | 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|---|---|---|---|---|---|
| F-1 | Stage 14 为命中 claim 生成 annotation | `test_annotations_bind_metric_and_digest` | metric/value/n/digest 正确 | ✅ | 114 passed 套件内 |
| F-2 | DR-1：annotation 带 `evidence_locator` 且 digest 可复算 | 同上 | locator=`stage-14/experiment_summary.json` | ✅ | 同上 |
| F-3 | 未命中 claim 不生成 annotation | `test_annotations_skip_unmatched_claim` | 结果无该 id | ✅ | 同上 |
| F-4 | 条件命中时用 condition 的 CI/n；外部覆盖生效 | `test_annotations_use_condition_ci_and_external_override` | `ci=[0.88,0.92]`、`source=external` | ✅ | 同上 |
| F-5 | 最长 token 匹配（`accuracy` 不压过 `balanced_accuracy`） | `test_annotations_use_longest_token_match` | 选中 `balanced_accuracy` | ✅ | 同上 |
| F-6 | 标记按最近标题归属 | `test_extract_markers_maps_sections` | `§Preamble` / `§4.2` / `§Discussion` | ✅ | 同上 |
| F-7 | 同 claim 多段引用去重 | `test_extract_markers_deduplicates` | 单 ref 出现一次 | ✅ | 同上 |
| F-8 | DR-3：external > legacy root > stage14 | `test_stage20_consumes_stage14_annotations` | gate 不阻断；合并后 `source=external` | ✅ | 25 passed 钩子套件内 |
| F-9 | `cap_reasons` 进 decision 与 export | `test_evaluate_claim_records_cap_reasons`、`test_export_maps_citation_label_and_cap_reasons` | `["AR-06:latex_verified"]` | ✅ | 同上 |
| F-10 | 未发布 claim 不导出 | `test_export_excludes_unpublished_claim` | export 无该 id | ✅ | 同上 |
| F-11 | 未发布 claim 被引用 → export/trace 错误 | `test_export_reports_unpublished_citation` | `unpublished_claim_cited` | ✅ | 同上；E2 探针 `failed` claim 复现 |
| F-12 | DR-4：`require_export` 开关 | `test_verify_trace_requires_export_when_enabled` | True 判红 / 默认不判 | ✅ | 同上 |
| F-13 | 三出口 status 不一致判红 | `test_verify_trace_detects_status_mismatch` | `ok=False`、code 精确 | ✅ | 同上 |
| F-14 | digest 复算检出篡改 | `test_verify_digests_detects_tampered_summary` | `ok=False`、code 精确 | ✅ | 同上 |

## 3. 接口验收

| # | 接口 | 通过条件 | 状态 |
|---|---|---|---|
| API-1 | `annotations_from_stage14(run_dir) -> dict` | 键为 claim_id，条目字段齐全 | ✅ |
| API-2 | `extract_claim_markers(text) -> dict` | 值与 DESIGN §4.2 文法一致 | ✅ |
| API-3 | `export_claim_labels(run_dir) -> dict` | 返回 `{claims, errors}`；文件为裸映射 | ✅ |
| API-4 | `verify_claim_trace(run_dir, *, require_export=False) -> dict` | 返回 `{ok, checked, errors}` | ✅ |
| API-5 | `verify_claim_digests(run_dir, *, annotations=None) -> dict` | 返回 `{ok, checked, skipped, errors}` | ✅ |
| API-6 | `ClaimDecision.as_dict()` | 含 `cap_reasons`；既有键不变 | ✅ |
| API-7 | `run_stage23_consistency(..., require_export=False)` | payload 含 `trace`/`digests`；`consistent` 语义不变 | ✅ |

## 4. 不变式验收

| # | 不变式（DESIGN §13） | 验证方法 | 状态 |
|---|---|---|---|
| INV-1 | I-1 不改 C4/AR 判定结果 | 既有 `test_claim_policy.py` 全绿；diff 只增字段 | ✅ |
| INV-2 | I-2 词表单一真值源 | `test_vendor_label_and_status_order_are_consistent` | ✅ |
| INV-3 | I-3 原子写 | 读码 `claim_spine._atomic_write_text` / `stage_hooks._atomic_write_text` | ✅ |
| INV-4 | I-4 校验只读 | git diff 无 `verify_*` 写文件 | ✅ |
| INV-5 | I-5 1:1 claim/decision 零新增错误 | `test_stage23_reports_trace_and_digests` | ✅ |
| INV-6 | I-6 空输入 `ok=True, checked=0` | `test_verify_digests_skips_pointer_evidence` + 空目录 E2 探针 | ✅ |

## 5. 错误处理验收

| # | 场景 | 触发方式 | 预期 | 状态 |
|---|---|---|---|---|
| E-1 | 生产有 decisions、无 export、`require_export=true` | 删 `claim_export.json` | `E_CLAIM_TRACE_MISMATCH`（`claim_export_missing`） | ✅ |
| E-2 | export 有、decisions 无该 id | 手工加条目 | `E_CLAIM_TRACE_MISMATCH`（`orphan_export_claim`） | ✅ |
| E-3 | annotation digest 被改 | 篡改 `experiment_summary.json` | `E_CLAIM_DIGEST_MISMATCH` | ✅ |
| E-4 | pointer 证据不可复算 | `kind=pointer` fixture | 计入 `skipped`，不判红 | ✅ |
| E-5 | 坏 JSON / 坏行 | 写坏 `claim_gate.json` | `ok=False`，不抛 | ✅ |

## 6. 性能验收

| # | 指标 | 目标 | 实测 | 状态 |
|---|---|---|---|---|
| P-1 | 100 claims × 20 metrics 绑定 | < 50 ms | 35.83 ms（E2，单次测量） | ✅ |

## 7. 兼容性验收

| # | 环境 | 状态 | 说明 |
|---|---|---|---|
| C-1 | Python 3.13.5 | ✅ | 四文件套件 114 passed（1.66s） |
| C-2 | Python 3.11.15 | ✅ | 同读数 114 passed（3.21s） |
| C-3 | 既有 M1/M2/M4/M5 套件 | ✅ | 十文件 177 passed；`test_rc_executor` 207 passed |

## 8. ADD 审计（Step 10）

### 8.1 四阶段

| # | 阶段 | 检查内容 | 结果 | 状态 |
|---|---|---|---|---|
| ADD-1 | Phase 1 完整性 | DESIGN §3 五接口、§4 三形态、§5-§9 接线全部有实现 | 零缺失 | ✅ |
| ADD-2 | Phase 2 忠实度 | 一处生产口径细化：`require_export` 以 `stage-22/` 存在判定（DR-4），已登记；其余逐条一致 | 零静默偏离 | ✅ |
| ADD-3 | Phase 3 必要性 | 新增行为均有依据：D-1..D-6；`speculation` 差集、pointer 跳过均有读码/标准依据 | 零无据行为 | ✅ |
| ADD-4 | Phase 4 语义 | Stage 23 真实阻断（E-1/E-2 复现）；export 真实排除 failed/falsified（E2 探针） | 意图一致 | ✅ |

### 8.2 审计发现（诚实结果列）

| 严重性 | 发现 | 证据 | 修复建议 |
|---|---|---|---|
| P3 | Stage 17 的 `[c-xxxxxxxx]` 依赖 LLM 遵守，未标记的数值断言不被检出 | 读码 `_paper_writing.py` claim grammar 块；U-1 | 后续引入受控 claim 抽取或文本核对 |
| P3 | 外部 annotation 缺 `evidence_locator` 时 digest 跳过 | 读码 `verify_claim_digests`；U-3 | 外部覆盖契约要求 locator，或引入外部 digest 提供方 |
| P3 | REFINE 后版本化 `stage-14_vN/claim_annotations.json` 不参与 Stage 20 | 读码 `_annotations` 只读 live `stage-14`；U-2 | 与 D-1 相同的版本选择语义扩展到 annotation |

### 8.3 ADD Iron Law 检查

- [x] 断言恒真式：错误码与状态值精确匹配（`E_CLAIM_*`、`status_mismatch`）
- [x] 单文件检查盲区：claim_spine 单测 + Stage 20/23 接线测试 + executor 阻断测试
- [x] 设计文档独有约束无测试：I-4 只读、I-6 空输入有断言
- [x] 修正阻断性项无测试：E-1/E-2/E-3 三错误场景

### 8.4 取证矩阵（RULE-6）

| 取证手段（等级） | 覆盖项 | 结果 |
|---|---|---|
| pytest 双环境输出（E1） | F-1..F-14、C-1/C-2 | ✅ 114 passed ×2 |
| pytest 回归输出（E1） | C-3、INV-1 | ✅ 177 passed；`test_rc_executor` 207 passed |
| 运行时探针（E2，含空目录 / 篡改 / failed-claim 引用 / 100×20 性能） | E-1..E-5、P-1、F-11 | ✅ 标注 1 条、导出 1 条、trace/digest 判红、35.83 ms |
| git status/diff（E1） | 改动边界：6 代码/配置 + 3 测试 + 4 spec + session | ✅ 无越界写入 |
| 静态读码（E3） | INV-2/3/4、API-1..7 | ✅ 逐条核对 |
| 盲区扫描（E4，扫描范围：46 项验收 + 3 类 U 项） | 全部 | **发现 3 项 P3**（见 §8.2） |

## 9. 文档完整性

| 文档 | 存在 | 与实现一致 |
|---|---|---|
| RESEARCH.md | ✅ | ✅ |
| DESIGN.md | ✅ | ✅ |
| IMPLEMENTATION.md | ✅ | ✅ |
| CHECKLIST.md（本文件） | ✅ | ✅ |
| ADR | 不适用（无框架级决策） | — |
| 开发日志 | PROGRESS P-083 行 | ✅ |

## 10. 验收结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|---|---|---|---|---|
| 文档一致性 | 6 | 6 | 0 | 0 |
| 功能 | 14 | 14 | 0 | 0 |
| 接口 | 7 | 7 | 0 | 0 |
| 不变式 | 6 | 6 | 0 | 0 |
| 错误处理 | 5 | 5 | 0 | 0 |
| 性能 | 1 | 1 | 0 | 0 |
| 兼容性 | 3 | 3 | 0 | 0 |
| ADD 审计 | 4 | 4 | 0 | 0 |
| **总计** | 46 | 46 | 0 | 0 |

> 统计口径（RULE-2）：来自上表逐项勾选，非事后推算。

### 10.2 验收决定

- [x] **验收通过**（P1/P2 零缺陷；3 项 P3 已登记，不阻塞）
- [ ] **有条件通过**
- [ ] **验收失败**

### 10.3 签字

| 角色 | 签字 | 日期 |
|---|---|---|
| 实施者 | DeepSeek-V4.1-Flash（本会话） | 2026-11-12 |
| 审查者 | 自查（单视角）+ 机械核验；独立异构 pass 待后续批次 | 2026-11-12 |

## 11. 后续行动

| 行动 | 责任人 | 期限 | 状态 |
|---|---|---|---|
| U-1 未标记数值断言检出 | G3 后续 | 首个真实 run | pending |
| U-2 版本化 Stage 14 annotation 归属 | G3 后续 | 首次 REFINE 重跑 | pending |
| U-3 外部 annotation digest 复算 | G3 后续 | 首次外部覆盖 | pending |
