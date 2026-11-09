---
id: arc-roadmap-v06-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-master-roadmap, arc-belief-revision-propagation-RESEARCH, arc-r3-engine-impact-RESEARCH]
upstream: arc-master-roadmap
---

# 调研：总纲 v0.6 状态同步的必要性

> **Feature**: 将 P-011..P-015 的结果回写总纲，修正 G-1/G0b/Q17 的状态与依据表。
> **状态**: verified（审计完成，改动仅状态/引用，不改路线与验收计数）
> **Spec 步骤**: Step 1-2

## 1. 调研目标

1. P-011..P-015 之后，总纲哪些状态已过期？
2. 哪些新研究应挂到总纲的“依据文档”？
3. 是否必须改动 106 条验收、阶段顺序或 C 套件？

## 2. 审计发现

| # | 位置 | 过期事实 | 证据 |
|---|---|---|---|
| F-1 | 头部版本与修订记录 | 停在 v0.5（P-006） | 总纲 `:4`、`:19-25` |
| F-2 | G-1 标题 | 未标“已完成”，但 P-006 已交付 | P-006 CHECKLIST；G-1 测试 28 passed |
| F-3 | G0b 标题 | 未标“未就绪”；缺 4 类交付物，Q3 待裁决 | 2026-11-10 审计 |
| F-4 | Q17 | 仍为“待确认”，但 P-012/P-013 已按 API-first + CLI opt-in 落地 | P-012/P-013 文档 |
| F-5 | §11 依据文档 | 缺 P-011..P-015 五批研究 | `spec/arc-cli-agent-*`、`arc-belief-revision-propagation`、`arc-r3-engine-impact` |
| F-6 | G3 交付物 | 无回退/传播候选；P-014 的“R-3 拒绝”已被 P-015 取代 | P-014 §6.2、P-015 §8 |

## 3. 不需要改的部分

- **106 条验收计数**：P-014/P-015 没有新增可机械验收的阶段出口；本批只加“候选增量”备注，不新增 ID。
- **阶段顺序**：`G0a → G-1 → G0b → G2 → G3` 不变；G1/G2 并行关系不变。
- **C-9**：H-1..H-5 已生效，无需改。
- **G0b 验收项**：A0-1..A0-6 不变；缺的是交付物，不是标准。

## 4. 结论

需要做一次 **v0.6 状态同步**：更新版本/修订记录、G-1/G0b 状态、Q17 裁决、§11 依据表、G3 候选增量；不改路线、不改 106 计数。

## 5. 未决项

- **U-1 G0b 开工**：Q3 待裁决；交付物补齐前不开工。
- **U-2 R-3c 引擎触发**：沿用 P-015 §8 五项条件，当前均未满足。
- **U-3 P-014 的 R-3 表述**：由 P-015 取代，不再单独修订 P-014 归档。

## 6. 参考文献

1. [arc-master-roadmap.md](../../arc-master-roadmap.md)
2. [P-014 RESEARCH](../arc-belief-revision-propagation/RESEARCH.md)
3. [P-015 RESEARCH](../arc-r3-engine-impact/RESEARCH.md)
