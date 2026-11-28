---
id: arc-stage10-repair-context-budget-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [arc-stage10-workspace-hygiene]
upstream: arc-master-roadmap
---

# 调研：修复上下文的预算、遥测与截断止损（P-228）

> **档位**：S1 缺陷型（§2.3）。运行 L 的 `repair_trace.jsonl` 提供了完整读数；外部两个项目的做法见 §3。

## 1. 问题

运行 L 的 16 次 `agent_repair` 全部 `truncated=True`，可见响应仅 16–18k 字符；prompt 42k–66k 字符且**无上限**（`_format_files` 全量拼接）。同时 trace 只有字符数，没有 token 级数据，无法判断截断是「输出太长」还是「reasoning 吃满预算」。

## 2. 本地事实

| # | 事实 | 锚点 |
|---|---|---|
| L-1 | 16/16 次 agent_repair 截断，响应 16–18k 字符，prompt 42 374–66 077 字符 | [postmortem §2.7](../../docs/arc-b-site-stage10-postmortem-20261126.md#L329) |
| L-2 | `_format_files` 全量拼接、无预算 | [code_agent.py#L2345](../../researchclaw/pipeline/code_agent.py#L2345) |
| L-3 | trace 只有 `prompt_chars/response_chars`，无 token usage | [repair_trace.py#L85](../../researchclaw/pipeline/repair_trace.py#L85) |
| L-4 | 截断重试只做一次 16 384 → 32 768，仍截断时继续静默提取候选 | [code_agent.py#L1650](../../researchclaw/pipeline/code_agent.py#L1650) |
| L-5 | 阶段级深修 prompt 38–54k 字符，同样无上限 | [\_code_generation.py#L1742](../../researchclaw/pipeline/stage_impls/_code_generation.py#L1742) |

## 2.3 调研档位

- **档位**：S1 缺陷型。
- **最小来源**：E1 ≥2 —— L-1（现场 trace）与 L-2/L-4（代码路径）。
- **豁免说明**：外部项目仅用于形态对照（§3），根因无需外部检索即可复现。

## 2.4 降级链

| 目标通道 | 实际走到 | 结果 |
|---|---|---|
| MCP 学术检索 | 未调用（S1 豁免） | 不适用 |
| 现场 trace | 解析 `repair_trace.jsonl` 35 事件 | 命中 L-1 |
| 仓内代码 | 读 `code_agent.py` / `_code_generation.py` | 命中 L-2/L-4/L-5 |
| 外部实现 | 扫描 `D:\ds\codex-main`、`D:\ds\claude-code-haha-main` | 命中 §3 |

## 3. 外部实现对照

| 机制 | 来源 | 可借鉴 |
|---|---|---|
| 中间截断 + 原始 token/行数标记 | Codex `utils/output-truncation/src/lib.rs#L15-L29` | 高：保留头尾，避免只砍尾丢掉 critical 指向的行 |
| 有效窗口 = 上下文 − 预留输出；warning/error/compact 阈值 | Claude Code `compact/autoCompact.ts#L28-L158` | 中：ARC 无历史，但可借阈值形态切摘要模式 |
| usage 记录 + 估算兜底 | Claude Code `utils/tokens.ts#L201-L260`、`cost-tracker.ts` | 高：先有 token 读数 |
| prompt-too-long 删头重试 + 标记 | Claude Code `compact/compact.ts#L230-L290` | 中：改为「摘要模式」降级重试一次 |
| 压缩后固定区块顺序 | Claude Code `compact.ts#L325-L338` | 中：修复 prompt 用固定区块标注摘要 |

## 4. 结论

四条：G-1 分文件预算 + 中间截断；G-2 usage 遥测；G-3 硬上限 + 超长降级重试；G-4 二次截断即止损（接入 P-226）。

## 5. 来源

- [postmortem §2.7](../../docs/arc-b-site-stage10-postmortem-20261126.md)
- [P-227 RESEARCH](../arc-stage10-workspace-hygiene/RESEARCH.md)
- 外部：`codex-main/codex-rs/utils/output-truncation`、`claude-code-haha-main/src/services/compact`
