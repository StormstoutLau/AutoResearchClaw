---
id: arc-g3-indent-context-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-13
depends: [arc-g3-indent-context-RESEARCH]
upstream: arc-g3-indent-context-RESEARCH
---

# 设计：上下文感知的缩进代码块判定（P-096）

> 基于 [RESEARCH.md](RESEARCH.md) 与 [P-095 复评](../../docs/arc-g3-p3-cleanup-review-20261113.md) D-1。目标：消除 fail-open 回归，保持 P-085/P-094 既有语义零回退。

## 1. 修复范围

| # | 缺陷 | 修复 | 出口 |
|---|---|---|---|
| F-1 | 4 空格嵌套 bullet 内真实标记被丢弃 | 行首列表标记（`-`/`*`/`+`/`1.`）不判缩进代码块 | A5 |
| F-2 | 4 空格数字列表嵌套被丢弃 | 同上（覆盖有序标记） | J8 |
| F-3 | 悬挂缩进续行被丢弃 | 缩进代码块不得中断段落：前一非空行为正文/列表且无空行间隔 → 按正文处理 | A6 |
| F-4 | tab 缩进代码块内示例被提取 | tab 等价 4 空格（`^\t` 纳入缩进判定） | A1 |
| F-5 | 下游静默（K1） | F-1/F-2/F-3 生效后，嵌套列表中的未发布 claim 引用恢复报 `unpublished_claim_cited` | K1 |
| F-6 | P-094/P-085 语义回退 | 回归护栏：6 + 4 项既有用例零改动通过 | V-6 |

## 2. 判定算法（`extract_claim_markers`）

### 2.1 新增正则

```python
_INDENT_CODE_RE = re.compile(r"^(?:\t| {4,})\S")          # tab 等价 4 空格
_NESTED_LIST_RE = re.compile(r"^(?:\t| {4,})(?:[-*+]|\d{1,9}[.)])\s+\S")
_LIST_ITEM_RE   = re.compile(r"^ {0,3}(?:[-*+]|\d{1,9}[.)])\s+\S")
```

### 2.2 逐行状态机（替换 P-094 §2.5）

维护 `prev_kind ∈ {None, "blank", "para", "list", "heading", "fence_close", "code"}`：

1. 空行 → `prev_kind = "blank"`，跳过（缩进块内空行不断块，状态 `in_indent` 不变）。
2. `in_fence` → 仅识别围栏闭合行（闭合置 `in_fence=False, prev_kind="fence_close"`），其余跳过。
3. 围栏开行 → `in_fence=True, in_indent=False, prev_kind="fence_close"`，跳过。
4. `_INDENT_CODE_RE` 命中（4+ 空格或 tab 起首）：
   - 若同时命中 `_NESTED_LIST_RE` → **不判代码**（列表项内容），落到正文处理（F-1/F-2）；
   - 否则若 `prev_kind ∈ {None, "blank", "heading", "fence_close"}` → `in_indent=True, prev_kind="code"`，跳过（真代码块）；
   - 否则（`prev_kind ∈ {"para", "list", "code"}`）→ **段落/列表续行**，落到正文处理（F-3）。
5. 非缩进行 → `in_indent=False`；标题行 → 更新 `current`，`prev_kind="heading"`，跳过。
6. 正文行 → 先 `_strip_inline_code`，提取标记；随后 `_LIST_ITEM_RE` 命中则 `prev_kind="list"`，否则 `prev_kind="para"`。

### 2.3 语义对照（迁移表）

