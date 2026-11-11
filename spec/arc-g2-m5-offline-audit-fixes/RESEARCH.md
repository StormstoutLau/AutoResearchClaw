---
id: arc-g2-m5-offline-audit-fixes-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g2-m5-offline-audit-IMPLEMENTATION]
upstream: arc-g2-m5-offline-audit-IMPLEMENTATION
---

# 调研：G2 M5 复审缺陷修复（P-068）

> **Feature**：P-068，P-065/P-066/P-067 复核结论的修复批。
> **Spec 步骤**：T1 完整管线（修改 `stage_hooks.py`/`offline_audit.py`/`cli.py`，新增 7 项测试）。
> **结论先行**：四项缺陷全部位于**比对边界与 CLI 语义**，判定内核不变。修复核心是把 `compare_claims` 从「单向 claim→decision」扩为**双向集合校验**（孤儿 + 重复），并严格区分「续跑无 gate」与「gate 与 claims 不一致」。P-067 D-5 的集成约束是硬要求：**逐条循环保留原守卫，duplicate/orphan 集合检查无条件执行**。

## 1. 输入

| 来源 | 内容 |
|---|---|
| P-065 | D-1 孤儿生产决定不可见；D-2 `--policy-version 0` 被吞；D-3 stdout 污染 |
| P-066 | 六探针复现 + D-4 重复 `claim_id`；F-1..F-5 修复草案 |
| P-067 | D-5：F-1 naive 集成破坏跳过语义；正确集成 = 守卫保留 + 集合检查无条件；O-B `--output` 写失败未捕获 |

## 2. 一手事实（F）

| # | 事实 | 证据 |
|---|---|---|
| F-1 | `compare_claims` 只遍历 claims，无 `set(production) − set(claim_keys)` 检查；claims 为空时循环空转 | [`stage_hooks.py`](../../researchclaw/evidence/stage_hooks.py) `compare_claims` |
| F-2 | gate 以 `claim_id` 为 decisions 键，重复 id 后写覆盖前写 | 同上 `run_stage20_gate` |
| F-3 | `cmd_audit` 用 `args.policy_version or CURRENT_POLICY_VERSION`；提示行走 stdout | [`cli.py`](../../researchclaw/cli.py) `cmd_audit` |
| F-4 | `offline_audit` 在 claims 为空时无条件 `skipped=no_claims` | [`offline_audit.py`](../../researchclaw/evidence/offline_audit.py) |
| F-5 | 原 29 项 M5 测试中无孤儿/重复 fixture；全部 gate 由同一批 claims 生成（1:1） | `tests/test_offline_audit.py` 枚举 |

## 3. 决策

| # | 决策 | 理由 |
|---|---|---|
| D-1 | `compare_claims` 增孤儿 diff：`orphan_production_decision`，`production` 字段带状态 | 有 decision 无 claim 是完整性缺口；Argo CD Orphaned Resources 先例 |
| D-2 | 重复 `claim_id`：gate 直接 block（`duplicate_claim_id` + payload `duplicate_claim_ids`）；审计同步报 diff | 防一条 decision 冒充多条 claim；Flyway validate 先例 |
| D-3 | 集合检查**无条件执行**；逐条循环保留 `if claims and not production: skipped` 守卫 | P-067 D-5 仿真实证：naive 集成会阻断合法续跑 |
| D-4 | `--policy-version < 1` → exit 2；`--output` 失败 → exit 2；提示走 stderr | C4 要求版本 ≥1；stdout 只放数据 |
| D-5 | `skipped=no_claims` 仅在「无 claims **且**无 production」时写 | 有 gate 无 claims 属于漂移，不是空跑 |

## 4. 范围

**做**：F-1..F-5、O-B、7 项测试、M5 四文档升版。
**不做**：O-1 gate verdict 透传、O-2 claims 溯源、O-3 报告原子写、O-5 状态矩阵绑定（留后续）；不改判定内核与 C4。
