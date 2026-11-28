---
id: arc-stage10-split-rejection-accounting-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-29
depends: [arc-stage10-repair-minimal-edit]
upstream: arc-master-roadmap
---

# 调研：拆分修复的拒收记账（P-233）

> **档位**：S1 缺陷型（§2.3）。根因由运行 Q 的 `repair_trace.jsonl` 直接给出。

## 1. 问题

运行 Q（P-231/P-232 快照）的修复轨迹自相矛盾：

```
2026-11-28T16:26:15Z agent_repair split_per_file
  accepted = [config.py, data.py, main.py, methods.py, models.py]
  rejected_reasons = {config.py: not_returned, data.py: not_returned,
                      main.py: not_returned, methods.py: not_returned,
                      models.py: not_returned}
2026-11-28T16:57:12Z agent_repair_stopped  reason=not_returned
```

五个文件都被接受，却同时被记为「未返回」；下一轮 P-226 的同因止损据此触发，把一条**已成功修复全部五个文件**的路径停掉。

## 2. 本地事实

| # | 事实 | 锚点 |
|---|---|---|
| L-1 | `_repair_files_individually` 用 `if why: ... else: rejected.setdefault(name, "not_returned")` | [code_agent.py#L1941](../../researchclaw/pipeline/code_agent.py#L1941) |
| L-2 | 文件被接受时 `why` 为空字典，于是落入 `else` 分支被标 `not_returned` | 同上 |
| L-3 | 父函数把 `rejected_reasons` 喂给 P-226 连续同因计数，计数达 2 即返回原文件并写 `agent_repair_stopped` | [code_agent.py#L1787](../../researchclaw/pipeline/code_agent.py#L1787) |
| L-4 | 拆分路径的 `fixed` 仍然正确合并，因此日志说「修复成功」、止损说「同因失败」并存 | 运行 Q 16:26:15Z 轨迹 |
| L-5 | 运行 Q 因此多轮空转：00:26、00:57、01:07、01:15 四段修复都在拆分模式下进行 | `p232-stage10.log` |

## 2.3 档位与最小来源

- **档位**：S1。
- **来源**：E1 ≥2 —— `repair_trace.jsonl` 的两条记录（accepted 与 rejected_reasons 冲突）、`_repair_files_individually` 读码。
- **豁免**：记账逻辑缺陷，本机可复现（一次拆分修复即触发），无需外部检索。

## 2.4 降级链

MCP 学术检索（S1 豁免，未调用）→ 运行 Q 轨迹 → 仓内代码 → P-231 设计。

## 3. 结论

拆分路径的拒收记账必须以「文件是否真的被接受」为准：只有既不在 `fixed` 也不在 `rejected` 的文件才记 `not_returned`。

## 4. 来源

- 运行 Q：B 站 `~/arc-runs/g7-baseline/stage-10/repair_trace.jsonl`（16:26:15Z、16:57:12Z）
- `~/arc-runs/g7-baseline/p232-stage10.log`（00:26–01:19）
- [code_agent.py#L1941](../../researchclaw/pipeline/code_agent.py#L1941)
