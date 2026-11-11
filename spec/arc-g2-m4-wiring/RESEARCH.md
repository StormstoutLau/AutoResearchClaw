---
id: arc-g2-m4-wiring-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g2-m0-contracts, arc-g2-m1-ar-checks, arc-g2-m3-implementation]
upstream: arc-g2-m3-implementation
---

# 调研：G2 M4 Stage 9/20/23 接线与双平面测试

> **Feature**：P-061，G2 M4 实施批。
> **Spec 步骤**：T1 完整管线（Layer-1：新增 `researchclaw/evidence/claim_policy.py`、`stage_hooks.py`、两个测试文件，并修改 Stage 9/20/23）。
> **结论先行**：M0–M3 已把契约、AR 判据与 sidecar 判定内核交付完毕，但 `ClaimRecord` 尚未进入任何生产 Stage。M4 让 **Stage 9 产出 C 类 claim**、**Stage 20 执行 A2-4/A2-5/A2-6 发布谓词**、**Stage 23 用同一纯函数重算并与 Stage 20 的生产决定逐条比对**（双平面）。所有判定逻辑集中在纯函数 `evaluate_claim`，生产与审计共享；Stage 层只负责 IO 与失败映射。

## 1. 问题与范围

### 1.1 现状

| # | 事实 | 证据 |
|---|---|---|
| F-1 | Stage 9 只落 `exp_plan.yaml`；`hypotheses.md` 是其上游输入，尚无 `ClaimRecord` 产物 | [`_experiment_design.py`](../../researchclaw/pipeline/stage_impls/_experiment_design.py) 末尾 return |
| F-2 | C4 契约 14 项必填且 `additionalProperties: false`；**没有 `annotation` 字段** | [`c4_claim_record.schema.json`](../../contracts/v1/c4_claim_record.schema.json) |
| F-3 | AR-01/AR-02 的严重度为 `downgrade`，AR-05/AR-06 为 `warn + cap`，AR-03/AR-04/AR-07/AR-08 为 `fail` | [`ar_checks.py`](../../researchclaw/evidence/ar_checks.py) 各判据 |
| F-4 | Stage 20 已有文本级 `_write_claim_verification`（`claim_verification.json`），与 C4 `ClaimRecord` 无关，不能替代 A2-4..A2-6 | [`_review_publish.py`](../../researchclaw/pipeline/stage_impls/_review_publish.py) `_write_claim_verification` |
| F-5 | Stage 23 只做引文核验（bib → CNKI/CrossRef/OpenAlex/arXiv/S2），没有 claim 级一致性检查 | `_execute_citation_verify` |
| F-6 | `_read_prior_artifact` 按 stage 目录 **逆序** 查找，`stage-20` 优先于 `stage-09`；`load_claims` 独立 glob，按 stage 前缀显式选择 | [`_helpers.py`](../../researchclaw/pipeline/_helpers.py) `_read_prior_artifact` |
| F-7 | Stage 20 是 CRITICAL gate（不可跳过），Stage 9 也是 GATE | [`stages.py`](../../researchclaw/pipeline/stages.py) |
| F-8 | 总纲 A2-5 要求 `NUMERICALLY_VERIFIED` 必须携带 `annotation`；C4 又不允许扩展字段 | 见 F-2；[`arc-master-roadmap.md`](../../arc-master-roadmap.md) §G2 |

### 1.2 范围

- Stage 9：把 `hypotheses.md` 的条目机械抽取为 C 类、`speculation`、`stage1` 的 ClaimRecord，写 `stage-09/claims.jsonl`。
- Stage 20：读取 claim，执行 AR 检查 + 降级 + 封顶 + 发布谓词；写 `stage-20/claims.jsonl` 与 `stage-20/claim_gate.json`；不可发布则 Stage 20 FAILED。
- Stage 23：读取 Stage 20 的 claim 与生产决定，用 `audit_claim` 重算，逐条比对 `status`/`deliverable`；漂移则 Stage 23 FAILED。
- 双平面测试：生产决定与审计决定在同一输入下必须一致；篡改 `stage-20/claims.jsonl` 必须触发漂移。