| 输入形态 | P-094 行为 | P-096 行为 | 方向 |
|---|---|---|---|
| 空行后 `    [c-…]` 裸行 | 跳过 | 跳过（`prev_kind=blank`） | 不变 |
| 标题后紧邻 `    [c-…]` | 跳过 | 跳过（`heading`） | 不变 |
| 围栏关闭后 `    [c-…]` | 跳过 | 跳过（`fence_close`） | 不变 |
| 4 空格 `    - nested [c-…]` | 跳过 | **提取** | fail-closed 收紧（F-1） |
| 4 空格 `    2. nested [c-…]` | 跳过 | **提取** | 同上（F-2） |
| 段落行后 `    cont [c-…]`（无空行） | 跳过 | **提取** | 同上（F-3） |
| tab `\t[c-…]`（空行后） | 提取 | **跳过** | 示例跳过（F-4） |
| 缩进块内 `    - x`（块已开） | 跳过 | 跳过（`in_indent` 状态优先） | 不变（A4 保护） |

### 2.4 不变的部分

- `CLAIM_MARKER_RE`、`MARKER_PLACEHOLDER`、`_strip_inline_code`、`_paper_text`、annotation/export/trace/digest 全部语义。
- 围栏优先于缩进、`in_indent` 由低缩进非空行关闭、空白行不断块。

## 3. 数据流

```text
行 → [空行] → prev=blank
   → [围栏] → in_fence / fence_close
   → [4+空格|tab] ─┬─ 列表标记 → 正文提取（F-1/F-2）
                   ├─ prev ∈ {start,blank,heading,fence_close} → 代码块跳过
                   └─ prev ∈ {para,list,code} → 正文提取（F-3）
   → [标题] → current 更新
   → [正文] → 行内码剔除 → 提取 → prev=para|list
```

## 4. 决策表（含拒绝方案）

| # | 决策 | 依据 | 拒绝方案与理由 |
|---|---|---|---|
| D-1 | 三规则并用（列表排除 + tab 等价 + 不中断段落） | RESEARCH §4 S-3 | 拒绝 S-1/S-2（覆盖不全）；拒绝 S-4（依赖膨胀） |
| D-2 | 用「前一非空行类型」而非完整块解析 | 实现面 ~20 行、纯 helper 定位 | 拒绝引入 markdown 解析器 |
| D-3 | 列表标记排除仅作用于**开块判定** | 块内行由 `in_indent` 优先，A4 伪标题用例不受影响 | 拒绝同时改块内逻辑（会破坏「块内 `- x` 仍为代码」） |
| D-4 | tab 仅作为**缩进**等价，不改行内码/围栏语义 | 最小变更 | 拒绝全局 tab 展开（污染行内码判定） |
| D-5 | 不修 P-095 O 表各项 | 用户裁决范围 = D-1 | 拒绝顺手扩面 |

## 5. 验收映射

| 验收 ID | 落点 |
|---|---|
| F-1 | `test_extract_markers_keeps_nested_bullet_marker` |
| F-2 | `test_extract_markers_keeps_nested_ordered_marker` |
| F-3 | `test_extract_markers_keeps_hanging_indent_continuation` |
| F-4 | `test_extract_markers_skips_tab_indented_code_block` |
| F-5 | `test_export_reports_unpublished_claim_in_nested_list` |
| F-6 | 既有 25 项 `test_claim_spine` + 套件零回归 |
| 迁移表 | `test_extract_markers_skips_indented_block_after_heading`（标题后裸缩进行仍跳过） |

## 6. 不变式

- I-1 五接口签名、错误码、返回结构不变。
- I-2 新增提取（A5/J8/A6/K1）为 fail-closed 方向；新增跳过仅 tab 缩进块（与 P-085 示例跳过同向）。
- I-3 围栏判定仍先于缩进判定（P-085 四反引号/围栏内伪标题用例保持）。
- I-4 空行不断块、低缩进非空行闭块（P-094 A7/A3 用例保持）。
- I-5 `MARKER_PLACEHOLDER` 与 IGNORECASE 语义不变。
- I-6 marker 键恒小写。

## 7. 非目标

- 不修 P-095 O-1..O-7（派生视图边界、标题内标记、bool/float count、空修订稿、HTML 注释、CI 版本边界）。
- 不引入 Markdown 解析依赖。
- 不改变 `_strip_inline_code` 行为。

---
