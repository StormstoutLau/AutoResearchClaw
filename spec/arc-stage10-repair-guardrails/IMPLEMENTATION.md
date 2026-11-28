---
id: arc-stage10-repair-guardrails-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [arc-stage10-repair-guardrails-DESIGN]
upstream: arc-stage10-repair-guardrails-DESIGN
---

# 实施：D-7 修复护栏离线基准（P-224）

> 本批只实施 D-7：新增 6 场景 fixture 基准，**零生产代码改动**。D-1..D-6 未实施。

## 1. 交付物

| 项 | 位置 | 说明 |
|---|---|---|
| 基准测试 | [tests/test_repair_guardrails_fixture.py](../../tests/test_repair_guardrails_fixture.py) | 6 场景 + 覆盖断言，共 7 例 |
| 场景驱动 | 同上 `TestRepairGuardrailFixture` | 单轮场景直调 `_repair_critical_issues`；重复拒收走真实 `_hard_validate_and_repair` |

生产代码（[code_agent.py](../../researchclaw/pipeline/code_agent.py)、[repair_trace.py](../../researchclaw/pipeline/repair_trace.py)）未改。

## 2. 场景与基线读数

实测（`pytest tests/test_repair_guardrails_fixture.py -q -s`，2026-11-28）：

| # | 场景 | calls | kept | accepted_bad | 断言 |
|---|---|---|---|---|---|
| 1 | syntax_break | 1 | True | False | `syntax_error` 拒收，原文逐字节保留 |
| 2 | entrypoint_break | 1 | True | False | `entrypoint_contract` 拒收 |
| 3 | symbol_regression | 1 | True | False | `symbol_contract` 拒收 |
| 4 | truncation | 2 | True | False | `max_tokens == [16384, 32768]`，第二次回复被接受 |
| 5 | unknown_file | 1 | True | False | `helpers.py` 不进入项目 |
| 6 | repeat_rejection | 4 | True | False | 5 条 `hard_validation` 全 failed；4 次修复全拒收（**D-1 目标：2**） |

基线结论：P-222 的 `accepted_bad` 已为 0（6/6），但同因拒收仍跑满 4 轮——这是 D-1 的量化依据。

## 3. 指标口径

- `calls`：LLM 调用次数，作为墙钟的确定性替代（无网络、无计时抖动）。
- `kept`：被拒文件与修复前字符串逐字节一致。
- `accepted_bad`：违反任一闸门的回复是否进入结果（必须为 False）。
- `rounds`：`steps.jsonl` 中 `hard_validation` 行数（attempt-0..4）。

## 4. 设计取舍

- 单轮场景直调 `_repair_critical_issues`：只验证「合并闸门」，不受 `_hard_validate` 其他规则干扰。
- 重复拒收走 `_hard_validate_and_repair`：用真实的 UnboundLocal 规则制造稳定 critical，才能测出轮次与调用数。
- 不引入计时断言：墙钟用调用数替代，避免 CI 抖动。

## 5. 回归

- 本文件：**7 passed**。
- 相关三套：`test_generation_budget_contract.py` + `test_codegen_truncation.py` + `test_repair_trace.py` = **71 passed**。

## 6. 未做

D-1（止损）、D-2（还原点读数）、D-3（执行级验收）、D-4（拒因回传）、D-5（diff 兜底）、D-6（测试级验收）均未实施；未部署、未改动 B 站运行 L。
