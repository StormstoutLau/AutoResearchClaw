---
id: arc-stage10-repair-stop-loss-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [arc-stage10-repair-stop-loss-DESIGN]
upstream: arc-stage10-repair-stop-loss-DESIGN
---

# 实施：Stage 10 重复拒收止损（P-226 / D-1）

## 1. 改动

| 文件 | 改动 |
|---|---|
| [researchclaw/config.py](../../researchclaw/config.py#L490) | `CodeAgentConfig.repair_stop_after_rejections = 2` |
| [researchclaw/pipeline/code_agent.py](../../researchclaw/pipeline/code_agent.py#L1323) | `_hard_validate_and_repair` 初始化 streak，修复后检查 `_repeated_rejection()`，命中则写 `agent_repair_stopped` 并返回 |
| 同上 L1642 | `_repair_critical_issues` 只对连续同 `(file, reason)` 累加；接受文件不进入新一轮计数 |
| [tests/test_repair_guardrails_fixture.py](../../tests/test_repair_guardrails_fixture.py#L187) | `test_06` 改为断言 2 轮/2 调用/1 次 stopped；新增 `test_07`（0 关闭）、`test_08`（交替原因不停） |

## 2. 读数

```
fixture syntax_break:       calls=1 kept=True accepted_bad=False
fixture entrypoint_break:   calls=1 kept=True accepted_bad=False
fixture symbol_regression:  calls=1 kept=True accepted_bad=False
fixture truncation:         calls=2 kept=True accepted_bad=False
fixture unknown_file:       calls=1 kept=True accepted_bad=False
fixture repeat_rejection:   calls=2 kept=True accepted_bad=False   ← was 4
9 passed
```

相关四套（fixture + generation_budget_contract + codegen_truncation + repair_trace）：**80 passed**。

## 3. 实施注意

P-222 的边界仍然成立：**单文件修复回复会被改名为 `main.py`**，因此 fixture 的重复拒收场景必须发送 `main.py + data.py` 双块，否则 streak 会记在 `main.py` 上。已在 `test_06/07/08` 按此构造。

## 4. 未做

未部署到 B 站；运行 L 仍在 P-222 快照上跑。现场验证需下一次部署后观察 `Repeated rejection ... stopping targeted repair` 与 `agent_repair_stopped` 事件。
