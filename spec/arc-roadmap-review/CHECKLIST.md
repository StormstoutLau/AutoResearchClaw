---
id: arc-roadmap-review-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-06
depends: [arc-roadmap-review-IMPLEMENTATION]
upstream: arc-roadmap-review-IMPLEMENTATION
---

# 验收清单：总纲与关联文档审查

## 1. 覆盖完整性

- [x] 总纲 12 阶段、106 条验收全部纳入审查范围
- [x] 8 条 H-1..H-8 代码事实逐条核验
- [x] G5 三组源数据（2,487 / 1,824 / 20,235）与源文件比对
- [x] 26 条外部引用逐条核验
- [x] 15 份文档的 `id/depends/upstream` 闭合检查
- [x] §5 C 套件对 106 条验收的覆盖检查

## 2. 规则合规

- [x] RULE-1：审查为独立 pass，非与正文同一次写入
- [x] RULE-2：106 条计数可逐阶段复算；无法复现项已单列
- [x] RULE-3：Linux-only 验收项已标记
- [x] RULE-4：报告声明单视角
- [x] RULE-5：声明未满足异质基座
- [x] RULE-6：每条 P1/P2 绑定 E1–E4 证据，E5 未入结论

## 3. 结论完整性

- [x] 已核验为真的项单独列出，避免全盘否定
- [x] P1/P2/P3 分级明确，每项含证据与影响阶段
- [x] 工程可行性覆盖关键路径、前置、可判定性、平台、成本、回滚
- [x] 给出最小修复顺序

## 4. 机检

- [x] `python scripts/dc_validator.py` 对本批 Spec 文档退出码 0
- [x] `spec_runner.py step-gate --session specwf-p002-arc-roadmap-review-20261106 --expect research design implement verify finalize` 退出码 0
- [x] `python scripts/console_gen.py --check` 退出码 0
- [x] `python scripts/rework_graph_check.py` 退出码 0
