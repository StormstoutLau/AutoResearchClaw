---
id: arc-roadmap-fix-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-06
depends: [arc-roadmap-fix-IMPLEMENTATION]
upstream: arc-roadmap-fix-IMPLEMENTATION
---

# 验收清单：总纲 v0.2 订正

## 1. 修正完整性

- [x] D-1：G3 交付物不再出现「H-4 已落地」，改为「待 G-1 的 H-4 落地」
- [x] D-2：§5 新增 C-9，且九个套件均有「生效起点」列
- [x] D-3：§5 规则含 `N/A` 语义与覆盖范围声明
- [x] D-4：A2-3 改为可冻结口径，不再出现「65 项」
- [x] D-5：§7 标题为 16 项；Q11 与 §10 均为 4 道激活钩子
- [x] D-6：front-matter 与标题均为 v0.2，且有修订块

## 2. 语义正确性

- [x] H-1..H-4 全部出现在 C-9，G-1 数据正确性有回归闸门
- [x] C-9 的生效起点为 G-1，不早于其成员交付阶段
- [x] G0a 出口在 `N/A` 语义下可满足（不再被 H-1..H-4 卡死）
- [x] A1-8 进入 C-4，A0a-4 进入 C-5（原 P3-03 漏项已补）
- [x] 106 条验收计数复算仍为 106，阶段与依赖图未变

## 3. 边界

- [x] 未修改 15 份已忽略调研文档
- [x] 未修改 P-002 四文档与审查报告
- [x] 未修改任何运行时代码
- [x] 未把 65 直接替换为 77（避免固化错误口径）

## 4. 机检

- [x] V1 钩子作用域内 `dc_validator` 退出码 0（裸跑全仓有 141 条既有违规，见 IMPLEMENTATION §2 注）
- [x] V2 验收计数复算 = 106
- [x] V3 C 套件对 H-1..H-4 覆盖 = 4/4
- [x] V4 全文不再出现「H-4 已落地」
- [x] V5 `console_gen --check` / `step-gate` / `rework_graph_check` 退出码 0
- [x] V6 `pre-commit run --all-files` 四道钩子全绿（不得使用 `SKIP=`）
