---
id: arc-g3-p3-cleanup-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-13
depends: [arc-g3-p3-cleanup-RESEARCH, arc-g3-m3-claim-spine, arc-g3-m3-claim-fixes]
upstream: arc-g3-p3-cleanup-RESEARCH
---

# 设计：G3 遗留 P3 清理批（P-094）

> 基于 [RESEARCH.md](RESEARCH.md)。全部修复为**单向 fail-closed**方向（只减 marker / 只省字段 / 只订正顺序），零判定内核改动；错误码与接口签名不变。

## 1. 修复范围

| # | 来源 | 缺陷 | 修复 | 出口 |
|---|---|---|---|---|
| F-1 | P-084 D-3 | `count` 缺失时 annotation 伪造 `n=1` | `n` 仅当 `count` 为正整数时写入，否则省略 | 与 `ci` 缺省口径一致 |
| F-2 | P-084 D-4 | 版本化 stage-14 场景 annotation 写入 `stage-14_v2/`，Stage 20/23 读 live 静默缺席 | `target_dir` 固定 `run_dir/stage-14`；`evidence_locator` 仍指向实际读取的 summary | 写侧一行闭环（P-083 DESIGN §5.6 原口径） |
| F-3 | P-084 D-5 | `_paper_text` 回退顺序 22→17→19 取较旧草稿 | 顺序改 `22 → 19 → 17` | 修订稿必新于草稿 |
| F-4 | P-084 D-6 | 大写 `[C-…]` 静默忽略 | `CLAIM_MARKER_RE` 加 `re.IGNORECASE`，提取键 `.lower()` 归一 | 真实未知大写 id 仍判红（fail-closed 保持） |
| F-5 | P-086 O-2 | 4 空格缩进代码块内 marker 被提取 | 缩进块状态机：≥4 空格非空行开块、空行不断块、低缩进非空行闭块 | 与围栏状态独立（围栏判定先行） |
| F-6 | P-086 O-3 | 未闭合行内码内 marker 被提取 | 成对剔除后余反引号为奇数 → 从最后一个反引号截断至行尾 | 未闭合跨度内全按行内码处理 |
| F-7 | P-083 O-3 | P-083 IMPLEMENTATION §5 计数 18 ≠ 实 19 | 订正为 19（14+2+3）；走 P-083 session 受控回边 | 登记面与 E1 计数一致 |
| F-8 | P-084 D-5 设计面 | P-083 DESIGN §8 顺序 22→17→19 缺口 | 订正为 22→19→17（与 F-3 同一回边） | 设计与实现一致 |
| F-9 | P-093 §6.3 | CI extras 无 mcp 版本断言 | extras job 增 `importlib.metadata` 元组比较断言 `>= (2,1)` | P-093 建议形式的订正落地（`mcp` 无 `__version__` 属性） |

## 2. 逐项设计

### 2.1 F-1：`n` 缺省省略

```python
count = metric_value.get("count") if isinstance(metric_value, dict) else None
annotation: dict[str, Any] = {"metric": ..., "value": mean, "source": "stage14", "evidence_digest": ...}
if isinstance(count, int) and count > 0:
    annotation["n"] = int(count)
```

- 条件分支的 `n_seeds` 覆盖逻辑不变（正整数才写）。
- 下游消费面：Stage 20 gate 只判 annotation 存在与否，不读 `n`；export/trace 不读 `n` → 省略零下游影响。

### 2.2 F-2：annotation 固定写 live 目录

```python
target_dir = run_dir / "stage-14"
```

- `evidence_locator` 仍取 `summary_path` 相对路径（版本化场景指向 `stage-14_v2/...`，digest 可复算原文件）。
- `verify_claim_digests` 默认读 `stage-14/claim_annotations.json`（live），与写侧对齐。
- Stage 14 impl（`_analysis.py`）按 `stage_dir / "claim_annotations.json"` 登记 artifact——live 目录即 `stage_dir`，接线零改动。

### 2.3 F-3/F-8：论文回退顺序

```python
for relative in ("stage-22/paper_final.md", "stage-19/paper_revised.md", "stage-17/paper_draft.md"):
```

- [P-083 DESIGN §8](../arc-g3-m3-claim-spine/DESIGN.md) 第 2 步同步订正（F-8，同一受控回边）。
- P-084 O-4（论文文本 live-or-latest）**非本批范围**，登记遗留。

### 2.4 F-4：大写标记 casefold

```python
CLAIM_MARKER_RE = re.compile(r"\[(c-[0-9a-f]{8})\]", re.IGNORECASE)
```

- `extract_claim_markers` 对捕获组 `.lower()` 后入键；marker 键恒小写，与 `CLAIM_ID_RE`（claim id 严格小写）口径衔接。
- 占位符不变式保持：`x`/`X` ∉ `[0-9a-fA-F]` → `CLAIM_MARKER_RE.findall(MARKER_PLACEHOLDER) == []` 仍成立。
- 大写未导出 id 仍走 `unknown_claim_marker` → trace 判红，fail-closed 未弱化。
- `CLAIM_ID_RE`/stage-09 claim id 生成侧不改。

### 2.5 F-5：缩进代码块状态机

逐行扫描新增 `in_indent` 状态，判定顺序：

1. 空白行 → 状态保持，跳过（缩进块内空行不断块）。
2. `in_fence` → 仅识别围栏闭合行（闭合则 `in_fence=False`），其余跳过。
3. 围栏开行（`_FENCE_RE`）→ `in_fence=True; in_indent=False`，跳过。
4. `^ {4,}\S` → `in_indent=True`，跳过。
5. 其余非空行 → `in_indent=False`；标题判定 → 即时更新 ref；正文提取。

