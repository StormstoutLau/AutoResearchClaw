---
id: arc-g3-tab-normalize-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-14
depends: [arc-g3-tab-normalize-IMPLEMENTATION]
upstream: arc-g3-tab-normalize-IMPLEMENTATION
---

# 检查清单：行首 tab 前缀缩进判定补全（P-098）

## 1. 文档一致性（Step 8）

| # | 检查项 | 状态 | 说明 |
|---|---|---|---|
| DC-1 | RESEARCH 结论在 DESIGN 被使用（R-1→D-1、规则回源→§2） | ✅ | DESIGN §4 挂来源 |
| DC-2 | DESIGN 模块在 IMPLEMENTATION 有对应实施 | ✅ | §2 正则 ↔ §3 记录 |
| DC-3 | IMPLEMENTATION 功能点在 CHECKLIST 有验收项 | ✅ | F-1..F-4 |
| DC-4 | 无文档间矛盾（正则、迁移表、不改清单） | ✅ | 四文档互查 |
| DC-5 | P-097 O-1 修复范围显式（O-2 非目标） | ✅ | DESIGN §7 |

## 2. 功能验收

| # | 验收项 | 测试方法 | 通过条件 | 状态 |
|---|---|---|---|---|
| F-1 | `\t\t`/`\t `/`\t \t` 前缀判代码 | `test_extract_markers_skips_tab_whitespace_prefix` | 三前缀标记均跳过 | ✅ |
| F-2 | `\t\t- [c-…]` 判代码（CommonMark 8 列非列表） | 同用例附加断言 | 跳过 | ✅ |
| F-3 | `\t- [c-…]` tab 列表项保持提取（M1d 护栏） | `test_extract_markers_tab_list_item_stays_list` | 提取 | ✅ |
| F-4 | 既有语义零回退 | 既有 31 项 + 双环境回归 | 全绿 | ✅ |

## 3. 接口与不变式

| # | 项 | 通过条件 | 状态 |
|---|---|---|---|
| API-1 | `extract_claim_markers` 签名/返回不变 | 既有 31 项零改动通过 | ✅ |
| INV-1 | 新增行为全部为示例跳过（零提取新增） | DESIGN §3 迁移表逐行 | ✅ |
| INV-2 | 状态机/围栏/行内码/casefold 语义不变 | 既有用例 | ✅ |

## 4. 回归与门禁

| # | 检查 | 结果 |
|---|---|---|
| R-1 | 3.13.5 四文件套件 | 133 passed |
| R-2 | 3.11.15 四文件套件 | 133 passed |
| R-3 | M1-M5 十文件回归 | 207 passed |
| R-4 | 扩展组（rc_executor 等十文件） | 348 passed |
| R-5 | 门禁链（DC/step-gate/step-enforce/pre-commit） | 待回填 |

## 5. 遗留登记

| # | 项 | 处置 |
|---|---|---|
| U-1 | P-097 O-2（块内深缩进围栏翻转） | 维持登记，另行裁决 |
| U-2 | P-095 O-1..O-7 沿袭项 | 维持登记 |
| U-3 | P-099 复评 | 建议由 DeepSeek 基座执行（本轮实施为 GLM，保持 RULE-5 交叉） |

---
