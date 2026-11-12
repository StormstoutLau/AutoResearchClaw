---
id: arc-g3-p3-cleanup-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-13
depends: [arc-g3-p3-cleanup-IMPLEMENTATION]
upstream: arc-g3-p3-cleanup-IMPLEMENTATION
---

# 检查清单：G3 遗留 P3 清理批（P-094）

## 1. 文档一致性验收（Step 8）

| # | 检查项 | 状态 | 说明 |
|---|---|---|---|
| DC-1 | RESEARCH 结论在 DESIGN 中被使用（R-1→D-1、R-2→D-2、R-4→D-4、R-7→D-7 等） | ✅ | DESIGN §4 决策表逐条挂来源 |
| DC-2 | DESIGN 模块在 IMPLEMENTATION 有对应实施 | ✅ | DESIGN §2.1-2.8 ↔ IMPL §1/§4 |
| DC-3 | IMPLEMENTATION 功能点在 CHECKLIST 有验收项 | ✅ | F-1..F-9 |
| DC-4 | 无文档间矛盾（错误码、顺序、目录口径） | ✅ | 四文档 grep `stage-14`/`22 → 19 → 17`/`IGNORECASE` 一致 |
| DC-5 | 术语一致（annotation / marker / casefold / 回边） | ✅ | 四文档互查 |
| DC-6 | P-083 订正双落点（IMPL §5 + DESIGN §8）均有回边声明 | ✅ | DESIGN §2.7；IMPL §1 行 3-5 |

## 2. 功能验收

| # | 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|---|---|---|---|---|---|
| F-1 | `count` 缺失时 `n` 省略 | `test_annotations_omit_n_when_count_missing` | `"n" not in entry` | ✅ | pytest |
| F-2 | 版本化 stage-14 场景 annotation 写 live 目录 | `test_annotations_write_live_stage14_dir` | 落盘 `stage-14/claim_annotations.json`；locator 指向 `stage-14_v2/...` | ✅ | pytest |
| F-3 | 论文回退 19 优先于 17 | `test_export_prefers_revised_over_draft` | `paragraph_refs == ["§Revised"]` | ✅ | pytest |
| F-4 | 大写标记 casefold 提取 | `test_extract_markers_casefolds_uppercase` | `[C-11111111]` → `c-11111111` | ✅ | pytest |
| F-5 | 缩进代码块跳过 | `test_extract_markers_skips_indented_code_block` | 块内 marker 不提取，块外正常 | ✅ | pytest |
| F-6 | 未闭合行内码截断 | `test_extract_markers_skips_unclosed_inline_code` | 跨度内不提取，跨度前 marker 正常 | ✅ | pytest |
| F-7 | P-083 IMPL §5 计数订正 19 | 读码 + P-083 session 回边行 | 写 19（14+2+3）+ P-094 注记 | ✅ | git diff |
| F-8 | P-083 DESIGN §8 顺序订正 | 读码 + 同上回边 | `22 → 19 → 17` + 增补注记 | ✅ | git diff |
| F-9 | CI extras mcp 版本断言 | yml 读码 + 本地探针 | `importlib.metadata` 元组比较 `>= (2,1)` | ✅ | 本机 2.3.0 探针 |

## 3. 接口验收

| # | 接口 | 通过条件 | 状态 |
|---|---|---|---|
| API-1 | `annotations_from_stage14(run_dir)` | 签名/返回不变；`n` 有值才写；落盘恒 live | ✅ |
| API-2 | `extract_claim_markers(text)` | 签名/返回不变；键恒小写；缩进块/行内码形态跳过 | ✅ |
| API-3 | `export_claim_labels(run_dir)` | 段引取自修订稿（final 缺失时） | ✅ |
| API-4 | `verify_claim_trace(run_dir, *, require_export)` | 判定语义零变化；未知大写 id 仍判红 | ✅ |
| API-5 | `verify_claim_digests(run_dir, *, annotations)` | 默认读 live annotation；版本化 locator 可复算 | ✅ |

## 4. 不变式验收（DESIGN §6）

| # | 不变式 | 验证方法 | 状态 |
|---|---|---|---|
| INV-1 | 五接口签名与错误码不变 | 读码 diff | ✅ |
| INV-2 | 提取修复单向（只减 marker） | F-5/F-6 用例 + `unknown_claim_marker` 用例保持 | ✅ |
| INV-3 | `MARKER_PLACEHOLDER` 不变式 | 既有 `test_stage17_prompt_example_is_non_matching_placeholder`（IGNORECASE 下仍不匹配） | ✅ |
| INV-4 | marker 键恒小写 | F-4 用例 | ✅ |
| INV-5 | `n`/`ci` 有值才写；`n_seeds` 覆盖不变 | F-1 用例 + 既有 condition 用例保持 | ✅ |
| INV-6 | 既有套件零回归 | 双环境四文件 124 passed + 十文件回归 | ✅ |

## 5. 错误处理验收

| # | 场景 | 行为 | 状态 |
|---|---|---|---|
| E-1 | 大写未知 id `[C-DEADBEEF]` | `unknown_claim_marker` → trace 判红（比静默更严格） | ✅ |
| E-2 | `metrics_summary` 条目缺 `count` | annotation 无 `n`，不伪造样本量 | ✅ |
| E-3 | 仅版本化 stage-14 | annotation 落 live `stage-14/`，Stage 20/23 可读 | ✅ |
| E-4 | 未闭合围栏 + 缩进块混合 | 状态机互不误翻转（F-5 用例含混合形态） | ✅ |

## 6. ADD 审计（忠实度）

### 6.1 四阶段

| # | 阶段 | 检查内容 | 结果 | 状态 |
|---|---|---|---|---|
| ADD-1 | Phase 1 完整性 | DESIGN §1 九项修复全部有实施 | 零缺失 | ✅ |
| ADD-2 | Phase 2 忠实度 | F-9 断言形式按 RESEARCH R-7 订正（非 P-093 原文）——已显式登记非静默偏离 | 零静默偏离 | ✅ |
| ADD-3 | Phase 3 必要性 | 每项修复均挂 P-084/P-086/P-083/P-093 编号 | 零无据行为 | ✅ |
| ADD-4 | Phase 4 语义 | 全部单向 fail-closed；E-1 比 P-084 基线更严格 | 意图一致 | ✅ |

### 6.2 审计发现（诚实结果列）

- 无新增缺口；O-4/O-1 保持登记遗留（DESIGN §7 显式声明）。

## 7. 双环境与回归（Step 9-10）

| # | 检查 | 结果 |
|---|---|---|
| R-1 | 3.13.5 四文件套件 | 125 passed |
| R-2 | 3.11.15 四文件套件 | 125 passed |
| R-3 | M1-M5 十文件回归 | 199 passed |
| R-4 | 扩展回归组（rc_executor 等十文件） | 348 passed |
| R-5 | 门禁链（DC/step-gate/step-enforce/pre-commit） | 全绿 |
| R-6 | P-083 session 回边（seq 8-9） | step-gate legacy 一致；rebind_reason 在位 |

## 8. 遗留登记

| # | 项 | 处置 |
|---|---|---|
| U-1 | P-084 O-4：论文文本 live-or-latest | 登记遗留（超本批裁决范围） |
| U-2 | P-086 O-1：标题行内标记静默丢弃 | 记录性观察项，维持 |
| U-3 | F-9 CI 断言的实际生效 | 由 GitHub Actions 实跑确证（本批本地探针） |

---
