---
id: arc-g3-m3-claim-fixes-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-12
depends: [arc-g3-m3-claim-fixes-DESIGN]
upstream: arc-g3-m3-claim-fixes-DESIGN
---

# 实施记录：G3 M3 D-1 修复（P-085）

> **状态**：施工完成；读数见 §5。

## 1. 改动清单

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `researchclaw/evidence/claim_spine.py` | 修改 | 新增 `MARKER_PLACEHOLDER`、`_FENCE_RE`、`_INLINE_CODE_RE`；`extract_claim_markers` 改逐行扫描（围栏开关/行内代码剔除/标题即时生效） |
| 2 | `researchclaw/pipeline/stage_impls/_paper_writing.py` | 修改 | 顶层 import `MARKER_PLACEHOLDER`；文法示例改为占位符并加「勿复制/勿虚构」 |
| 3 | `tests/test_claim_spine.py` | 修改 | 新增 4 项：占位符不匹配 + 提示词无合法示例、围栏/行内代码跳过、标题归属、围栏内伪标题 |

**不改**：`CLAIM_MARKER_RE`、export/trace/digest 判定、Stage 22/23 接线、C4/AR 内核、错误码。

## 2. 接口与回退点

| 接口 | 签名 | 回退点 |
|---|---|---|
| `MARKER_PLACEHOLDER` | `str` 常量 | 仅提示词引用；改回合法示例即回退到 D-1 |
| `extract_claim_markers` | `(text: str) -> dict[str, list[str]]` | 纯函数；输出只减少、不新增 marker |
| `CLAIM_MARKER_RE` | 不变 | 正则未改 |

## 3. 关键行为

- **提示词**：`e.g. [c-xxxxxxxx]`；`x` 不匹配 `[0-9a-f]{8}`。
- **围栏**：行首 ``` / ~~~ 翻转状态；围栏内伪标题与示例 id 全部跳过。
- **行内代码**：单反引号跨度在提取前剔除。
- **标题**：遇到即更新 `current`，只作用于其后行；修复 P-084 D-2。
- **判定**：真实未知 hex id 仍触发 `unknown_claim_marker` → `claim_marker_not_exported` → Stage 23 FAILED。

## 4. 版本与 API 兼容性核验（Step 6）

| 依赖 | 用法 | 下限可用性 | 状态 |
|---|---|---|---|
| `re` / `pathlib` / `json` / `hashlib` | 扫描与落盘 | 3.11 全有 | ✅ |
| `researchclaw.evidence.claim_spine` | Stage 17 常量 import | 仓内既有（P-083） | ✅ |
| 3.12+ stdlib API | 无 | — | ✅ |

## 5. 读数（Step 9-10 回填）

| 项 | 读数 |
|---|---|
| 新增测试 | 4 项（占位符/提示词、围栏+行内代码、标题归属、围栏内伪标题） |
| 双环境 | 3.13.5 **118 passed**（2.15s）；3.11.15 **118 passed**（3.25s） |
| 相关回归 | M1-M5 十文件 **181 passed** |
| E2 修复验证 | 占位符+围栏示例：`trace.ok=True`；真实未知 hex `c-deadbeef`：`trace.ok=False`（fail-closed 保持） |
| 门禁 | DC 0 违规；step-gate 5/5；step-enforce `digest_bound=3`；pre-commit **9/9 Passed** |
| 红→绿 | 红：`ImportError: cannot import name 'MARKER_PLACEHOLDER'`（1 collection error）；绿：`test_claim_spine` 18 passed |

## 6. 验收边界（诚实口径）

- **D-1**：由 ①+② 关闭；③ 未采纳，模型幻觉出的合法 hex id 仍阻断。
- **D-2**：作为逐行扫描的附带结果关闭（`test_extract_markers_heading_applies_to_following_lines`）。
- **未闭合围栏**：按「其后全部视为代码」处理（U-1）。
- **多反引号行内代码**：未处理（U-2）。
- **O-3**：P-083 IMPLEMENTATION §5 的 18≠19 读数偏差未在本批订正（见 CHECKLIST §11）。

## 7. 风险

- 未闭合围栏会静默跳过其后所有 marker（fail-closed 方向；U-1）。
- 多反引号行内代码仍可能被提取（U-2）。
- 提示词占位符依赖 LLM 遵守「勿复制」；即使复制也不匹配正则，无阻断风险。
