---
id: arc-stage10-symbol-recheck-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [arc-stage10-repair-context-budget]
upstream: arc-master-roadmap
---

# 调研：晚写入后的符号契约复检（P-229）

> **档位**：S1 缺陷型（§2.3）。根因由运行 M 日志直接给出。

## 1. 问题

运行 M 的 attempt 1 在 15:10:05 被出口门拦下：

```
blueprint_symbols_missing: main.py:evaluate_monitor, main.py:run_condition,
main.py:set_seed, main.py:train_model
```

但 P-227 的 F-2 已在深修前检查过符号且通过。差异来自时序：14:59:51 的 `_ensure_entrypoint` 重新生成了 main.py，此后没有再检查。

## 2. 本地事实

| # | 事实 | 锚点 |
|---|---|---|
| L-1 | 入口重生成晚于 F-2，写盘后无复检 | [\_code_generation.py#L2506](../../researchclaw/pipeline/stage_impls/_code_generation.py#L2506) |
| L-2 | 对齐重生成同样直接覆盖文件集 | [\_code_generation.py#L2300](../../researchclaw/pipeline/stage_impls/_code_generation.py#L2300) |
| L-3 | 首个入口修复点也在校验循环之前，同样缺复检 | [\_code_generation.py#L1572](../../researchclaw/pipeline/stage_impls/_code_generation.py#L1572) |
| L-4 | 出口门是唯一兜底，代价是整轮 attempt 的耗时 | [postmortem §2.7](../../docs/arc-b-site-stage10-postmortem-20261126.md#L329) |

## 2.3 档位与最小来源

- **档位**：S1。
- **来源**：E1 ≥2 —— L-1/L-2（代码路径）与运行 M 日志（现场失败）。
- **豁免**：无需外部检索，根因是本地时序缺口。

## 2.4 降级链

MCP 学术检索（S1 豁免）→ 现场日志 → 仓内代码 → 既有 P-227 设计。

## 3. 结论

在三个晚写入点后统一调用 `_ensure_symbol_contract`：复检 → 一次定向修复 → 仍缺则保留原文件并交出口门。

## 4. 来源

- 运行 M 日志（B 站 `p228-stage10.log` 15:10:05 行）
- [P-227 RESEARCH](../arc-stage10-workspace-hygiene/RESEARCH.md)
- [codegen_evidence.py#L295](../../researchclaw/pipeline/codegen_evidence.py#L295)
