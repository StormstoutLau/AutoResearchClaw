---
id: arc-q3-grandfather-policy-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-10
depends: [arc-q3-grandfather-policy-IMPLEMENTATION]
upstream: arc-q3-grandfather-policy-IMPLEMENTATION
---

# 验收清单：Q3 裁决调研

## 1. 调研完整性

- [x] Q3 拆成新文档/存量/豁免边界三个子问题
- [x] 实测当前 `pre-commit run --all-files` exit 0、DC 0 违规
- [x] 确认当前无存量违规，grandfather 可为空
- [x] 对比 A/B/C/D 四方案及优缺点
- [x] 定义语义触碰 vs 非语义维护
- [x] 外部锚点 ≥8 项，标验证状态
- [x] 方案评分覆盖新代码/存量/应急/复杂度/审计/成本/债务
- [x] 明确建议 B 及 7 条参数
- [x] 说明不选 A/C/D 的理由

## 2. 设计输入

- [x] `grandfather.yaml` schema 与字段规则
- [x] `dc_validator` 读取/过期/fail-closed 规则
- [x] 续期一次、90 天、owner/reason
- [x] 只豁免 DC1/DC2/DC3；不豁免 DC4/DC5/Step/digest/CONSOLE
- [x] 实施批 6 条验收
- [x] T1 档位理由

## 3. 边界

- [x] 未创建 `spec/grandfather.yaml`
- [x] 未改 `scripts/dc_validator.py`
- [x] 未改总纲 Q3 状态
- [x] 未实施 G0b
- [x] 未改 `researchclaw/` 代码

## 4. 机检

- [x] V1 `dc_validator` → 0 违规
- [x] V2 `step-gate` → 5/5 pass
- [x] V3 `console_gen --check` → 一致
- [x] V4 `private_config_check` → exit 0
- [x] V5 `step_enforce --base HEAD` → mode=batch, exit 0

## 5. 裁决后下一批

- [ ] 总纲 Q3 标记“已裁决（B）”
- [ ] G0b 实施批：创建空 `grandfather.yaml`
- [ ] `dc_validator` 增加读取/过期/schema 校验
- [ ] 固化 6 条验收
