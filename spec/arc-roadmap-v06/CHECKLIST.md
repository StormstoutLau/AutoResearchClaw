---
id: arc-roadmap-v06-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-10
depends: [arc-roadmap-v06-IMPLEMENTATION]
upstream: arc-roadmap-v06-IMPLEMENTATION
---

# 验收清单：总纲 v0.6 状态同步

## 1. 内容验收

- [x] 版本升为 0.6，修订记录含 P-016
- [x] G-1 标记“已完成（P-006）”并注明 28 passed / C-9 / missing=0
- [x] G0b 标记“未就绪”，列出 4 类交付缺口与 Q3
- [x] Q17 改为“已裁决（P-012/P-013）”
- [x] §11 新增 P-011..P-013、P-014、P-015 三行
- [x] G3 增加 P-014/P-015 候选增量注，并声明 R-3 以 P-015 为准
- [x] 106 条验收 ID 未增未删
- [x] 阶段顺序、C 套件、G0b 验收标准未改

## 2. 一致性

- [x] P-014 的“R-3 拒绝”已被 P-015 取代，总纲只引用 P-015
- [x] G-1 状态与 P-006 CHECKLIST 一致
- [x] G0b 状态与 2026-11-10 交付物审计一致
- [x] Q17 状态与 P-012/P-013 实现一致
- [x] 新增依据行均指向存在的 `spec/` 文档

## 3. 边界

- [x] 未修改 `researchclaw/` 代码
- [x] 未新增/删除验收 ID
- [x] 未改阶段顺序或 C 套件成员
- [x] 未修改 P-011..P-015 归档文档

## 4. 机检

- [x] V1 `roadmap_coverage_check --check` → accept=106, missing=0
- [x] V2 `dc_validator` → 0 违规
- [x] V3 `step-gate` → 5/5 pass
- [x] V4 `console_gen --check` → 一致
- [x] V5 `private_config_check` → exit 0
- [x] V6 `step_enforce --base HEAD` → mode=batch, exit 0
