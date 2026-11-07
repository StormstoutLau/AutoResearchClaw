---
id: arc-roadmap-verdict-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-08
depends: [arc-roadmap-verdict-IMPLEMENTATION]
upstream: arc-roadmap-verdict-IMPLEMENTATION
---

# 验收清单：总纲 v0.4 落地

## 1. 裁决完整性

- [x] D-1=A 落地：C-9 覆盖 H-1..H-5、生效 G-1；C-7 收缩为 FC/FA、生效 G7
- [x] D-2=C 落地：A2-4/5/6 谓词化且 ID 未变；G2 交付物含三谓词 + fixture
- [x] A3-1 扩写覆盖 Stage 22；G3 交付物含 Stage 22 接线（Stage 22 无归属缺口闭环）
- [x] D-3 矩阵首批 12 条（计数按复核 F-1 修正）
- [x] D-4 最小集在 §1 显式定义且 §6 引用一致
- [x] D-5 交付物缺口 10 条全部补位（G1 +7、G3 +4、G5 +2，含 Stage 22）
- [x] D-6 声明重写 + 覆盖率脚本 + CI job
- [x] D-7 Q18/Q19/Q20 登记且标题计数同步（20 项）
- [x] 复核 F-1..F-8 全部有 disposition（3 项落地修复、4 项勘误登记、1 项佐证）

## 2. 不变量

- [x] 106 条验收计数不变（V5）
- [x] 12 阶段、依赖拓扑、§3 阶段总表计数不变
- [x] P-004 归档四文档未被修改
- [x] `researchclaw/` 代码零改动（仅新增独立脚本 + ci.yml）

## 3. 机检

- [x] V1 `roadmap_coverage_check.py --check` 退出码 0（accept=106 missing=0）
- [x] V2 dc-validator 四文档 + PROGRESS/CONSOLE 0 违规
- [x] V3 step-gate 五步 pass
- [x] V4 console_gen --check 退出码 0
- [x] V6 C-9 含 H-1..H-5、C-7 为 FC/FA

## 4. 未纳入本批

- Q18/Q19/Q20 裁决；H-1..H-8 pytest 实现；预算字段代码统一
