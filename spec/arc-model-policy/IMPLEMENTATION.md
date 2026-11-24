---
id: arc-model-policy-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-model-policy-DESIGN]
upstream: null
---

# 实施：G6 模型分层与预算治理（P-158）

> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **状态**：实施完成；代码、测试与读数已回填。
> **批次口径**：G6 单批（含 Q12）；G7 另立。

---

## 1. 计划变更清单

| 文件 | 动作 | 内容 |
|---|---|---|
| `model_policy.yaml` | 新增 | 默认单层策略（四 role → balanced，model 空） |
| `researchclaw/llm/model_policy.py` | 新增 | 加载/校验、路由、模型解析、digest、预算/本地检查、异常 |
| `researchclaw/config.py` | 修改 | `ModelPolicyConfig` + RCConfig 字段与解析 |
| `researchclaw/llm/client.py` | 修改 | 前置预算/本地检查、role 路由、`policy_version` 落账 |
| `researchclaw/cost_tracker.py` | 修改 | `CostRecord.policy_version`（默认 0） |
| `researchclaw/runtime/event_log.py` | 修改 | `EVENT_TYPES` 增 `budget_exhausted` |
| `tests/test_model_policy.py` | 新增 | T01-T09 |
| `tests/test_model_policy_wiring.py` | 新增 | T10-T15 |

## 2. 实施顺序

1. `model_policy.py` 纯函数与默认策略（先写负向用例）；
2. `model_policy.yaml` 与配置解析；
3. `LLMClient` 前置检查与路由；
4. `CostRecord.policy_version` 与事件类型；
5. 回归与门禁。

## 3. 测试用例清单

### 3.1 策略与路由（`tests/test_model_policy.py`）

| # | 用例 | 输入 | 期望 | 反例/边界 | 验收 |
|---|---|---|---|---|---|
| T01 | `test_default_policy_is_single_tier` | 默认 policy | 四 role=balanced，三 tier model 空 | role 缺失 → 失败 | A6-1 |
| T02 | `test_route_is_deterministic` | 同输入两次 | tier 相同 | 结果不同 → 失败 | A6-1 |
| T03 | `test_route_uses_role_table` | 四 role | 各自映射 | 未知 role → 失败 | A6-1 |
| T04 | `test_escalation_requires_trigger` | 无 trigger | 不升级 | gate_reject/attempts=2 才升级 | A6-2 |
| T05 | `test_no_escalation_without_budget` | budget_left=0 | 不升级 | 越级 → 失败 | A6-2 |
| T06 | `test_invalid_policy_rejected` | 未知 tier/role/trigger | `ModelPolicyError` | 静默回退 → 失败 | J-7 |
| T07 | `test_resolve_model_falls_back_to_primary` | tier model 空 | 返回 primary | 返回空串 → 失败 | A6-1 |
| T08 | `test_policy_digest_deterministic` | 同 policy / 改字段 | 同值 / 变化 | 顺序敏感 → 失败 | J-2 |
| T09 | `test_pre_call_budget_check` | 0/0.9/1.0/超过 | 仅 >= 才抛 | 预算 0 抛错 → 失败 | A6-3 |

### 3.2 接线（`tests/test_model_policy_wiring.py`）

| # | 用例 | 输入 | 期望 | 反例/边界 | 验收 |
|---|---|---|---|---|---|
| T10 | `test_config_defaults` | 无 `model_policy` | enabled=false、budget=0、local_only=false | 默认启用 → 失败 | J-1 |
| T11 | `test_config_parses_fields` | YAML 字段 | 值解析正确 | 类型错 → 失败 | — |
| T12 | `test_local_only_blocks_remote_before_http` | 远程 base_url | `LocalOnlyViolation`，HTTP 未被调用 | 先外联 → 失败 | A6-5 |
| T13 | `test_budget_blocks_before_http_and_emits_event` | 已花 = 预算 | `BudgetExhausted` + `events.jsonl` 含 `budget_exhausted` | 先调用 → 失败 | A6-3 |
| T14 | `test_cost_record_has_policy_version` | 启用策略 | `model` + `policy_version=1` | 缺字段 → 失败 | A6-4 |
| T15 | `test_enabled_policy_routes_to_tier_model` | hard tier model 指定 | 首个模型 = 该 model | 仍用 primary → 失败 | A6-1 |

## 4. 算法级证据锚点