### 1.3 不做

- 不在 M4 引入 Stage 14/17 的 claim 接线（属 G3）。
- 不做 Lean/sidecar 的批量调用（M3 已交付单次 `run_lean_check`，批量属后续）。
- 不改 C4 schema；不新增 `annotation` 字段。
- 不实现 A7-3 的跨平面长期审计（属 G7），M4 只交付可复算的即时比对。

## 2. 关键决策

| # | 决策 | 理由 | 备选与否决 |
|---|---|---|---|
| D-1 | Stage 9 产出的 hypothesis claim 一律 **C 类 / speculation / stage1 / policy_version=2** | 假设是探索性陈述，尚无证据与形式化；C 类不触发 AR-05/AR-07 的 A/B 约束 | 设为 A 类 → 无证据立即触发 AR-07 fail，Stage 20 全量阻断 |
| D-2 | 生产与审计共用 `evaluate_claim`；`audit_claim` 只是无 IO 别名 | 双平面的价值在于「同一纯函数、不同输入路径」；两套实现必然漂移 | 审计端另写一套规则 → 无法排除实现分歧 |
| D-3 | `annotation` 走 run 级 `annotations.json`（`{claim_id: text}`），不进 C4 | C4 `additionalProperties: false`，扩字段需破坏 M0 契约；A2-5 只要求谓词消费 annotation | 修改 C4 → 违反 M0 冻结；把 annotation 塞进 `statement` → 不可机检 |
| D-4 | Stage 23 检测到漂移 → FAILED（`E23_CLAIM_DRIFT`）；若完全没有 Stage 20 生产决定 → 记 `skipped=no_production_gate` 并放行 | 从 Stage 21 续跑的 run 没有 Stage 20 产物，不能误杀；有产物则必须一致 | 无产物也阻断 → 破坏 G1b 续跑 |
| D-5 | Stage 9 hook 失败仅 warning；Stage 20/23 hook 失败 fail-closed | Stage 9 的 claim 抽取是附加产物，不应阻断实验设计；门禁与审计是安全边界 | 全部 fail-open → 门禁可被异常绕过 |
| D-6 | Stage 20 的 gate 在 `_write_claim_verification` 之后、模拟数据检查之前执行 | claim 契约优先级高于数据来源检查；两者都失败时先报 `E20_CLAIM_CONTRACT` | 放在门禁评分后 → 低分论文先触发评分错误，claim 证据丢失 |

## 3. 谓词语义

| 谓词 | 输入 | 输出 | 负向用例 |
|---|---|---|---|
| `can_enter_deliverables(claim, findings)` | 任意 claim + AR findings | `status ∈ {failed, falsified}` 或存在 `fail` finding → False | `FALSIFIED` 被放行即失败（A2-4） |
| `requires_annotation(claim)` | 任意 claim | `status == numerically_verified` → True | 数值 claim 无 annotation 仍通过即失败（A2-5） |
| `downgrade_missing_citation(claim)` | 任意 claim | A/B 缺完整引文 → 复制 claim、追加 `assumptions`、`status=speculation`，返回 `(working, True)` | 直接 fail 即违背 A2-6 |
| `evaluate_claim(claim, annotation)` | 任意 claim + 可选标注 | `ClaimDecision(claim, findings, deliverable, blocked_reasons, downgraded, capped)` | 生产/审计结果不一致即失败 |
| `audit_claim(claim, annotation)` | 同上 | 纯函数别名 | — |

`_evidence_complete` 要求至少一条 evidence 同时具备 `source_id`、`locator`、`quote`；缺一即视为缺引文（与 AR-01 的口径一致）。

## 4. 外锚

- JSON Schema 2020-12：C4 闭合 schema 是 D-3 的直接约束。
- W3C PROV-O：`EvidenceRef` 的 `source_id/locator/digest` 对应 `Entity` 标识；M4 只消费，不新增映射。
- 变异测试（M1）：谓词必须有可判红的负向用例。
- 总纲 A2-4/A2-5/A2-6 与 A7-3：M4 是 A7-3 的双平面预埋，不宣称 A7-3 完成。
