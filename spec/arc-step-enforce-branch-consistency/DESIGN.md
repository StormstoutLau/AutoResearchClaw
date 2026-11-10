---
id: arc-step-enforce-branch-consistency-DESIGN
type: design
version: 1.0
status: draft
date: 2026-11-10
depends: [arc-step-enforce-branch-consistency-RESEARCH]
upstream: arc-step-enforce-branch-consistency-RESEARCH
---

# 设计：两分支 feature 门槛对齐

> 输入：[RESEARCH.md](RESEARCH.md) §4 方案 A。

## 1. 决策

| ID | 决策 |
|---|---|
| D-1 | `_resolve_declared` 的 feature 要求改为与 `batch-registration` 同谓词：`_pid_num(pid) >= BATCH_BINDING_MIN_P` 才要求非空 |
| D-2 | 不新增常量、不重定门槛、不改覆盖检查（`missing = docs_features - allowed`） |
| D-3 | 门槛语义保持「P-129 起要求绑定」，历史批次豁免；ARC 当前全部 `< 129` → 该要求自然不触发，由覆盖检查兜底 |
| D-4 | 不因 T3 无 feature 而跳过**session 完整性**校验：`d.pids` 仍全部参与 `_sessions_for_pid` + `require_complete=True` |

## 2. 代码改动

```python
# scripts/spec/step_enforce.py  _resolve_declared
        if not row["features"]:
            if _pid_num(pid) >= BATCH_BINDING_MIN_P:      # P-024：与 L478 同谓词
                d.errors.append(f"{pid} 未声明任何 spec/<feature>/ 链接")
            continue
```

- 严格等价于 L478：`_pid_num(pid) >= BATCH_BINDING_MIN_P and not row["features"]`。
- 连续 `continue` 保留原控制流：无 feature 的批次不贡献 `allowed`。

## 3. 不变量

| # | 不变量 | 判据 |
|---|---|---|
| I-1 | **两分支同谓词** | 同一 `(pid, features)` 输入在两条路径下的 feature 判定必须一致 |
| I-2 | 覆盖检查不放宽 | 变更 feature 若未被任一声明 P 覆盖，仍 `exit 1` |
| I-3 | session 完整性不放宽 | 每个声明 P 仍要求 5/5 session |
| I-4 | 存量零回归 | P-001..P-023 的既有判定不变（全部 < 129） |

## 4. 测试设计（TDD 双要素）

新增 `tests/test_step_enforce_branches.py`，以纯函数 `resolve()` / `_resolve_declared()` 为被测面，monkeypatch `_sessions_for_pid` 隔离文件系统：

| 用例 | 构造 | 期望 |
|---|---|---|
| T-1 混合批（回归） | docs_features={feat-a}；P-024 无 feature、P-025 有 feature | 无「未声明任何 spec」错误；覆盖通过 |
| T-2 高编号 T3 行（负向） | P-200 无 feature（≥129） | 报「未声明任何 spec」 |
| T-3 两分支一致性 | 同 `(pid, features)` 分别走 `_resolve_declared` 与 `batch-registration` | feature 判定一致 |
| T-4 覆盖不放宽（负向） | docs_features={feat-b}；P 行只含 feat-a | 报「变更 feature 未被声明 P 覆盖」 |
| T-5 session 不放宽（负向） | 声明 P 无 session | 报「无 session」 |

## 5. 验收映射

| 验收 | 落点 |
|---|---|
| A-1 | T-1 通过（P-022/P-023 同提交场景） |
| A-2 | T-2 通过（高编号仍严格） |
| A-3 | T-3 通过（不变量 I-1） |
| A-4 | T-4 通过（I-2） |
| A-5 | T-5 通过（I-3） |
| A-6 | 全量 pre-commit 9/9 + 既有 pytest 无回归 |

## 6. 回滚

单行还原：恢复无条件 `d.errors.append(...)`。
