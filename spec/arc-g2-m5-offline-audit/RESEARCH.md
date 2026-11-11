---
id: arc-g2-m5-offline-audit-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g2-m4-wiring-fixes, arc-g2-m3-sidecar, arc-g2-m0-contracts]
upstream: arc-g2-m4-wiring-fixes
---

# 调研：G2 M5 离线审查模式 + 一致性套件

> **Feature**：P-064，G2 最后一个里程碑（R-03 §5.2 M5）。
> **Spec 步骤**：T1 完整管线（Layer-1：新增 `offline_audit.py` + `audit` CLI + 29 项测试；重构 `stage_hooks` 提取共享比对）。
> **结论先行**：M5 DoD 是「同一 claim 在生产/审查两条路径得到相同 `status`（同 `policy_version`）」。M4 已把判定收敛到单一纯函数 `evaluate_claim`，Stage 23 已有即时比对——缺的只是**离线入口**与**版本比对**。因此 M5 的正确形态极小：把 Stage 23 的比对抽成共享纯函数 `compare_claims`（防规则漂移），新增只读 `run_offline_audit` + `researchclaw audit` CLI（退出码 0/1/2），并以 claims 自带的 `policy_version` 字段做版本核验。

## 1. 一手事实（F）

| # | 事实 | 证据 |
|---|---|---|
| F-1 | R-03 §5.1 裁定：审查平面是 ARC 的**离线批次模式**（`arb audit`），不是独立进程/入口 | [`arb-v2-decisions-research-design.md`](../../arb-v2-decisions-research-design.md) §5.1「变化点」 |
| F-2 | R-03 §5.2 M5 DoD：同一 claim 生产/审查同 `status`（同 `policy_version`） | 同上 §5.2 里程碑表 |
| F-3 | M4 后判定唯一入口是 `evaluate_claim`；`audit_claim` 是其无 IO 别名；Stage 23 经 `compare_claims` 比对 | [`claim_policy.py`](../../researchclaw/evidence/claim_policy.py)、[`stage_hooks.py`](../../researchclaw/evidence/stage_hooks.py) |
| F-4 | C4 每条 claim 自带 `policy_version`（必填、integer≥1）；Stage 9 写 `CURRENT_POLICY_VERSION`；gate 不改写该字段 | [`c4_claim_record.schema.json`](../../contracts/v1/c4_claim_record.schema.json)、`build_claim_records` |
| F-5 | `claim_gate.json` 的 decisions **不带** policy_version——版本锚点只能取自 claims 本身 | M4 DESIGN §4 payload |
| F-6 | 既有 CLI 派发为 `if/elif args.command`，`report` 命令已用 `--run-dir` + `--output` 形态 | [`cli.py`](../../researchclaw/cli.py) `build_parser`/`main` |
| F-7 | P-062 遗留 O-1（封顶解除标注）/O-2（annotations 无生产者）标注为 M5/G3 输入；本批不解决 | [P-062 复审](../../docs/arc-g2-m4-wiring-review-20261111.md) O 表 |
| F-8 | 读侧 fail-closed（坏行/坏 gate JSON 抛 `ClaimStreamError`）与目录优先级（活目录优先）已由 P-063 落地 | [`stage_hooks.py`](../../researchclaw/evidence/stage_hooks.py) |

## 2. 决策

| # | 决策 | 理由 | 备选与否决 |
|---|---|---|---|
| D-1 | 抽取 `compare_claims(claims, production, annotations)` 供 Stage 23 与离线审计共用 | M5 的核心承诺是「两平面永不漂移」；两套比对实现本身就是漂移源 | Stage 23 保留私有实现 → 审计平面与生产规则可分歧 |
| D-2 | 版本锚点 = claims 自带的 `policy_version`（逐条比对 `--policy-version`，默认 `CURRENT_POLICY_VERSION`） | gate decisions 不带版本（F-5）；C4 每条 claim 已有该字段，无需改契约 | 给 gate payload 加版本 → 改 M4 冻结契约，超出最小面 |
| D-3 | 离线审计**只读**：不写 run 目录；报告经 stdout 或 `--output` 落任意路径 | 审计不得污染被审计对象；与「不写管线」承诺一致 | 写 `audit_report.json` 进 run → 篡改证据面 |
| D-4 | 退出码 0=一致（含空转）、1=漂移/版本不符、2=输入不可用 | 沿用 G1b 三态习惯（成功/可判定失败/环境性失败） | 全部归 1 → CI 无法区分坏输入与真漂移 |
| D-5 | `skipped` 语义与 Stage 23 完全一致：`no_production_gate`（有 claim 无 gate）/`no_claims`（无 claim），均 consistent=true | 续跑与无假设 run 是合法状态，审计如实报告而不新增政策 | 无 gate 即 fail → 破坏 G1b 续跑 |
| D-6 | `CURRENT_POLICY_VERSION = 2` 收敛进 `claim_policy.py`，`build_claim_records` 引用 | M5 DoD 的「同版本」需要一个唯一真值源 | 三处字面量 2 → 版本升级时必漏 |

## 3. 范围

**做**：`compare_claims` 重构（Stage 23 行为零变化）；`run_offline_audit`/`write_audit_report`；`researchclaw audit` CLI（`--run-dir/--json/--policy-version/--output`）；29 项测试（含 7 状态 × 双平面矩阵、只读性、确定性、失败封闭、CLI 三态退出码）。

**不做**：O-1/O-2（annotation 供给与封顶渲染语义，G3 输入）；gate payload 加版本字段（契约冻结）；跨 run 批量审计；`arb audit` 的远端/RPC 形态（R-03 明示 RPC 仅可选执行器）。
