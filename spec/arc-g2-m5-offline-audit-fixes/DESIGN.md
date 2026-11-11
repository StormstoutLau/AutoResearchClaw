---
id: arc-g2-m5-offline-audit-fixes-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g2-m5-offline-audit-fixes-RESEARCH]
upstream: arc-g2-m5-offline-audit-fixes-RESEARCH
---

# 设计：G2 M5 复审缺陷修复

> 基于 [RESEARCH.md](RESEARCH.md)。所有改动限于比对边界与 CLI，判定内核零变更。

## 1. 改动面

| 文件 | 改动 |
|---|---|
| `researchclaw/evidence/stage_hooks.py` | `compare_claims` 增 duplicate/orphan 集合检查；`run_stage20_gate` 增重复 id 阻断与 `duplicate_claim_ids` |
| `researchclaw/evidence/offline_audit.py` | `skipped=no_claims` 收紧为「无 claims 且无 production」 |
| `researchclaw/cli.py` | 版本参数显式判空；`--output` 失败捕获；提示走 stderr |
| `tests/test_offline_audit.py` | +7 项 |

## 2. `compare_claims` 算法（含 D-5 集成约束）

```text
keys   = [_claim_key(claim, i) for i, claim in enumerate(claims)]
counts = Counter(keys)

# 集合检查无条件执行（P-067 D-5）
for key where counts[key] > 1:
    diffs += duplicate_claim_id

if claims and not production:
    skipped = "no_production_gate"          # 逐条循环保持守卫
else:
    for each claim:
        audit_claim → status/deliverable
        比对 production[key] → missing / status_mismatch / deliverable_mismatch

# 对称孤儿检查无条件执行
for key in sorted(set(production) - set(keys)):
    diffs += orphan_production_decision
```

**为什么守卫不能去掉**：naive 集成会在续跑（有 claims、无 gate）时产出 `missing_production_decision`，使 `consistent=False`，Stage 23 以 `E23_CLAIM_DRIFT` 阻断合法续跑（P-067 SIM 实证）。

## 3. `run_stage20_gate` 重复 id

```text
claim_keys    = [...]
duplicate_keys = sorted(k for k, n in Counter(claim_keys).items() if n > 1)
...
for key in duplicate_keys:
    blocked += {claim_id: key, status: None,
                reasons: ["duplicate_claim_id"], problems: ["duplicate_claim_id"]}
payload["duplicate_claim_ids"] = duplicate_keys
```

- `decisions` 仍为 dict（后写覆盖），但 verdict 必为 `block`，Stage 20 失败，下游不会消费被覆盖的 decision。
- `duplicate_claim_ids` 仅作审计说明，不改变 `total`。

## 4. CLI

| 场景 | 行为 |
|---|---|
| `--policy-version` 缺省 | `CURRENT_POLICY_VERSION` |
| `--policy-version 0` / 负数 | stderr 提示，exit 2，stdout 为空 |
| `--output` 写失败（OSError） | stderr 提示，exit 2 |
| `--output` 成功 | 提示写 **stderr**；`--json` 时 stdout 仍为纯 JSON |
| 一致 / 漂移 | exit 0 / 1 |

## 5. 契约变更

| 位置 | 变更 |
|---|---|
| `compare_claims` diff reasons | +`duplicate_claim_id`、+`orphan_production_decision` |
| `claim_gate.json` | +`duplicate_claim_ids`；blocked 可含 `duplicate_claim_id` |
| offline report | `skipped` 不再在「有 production 无 claims」时出现 |
| Stage 23 | 孤儿/重复 → `consistent=False` → `E23_CLAIM_DRIFT` |

## 6. 测试设计（+7）

| 组 | 用例 |
|---|---|
| 孤儿 | 删一行 → offline/Stage 23 均报 `orphan_production_decision`；整删 → 孤儿 diff 且无 `skipped` |
| 重复 | gate block + `duplicate_claim_ids`；offline 报 `duplicate_claim_id` |
| CLI | `--policy-version 0` → exit 2、stdout 空；`--json --output` stdout 纯 JSON、提示在 stderr |

## 7. 不变量

- 判定内核（`evaluate_claim`/`audit_claim`/AR）零变更。
- 正常管线 claim/decision 1:1，不触发新增 diff。
- 续跑（有 claims 无 gate）仍 `skipped=no_production_gate, consistent=True`。
- 无 claims 且无 production → `skipped=no_claims, consistent=True`。
