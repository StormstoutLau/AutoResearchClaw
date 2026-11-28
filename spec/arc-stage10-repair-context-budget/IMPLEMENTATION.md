---
id: arc-stage10-repair-context-budget-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [arc-stage10-repair-context-budget-DESIGN]
upstream: arc-stage10-repair-context-budget-DESIGN
---

# 实施：修复上下文的预算、遥测与截断止损（P-228）

## 1. 改动

| 文件 | 改动 |
|---|---|
| [code_agent.py#L2322](../../researchclaw/pipeline/code_agent.py#L2322) | 新增 `_middle_truncate`：头 60% + 尾 40% + `[truncated: N chars / M lines omitted, original K chars]` |
| 同上 #L2345 | `_format_files(files, keep_full, budget=60000)`：超预算时未受影响文件降为 CodeMem 摘要，keep 文件按份额中间截断 |
| 同上 #L1601-L1688 | 修复 prompt 使用 `keep_full=affected_files`；硬上限 140 000；prompt-too-long 降级为「仅摘要」重试一次 |
| 同上 #L1669-L1734 | 32 768 后仍截断 → 本轮不提取候选，`reason=truncated_after_escalation` 计入 P-226；trace 增 usage 与 `summary_mode` |
| [\_code_generation.py#L1742](../../researchclaw/pipeline/stage_impls/_code_generation.py#L1742) | 阶段深修上下文改为 80 000 字符预算（保留全部文件、超限中间截断） |
| 同上 #L1806 | `project_repair` trace 增 usage |
| [tests/test_context_budget.py](../../tests/test_context_budget.py) | 新增 6 例 |

## 2. 读数

```
pytest test_context_budget + repair_guardrails_fixture
       + workspace_hygiene + generation_budget_contract  → 61 passed
```

覆盖：
- 中间截断保留头尾、标记含 `original N chars`；
- 短文本不被改写；
- 预算内逐字保留；超预算时未受影响文件成摘要、keep 文件保留、总长下降；
- trace 记录 `usage.prompt_tokens=1234`、`finish_reason`、`summary_mode=True`；
- 连续两次截断：4 次调用（每轮 16k+32k）、两轮均 `truncated_after_escalation`、streak=2、文件不变。

## 3. 现场预期

- 修复日志出现 `Repair prompt over hard cap — switching to summaries only`（仅超限时）；
- trace 可直接读出 reasoning 是否吃满：`usage.completion_tokens` 与 `response_chars` 对比；
- 运行 L 类场景（16/16 截断）在第二轮后触发 `Repeated rejection ... truncated_after_escalation`，不再跑满 4 轮。

## 4. 未做

未部署、未重跑 B 站；未引入会话级摘要（与无状态设计冲突）。
