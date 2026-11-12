---
id: arc-g3-m3-claim-fixes-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-12
depends: [arc-g3-m3-review]
upstream: arc-g3-m3-review
---

# 调研文档：G3 M3 D-1 修复（示例标记误阻断）

> **Feature**：P-085，P-084 复核 D-1 的修复批。
> **Spec 步骤**：Step 1-2。
> **输入**：[P-084 独立异构复核](../../docs/arc-g3-m3-review-20261112.md) §2/§3；P-083 实现 [claim_spine.py](../../researchclaw/evidence/claim_spine.py)、[Stage 17 提示词](../../researchclaw/pipeline/stage_impls/_paper_writing.py)。

## 1. 调研目标

1. **误阻断链的精确边界**：示例 id 从哪来、经过哪些判定、在哪个出口变成 FAILED？
2. **最小修复面**：改提示词、改提取器、改判定三者各自关闭哪一段？能否只改一处？
3. **fail-closed 不可退化**：修复不能把真实的未知 claim id 一并放行。

## 2. 调研方法

### 2.1 使用的通道与降级链

| 通道 | 用途 | 结果 |
|---|---|---|
| 仓内读码（`Read` / `Grep`） | 提示词、提取器、export、trace、Stage 23 阻断链 | ✅ 一手定位 |
| P-084 X-12b 运行时探针（E2） | gate pass 的正常 run 上复现误阻断 | ✅ 已复现 |
| 本批 E2 复验脚本 | 修复前后对照（占位符/围栏/未知 hex） | ✅ 见 §3.2 |

**降级链记录**：本批为缺陷修复，事实源全部为仓内一手代码与 P-084 运行时证据（E1/E2）；未引入外部文献，**不以二手转述作为任何结论依据**。

### 2.2 调研范围

- 时间：P-083 实施（2026-11-12）至 P-084 复核（同日）。
- 排除：NLP 级「未标记数值断言」检出（P-083 U-1，非本批）。

## 3. 调研发现

### 3.1 误阻断链（读码，E1）

| # | 事实 | 位置 | 影响 |
|---|---|---|---|
| R-1 | Stage 17 文法说明的示例原为 `[c-1a2b3c4d]`——**合法 hex id**，与真实 claim id 同构 | `_paper_writing.py` claim grammar 块 | LLM 复述示例即产生一个「不存在于 decisions」的合法标记 |
| R-2 | `extract_claim_markers` 按空行分块；块内先扫标题、再扫正文，正文统一归到**块末**标题；无代码围栏/行内代码跳过 | `claim_spine.py` 原实现 | ① 代码示例中的 id 被当正文引用；② 标题紧贴正文时归属错位（P-084 D-2） |
| R-3 | `export_claim_labels` 对 markers 中不在 decisions 的 id 记 `unknown_claim_marker`；`verify_claim_trace` 对不在 export 的 marker 记 `claim_marker_not_exported`；Stage 23 见 `trace.ok=False` 即 FAILED | `claim_spine.py`、`_review_publish.py` | 误阻断链的完整出口 |
| R-4 | `CLAIM_MARKER_RE = \[(c-[0-9a-f]{8})\]` | `claim_spine.py` | 非 hex 占位符（`x`）天然不匹配，是可用的「安全示例」 |
| R-5 | 真实未知 hex id 在 X-12b 之外的场景仍应阻断（fail-closed） | P-084 §3 D-1 修复建议③被拒绝的理由 | 修复必须保留该路径 |

### 3.2 修复前后对照（E2）

| 场景 | 修复前 | 修复后 |
|---|---|---|
| 论文含文法占位符 `[c-xxxxxxxx]` + 围栏内示例 `[c-1a2b3c4d]` | 占位符不匹配、围栏内 id 被提取 → trace 判红 | 两者均不提取 → `trace.ok=True` |
| 论文含真实未知 hex id `[c-deadbeef]` | 判红 | **仍判红**（`unknown_claim_marker` + `claim_marker_not_exported`） |
| 标题紧贴正文（无空行） | 正文被归到后一标题 | 标题只作用于其后行 |

## 4. 综合分析

### 4.1 关键发现

