---
id: arc-roadmap-v07-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-10
depends: [arc-roadmap-v07-IMPLEMENTATION]
upstream: arc-roadmap-v07-IMPLEMENTATION
---

# 验收清单：总纲 v0.7

## 1. 内容验收

- [x] 版本 0.7，标题与修订记录更新
- [x] G0b 标题“未就绪（调研完成，待实施）”
- [x] 状态注含 P-017 实测（6 钩子全绿但组成不符）
- [x] 状态注含 S-1/T-1/H-1 推荐
- [x] 交付物含 `spec_map.py`、`blackbox_check.py`、根兼容壳
- [x] A0-1 明确“必需六 + 两额外”
- [x] 表后注明 A0-2..A0-5 机制已存在、负向用例待固化
- [x] Q3 写 P-017 建议（空 grandfather + 90 天），仍标待确认
- [x] Q11 写调研确认（G0a 四道足够；G0b 补 m7/repo/blackbox + 两额外）
- [x] 外锚扩为 Spec Kit/OpenSpec/ISO 29148/SonarQube/pre-commit
- [x] §11 增 P-017 依据行
- [x] 106 计数未变

## 2. 边界

- [x] 未新增/删除验收 ID
- [x] 未改路线顺序或 C 套件
- [x] 未裁决 Q3/Q11
- [x] 未实施 G0b 迁移/钩子/CI
- [x] 未改 `researchclaw/` 代码

## 3. 机检

- [x] V1 `roadmap_coverage_check --check` → accept=106, missing=0
- [x] V2 `dc_validator` → 0 违规
- [x] V3 `step-gate` → 5/5 pass
- [x] V4 `console_gen --check` → 一致
- [x] V5 `private_config_check` → exit 0
- [x] V6 `step_enforce --base HEAD` → mode=batch, exit 0
