---
id: arc-g3-indent-context-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-13
depends: [arc-g3-indent-context-IMPLEMENTATION]
upstream: arc-g3-indent-context-IMPLEMENTATION
---

# 检查清单：上下文感知的缩进代码块判定（P-096）

## 1. 文档一致性（Step 8）

| # | 检查项 | 状态 | 说明 |
|---|---|---|---|
| DC-1 | RESEARCH 结论在 DESIGN 被使用（S-3→D-1、规则表→§2.2） | ✅ | DESIGN §4 挂来源 |
| DC-2 | DESIGN 模块在 IMPLEMENTATION 有对应实施 | ✅ | DESIGN §2 ↔ IMPL §1/§4 |
| DC-3 | IMPLEMENTATION 功能点在 CHECKLIST 有验收项 | ✅ | F-1..F-6 |
| DC-4 | 无文档间矛盾（正则、状态集、迁移表方向） | ✅ | 四文档互查 |
| DC-5 | 术语一致（prev_kind / 迁移表 / fail-closed 方向） | ✅ | |

## 2. 功能验收

| # | 验收项 | 测试方法 | 通过条件 | 状态 |
|---|---|---|---|---|
| F-1 | 4 空格嵌套 bullet 内真实标记被提取 | `test_extract_markers_keeps_nested_bullet_marker` | 两 id 均在 `§R` | ✅ |
| F-2 | 数字列表嵌套被提取 | `test_extract_markers_keeps_nested_ordered_marker` | 两 id 均在 `§R` | ✅ |
| F-3 | 悬挂缩进续行被提取 | `test_extract_markers_keeps_hanging_indent_continuation` | `c-11111111` 在 `§R` | ✅ |
| F-4 | tab 缩进代码块被跳过 | `test_extract_markers_skips_tab_indented_code_block` | 仅块外标记 | ✅ |
| F-5 | 嵌套列表中的未发布 claim 引用报错 | `test_export_reports_unpublished_claim_in_nested_list` | `unpublished_claim_cited` | ✅ |
| F-6 | 迁移护栏：标题后裸缩进行仍跳过 | `test_extract_markers_skips_indented_block_after_heading` | 仅块外标记 | ✅ |

## 3. 接口与不变式

| # | 项 | 通过条件 | 状态 |
|---|---|---|---|
| API-1 | `extract_claim_markers` 签名/返回不变 | 读码 + 既有 25 项 | ✅ |
| INV-1 | 围栏优先于缩进（P-085 用例） | 既有用例零改动通过 | ✅ |
| INV-2 | 空行不断块、低缩进闭块（A7/A3） | 既有用例 | ✅ |
| INV-3 | 占位符 + IGNORECASE 语义不变 | 既有用例 | ✅ |
| INV-4 | 新增提取为 fail-closed、新增跳过仅 tab | DESIGN §2.3 表逐项 | ✅ |

## 4. 回归与门禁

| # | 检查 | 结果 |
|---|---|---|
| R-1 | 3.13.5 四文件套件 | 131 passed |
| R-2 | 3.11.15 四文件套件 | 131 passed |
| R-3 | M1-M5 十文件回归 | 205 passed |
| R-4 | 扩展组（rc_executor 等十文件） | 348 passed |
| R-5 | 门禁链（DC/step-gate/step-enforce/pre-commit） | 全绿（digest_bound=2） |

## 5. 遗留登记

| # | 项 | 处置 |
|---|---|---|
| U-1 | P-095 O-1..O-7 | 维持登记（非本批范围） |
| U-2 | 行级启发式未覆盖形态（列表项内 6+ 空格续行等） | DESIGN §6 显式声明 |
| U-3 | P-097 复评 | 建议由 GLM 基座执行（本轮实施为 DeepSeek，保持 RULE-5 交叉） |

---
