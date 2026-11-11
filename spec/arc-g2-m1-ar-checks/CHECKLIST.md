---
id: arc-g2-m1-ar-checks-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-11
depends: [arc-g2-m1-ar-checks-IMPLEMENTATION]
upstream: arc-g2-m1-ar-checks-IMPLEMENTATION
---

# 验收清单：G2 M1 学术八条判据

## 1. M1 DoD（R-03 §5.2 / A2-2）

- [x] AR-01..AR-08 全部落为纯函数（`researchclaw/evidence/ar_checks.py`）
- [x] 16 个 fixture：每判据 1 正 1 反（`tests/fixtures/g2/ar/`）
- [x] 8 条变异自检：禁用任一判据后，对应反例不再触发（`test_pre_red_disabling_check_clears_finding`）
- [x] 判据空实现会使套件变红（反例分类 + 变异首断言）
- [x] ClaimRecord 消费 M0 的 C4 映射；8 个正例回验 C4 schema

## 2. A2-2

- [x] 16 fixture 全绿
- [x] 变异测试：删掉任一判据 → 对应 fixture 变红
- [x] 判据空实现必须失败
- [x] 失败可归因到判据 ID（`Finding.code` + `field`）

## 3. 不变式

- [x] 严重度仅 `fail/warn/downgrade`，与 R-03 §3.4 一一对应
- [x] 检查层只读，不写回 `status`；`cap` 仅 AR-05/06
- [x] 无 IO、无 schema 运行时依赖、无全局可变状态（除可被 monkeypatch 的注册表）
- [x] 缺失字段容错，不抛异常；持久化结构由 M0 schema 负责
- [x] findings 排序确定

## 4. 机检

- [x] `python -m pytest tests/test_g2_ar_checks.py -q` → 28 passed（3.13.5）
- [x] 同一命令在 3.11.15 venv → 28 passed
- [x] `tests/test_g2_ar_checks.py` 加入 CI 固定清单
- [x] 9 道 pre-commit 门禁全绿；`roadmap_coverage_check.py` accept=106 missing=0

## 5. 未纳入本批

- [ ] A2-4 `can_enter_deliverables`（FALSIFIED/FAILED 阻断）
- [ ] A2-5 `requires_annotation`（NUMERICALLY_VERIFIED ⇒ annotation）
- [ ] A2-6 `downgrade_missing_citation`（缺引文迁入 assumptions）
- [ ] AR-06「共识不得提升 tier」的比较性判定（登记为不可机械）
- [ ] 3.11 内核 vendor（M2）