- 单向性：缩进块跳过只会减少 marker，不新增。
- 围栏判定先行保证既有围栏语义（P-085 X-4 四反引号用例）零回归。

### 2.6 F-6：未闭合行内码截断

```python
def _strip_inline_code(line: str) -> str:
    cleaned = _INLINE_CODE_RE.sub("", line)
    if cleaned.count("`") % 2 == 1:
        cleaned = cleaned[: cleaned.rfind("`")]
    return cleaned
```

- 奇数余反引号 = 存在未闭合跨度，其开启位置为最后一个反引号（前序反引号已两两成对）→ 截断至行尾。
- 单向性：截断只会减少 marker。

### 2.7 F-7/F-8：P-083 订正与受控回边

- [IMPLEMENTATION §5](../arc-g3-m3-claim-spine/IMPLEMENTATION.md)：`新增 18 项` → `新增 19 项`（`test_stage_claim_hooks.py` 2→3），注明 P-094 订正来源。
- [DESIGN §8](../arc-g3-m3-claim-spine/DESIGN.md) 第 2 步顺序订正（同 F-3）。
- P-083 session（`specwf-p083-arc-g3-m3-claim-spine.jsonl`）追加 seq 8-9：verify（step_seq=4）+ finalize（step_seq=5，`rebind_reason` + 四文档新 digest）。**新增 digest 以 P-094 批内订正后的最终工作树为准，最后生成**。

### 2.8 F-9：CI mcp 版本断言

```yaml
- name: Assert MCP SDK version (P-094 / P-093 6.3)
  run: |
    python -c "import importlib.metadata as m; v = tuple(int(p) for p in m.version('mcp').split('.')[:2]); assert v >= (2, 1), f'mcp {v} does not satisfy pin >=2.1,<3'; print('mcp OK', v)"
```

- P-093 §6.3 原建议 `mcp.__version__` 不存在（RESEARCH R-7），本批以 `importlib.metadata` 订正落地。

## 3. 数据流

```text
metrics_summary 缺 count ──> annotation 无 n（不再伪造 1）        [F-1]
仅 stage-14_v2/ 存在 ──> annotation 写 stage-14/（live）          [F-2]
paper_final 缺失 ──> 段引取 stage-19 修订稿（不再取 17 草稿）      [F-3]
[C-11111111] ──> 提取为 c-11111111（未导出仍判红）                [F-4]
缩进块 / 未闭合行内码 ──> 示例区域不产生 marker                    [F-5/F-6]
P-083 计数与 DESIGN §8 ──> 订正 + 受控回边                        [F-7/F-8]
CI extras ──> mcp 版本断言（importlib.metadata）                  [F-9]
```

## 4. 决策表（含拒绝的替代方案）

| # | 决策 | 依据 | 拒绝的方案与理由 |
|---|---|---|---|
| D-1 | `n` 省略而非置 null | RESEARCH R-1；DESIGN §4 `ci` 缺省先例 | 拒绝 `null`：引入第三态，下游须判空 |
| D-2 | 只改写侧（annotation 固定 live） | RESEARCH R-2；读取侧已有 live-or-latest | 拒绝读侧兜底：掩盖写侧偏离 |
| D-3 | 顺序一行订正，不做 live-or-latest | RESEARCH R-3；用户裁决范围 | 拒绝扩 O-4：超裁决范围，登记遗留 |
| D-4 | casefold 提取而非文档声明 | RESEARCH R-4 | 拒绝只写文档：静默面仍在 |
| D-5 | 缩进块状态机独立于围栏状态 | RESEARCH R-5 | 拒绝合并状态：围栏语义（P-085 先例）零回归优先 |
| D-6 | 奇数截断 | RESEARCH R-6 | 拒绝配对计数器重写：改动面大且与成对剔除叠加易错 |
| D-7 | CI 断言用 importlib.metadata | RESEARCH R-7（P-093 建议订正） | 拒绝 `mcp.__version__`：属性不存在 |
| D-8 | P-083 两处订正合并一个回边 | 门禁机制（同 feature 单 digest 表） | 拒绝两次回边：同 session 重复回边无增益 |

## 5. 验收映射

| 验收 ID | 落点 |
|---|---|
| F-1 | `test_annotations_omit_n_when_count_missing` |
| F-2 | `test_annotations_write_live_stage14_dir` |
| F-3 | `test_export_prefers_revised_over_draft` |
| F-4 | `test_extract_markers_casefolds_uppercase` |
| F-5 | `test_extract_markers_skips_indented_code_block` |
| F-6 | `test_extract_markers_skips_unclosed_inline_code` |
| F-7/F-8 | P-083 订正 diff + step-gate 回边 + P-094 session finalize digest |
| F-9 | ci.yml diff + 本地 importlib 探针（CI 由 GitHub Actions 实跑） |

## 6. 不变式

- I-1 五接口签名与错误码不变；`consistent` 双平面语义不变。
- I-2 全部提取修复单向（只减 marker）；`unknown_claim_marker` 判红路径保持。
- I-3 `MARKER_PLACEHOLDER` 不变式保持（IGNORECASE 下仍不匹配）。
- I-4 marker 键恒小写（casefold 归一后入键）。
- I-5 annotation `n`/`ci` 均为「有值才写」；条件 `n_seeds` 覆盖逻辑不变。
- I-6 既有 118 项 claim spine 套件与十文件回归零失败（空白分块语义测试保持）。

## 7. 非目标

- 不做论文文本 live-or-latest（P-084 O-4，登记遗留）。
- 不处理标题行内标记（P-086 O-1，记录性观察项）。
- 不把未知 marker 降 warning（P-085 ③ 维持未采纳）。
- 不改 `CLAIM_ID_RE` 与 stage-09 claim id 生成口径。

---
