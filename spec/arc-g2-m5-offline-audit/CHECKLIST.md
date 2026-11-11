---
id: arc-g2-m5-offline-audit-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-11
depends: [arc-g2-m5-offline-audit-IMPLEMENTATION]
upstream: arc-g2-m5-offline-audit-IMPLEMENTATION
---

# 验收清单：G2 M5 离线审查模式（P-064）

## 1. M5 DoD（R-03 §5.2）

- [x] 同一 claim 在生产/审查两条路径得到相同 `status`：7 状态矩阵逐项断言（`test_offline_audit_status_matrix_reproduces_production`）
- [x] 同 `policy_version`：版本锚点取 claims 自带字段，`policy_version_mismatch` 可判红
- [x] 审查平面为离线批次模式：`researchclaw audit --run-dir`，无 LLM/无网络/不写 run

## 2. 离线审计核心

- [x] `run_offline_audit` 只读：全树字节快照前后不变
- [x] 读取优先级与 Stage 23 同构：stage-20 优先、活目录优先于版本目录
- [x] 比对经共享 `compare_claims`，Stage 23 与审计无第二实现
- [x] 漂移四态可判红：status_mismatch / deliverable_mismatch / missing_production_decision / policy_version_mismatch
- [x] 跳过语义与管线一致：`no_production_gate` / `no_claims` 均 consistent=true
- [x] 失败封闭：目录缺失→`FileNotFoundError`；claims 坏行、gate 损坏→`ClaimStreamError`
- [x] 确定性：同 run 两次审计 JSON 逐字节相等
- [x] 报告契约：consistent/checked/diffs/production/audit/expected_policy_version[/skipped]

## 3. CLI

- [x] `researchclaw audit --run-dir` 接入 `main()` 派发；`--help` 正常
- [x] 退出码 0（一致）/ 1（漂移或版本不符）/ 2（目录缺失或损坏），冒烟三态实测
- [x] `--json` 输出完整可解析报告
- [x] `--policy-version N` 触发版本比对并影响退出码
- [x] `--output` 落盘报告（run 目录之外）

## 4. 回归

- [x] 既有 M4 用例 59 项零回归（`compare_claims` 重构后原样通过）
- [x] 相关回归 108 passed（含 test_cli.py）
- [x] M5 套件 29 passed（3.13.5）；M4+M5 88 passed 双环境（3.13.5 与 3.11.15）
- [x] `test_offline_audit.py` 加入 CI 固定清单
- [x] P-068 修复后 M5 **36 passed**、M4+M5 **95 passed**（见 [修复验收清单](../arc-g2-m5-offline-audit-fixes/CHECKLIST.md)）

## 5. 机检

- [x] pre-commit 9/9
- [x] `step_enforce` exit 0（P-064 session 5/5）
- [x] `roadmap_coverage_check.py --check` accept=106 missing=0
- [x] `repo_stats --check` / `console_gen --check` 一致
- [x] DC 契约校验通过（四文档 front-matter + 锚点）

## 6. G2 收口

- [x] M0 契约（P-047）/ M1 AR 判据（P-048）/ M2 vendor（P-049）/ M3 sidecar（P-060）/ M4 接线（P-061，P-063 修复）/ **M5 离线审查（本批）**
- [x] 总纲 v1.3k：G2 全部里程碑交付，G3 可开工

## 7. 未纳入本批

- [ ] O-1 封顶后 annotation 的渲染语义（G3 输入）
- [ ] O-2 `annotations.json` 生产者（G3 输入）
- [ ] O-3 空 claims 空转通过（后续批次）
- [ ] O-4 gate JSON 缺 `message`/`cap`（后续批次）
- [ ] 跨 run 批量审计 / 远端 RPC 执行器（R-03 可选项，暂无需求）
