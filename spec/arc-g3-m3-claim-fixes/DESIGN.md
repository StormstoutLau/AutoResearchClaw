---
id: arc-g3-m3-claim-fixes-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-12
depends: [arc-g3-m3-claim-fixes-RESEARCH, arc-g3-m3-review]
upstream: arc-g3-m3-claim-fixes-RESEARCH
---

# 设计：G3 M3 D-1 修复

> 基于 [RESEARCH.md](RESEARCH.md) 与 [P-084 复核](../../docs/arc-g3-m3-review-20261112.md)。本批只修「示例标记误阻断」及其附带归属错位，不动判定内核。

## 1. 修复范围

| # | 缺陷 | 修复 | 出口 |
|---|---|---|---|
| D-1a | Stage 17 提示词示例为合法 hex id | 改用非匹配占位符 `MARKER_PLACEHOLDER` | 提示词不再注入可被提取的示例 |
| D-1b | 提取器不跳过代码围栏/行内代码 | 逐行扫描 + 围栏开关 + 行内代码剔除 | 示例区域不产生 marker |
| D-2（附带） | 标题按块末归属正文 | 标题即时生效，仅作用于其后行 | 段引归属正确 |
| ③ | 未知 marker 降 warning | **不采纳**（保持 fail-closed） | 真实未知 hex id 仍阻断 |

## 2. 接口与常量

### 2.1 `MARKER_PLACEHOLDER`

```python
MARKER_PLACEHOLDER = "[c-xxxxxxxx]"
```

- 定义在 `researchclaw/evidence/claim_spine.py`（marker 语法的单一真值源）。
- 不变式：`CLAIM_MARKER_RE.findall(MARKER_PLACEHOLDER) == []`（`x` 不属于 `[0-9a-f]`）。
- Stage 17 提示词通过 `f"e.g. {MARKER_PLACEHOLDER}"` 引用，**禁止**再写任何合法 hex 示例。
- 提示词追加一句「never copy the placeholder or invent an id」。

### 2.2 `extract_claim_markers`（签名不变）

```python
def extract_claim_markers(text: str) -> dict[str, list[str]]
```

算法（逐行）：

1. 行首匹配 `^\s*(```|~~~)` → 翻转 `in_fence`，该行跳过（围栏标记行不参与正文）。
2. `in_fence=True` → 整行跳过（含围栏内的伪标题与示例 id）。
3. 标题行 `^#{1,6}\s+` → 立即更新 `current`，该行跳过。
4. 其余行：用 `` `[^`]*` `` 剔除行内代码跨度，再提取 `CLAIM_MARKER_RE`。
5. 每个 `claim_id` 的 `refs` 去重且保持首次出现顺序。
6. 无标题前 → `§Preamble`；编号标题 → `§<number>`；其余 → `§<title>`。

### 2.3 不变的部分

- `CLAIM_MARKER_RE`、`_CLAIM_ID_RE`、错误码 `E_CLAIM_TRACE_MISMATCH` / `E_CLAIM_DIGEST_MISMATCH`。
- `export_claim_labels` / `verify_claim_trace` / `verify_claim_digests` 的签名与判定语义。
- Stage 22/23 接线与 `require_export` 口径。

## 3. 数据流

```text
Stage 17 prompt ── e.g. [c-xxxxxxxx]（不匹配）──> LLM 正文
                                                   │
                                        代码围栏/行内代码示例 ──> 跳过
                                                   │
                                          真实 [c-xxxxxxxx] ──> marker
                                                   │
Stage 22 export ──> paragraph_refs（标题即时归属）
                                                   │
Stage 23 trace ──> 未知 hex id 仍判红；占位符/围栏示例不判红
```

## 4. 决策表（含拒绝的替代方案）

| # | 决策 | 依据 | 拒绝的方案与理由 |
|---|---|---|---|
| D-1 | 提示词示例改非 hex 占位符 | RESEARCH R-1/R-4 | 拒绝保留合法示例：LLM 会复述，根因不除 |
| D-2 | 提取器逐行 + 围栏/行内代码跳过 | RESEARCH R-2；P-084 X-3 | 拒绝只改提示词：覆盖不了模型自行写出的代码示例 |
| D-3 | 标题即时生效（D-2 附带修复） | P-084 D-2 | 拒绝保留块级归属：逐行扫描已自然修复，无额外成本 |
| D-4 | 不采纳 ③（unknown marker 降 warning） | RESEARCH R-5 | 拒绝弱化 fail-closed：会放行幻觉 hex id |
| D-5 | 占位符常量单点定义 | 词表单一真值源纪律 | 拒绝两处字面量：提示词与测试会漂移 |

## 5. 验收映射

| 验收 ID | 落点 |
|---|---|
| P-084 D-1 | F-1/F-2/F-3/F-4 |
| P-084 D-2 | F-5 |
| fail-closed 保持 | F-6 |
| A3-1 不回退 | F-6 + 既有 118 项套件 |

## 6. 不变式

- I-1 不修改 `CLAIM_MARKER_RE` 与字面 id 规则；占位符只是不匹配。
- I-2 不修改 export/trace/Stage 23 的判定与错误码。
- I-3 围栏/行内代码的跳过是单向的（只会减少 marker，不会新增）。
- I-4 既有空白分块语义的测试保持通过（`test_extract_markers_maps_sections`）。
- I-5 真实未知 hex id 仍判红（F-6）。

## 7. 非目标

- 不检测「未标记的数值断言」（P-083 U-1）。
- 不处理多反引号行内代码（U-2）。
- 不把未知 marker 降级（③ 未采纳）。
- 不修复 P-083 O-3 读数偏差（留待后续批次，见 CHECKLIST §11）。
