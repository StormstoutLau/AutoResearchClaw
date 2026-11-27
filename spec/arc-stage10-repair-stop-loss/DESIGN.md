---
id: arc-stage10-repair-stop-loss-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [arc-stage10-repair-stop-loss-RESEARCH]
upstream: arc-stage10-repair-stop-loss-RESEARCH
---

# 设计：Stage 10 重复拒收止损（P-226 / D-1）

## 1. 决策

| ID | 决策 | 依据 | 被拒替代 |
|---|---|---|---|
| D-1 | 同一 `(file, reason类别)` 连续 2 次拒收 → 停止该轮循环并返回当前文件（保留原版本） | L-1 三轮同因、L-4 基线 | 跑满 4 轮（浪费 ~23 min） |
| D-2 | 连续计数：仅上一轮同 `(file, reason)` 才累加；接受任一文件或原因变化即从 1 重计 | 避免把「交替失败模式」误判为同因 | 按文件累计（会误杀） |
| D-3 | 新增配置 `repair_stop_after_rejections`（默认 2，0 关闭） | 现场可回退，无需改代码 | 硬编码 2 |
| D-4 | 停止时写 `agent_repair_stopped` trace（file / reason / count / attempt） | 与 `agent_repair` 同账本，可审计 | 只写日志 |

reason 类别取 `rejected_reasons` 的 `:` 前缀（`syntax_error` / `entrypoint_contract` / `symbol_contract` / `unknown_file`）。

## 2. 行为

```
attempt 0: validate fail → repair #1 (reject streak=1)
attempt 1: validate fail → repair #2 (reject streak=2) → stop → return files
```

- `hard_validation` 行：2（原 5）；
- LLM 调用：2（原 4）；
- 原文件逐字节保留；
- 阶段层继续按原有校验/证据门处理（本批不改）。

## 3. 验收

- fixture `repeat_rejection`：calls 4 → **2**，`kept=True`，`accepted_bad=False`；
- 新增：`repair_stop_after_rejections=0` 时仍为 5 行 / 4 调用；
- 新增：交替原因（syntax → symbol → syntax → symbol）不触发停止，仍为 5 行 / 4 调用；
- 相关回归（fixture + generation budget + truncation + repair trace）**80 passed**。

## 4. 非目标

- 不改 P-222 的三道拒收闸门；
- 不改变阶段层出口门与深修循环；
- 不部署、不改 B 站运行中的 L。
