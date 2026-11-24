---
id: arc-model-policy-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-model-policy-RESEARCH]
upstream: null
---

# 设计：G6 模型分层与预算治理（P-158）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **变更面**：新增 `model_policy.yaml` + `llm/model_policy.py`；`config.py` 增 `ModelPolicyConfig`；`LLMClient` 接前置预算/本地禁网/路由；`CostRecord` 增 `policy_version`；`EVENT_TYPES` 增 `budget_exhausted`。

---

## 1. 决策

| 编号 | 决策 |
|---|---|
| D-1 | Q12 = 接受 P2，默认单层实施：policy 默认 all→balanced，tier model 空 → `primary_model`，默认行为不变 |
| D-2 | 策略文件 `model_policy.yaml`：`version / default_tier / tiers / roles / escalation`；非法即 `ModelPolicyError` |
| D-3 | 路由器 `route(role, stage, attempts, gate, budget_left, policy)` 为纯函数；同输入同 tier |
| D-4 | 升级只在显式 trigger（`gate_reject` / `two_failures` / `context_over_80`）发生，且 `budget_left==0` 时不升级 |
| D-5 | `LLMClient.chat` 调用前检查预算：`spent >= budget` → `BudgetExhausted` + `budget_exhausted` 事件 |
| D-6 | 成本记录增 `policy_version`；`model` 即 `model_used`，不再新增同义字段 |
| D-7 | `local_only=true` 时仅允许 `localhost/127.0.0.1/::1`，其余 base_url 在调用前 `LocalOnlyViolation` |
| D-8 | 默认 `model_policy.enabled=false`；启用但用默认文件时仍是单层，分层为显式 opt-in |

## 2. 模块划分

| 模块 | 职责 |
|---|---|
| `model_policy.yaml`（仓库根） | 默认单层策略；role→balanced，balanced.model="" |
| `llm/model_policy.py` | 加载/校验、纯路由、模型解析、digest、预算/本地检查、异常 |
| `config.py` | `ModelPolicyConfig(enabled/path/run_budget_usd/local_only)` |
| `llm/client.py` | 前置预算与本地检查；启用时按 role 路由；`policy_version` 落账 |
| `cost_tracker.py` | `CostRecord.policy_version`（默认 0） |
| `runtime/event_log.py` | `budget_exhausted` 事件类型 |

## 3. 策略格式

```yaml
version: 1
default_tier: balanced
tiers:
  fast: {model: ""}
  balanced: {model: ""}
  hard: {model: ""}
roles:
  planner: balanced
  executor: balanced
  reviewer: balanced
  subagent: balanced
escalation:
  from: balanced
  to: hard
  triggers: [gate_reject, two_failures, context_over_80]
```

- `tiers.*.model` 为空 = 使用 `llm.primary_model`。
- `roles` 必须覆盖四类 role；未知 role 拒绝。
- `escalation.triggers` 只接受三个枚举值。

## 4. API

```python
load_model_policy(path=None) -> dict
route(role, *, stage=0, attempts=0, gate="", budget_left=None, policy=None) -> str
resolve_model(tier, policy, primary_model) -> str
policy_digest(policy) -> str
pre_call_budget_check(spent_usd, budget_usd) -> None   # raises BudgetExhausted
check_local_only(base_url, local_only) -> None         # raises LocalOnlyViolation
```

`LLMClient.chat(..., role="executor", stage=0, attempts=0, gate="")`：

1. `check_local_only(config.base_url, config.local_only)`；
2. `pre_call_budget_check(tracker.total_cost_usd, config.run_budget_usd)`；
3. 若 `model_policy_enabled`：`tier=route(...)`，首个模型 = `resolve_model(tier)`，后接 fallback；
4. 记录成本时带 `policy_version`（启用 = 1，否则 0）。

## 5. 验收映射

| ID | 落点 | 负向 |
|---|---|---|
| A6-1 | `route` 表驱动、同输入同 tier | 两次结果不同 → 失败 |
| A6-2 | 仅显式 trigger 升级；预算为 0 不升级 | 无 trigger 越级 → 失败 |
| A6-3 | `pre_call_budget_check` + `budget_exhausted` 事件 | 先调用后拒绝 → 失败 |
| A6-4 | `CostRecord.model` + `policy_version` | 缺字段 → 失败 |
| A6-5 | `check_local_only` 拒绝非 loopback | 发生外联 → 失败 |

## 6. 不变式

| 编号 | 不变式 |
|---|---|
| J-1 | 默认策略 + 默认配置下，模型链与 P-157 之前一致 |
| J-2 | 路由确定性；不依赖时间/随机/网络 |
| J-3 | 升级必须有显式 trigger，且不跨多级 |
| J-4 | 预算为 0 = 关闭检查；`spent >= budget` 才拒绝 |
| J-5 | 本地禁网在 HTTP 之前生效 |
| J-6 | 成本记录只增字段，旧日志可读 |
| J-7 | policy 非法 fail-closed，不静默回退 |
| J-8 | 无 run 上下文时预算检查不写事件、不阻断 |

## 7. Review 记录（Step 6）

- 复用 `cost_log.jsonl` 单一账本（Q20 分层），不新建第二账本。
- 默认关闭 + 默认单层双保险，避免改变既有复现性。
- `budget_exhausted` 事件复用 `EventLog`，不新增日志格式。

## 8. 非目标

训练/偏好数据 router、跨 provider 自动比价、网络层防火墙、G7 的并发/长时程。
