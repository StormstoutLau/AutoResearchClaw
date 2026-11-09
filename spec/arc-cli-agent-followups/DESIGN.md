---
id: arc-cli-agent-followups-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-cli-agent-followups-RESEARCH]
upstream: arc-cli-agent-followups-RESEARCH
---

# 设计：U-3/U-5 收口与 U-4 前移

> 输入：[RESEARCH.md](RESEARCH.md) §3 处置建议、§6.2 四元块。目标：只做登记与最小代码约束，不改变默认路径。

## 1. 设计不变量

1. `provider="llm"` 时 Stage 13 的 prompt 与行为不变。
2. 不修改 P-011/P-012 归档文档。
3. U-3 以“裁决记录”关闭，不新增代码。
4. U-5 以“提示级边界 + 审计字段”落地，不引入条件集硬门。
5. U-4 在本批文档中可检索，保留原触发条件。

## 2. 决策表

| # | 决策 | 选择 | 被拒绝的替代 | 理由 |
|---|---|---|---|---|
| D-1 | U-3 传输选型 | Stage 10/13 用 CLI-stdin（Claude/Codex）；ACP 保持 LLM 层；SDK 暂缓 | 改用 SDK；Stage 10/13 走 ACP | 与 P-012 实现一致；SDK 增加依赖；ACP 不适配“生成项目文件”语义 |
| D-2 | U-5 边界强度 | 提示级边界 + `boundary` 审计字段 | 立即做条件集静态/差异门 | 误报高、需真实案例 |
| D-3 | U-5 预算 | 沿用 `cli_agent.timeout_sec` + `max_budget_usd`；Stage 13 wall-clock cap 不变 | 新增独立 Stage 13 预算字段 | 无证据需要新字段 |
| D-4 | U-4 处置 | 在 P-013 重新登记，保留触发条件 | 修改 P-012 归档文档补一行 | 归档文档不改，勘误记录在本批 |
| D-5 | P-011 §5.3 | 前两条标记 superseded；第三条保留 | 直接编辑 P-011 | 同上 |
| D-6 | U-1/U-2 | 保持 pending | 提前做 A/B / Windows 矩阵 | 触发条件未命中 |

## 3. 接口

### 3.1 Stage 13 CLI 边界常量

```python
_STAGE13_CLI_BOUNDARY = (
    "STAGE 13 BOUNDARY: This is a repair/tuning pass, not a redesign. "
    "Do NOT change the experimental design, conditions, dataset, model family, "
    "or evaluation protocol. Preserve every condition name from the plan. "
    "Only fix bugs, improve robustness, and tune existing parameters."
)
```

使用点：`_try_agent_refine(..., extra_hints=_STAGE13_CLI_BOUNDARY + ...)`。
作用域：仅 CLI refine；LLM refine 的 `ip.user` 不变。

### 3.2 审计字段

`refinement_log.json` 的 `cli_agent` 增加：

```json
{"provider": "...", "enabled": true, "boundary": "repair_and_tune",
 "refine_calls": 0, "repair_calls": 0}
```

### 3.3 适应度函数

`scripts/code_agent_wiring_check.py` 新增断言：

1. `_execution.py` 中存在 `_STAGE13_CLI_BOUNDARY` 定义与使用（出现 ≥2 次）。
2. `cli_agent` 日志块包含 `"boundary": "repair_and_tune"`。

## 4. 测试策略（TDD）

1. 先写 `test_stage13_cli_boundary_declared`：导入常量并断言包含 “Do NOT change the experimental design” 与 “condition”。
2. 先写 `test_stage13_cli_boundary_is_wired`：读 `_execution.py`，断言常量出现 ≥2 次且日志含 `repair_and_tune`。
3. 更新适应度函数负向用例：缺失边界时 exit 1（现有 ghost provider 用例仍覆盖主流程）。

## 5. 影响面与回滚

- 代码：`_execution.py`（常量、extra_hints、日志字段）、`scripts/code_agent_wiring_check.py`、`tests/test_cli_agent_wiring.py`。
- 默认路径：无变化（常量只进入 CLI refine 分支）。
- 回滚：删除常量与日志字段即可；不影响 Stage 10/13 产物契约。

## 6. 未决项

沿用 RESEARCH §6.2 的 U-1、U-2、U-4、U-6。U-3/U-5 在本批关闭。
