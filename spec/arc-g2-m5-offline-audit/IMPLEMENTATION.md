---
id: arc-g2-m5-offline-audit-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g2-m5-offline-audit-DESIGN]
upstream: arc-g2-m5-offline-audit-DESIGN
---

# 实施记录：G2 M5 离线审查模式（P-064）

> **状态**：施工完成，本文件记录实际改动与读数；CHECKLIST accepted。G2 自此收口（M0–M5 全部交付）。
> **依据**：[DESIGN.md](DESIGN.md) §2（共享比对）、§3（离线审计）、§4（CLI）、§5（测试）。

## 1. 改动清单

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `researchclaw/evidence/claim_policy.py` | 修改 | `CURRENT_POLICY_VERSION = 2`；`build_claim_records` 引用 |
| 2 | `researchclaw/evidence/stage_hooks.py` | 修改 | 提取共享 `compare_claims` + `_load_production_gate`；`run_stage23_consistency` 复用（行为零变化） |
| 3 | `researchclaw/evidence/offline_audit.py` | 新增 | `run_offline_audit`（只读）+ `write_audit_report` + `policy_version_mismatch` 核验 |
| 4 | `researchclaw/cli.py` | 修改 | `audit` 子命令 + `cmd_audit` + 派发分支 |
| 5 | `tests/test_offline_audit.py` | 新增 | 29 项测试 |
| 6 | `.github/workflows/ci.yml` | 修改 | 固定清单加入 `test_offline_audit.py` |
| 7 | `arc-master-roadmap.md` | 修改 | v1.3k：M5 交付、G2 收口 |
| 8 | `docs/PROGRESS.md` | 修改 | P-064 执行行 |

**不改**：C4 schema、AR 判据、A2-4/5/6 语义、Stage 9/20 接线、M0–M4 契约。

## 2. 关键实现点

### 2.1 共享比对

`compare_claims` 含跳过语义（`claims 非空 且 production 空 → no_production_gate`），返回 `{"diffs", "audit", "skipped"}`。`run_stage23_consistency` 与 `run_offline_audit` 均消费同一函数——审计平面与生产平面在规则层面不可能分歧。

### 2.2 版本核验

`_policy_version_diffs` 逐条比对 `claim.policy_version != expected` → `policy_version_mismatch`。版本锚点是 claims 自带字段（RESEARCH F-4/F-5）；跳过场景仍执行（版本不符独立于生产决定存在）。

### 2.3 CLI 退出码

`cmd_audit`：目录缺失→2；`ClaimStreamError`→2；diffs 非空→1；否则 0。`--policy-version` 缺省取 `CURRENT_POLICY_VERSION`。

### 2.4 只读

除 `--output` 指定路径外，`run_offline_audit` 不写任何文件；测试以全树字节快照断言。

## 3. 验证读数

| 项 | 读数 |
|---|---|
| M5 测试 | **29 passed**（3.13.5） |
| M4+M5 合计 | **88 passed**（3.13.5 与 3.11.15 双环境） |
| 相关回归（CLI/simulated/fabrication/claim verifier/AR/sidecar/contracts） | **108 passed** |
| 既有 M4 用例 | 59 项零回归（`compare_claims` 重构后原样通过） |
| CLI 冒烟 | 合成 run：consistent→exit 0；`--policy-version 1`→`policy_version_mismatch`→exit 1；目录缺失→exit 2；`--help` 正常 |
| 机检 | pre-commit 9/9；step_enforce P-064 5/5；coverage missing=0 |

## 4. 施工注意

1. **比对函数是唯一比对实现**：后续任何状态/可发布性判定变更只改 `evaluate_claim`/`compare_claims`，禁止在 CLI 或 Stage 层重写比对。
2. **只读纪律**：`run_offline_audit` 不得新增写路径；报告落盘只经 `write_audit_report`（显式 `--output`）。
3. **版本升级路径**：未来 `policy_version=3` 时，只需改 `CURRENT_POLICY_VERSION` 并让历史 run 用 `--policy-version 2` 复核——审计报告会逐条给出 `policy_version_mismatch`。
4. **跳过语义勿收紧**：`no_production_gate`/`no_claims` 是合法续跑/无假设状态，不得改为阻断。

## 5. P-068 补记（2026-11-11）

P-065..P-067 复审缺陷已由 [修复设计包](../arc-g2-m5-offline-audit-fixes/DESIGN.md) 关闭：`compare_claims` 增双向集合检查（`orphan_production_decision`/`duplicate_claim_id`），gate 对重复 id 直接 block，CLI 版本参数/输出流修正。**P-067 D-5 集成约束**：集合检查无条件执行、逐条循环保留跳过守卫。M5 套件由 29 增至 **36 passed**，M4+M5 合计 **95 passed** 双环境；既有 29 项零回归。
