---
id: arc-g2-m3-implementation-CHECKLIST
type: design
version: 1.2
status: accepted
date: 2026-11-11
depends: [arc-g2-m3-implementation-IMPLEMENTATION]
upstream: arc-g2-m3-implementation-IMPLEMENTATION
---

# 验收清单：G2 M3 sidecar（已验收）

> P-060 施工完成。读数：单元 **10 passed**、live **8 passed**（Lean 4.20）、AP 测试 **30 passed/2 skipped**、vendor **99 passed**；O-2..O-7 全部落实。

## 0. 设计修复前置（P-056/P-058，已完成）

- [x] **D-A**：建树条件「success 即建树、sorry 计入 `tree.sorry`」；`latex_ok=report.success`
- [x] **D-B**：`failed`/`falsified` → `stage2`
- [x] **D-C**：AP `CompileReport.timed_out` + ARC 硬超时兜底
- [x] **O-1..O-5**：指针、样例、`request_id`、危险构造行、超时缓冲
- [x] **O-A**：删除 `evidence_complete` 建树条件
- [x] **O-B**：§7 判定优先级
- [x] **O-C**：`rejected:` 前缀判定
- [x] **O-D**：AP 基线 29 passed/2 skipped（real-Lean 需 per-run）

## 1. M3 DoD / A2-7

- [x] `arb_verify.py` 在 3.12 venv 下可执行（`--request/--response`）
- [x] `mode=lean_check` 对 4.20 工程的可证定理返回 `formally_verified` / `depth=stage3`
- [x] 无 Lean 时正确降级：必需 → 78；可选 → 0 + `degraded_reason`
- [x] 不产出冒充的 `formally_verified`（编译失败/sorry/axiom dirty/合法性失败均不提升）
- [x] 编译失败 → `FAILED`、`depth=stage2`；含 sorry → `partially_formalized`、`depth=stage2`

## 2. P-053 / P-055 / P-059 缺口关闭

- [x] **D-1**：最小树 + 真实 `LegalityChecker`；L-A `all_gates_passed`、L-F `legality_failed`
- [x] **D-2**：77 保留；必需缺失 78；可选降级 0；`_map_exit` 拒绝 77
- [x] **D-C**：L-G 返回 75 且 `timed_out=True`
- [x] **O-2**：RESEARCH §7 加「以 DESIGN §5 为准」指针
- [x] **O-3**：§7 编译失败/湖缺失措辞订正
- [x] **O-4**：`request_id` 字符集写入 §5.1
- [x] **O-5**：vendor `config.py` re-vendor + `SOURCE.json` 重算 sha256
- [x] **O-6**：白名单补 `USERPROFILE`、`PYTHONUTF8`、`PYTHONIOENCODING`
- [x] **O-7**：IMPL §2.3 补 `rejected:` 判定指针

## 3. 契约

- [x] `run` 满足 C1 必填且无 `verdict`
- [x] `claim_record` 通过 C4 schema（测试态 jsonschema）
- [x] `schema_version=1.0`；`request_id` 请求/响应一致
- [x] `tree_origin=compile_only` 仅在造树时出现

## 4. 生命周期与安全

- [x] 请求/响应原子写（无 `.tmp` 残留）
- [x] 超时 `taskkill /t /f` 终止子树；返回 75
- [x] 环境白名单不含 API key/endpoint（U-7）
- [x] 临时 Lean 工程在 `finally` 清理
- [x] `theorem_name`/长度/`timeout_s` 钳制生效

## 5. 测试

- [x] 单元 **10 passed**（3.13）
- [x] live **8 passed**（`ARB_LEAN_PROJECT` 本机，11.65s）
- [x] CI 固定清单含单元 + live（live 在 CI skip）
- [x] 覆盖 L-A..L-H 全部场景
- [x] AP `timed_out` 单测通过（30 passed/2 skipped 套件）

## 6. 机检

- [x] pre-commit 9/9
- [x] `step_enforce` exit 0
- [x] `roadmap_coverage_check.py` accept=106 missing=0
- [x] `repo_stats --check` / `console_gen --check` 一致
- [x] 无新增 ARC 运行时依赖

## 7. 未纳入本批

- [ ] `mode=verify`（NL→Lean，M4）
- [ ] `leanchecker` 独立深度（4.28+，M4+）
- [ ] sidecar 随 wheel 分发（U-3）
- [ ] Job Object 替代 taskkill（U-1）
