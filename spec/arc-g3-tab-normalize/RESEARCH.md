---
id: arc-g3-tab-normalize-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-14
depends: [arc-g3-indent-context, arc-g3-indent-context-review]
upstream: arc-g3-indent-context-review
---

# 调研：行首 tab 前缀缩进判定补全（P-098，收敛 P-097 O-1）

> **Feature**：P-098，修复 [P-097 复评](../../docs/arc-g3-indent-context-review-20261113.md) §4 O-1（用户裁决先行小修，G4 前置）。
> **Spec 步骤**：Step 1-2（T1 小批）。
> **结论先行**：O-1 根因是 `_INDENT_CODE_RE = ^(?:\t| {4,})\S` 中 tab 分支要求**tab 紧跟非空白**——tab 后跟空白（`\t\t`/`\t `/`\t \t`，CommonMark 展开 ≥5 列）整体不匹配 → 不判代码 → 示例被多提取。修复 = tab 分支改为 `\t[ \t]*`（tab 后跟任意空白序列再跟非空白），**单处正则改动**；行首 tab 起始的行缩进必然 ≥4 列（tab 在第 0 列展开至列 4），故该分支穷尽全部 tab 缩进形态。

## 1. 缺陷回源（P-097 探针 T2/T3/T4）

| 输入 | CommonMark 列数 | 实测 | 应为 |
|---|---|---|---|
| `\t\t[c-…]` | 8 | 提取（误） | 跳过 |
| `\t [c-…]` | 5 | 提取（误） | 跳过 |
| `\t \t[c-…]` | 8 | 提取（误） | 跳过 |
| `\t[c-…]`（T1） | 4 | 跳过 ✅ | 跳过 |

**方向**：多提取 → 示例 id 若未导出将触发 `unknown_claim_marker` 误阻断（**fail-closed 假阳性**，非漏检）；非 P-096 回归（P-094 及之前同形态行为相同），属 P-085 D-1「示例误阻断」家族最后残留。

## 2. 读码取证（E3）

- `_INDENT_CODE_RE`（claim_spine.py L34）：`^(?:\t| {4,})\S`——`\t` 分支的 `\S` 紧邻要求使 tab+空白前缀整体失配。
- `_NESTED_LIST_RE`（L36）：同前缀结构，`\t\t- x`（tab 后跟 tab 再列表标记）不匹配 → 修复后随 `_INDENT_CODE_RE` 判代码，与 CommonMark 一致（8 列处列表标记无外层列表时非列表项）。
- `extract_claim_markers` 状态机（L337-345）：开块判定只依赖 `_INDENT_CODE_RE`/`_NESTED_LIST_RE`/`prev_kind`，正则修正即可生效，**零状态机改动**。

## 3. 方案对比

| 方案 | 做法 | 取舍 | 判定 |
|---|---|---|---|
| R-1 正则修正 | `\t` 分支 → `\t[ \t]*`（tab 后任意空白再 `\S`） | 单处改动；穷尽行首 tab 形态（行首 tab ≥4 列） | **采纳** |
| R-2 行首归一化 | 循环内把 raw 的行首 tab 展开为 4 空格 | 改动更大；影响 `_FENCE_RE`/`_NESTED_LIST_RE` 的输入形态，回归面大 | 拒绝 |
| R-3 仅加 T2 形态 | `\t\t` 单独分支 | 打地鼠，`\t `/`\t \t` 仍漏 | 拒绝 |

## 4. 幻觉抑制审查（Step 2 Review）

| 声明 | 来源 | 验证方式 | 状态 |
|---|---|---|---|
| T2/T3/T4 三形态现状 | P-097 探针 tab 扫描 | 复评报告 §2.2（一手） | ✅ E2 |
| 行首 tab 必 ≥4 列 | CommonMark 0.31.2 §1.1（tab stop） | 规范条文 | ✅ T1 |
| 单处正则可生效 | 读码状态机 | 本批 §2 | ✅ E3 |
| `\t\t- x` 判代码符合 CommonMark | 8 列列表标记无外层列表非列表项 | 规范 §5.2（列表项缩进 0-3） | ✅ T1 |

## 5. 对设计的输入

1. 修复仅动 `_INDENT_CODE_RE`；`_NESTED_LIST_RE` 保持原样（`\t- x` 单 tab 列表项 M1d 语义保持；`\t\t- x` 修复后正确判代码）。
2. 回归护栏：M1d（tab 列表项提取）、T1（单 tab 代码跳过）、T5（行内 tab 不受影响）。
3. 修复方向：新增跳过（示例区域）= 与 P-085 示例跳过同向，fail-closed 收敛。

---
