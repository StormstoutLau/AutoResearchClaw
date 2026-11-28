---
id: arc-stage10-repair-context-budget-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [arc-stage10-repair-context-budget-RESEARCH]
upstream: arc-stage10-repair-context-budget-RESEARCH
---

# 设计：修复上下文的预算、遥测与截断止损（P-228）

## 1. 决策

| ID | 决策 | 依据 | 被拒替代 |
|---|---|---|---|
| G-1 | `_format_files(files, keep_full, budget)`：超预算时未受影响文件降为 CodeMem 摘要；受影响文件保全文，按剩余预算中间截断（头 60% + 尾 40% + 显式标记） | L-2；Codex 中间截断 | 全量拼接（现状）；只砍尾（丢失 critical 行） |
| G-2 | `agent_repair` / `project_repair` trace 增 `usage.{prompt_tokens, completion_tokens, total_tokens, finish_reason}` 与 `summary_mode` | L-3；Claude usage 记录 | 仅字符数（无法判断 reasoning 占用） |
| G-3 | prompt 硬上限 140 000 字符；超限或 provider 报 prompt-too-long 时切「仅摘要」重建并重试一次 | L-4；Claude PTL 降级 | 无上限（未来文件增多会撞窗口） |
| G-4 | 16k→32k 后仍截断：本轮不提取候选，按 `truncated_after_escalation` 计入 P-226 拒收计数 | L-4；P-226 止损 | 静默继续（同 prompt 反复截断） |

## 2. 行为

- 预算默认 60 000 字符（agent 层）、80 000（阶段深修层）；keep 文件按 `预算 − 摘要体积` 均分，单文件下限 1 500。
- 摘要块以 `# [summary — this file is not modified by this repair]` 开头，模型可区分「不必输出」。
- 截断标记格式：`... [truncated: N chars / M lines omitted, original K chars] ...`。
- G-4 走原有 P-226 streak：同一文件连续两次 `truncated_after_escalation` 即停。

## 3. 验收

- 中间截断保留头尾且标记含原始字符数；
- 超预算时 keep 文件保全文、其他文件成摘要，总长小于原文；
- trace 出现 usage 与 `summary_mode`；
- 连续两轮截断 → 4 次调用、无合并、streak=2；
- 既有 61 例全部通过。

## 4. 非目标

- 不引入会话历史或自动摘要（ARC 修复无状态）；
- 不改 provider 的 max_tokens 配置；
- 不部署、不重跑 B 站。
