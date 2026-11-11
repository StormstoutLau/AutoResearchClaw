---
id: arc-g2-m5-offline-audit-fixes-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g2-m5-offline-audit-fixes-DESIGN]
upstream: arc-g2-m5-offline-audit-fixes-DESIGN
---

# 实施记录：G2 M5 复审缺陷修复（P-068）

> **状态**：F-1..F-5 与 O-B 全部落地；M5 测试 29→36，M4+M5 88→95 双环境通过。CHECKLIST accepted。

## 1. 改动清单

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `researchclaw/evidence/stage_hooks.py` | 修改 | `Counter` 导入；`compare_claims` 增 duplicate/orphan 集合检查（守卫保留）；`run_stage20_gate` 增 `duplicate_keys` 阻断与 `duplicate_claim_ids` |
| 2 | `researchclaw/evidence/offline_audit.py` | 修改 | `skipped=no_claims` 收紧为 `not claims and not production` |
| 3 | `researchclaw/cli.py` | 修改 | 版本显式判空（<1→2）；`--output` OSError→2；提示改 stderr |
| 4 | `tests/test_offline_audit.py` | 修改 | +7 项（孤儿×3、重复×2、CLI×2） |
| 5 | `spec/arc-g2-m5-offline-audit/DESIGN.md` | 修改 | v1.1：diff reasons、gate payload、skip 语义、CLI |
| 6 | `docs/PROGRESS.md` / `arc-master-roadmap.md` | 修改 | P-068 行 / v1.3l |

**不改**：C4 schema、AR 判据、`evaluate_claim`/`audit_claim`、M0–M4 契约。

## 2. 修复后行为（原探针复跑）

| 探针 | 修复前 | 修复后 |
|---|---|---|
| D-1a 删一行 | `consistent=True` | `consistent=False`，`orphan_production_decision c-22222222`（Stage 23 同步 False） |
| D-1b 整删 | `skipped=no_claims, True` | `consistent=False`，孤儿 diff，无 `skipped` |
| D-1c 重复 id | gate `pass`, `decisions=1` | gate `block`，`duplicate_claim_ids=['c-...']`；offline 报 `duplicate_claim_id` |
| D-2 `--policy-version 0` | `rc=0, expected=2` | `rc=2`，stdout 空，stderr 提示 |
| D-3 `--json --output` | stdout 非 JSON | stdout 纯 JSON，提示在 stderr |

## 3. 读数

| 项 | 读数 |
|---|---|
| M5 套件 | **36 passed**（3.13.5） |
| M4+M5 | **95 passed**（3.13.5 与 3.11.15 双环境） |
| 相关回归（CLI/simulated/fabrication/claim verifier/AR/sidecar/contracts） | **108 passed** |
| 既有 29 项 | 零回归 |
| 机检 | pre-commit 9/9；step_enforce P-068 5/5；coverage missing=0 |

## 4. 施工注意

1. **D-5 集成约束**：逐条循环必须保留 `if claims and not production` 守卫；集合检查放守卫外。否则续跑会被 `E23_CLAIM_DRIFT` 阻断。
2. **重复 id 的 decisions 仍折叠**：gate 已 block，不得复用该 payload 做下游消费；`duplicate_claim_ids` 仅审计。
3. **stdout 纪律**：`--json` 时 stdout 只放 JSON；所有提示（report written / version error / write error）走 stderr。
4. **skip 语义**：`no_production_gate` 与 `no_claims` 都是 `consistent=True` 的合法状态；「有 production 无 claims」不是 skip，是 drift。
