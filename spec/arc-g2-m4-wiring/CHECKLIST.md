---
id: arc-g2-m4-wiring-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-11
depends: [arc-g2-m4-wiring-IMPLEMENTATION]
upstream: arc-g2-m4-wiring-IMPLEMENTATION
---

# 验收清单：G2 M4 Stage 9/20/23 接线与双平面

## 1. M4 DoD

- [x] Stage 9 产出 `stage-09/claims.jsonl`（C 类 / speculation / stage1 / policy_version=2）
- [x] Stage 20 读取 claim 并写 `stage-20/claims.jsonl` + `stage-20/claim_gate.json`
- [x] Stage 20 对不可发布 claim 返回 FAILED（`E20_CLAIM_CONTRACT`）
- [x] Stage 23 用 `audit_claim` 重算并写 `stage-23/claim_consistency.json`
- [x] Stage 23 对漂移返回 FAILED（`E23_CLAIM_DRIFT`）
- [x] 生产与审计共用 `evaluate_claim`，无第二套规则

## 2. A2-4 / A2-5 / A2-6

- [x] A2-4：`FALSIFIED` / `FAILED` → `can_enter_deliverables=False`（参数化 2 例）
- [x] A2-4：存在 `fail` finding → False；`warn`/`downgrade` → True
- [x] A2-5：`NUMERICALLY_VERIFIED` 无 annotation → `missing_annotation` 阻断
- [x] A2-5：补 `annotations.json` 后同 claim 通过
- [x] A2-5：非数值状态不要求 annotation（参数化 6 例）
- [x] A2-6：A 类缺引文 → 追加 assumptions + `speculation`，**不阻断**
- [x] A2-6：B 类缺 reasoning_chain → 降级；B 类链完整 → 不降级
- [x] A2-6：C 类不因缺引文降级
- [x] A2-6：降级不修改原 claim，重复评估不重复追加 assumptions

## 3. 双平面

- [x] 生产通过后立即审计 → `consistent=true`、`checked=1`
- [x] 篡改 `status` → `status_mismatch`，Stage 23 FAILED
- [x] 篡改 statement 触发 AR-03 → `deliverable_mismatch`
- [x] 续跑无 Stage 20 生产决定 → `skipped=no_production_gate` 且放行
- [x] 无 `references.bib` 仍写 `claim_consistency.json`
- [x] Stage 23 钩子异常 → `E23_CLAIM_DRIFT_INTERNAL`（fail-closed）

## 4. 不变式

- [x] C4 schema 未改；claim 无 `annotation` 字段
- [x] AR-01..08 未改；降级口径与 AR-01 的 A/B 条件一致
- [x] `failed`/`falsified` 不被 cap 抬升
- [x] Stage 9 抽取失败不阻断 `exp_plan.yaml`
- [x] Stage 20 gate 先于 SIM 检查；Stage 23 一致性先于 bib 核验
- [x] 无新增运行时依赖

## 5. 测试与回归

- [x] `python -m pytest tests/test_claim_policy.py tests/test_stage_claim_hooks.py -q` → **46 passed**（3.13.5）
- [x] P-063 修复后同一命令 → **59 passed**（+13，见 [修复验收清单](../arc-g2-m4-wiring-fixes/CHECKLIST.md)）
- [x] 同一命令在 Python 3.11.15 venv → **46 passed**（P-063 后 **59 passed**）
- [x] 相关回归 6 文件 → **105 passed**
- [x] `tests/test_rc_executor.py` → **207 passed**
- [x] 全量（排除需 `[mcp]` extra 的两个模块）→ 3328 passed / 7 既有环境性失败 / 108 skipped
- [x] 反例均可判红：FALSIFIED、缺 annotation、status 漂移、deliverable 漂移
- [x] 两个 M4 测试文件已加入 CI 固定清单

## 6. 机检

- [x] pre-commit 9/9
- [x] `step_enforce` exit 0（P-061 session 5/5）
- [x] `roadmap_coverage_check.py --check` accept=106 missing=0
- [x] `repo_stats --check` / `console_gen --check` 一致
- [x] DC 契约校验通过（四文档 front-matter + 锚点）

## 7. 未纳入本批

- [ ] A7-3 跨平面长期审计（G7）——M4 只交付即时可复算比对
- [ ] Stage 14/17 的 ClaimStatus 接线（G3）
- [ ] Lean sidecar 的批量检查（M3 已交付单次调用）
- [ ] `annotation` 进入 C4 schema（需契约版本升级，不在 M4）
