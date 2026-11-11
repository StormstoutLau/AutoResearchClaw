---
id: arc-g2-m4-wiring-fixes-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-11
depends: [arc-g2-m4-wiring-fixes-IMPLEMENTATION]
upstream: arc-g2-m4-wiring-fixes-IMPLEMENTATION
---

# 验收清单：G2 M4 复审缺陷修复（P-063）

## 1. D-1 验收

- [x] `stage-09` 与 `stage-09_v{N}` 并存时，活目录优先
- [x] 无活目录时按版本号数值降序取最新（`v10 > v2`）
- [x] `stage-20` 前缀复用同一优先级
- [x] PIVOT 后 Stage 20 不再读到旧 claim（探针 F-A + 用例）

## 2. D-2 验收

- [x] claim 文件坏行 → `ClaimStreamError`，不静默跳过
- [x] `claim_gate.json` 损坏 → `ClaimStreamError`，不再误判 `skipped`
- [x] `annotations.json` 非对象 → `ClaimStreamError`
- [x] Stage 20/23 执行器把上述异常映射为 `E20_CLAIM_CONTRACT_INTERNAL` / `E23_CLAIM_DRIFT_INTERNAL`
- [x] claims/gate/consistency 全部 `tmp + os.replace`
- [x] `os.replace` 失败时原文件不变、无 `.tmp` 残留
- [x] 缺失文件仍按续跑语义处理（`[]` / 默认值 / `skipped`）

## 3. D-3 验收

- [x] 非法 status → `invalid_claim_record`
- [x] 缺 C4 必填键 → `invalid_claim_record` 且 `problems` 列出缺失键
- [x] 非法 `claim_id` → `invalid_claim_record`
- [x] 合法 claim 不受影响（无 problems）
- [x] 生产门禁与审计平面共用同一校验
- [x] `claim_gate.json` 的 blocked/decision 均带 `problems`

## 4. 回归

- [x] 原 M4 46 项全部通过
- [x] 新增 13 项全部通过（合计 59）
- [x] 相关回归 105 passed
- [x] Python 3.11.15 双环境 59 passed
- [x] 合法 claim 全链路 `pass` + `consistent=True`

## 5. 机检

- [x] pre-commit 9/9
- [x] `step_enforce` exit 0（P-063 session 5/5）
- [x] `roadmap_coverage_check.py --check` accept=106 missing=0
- [x] `repo_stats --check` / `console_gen --check` 一致
- [x] DC 契约校验通过（四文档 front-matter + 锚点）

## 6. 未纳入本批

- [ ] O-3 空 claims 空转通过（后续批次）
- [ ] O-4 gate JSON 缺 `message`/`cap`（后续批次）
- [ ] O-1/O-2 annotation 供给与封顶语义（M5/G3）
- [ ] O-5/O-6 时间戳与临时 venv 记录（存档）
