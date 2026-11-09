---
id: arc-roadmap-v06-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-roadmap-v06-RESEARCH]
upstream: arc-roadmap-v06-RESEARCH
---

# 设计：总纲 v0.6 编辑图

> 输入：[RESEARCH.md](RESEARCH.md) §2 的 F-1..F-6。本文件给出精确落点与不变量。

## 1. 设计不变量

1. **106 计数不变**：不新增/删除验收 ID。
2. **路线不变**：不调换 G0a/G-1/G0b/G2/G3 串行关系。
3. **只做状态同步**：不新增阶段、不改 C 套件成员。
4. **P-015 为准**：R-3 结论引用 P-015，不沿用 P-014 的“拒绝”表述。
5. **G0b 只标状态**：不把交付物缺口写成新的验收项。

## 2. 编辑落点

| # | 节 | 改动 |
|---|---|---|
| E-01 | 头部 | `version: 0.6`、`date: 2026-11-10`、新增 v0.6 修订块 |
| E-02 | §4 G-1 | 标题加“已完成（P-006，2026-11-08）”；加状态注（28 passed、C-9、missing=0） |
| E-03 | §4 G0b | 标题加“未就绪”；加状态注（缺 SPEC_PROCESS/scripts/spec/grandfather/spec-gates；Q3 待裁决） |
| E-04 | §7 Q17 | “待确认”改为“已裁决（P-012/P-013）：API-first；CLI opt-in；ACP 仅 LLM 层” |
| E-05 | §11 | 新增三行：P-011..P-013、P-014、P-015 |
| E-06 | §4 G3 | 加“候选增量（P-014/P-015，不改 106 计数）”：revision_log/impact_set、R-3a/b/c 触发 |

## 3. 影响面

- 文档：仅 `arc-master-roadmap.md`；新增 P-016 四文档与决策流。
- 代码：`researchclaw/` 零改动。
- 计数：106 不变；覆盖率脚本期望 `accept=106 missing=0`。
- 回滚：`git revert` 单提交；无数据迁移。

## 4. 未决项

沿用 [RESEARCH.md](RESEARCH.md) §5 的 U-1..U-3。