1. **单改提示词不足**（R-2）：论文仍可能在代码围栏或解释性文字里出现示例 id；必须同时让提取器跳过示例区域。[★★★★★]
2. **单改提取器不足**（R-1）：只要提示词给的是合法 hex 示例，LLM 就可能把它写进正文；提示词示例必须换成不匹配的占位符。[★★★★★]
3. **①② 组合关闭误阻断链且不弱化 fail-closed**：真实未知 id 的判定路径（R-3）未被触碰。[E2 对照]

### 4.2 被拒绝的方案

| 方案 | 拒绝理由 |
|---|---|
| ③ 把 `unknown_claim_marker` / `claim_marker_not_exported` 降为 warning | 会放行模型幻觉出的合法 hex id，直接削弱 A3-1 的 fail-closed 面；P-084 已将其列为「由用户裁决」，本批未采纳 |
| 只改提示词（①） | 无法覆盖代码围栏/行内代码中的示例 id（R-2） |
| 只改提取器（②） | 无法阻止 LLM 把提示词里的合法示例 id 写进正文（R-1） |

## 5. 幻觉抑制审查（Step 2 Review）

### 5.1 技术声明验证

| 声明 | 来源 | 状态 |
|---|---|---|
| 示例 id 为合法 hex、与真实 id 同构 | R-1 读码 | ✅ E1 |
| 原提取器不跳过代码围栏/行内代码 | R-2 读码 + P-084 X-3 | ✅ E1/E2 |
| 误阻断出口是 `trace.ok=False` → Stage 23 FAILED | R-3 读码 + P-084 X-12b | ✅ E1/E2 |
| `x` 占位符不匹配 `[0-9a-f]{8}` | R-4 读码 + 本批单测 | ✅ E1 |

### 5.2 待修正项

- [x] P-084 D-1 的触发面已按 R-1/R-2 拆成两段，分别由 ①② 关闭。
- [x] ③ 未采纳，已在 §4.2 显式登记拒绝理由。

## 6. 对设计的输入

### 6.1 可用方案

1. **安全占位符**：`MARKER_PLACEHOLDER = "[c-xxxxxxxx]"`，由 `claim_spine` 单点定义，Stage 17 引用。
2. **逐行提取器**：围栏开关（```/~~~）、行内代码剔除、标题即时生效、按 claim/ref 去重。
3. **判定不变**：export/trace/Stage 23 的 fail-closed 语义零改动。

### 6.2 关键约束

- 不改 `CLAIM_MARKER_RE`、不改 C4/AR 判定、不改错误码。
- 不引入 NLP/LLM 依赖。
- 不采纳 ③；真实未知 hex id 必须继续判红。

### 6.3 风险

- 围栏开关按行首 ``` / ~~~ 简单切换；未闭合围栏会把其后正文全部跳过（fail-closed 方向，登记 U-1）。
- 行内代码仅处理单反引号跨度（P-083 语法约定）；多反引号跨度登记 U-2。

### 6.4 未决项登记（四元块）

- **U-1 未闭合围栏**
  - **判据**：出现未闭合围栏时，提取器行为有明确文档与测试
  - **触发条件**：首个真实论文出现未闭合围栏，或用户报告漏检
  - **当前倾向**：按「其后全部视为代码」处理（不误提取）；如需告警另立批次
  - **证据等级**：R-2 + 本批单测

- **U-2 多反引号行内代码**
  - **判据**：`` ``[c-…]`` `` 形态不被误提取
  - **触发条件**：真实论文出现多反引号示例
  - **当前倾向**：不处理；单反引号为 P-083 约定形态
  - **证据等级**：R-2

- **U-3 幻觉 hex id**
  - **判据**：模型写出不在 decisions 的合法 hex id 时的期望行为
  - **触发条件**：③ 若被用户重新裁决
  - **当前倾向**：保持阻断（fail-closed）；③ 未采纳
  - **证据等级**：R-3 + P-084 §3

## 7. 参考文献

- P-084 独立异构复核：`docs/arc-g3-m3-review-20261112.md`（仓内一手证据 E1/E2）。
- P-083 实现：`researchclaw/evidence/claim_spine.py`、`researchclaw/pipeline/stage_impls/_paper_writing.py`。

---

**Review 签字**: 自查（单视角）+ 机械核验 日期: 2026-11-12
