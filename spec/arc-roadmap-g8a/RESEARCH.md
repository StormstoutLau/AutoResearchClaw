---
id: arc-roadmap-g8a-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-research-plan-CHECKLIST, arc-master-roadmap]
upstream: null
---

# 回填：G8a 收口与总纲进度（P-153 / T3）

> **Feature**：P-153。T3 轻批：Layer-0 文档回填，零代码、零测试、零门禁改动。
> **依据**：[P-152 实施](../arc-research-plan/IMPLEMENTATION.md)、[P-152 验收](../arc-research-plan/CHECKLIST.md)。

## 1. 问题

P-152 已合并（`db4ad47`），G8a 的 A8a-1..4 全部通过，但总纲仍停留在 P-144 的 v1.4s：G8a 标「未开始」、进度 64/106、开放 42、下一批仍建议 G8a。三处读数均滞后。

## 2. 读数与算术

| 项 | 旧值 | 新值 | 依据 |
|---|---|---|---|
| G8a | 0/4 未开始 | **4/4 已完成（P-152）** | CHECKLIST 34/34 |
| 完成 | 64 | **68** | 64 + G8a 4 |
| 开放 | 42 | **38** | 106 − 68 |
| 开放构成 | G5 14 + G6 5 + G7 15 + G8a 4 + G8b 4 | G5 14 + G6 5 + G7 15 + G8b 4 | 38 = 14+5+15+4 |

Q15 的默认值（深度 3 / 扇出 8 / 节点 40 / `max_versions=3`）由 P-152 provisional 采用，仍待 ARC-Bench 校准；本批只把状态从「待确认」改为「provisional」，不宣称已裁决。

## 3. 回填面

1. front-matter `version` 1.4s → 1.4t，`date` 2026-11-11 → 2026-11-24。
2. 标题版本 v1.4s → v1.4t。
3. 修订日志新增 v1.4t 行（P-153）。
4. §3.1 进度表：G8a 4/4、合计 68、开放 38；口径补 P-145..P-151 与 P-152 的归属。
5. G8a 阶段标题改为「已完成（P-152）」并加实施记录。
6. §6 依赖图说明与 §7 未决项：可并行项去掉 G8a、下一批 P1 改为 G5、Q15 标 provisional、路线步骤 7 改为「规划对象已补」。

## 4. Review 记录（Step 4）

- 只改读数与状态，不改 G8a 的验收条目、A8a-1..4 定义或 106 口径。
- 不把 P-145..P-151（pipeline 复用/等价性）计入 106；它们不在总纲 G0a..G8b 的验收表内。
- 未重新验证 P-152 代码；G8a 的 4/4 直接引用其 CHECKLIST 34/34 与合并提交。

## 5. 边界

- 本批是文档回填，不产生代码或行为变化。
- 总纲的 `status: draft` 保持不变；G8a 只标完成，不改变其 P1 定位。
- Q15 仍是 provisional，正式裁决需 ARC-Bench 数据。
