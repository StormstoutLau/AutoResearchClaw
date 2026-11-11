---
id: arc-g2-m5-offline-audit-fixes-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-11
depends: [arc-g2-m5-offline-audit-fixes-IMPLEMENTATION]
upstream: arc-g2-m5-offline-audit-fixes-IMPLEMENTATION
---

# 验收清单：G2 M5 复审缺陷修复（P-068）

## 1. D-1 孤儿生产决定

- [x] 删一行 → offline 报 `orphan_production_decision`，`consistent=False`
- [x] 同一 run → Stage 23 `consistent=False`
- [x] 整删 claims（保留 gate）→ 孤儿 diff，无 `skipped`
- [x] 正常 1:1 run 不触发孤儿

## 2. D-4 重复 `claim_id`

- [x] gate verdict `block`，payload `duplicate_claim_ids`
- [x] blocked 含 `duplicate_claim_id`
- [x] offline 报 `duplicate_claim_id`
- [x] 单条 claim 不触发

## 3. D-2 / D-3 / O-B CLI

- [x] `--policy-version 0` → exit 2，stdout 空，stderr 提示
- [x] `--policy-version` 缺省 → `CURRENT_POLICY_VERSION`
- [x] `--json --output` → stdout 纯 JSON，提示在 stderr
- [x] `--output` 写失败 → exit 2（O-B）
- [x] 一致/漂移仍 exit 0/1

## 4. D-5 集成约束

- [x] 逐条循环保留 `if claims and not production` 守卫
- [x] duplicate/orphan 集合检查无条件执行
- [x] 续跑（有 claims 无 gate）仍 `skipped=no_production_gate, consistent=True`
- [x] 「有 production 无 claims」不再 `skipped`

## 5. 回归

- [x] M5 36 passed（3.13.5）
- [x] M4+M5 95 passed（3.13.5 与 3.11.15）
- [x] 相关回归 108 passed
- [x] 既有 29 项零回归
- [x] 原 P-066 六探针按修复后预期复跑

## 6. 机检

- [x] pre-commit 9/9
- [x] `step_enforce` exit 0（P-068 session 5/5）
- [x] `roadmap_coverage_check.py --check` accept=106 missing=0
- [x] `repo_stats --check` / `console_gen --check` 一致
- [x] DC 契约校验通过

## 7. 未纳入本批

- [ ] O-1 gate verdict 透传（报告增强）
- [ ] O-2 claims 来源溯源（报告增强）
- [ ] O-3 报告原子写
- [ ] O-5 状态矩阵绑定 `STATUS_ORDER`
- [ ] O-6 退出码语义文档注明