| 设计点 | 锚点 | 代码落点 | 用例 |
|---|---|---|---|
| 分层与预算 | FrugalGPT E1：cascade + 成本 | `route` + `pre_call_budget_check` | T02/T09 |
| 显式路由阈值 | RouteLLM E2：阈值控制质量-成本 | role→tier 表 + trigger | T03/T04 |
| 审计字段 | OTel GenAI E3：model 属性 | `CostRecord.model/policy_version` | T14 |
| 单一账本 | 本仓 Q20 / `cost_tracker` | 复用 `cost_log.jsonl` | T13/T14 |

## 5. 接口签名与回退点

| 接口 | 签名 | 回退点 |
|---|---|---|
| `load_model_policy` | `(path=None) -> dict` | 不提供文件 → 默认策略 |
| `route` | `(role, *, stage=0, attempts=0, gate="", budget_left=None, policy=None) -> str` | 删除路由；模型链回到 primary+fallback |
| `resolve_model` | `(tier, policy, primary_model) -> str` | tier model 空 → primary |
| `pre_call_budget_check` | `(spent_usd, budget_usd) -> None` | budget=0 关闭 |
| `check_local_only` | `(base_url, local_only) -> None` | local_only=false 关闭 |
| `LLMClient.chat` | 新增 `role/stage/attempts/gate` 关键字，默认 executor | 默认参数保持旧行为 |

## 6. 低效排除表

| 排除项 | 理由 |
|---|---|
| 训练式 router（RouteLLM） | 需偏好数据与训练，超出 G6；默认单层已满足复现性 |
| 跨 provider 自动比价 | 价格漂移、需外部目录；本批只做显式策略 |
| 新建第二本账 | 违反 Q20 单一账本；复用 `cost_log.jsonl` |
| 网络层防火墙 | `local_only` 只做调用前主机检查；防火墙属部署 |
| 默认启用分层 | 会改变成本与复现性；opt-in |

## 7. 版本核验表

| 依赖 | 版本 | 核验 | 用途 |
|---|---|---|---|
| Python | 3.11–3.14 | CI | 运行时 |
| `PyYAML` | 既有依赖 | 本仓 | policy 解析 |
| `ipaddress`/`urllib.parse` | stdlib | Python 文档 | 本地主机判定 |
| FrugalGPT | arXiv 2305.05176 | arXiv | 分层动机 |
| RouteLLM | arXiv 2406.18665 | arXiv/ICLR 2025 | 阈值路由形态 |
| OTel GenAI | 访问 2026-11-25 | 官方语义约定 | 审计字段 |

## 8. 红→绿记录

| 阶段 | 预期失败态 | 实际读数 |
|---|---|---|
| 初版测试（模块未建） | `ModuleNotFoundError` | `2 errors in 0.27s`（`researchclaw.llm.model_policy`） |
| 实现后 | 负向用例（T05/T06/T09/T12/T13）先红后绿 | **17 passed in 0.21s**（一次通过，无测试缺陷） |
| 回归 | LLM/cost/config/executor | **431 passed in 196.14s** |
| CI 首轮 | 全量契约测试 | **1 failed, 3889 passed**：`test_frontend_event_types_match_runtime`——前端 `EVENT_TYPES` 未含 `budget_exhausted`；修复 `frontend-legacy/src/services/api.js` 后 `test_event_stream.py` 9 passed |

## 9. 读数

```text
$ python -m pytest tests/test_model_policy.py tests/test_model_policy_wiring.py -q
17 passed in 0.21s

$ python -m pytest tests/test_rc_llm.py tests/test_reviewer_llm.py \
    tests/test_cost_tracker.py tests/test_rc_config.py tests/test_rc_templates.py \
    tests/test_offline_audit.py tests/test_rc_executor.py -q
431 passed in 196.14s
```

- 17 = 策略/路由 9 条 + 接线 6 条 + local_only 2 条（T09 中预算与本地分文件）。
- 默认 `enabled=false`；即使启用，默认 policy 四 role→balanced 且 tier model 空，模型链仍是 `primary_model`。
- 一次通过；无测试缺陷修正。

## 10. 门禁

| 门禁 | 读数 |
|---|---|
| dc_validator | 本批 0 违规（全仓 148 存量：P1=62/P2=86） |
| grandfather_gate | grandfathered=0 expired=0 violations=0 |
| step-gate | 5/5（research/design/implement/verify/finalize） |
| verify-anchor | 10 真实 / 0 缺失 / 0 漂移 |
| step_enforce | `digest_bound=1` |
| pre-commit | 全绿 |
| PR CI | 8/8（首轮前端契约 1 failed 已修；重跑 8/8） |

## 11. 未做与边界

- 不训练 router、不做偏好数据、不做跨 provider 比价。
- 默认策略单层；分层需显式改 policy 并启用。
- `local_only` 是调用前检查，不是网络层隔离。
