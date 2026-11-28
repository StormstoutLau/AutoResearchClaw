---
id: arc-stage10-split-rejection-accounting-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-29
depends: [arc-stage10-split-rejection-accounting-DESIGN]
upstream: arc-stage10-split-rejection-accounting-DESIGN
---

# 实施：拆分修复的拒收记账（P-233）

## 1. 改动

| 文件 | 改动 |
|---|---|
| [code_agent.py#L1941](../../researchclaw/pipeline/code_agent.py#L1941) | `_repair_files_individually` 的兜底拒因改为 `if name not in fixed and name not in rejected` |
| [test_generation_budget_contract.py](../../tests/test_generation_budget_contract.py) | 新增 2 例：接受文件不进 `rejected_reasons`；拆分轮不触发 P-226 |

## 2. 测试

| 用例 | 判据 |
|---|---|
| `test_accepted_file_is_not_recorded_as_rejected` | 单文件接受 → `rejected == {}` |
| `test_split_round_does_not_trip_stop_loss` | 拆分轮全部接受 → trace 无该文件的 `rejected_reasons`，`_repeated_rejection() is None` |

## 3. 读数

```
pytest tests/test_generation_budget_contract.py tests/test_context_budget.py \
       tests/test_codegen_evidence.py tests/test_symbol_recheck.py \
       tests/test_entrypoint_contract.py -q
115 passed
```

红→绿记录：两例在修复前均红（接受文件出现在 `rejected_reasons`、止损返回 `("data.py","not_returned",1)`）；修复后转绿。

全量回归：

```
pytest tests -q
6 failed, 4262 passed, 108 skipped in 355.79s
```

6 项失败均为本机环境类（壳钩子 WinError 193、`test_memory_system` 4 项 Keras 3、`test_rc_sentinel` bash 路径）。

## 4. 现场预期

重跑后拆分修复轮不应再出现：

```
Repair rejected config.py: not_returned
agent_repair_stopped  reason=not_returned
```

正常形态：`Repair updated N file(s)` 或按文件记真实拒因（`truncated_after_escalation` / `symbol_contract` / `catastrophic_rewrite`）。

## 5. 未做

不改 P-226 计数器；不改拆分阈值与预算；不改 `_accept_repair_files`。
