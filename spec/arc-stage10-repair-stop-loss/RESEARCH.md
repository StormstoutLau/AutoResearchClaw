---
id: arc-stage10-repair-stop-loss-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [arc-stage10-repair-guardrails]
upstream: arc-master-roadmap
---

# 调研：Stage 10 重复拒收止损（P-226 / D-1）

> **档位**：S1 缺陷型（§2.3）。现场读数与代码路径均在仓内可复现。

## 1. 问题

P-222 的拒收闸门已能阻止修复写坏文件，但不阻止「同一失败原因反复重试」。运行 L（P-222 快照）attempt 1 连续三轮同因失败，每轮约 11.5 分钟，critical 数保持 12 不降。

## 2. 本地事实

| # | 事实 | 锚点 |
|---|---|---|
| L-1 | 运行 L 02:00 / 02:11 / 02:22 三轮均为 `data.py: syntax_error` + `main.py: entrypoint_contract`，12 → 12 → 12 | [postmortem §2.7](../../docs/arc-b-site-stage10-postmortem-20261126.md#L329) |
| L-2 | 修复循环上限 4 轮，无「同因重复」判据 | [code_agent.py `_hard_validate_and_repair`](../../researchclaw/pipeline/code_agent.py#L1308) |
| L-3 | 拒收原因已在 `repair_trace` 的 `rejected_reasons` 中，但未被用于止损 | [code_agent.py `_repair_critical_issues`](../../researchclaw/pipeline/code_agent.py#L1642) |
| L-4 | P-224 基线：同因场景 5 条 `hard_validation` / 4 次调用 / 0 接受 | [IMPLEMENTATION](../arc-stage10-repair-guardrails/IMPLEMENTATION.md#L24) |
| L-5 | 单文件修复回复会被 `_extract_multi_file_blocks` 改名为 `main.py`，测试须用双文件回复才能命中 `data.py` | [code_agent.py `_accept_repair_files`](../../researchclaw/pipeline/code_agent.py#L1684) |

## 2.3 调研档位

- **档位**：S1 缺陷型。
- **最小来源**：E1 ≥2 —— L-1（现场日志）与 L-4（fixture 基线）满足。
- **豁免说明**：止损阈值由现场「2 轮已可判定同因」决定，外部检索不改变判据；社区同类做法（Cline 3.54 防无限重试）已在 P-223 RESEARCH §2.2 记录，本批不重复。

## 2.4 降级链

| 目标通道 | 实际走到 | 结果 |
|---|---|---|
| MCP 学术检索 | 未调用（S1 豁免） | 不适用 |
| 现场日志 | `ssh` 读 `p222-stage10.log` | 命中 L-1 |
| 仓内代码 | 读 `_hard_validate_and_repair` / `_repair_critical_issues` | 命中 L-2/L-3 |
| 基线测试 | P-224 fixture 输出 | 命中 L-4 |

## 3. 结论

止损条件 = **同一文件 + 同一拒收类别连续 2 次**；接受任意文件或原因变化即重置。默认开启（2），可配置为 0 关闭。

## 4. 来源

- [postmortem §2.7](../../docs/arc-b-site-stage10-postmortem-20261126.md)
- [P-224 IMPLEMENTATION](../arc-stage10-repair-guardrails/IMPLEMENTATION.md)
- [P-223 RESEARCH §2.2](../arc-stage10-repair-guardrails/RESEARCH.md)
