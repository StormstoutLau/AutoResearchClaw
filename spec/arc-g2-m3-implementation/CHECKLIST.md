---
id: arc-g2-m3-implementation-CHECKLIST
type: design
version: 1.1
status: pending
date: 2026-11-11
depends: [arc-g2-m3-implementation-IMPLEMENTATION]
upstream: arc-g2-m3-implementation-IMPLEMENTATION
---

# 验收清单：G2 M3 sidecar（待执行）

> 状态 **pending**：本清单对应 P-054 设计包的施工验收；P-056/P-058 已落实两轮复审修正，P-059 一致性审查零缺陷（O-1..O-7）；执行批（**P-060**）完成后逐项勾选并回填读数。

## 0. 设计修复前置（P-056，已完成）

- [x] **D-A**：建树条件改为「success 即建树、sorry 计入 `tree.sorry`」；`latex_ok=report.success`
- [x] **D-B**：lean_check 下 `failed` / `falsified` → `stage2`
- [x] **D-C**：AP `CompileReport.timed_out` + ARC 硬超时兜底（不再依赖无效的 `wait_for`）
- [x] **O-1**：F-5 指针订正为 `datatypes/config.py:194`
- [x] **O-2**：响应样例 `inputs_digest` 改为合法 64 hex
- [x] **O-3**：`request_id` 经 `_sanitize_run_id` 改名，`lean.project` 为准
- [x] **O-4**：§7 补「危险构造被拒」行 + L-H
- [x] **O-5**：ARC 硬超时 = 请求 `timeout_s` + 30s 写入契约

## 0.1 施工注意项（P-058，已完成）

- [x] **O-A**：删除 §3.1 的 `evidence_complete` 建树条件（交由 policy `evidence_incomplete`）
- [x] **O-B**：§7 补判定优先级（tree_partial > file_sorry > evidence_incomplete > axiom > legality）
- [x] **O-C**：`rejected_dangerous_construct` 以 `diagnostics.startswith("rejected:")` 判定
- [x] **O-D**：AP 基线 `test_b27_compile_check.py` + `test_w2_lean_filter.py` = **29 passed, 2 skipped**；real-Lean 用例须用 per-run 项目（`lean_src` 无 `Main` 目标）

## 1. M3 DoD / A2-7

- [ ] `arb_verify.py` 在 3.12 venv 下可执行（`--request/--response`）
- [ ] `mode=lean_check` 对 4.20 工程的可证定理返回 `formally_verified` / `depth=stage3`
- [ ] 无 Lean 时正确降级：必需 → 78；可选 → 0 + `degraded_reason`
- [ ] 不产出冒充的 `formally_verified`（编译失败/sorry/axiom dirty/合法性失败均不提升）
- [ ] 编译失败 → `FAILED`、`depth=stage2`；含 sorry → `partially_formalized`、`depth=stage2`

## 2. P-053 / P-055 缺口关闭

- [ ] **D-1**：最小树 + 真实 `LegalityChecker`；合法代码 `all_gates_passed`，axiom 注入 `legality_failed`
- [ ] **D-2**：77 保留给 REVOKED；必需缺失 78；可选降级 0；`_map_exit` 拒绝 77
- [ ] **D-C**：极短 timeout 返回 75 且 `timed_out=True`；客户端硬超时也能合成 75
- [ ] 响应 `claim_record` 为完整 C4（14 必填）
- [ ] 降级措辞与 `_fallback` 一致（无树 → ≤ latex）
- [ ] 验收计时允许 warm 8–60s 区间
- [ ] 诊断只信 `compile_report` 结构化字段

## 3. 契约

- [ ] `run` 满足 C1 必填且无 `verdict`
- [ ] `claim_record` 通过 C4 schema（测试态 jsonschema）
- [ ] `schema_version=1.0`；`request_id` 请求/响应一致
- [ ] `tree_origin=compile_only` 仅在造树时出现

## 4. 生命周期与安全

- [ ] 请求/响应原子写（无 `.tmp` 残留）
- [ ] 超时 `taskkill /t /f` 终止子树；返回 75
- [ ] 环境白名单不含 API key/endpoint
- [ ] 临时 Lean 工程在 `finally` 清理（Windows 锁重试）
- [ ] `theorem_name`/长度/`timeout_s` 钳制生效

## 5. 测试

- [ ] 单元 8 项全绿（3.11 + 3.13）
- [ ] live 8 项全绿（`ARB_LEAN_PROJECT` 本机）
- [ ] CI 固定清单含单元测试；live 在 CI skip
- [ ] 覆盖 L-A..L-H 全部场景
- [ ] AP 侧 `timed_out` 单测通过

## 6. 机检

- [ ] `pre-commit run --all-files` 9/9
- [ ] `step_enforce --base HEAD` exit 0
- [ ] `roadmap_coverage_check.py` accept=106 missing=0
- [ ] `repo_stats --check` / `console_gen --check` 一致
- [ ] 无新增 ARC 运行时依赖

## 7. 未纳入本批

- [ ] `mode=verify`（NL→Lean，M4）
- [ ] `leanchecker` 独立深度（4.28+，M4+）
- [ ] sidecar 随 wheel 分发（U-3）
- [ ] Job Object 替代 taskkill（U-1）
