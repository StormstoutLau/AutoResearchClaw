---
id: arc-step-enforce-branch-consistency-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-10
depends: [arc-step-enforce-branch-consistency-IMPLEMENTATION]
upstream: arc-step-enforce-branch-consistency-IMPLEMENTATION
---

# 验收清单：step_enforce 分支门槛对齐（R-5）

## 1. 交付物

- [x] `_resolve_declared` 使用 `BATCH_BINDING_MIN_P` 谓词
- [x] `tests/test_step_enforce_branches.py` 存在且 8 用例全绿
- [x] 未改常量数值 / 覆盖检查 / session 校验

## 2. 验收（DESIGN §5）

- [x] A-1 混合批（T1+T3 同提交）不再误红
- [x] A-2 高编号 P（≥129）无 feature 仍红
- [x] A-3 两分支对同一输入判定一致
- [x] A-4 变更 feature 未被覆盖仍红
- [x] A-5 声明 P 缺 session 仍红
- [x] A-6 全量 pre-commit 9/9；既有 pytest 无回归

## 3. 机检

- [x] V1 `pytest tests/test_step_enforce_branches.py` → 8 passed
- [x] V2 混合批真实复现（P-022+P-023 同批）→ exit 0
- [x] V3 `pre-commit run --all-files` → 9/9
- [x] V4 `step_enforce --base HEAD` → exit 0
- [x] V5 既有 pytest 子集 → 36 passed

## 4. 收口

- [x] PROGRESS 增 P-024 行
- [x] `specwf-p024` session 5/5
- [x] `docs/CONSOLE.md` 派生刷新
