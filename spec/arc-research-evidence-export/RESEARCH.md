---
id: arc-research-evidence-export-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [SPEC-PROCESS]
upstream: arc-master-roadmap
---

# 调研：调研证据出口规范化（P-225）

> **档位**：S1 缺陷型（见 §2.3）。本批分析对象是仓内规范与模板，根因全部可在本机复现。

## 1. 问题

`spec/SPEC_PROCESS.md` 的 Step 1-2 要求「使用多种 MCP 工具调研」并给出证据出口，但实际批次（P-208..P-224）普遍只写结论锚点，未留「怎么搜的、来源属于哪一层、ID 是否可解析」。P-223 是例外：调研本身做了（5 篇 arXiv + 官方 changelog/issue），但没有按 T1/T2/T3 标注，也没有落降级链。

## 2. 本地事实

| # | 事实 | 锚点 |
|---|---|---|
| L-1 | 规范已定三档（T1 完整 / T3 轻批），但只约束**工件多少**，不约束**调研强度** | [SPEC_PROCESS §批次档位](../SPEC_PROCESS.md#L562) |
| L-2 | 方法节明确「不新增 RULE / 门禁 / 依赖」，违反的唯一后果是「无法出示证据出口」 | [SPEC_PROCESS](../SPEC_PROCESS.md#L119) |
| L-3 | 契约表已有硬约束：≥2 独立来源且 ≥1 T1、每条标 Layer+日期+版本、失败写降级链 | [SPEC_PROCESS](../SPEC_PROCESS.md#L131) |
| L-4 | 模板本来就有 §2 调研方法（工具/范围）与 §5 文献验证表，但实例很少用 | [RESEARCH_TEMPLATE](../templates/RESEARCH_TEMPLATE.md#L28) |
| L-5 | `verify-anchor` 对 `http(s)` 只标「软性：外部证据，本地不可核」，不判红 | [spec_runner.py](../../tools/spec_runner/spec_runner.py#L397) |
| L-6 | session 的 research 决策只有 `evidence` 锚点，没有 `sources`（层/ID/日期/状态） | [p223 session](../../tools/spec_runner/sessions/specwf-p223-repair-guardrails.jsonl#L1) |

## 2.3 调研档位

- **档位**：S1 缺陷型。
- **最小来源**：E1 读数 ≥2 —— 已满足（L-1..L-6 均为仓内可重放锚点）。
- **豁免说明**：本批问题是「规范与执行脱节」，判据在仓内规范/模板/门禁代码中可直接读出；外部检索无法提供比 L-1..L-6 更强的证据，故不走 S2。

## 2.4 降级链

| 目标通道 | 实际走到 | 结果 |
|---|---|---|
| MCP 学术检索 | 未调用（S1 豁免） | 不适用 |
| 仓内规范检索 | `Grep spec/SPEC_PROCESS.md` | 命中 L-2/L-3 |
| 仓内模板检索 | 读 `spec/templates/RESEARCH_TEMPLATE.md` | 命中 L-4 |
| 仓内门禁代码 | 读 `tools/spec_runner/spec_runner.py` | 命中 L-5 |
| 历史实例 | 读 P-223 session / RESEARCH §5 | 命中 L-6 |

## 3. 发现

1. **缺口不在能力，在留证**：模板已有方法节，规范已有硬约束，缺的是「每批必须填」的执行锚点。
2. **门禁刻意不覆盖来源质量**：`verify-anchor` 对外部 URL 只做软性提示，这是原规范的设计选择，不应改动。
3. **需要的是分级，不是全量强制**：纯缺陷修复用 E1 即可，探索型才需要外部 ≥5 条 + T1。
4. **最小改动点**：模板加 §2.3/§2.4、SPEC_PROCESS 加 S0/S1/S2 小节、CHECKLIST 模板加一行自证、AGENTS 五步补一句、session 加 `sources`。

## 4. 结论

把「调研强度」写成可判档的形态（S0/S1/S2），并给出证据出口（RESEARCH §2.3/§2.4 + session `metadata.sources`），不新增门禁。这样既不重犯「为判断造门禁」，也让 Review 可复核。

## 5. 来源

- [SPEC_PROCESS.md](../SPEC_PROCESS.md)
- [RESEARCH_TEMPLATE.md](../templates/RESEARCH_TEMPLATE.md)
- [CHECKLIST_TEMPLATE.md](../templates/CHECKLIST_TEMPLATE.md)
- [spec_runner.py](../../tools/spec_runner/spec_runner.py)
- [P-223 RESEARCH](../arc-stage10-repair-guardrails/RESEARCH.md)
