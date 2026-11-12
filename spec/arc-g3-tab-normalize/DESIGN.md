---
id: arc-g3-tab-normalize-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-14
depends: [arc-g3-tab-normalize-RESEARCH]
upstream: arc-g3-tab-normalize-RESEARCH
---

# 设计：行首 tab 前缀缩进判定补全（P-098）

> 基于 [RESEARCH.md](RESEARCH.md)。单处正则改动，零状态机变化。

## 1. 修复范围

| # | 缺陷（P-097 O-1） | 修复 | 出口 |
|---|---|---|---|
| F-1 | `\t\t` 前缀不判代码（T2） | tab 分支改 `\t[ \t]*` | T2 |
| F-2 | `\t ` 前缀不判代码（T3） | 同上 | T3 |
| F-3 | `\t \t` 前缀不判代码（T4/M2h） | 同上 | T4 |
| F-4 | 既有 tab 语义回退 | 护栏：单 tab 代码跳过、tab 列表项提取、行内 tab 不受影响 | T1/M1d/T5 |

## 2. 正则变更

```python
# P-096（现状）
_INDENT_CODE_RE = re.compile(r"^(?:\t| {4,})\S")
# P-098（目标）
_INDENT_CODE_RE = re.compile(r"^(?:\t[ \t]*| {4,})\S")
```

- 语义：行首 tab 后跟**任意空白序列**再跟非空白 → 缩进代码块候选（行首 tab 起始缩进必 ≥4 列，穷尽全部 tab 形态）。
- `_NESTED_LIST_RE` **不改**：`\t- x`（M1d）保持列表内容提取；`\t\t- x` 随 `_INDENT_CODE_RE` 修复后判代码（8 列列表标记无外层列表非列表项，CommonMark §5.2）。
- `_LIST_ITEM_RE`、`_FENCE_RE`、`_strip_inline_code`、状态机零改动。

## 3. 行为迁移表

| 输入形态 | P-096 行为 | P-098 行为 | 方向 |
|---|---|---|---|
| `\t[c-…]`（T1） | 跳过 | 跳过 | 不变 |
| `\t\t[c-…]`（T2） | 提取 | **跳过** | 示例跳过（fail-closed 收敛） |
| `\t [c-…]`（T3） | 提取 | **跳过** | 同上 |
| `\t \t[c-…]`（T4） | 提取 | **跳过** | 同上 |
| `\t- [c-…]`（M1d） | 提取 | 提取 | 不变（列表内容） |
| `\t\t- [c-…]` | 提取 | **跳过** | 8 列非列表 → 代码（CommonMark 对齐） |
| `x\t[c-…]`（T5） | 提取 | 提取 | 不变（非行首缩进） |
| 4/8 空格（T6/T7） | 跳过 | 跳过 | 不变 |

## 4. 决策表（含拒绝方案）

| # | 决策 | 依据 | 拒绝方案与理由 |
|---|---|---|---|
| D-1 | 单处正则修正（R-1） | RESEARCH §3 | 拒绝 R-2（回归面大）；拒绝 R-3（打地鼠） |
| D-2 | `_NESTED_LIST_RE` 不改 | M1d 语义保持最小化 | 拒绝同步加 `[ \t]*`（`\t\t- x` 应判代码，加了反而错） |
| D-3 | 不动状态机与围栏 | DESIGN §2.4 不变式 | 拒绝顺手改 `_FENCE_RE`（O-2 另行裁决） |

## 5. 验收映射

| 验收 ID | 落点 |
|---|---|
| F-1/F-2/F-3 | `test_extract_markers_skips_tab_whitespace_prefix`（三前缀参数化于一用例） |
| F-4 | `test_extract_markers_tab_list_item_stays_list`（M1d）+ 既有 31 项零回退 |
| 迁移表 | E2 对照（P-097 tab 扫描 7 形态全表） |

## 6. 不变式

- I-1 五接口签名、错误码、返回结构不变。
- I-2 本批新增行为全部为「示例区域跳过」（与 P-085 示例跳过同向），零提取新增。
- I-3 `MARKER_PLACEHOLDER`、IGNORECASE、casefold、行内码截断语义不变。
- I-4 状态机 `prev_kind`/`in_indent`/`in_fence` 语义不变。

## 7. 非目标

- 不修 O-2（块内深缩进围栏翻转，另行裁决）。
- 不改 `_NESTED_LIST_RE`/`_FENCE_RE`/`_strip_inline_code`。
- 不做完整 tab stop 展开。

---
