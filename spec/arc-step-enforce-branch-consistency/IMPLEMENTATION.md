---
id: arc-step-enforce-branch-consistency-IMPLEMENTATION
type: design
version: 1.0
status: draft
date: 2026-11-10
depends: [arc-step-enforce-branch-consistency-DESIGN]
upstream: arc-step-enforce-branch-consistency-DESIGN
---

# 实施记录：step_enforce 分支门槛对齐

> 基于 [DESIGN.md](DESIGN.md) v1.0。

## 1. 步骤

| # | 动作 | 文件 |
|---|---|---|
| S-1 | `_resolve_declared` 加 `BATCH_BINDING_MIN_P` 谓词 | `scripts/spec/step_enforce.py` |
| S-2 | 新增分支一致性测试（5 用例） | `tests/test_step_enforce_branches.py` |
| S-3 | 跑 pytest + 全量 pre-commit + 混合批复现 | — |

## 2. 代码改动

`scripts/spec/step_enforce.py` `_resolve_declared`（单处，+6/-1）：

```python
if not row["features"]:
    # P-024（R-5）：与 `batch-registration` 分支（L478）同谓词——绑定要求只在
    # P-129 起生效，历史/轻批豁免；「变更 feature 是否被覆盖」另由下方 missing 检查兜底。
    if _pid_num(pid) >= BATCH_BINDING_MIN_P:
        d.errors.append(f"{pid} 未声明任何 spec/<feature>/ 链接")
    continue
```

未改动：`BATCH_BINDING_MIN_P` 数值、`missing = docs_features - allowed`、session 完整性校验、钩子配置、CI。

## 3. 测试结果

`tests/test_step_enforce_branches.py`：**8 passed**（5 个测试函数，其中分支一致性为 4 参数化）。

| 用例 | 断言 | 结果 |
|---|---|---|
| T-1 | T1+T3 同批，T3 行无 feature → 无「未声明任何 spec」 | PASS |
| T-2 | P-129 无 feature → 报错 | PASS |
| T-3 | 4 组 `(pid, features)` 两分支判定一致 | PASS ×4 |
| T-4 | 变更 feat-b 未被 feat-a 覆盖 → 报错 | PASS |
| T-5 | 声明 P 无 session → 报错 | PASS |

## 4. 机检

| # | 检查 | 结果 |
|---|---|---|
| V1 | `pytest tests/test_step_enforce_branches.py` | **8 passed** |
| V2 | 混合批真实复现（旧 PROGRESS = `09b17b4`，新 = 含 P-022/P-023） | **PASS**：mode=batch、pids=[P-022,P-023]、features=[arc-g1-readiness-research]、errors=[] |
| V3 | `pre-commit run --all-files` | **9/9 Passed** |
| V4 | `step_enforce --base HEAD` | exit 0 |
| V5 | 既有 pytest 子集（test_cli_agent_wiring / packaging / docs） | 36 passed |

## 5. 边界

- [x] 未改 `BATCH_BINDING_MIN_P` 数值（保持 129）
- [x] 未改覆盖检查与 session 完整性校验
- [x] 未改 `.pre-commit-config.yaml` / CI
- [x] 未改其他治理脚本（仅 `step_enforce.py` 一处）
