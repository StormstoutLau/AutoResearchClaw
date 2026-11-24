---
id: arc-model-policy-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-master-roadmap, arc-model-policy-DESIGN]
upstream: null
---

# 调研：G6 模型分层与预算治理（P-158）

> **Feature**：P-158。G6 唯一实施批，含 Q12 裁决；按总纲记为 **P2**。
> **Q12 裁决**：接受「降为 P2」的复现性理由，但**实施默认单层**的 G6——策略文件默认所有 role 走 primary，分层路由 opt-in，默认行为与固定模型一致。

---

## 1. 问题

| 面 | 现状（已核实） | 缺口 |
|---|---|---|
| 模型选择 | `LLMConfig.primary_model` + `fallback_models`；reviewer 可独立 | 无 `model_policy.yaml`、无 tier、无 role 路由 |
| 预算 | `cost_log.jsonl` + `CostTracker.check_budget`；runner 超预算停止 | 不是「调用前拒绝」，无 `budget_exhausted` 事件 |
| 审计 | 成本记录有 `model` | 无 `policy_version`；无「model_used」显式语义 |
| 本地模型 | 无 | 无 `local_only` 禁外联开关 |
| 复现性 | 固定模型 | 分层若默认启用会改变成本与输出分布 |

## 2. Q12 裁决

| 选项 | 结论 |
|---|---|
| A 固定模型，G6 不实施 | 不采用：A6-3/A6-4/A6-5 是治理能力，缺失会留下预算与审计缺口 |
| B 升 P1，完整分层默认启用 | 不采用：改变默认成本与复现性，Q12 原降级理由成立 |
| **C 接受 P2，默认单层实施 G6** | **采用**：策略默认 all→balanced（模型空 = primary），router 纯函数可测；分层 opt-in |
| D 只做三项审计 | 不采用：A6-1/A6-2 无法收口 |

## 3. 外部证据（T1）

| # | 来源 | Layer | 日期/版本 | 机制 | 本批借用 | 不借用 |
|---|---|---|---|---|---|---|
| E1 | [FrugalGPT（arXiv:2305.05176）](https://arxiv.org/abs/2305.05176) | T1 | v1 / 2023-05 | LLM cascade：按序调用，可靠性足够即停止；可降 98% 成本 | 「分层 + 预算上限」的动机 | 学习式 cascade 与可靠性判别器 |
| E2 | [RouteLLM（arXiv:2406.18665）](https://arxiv.org/abs/2406.18665) | T1 | v4 / ICLR 2025 | 强/弱模型路由；阈值 α 控制质量-成本权衡 | 「显式阈值 + 确定性路由」形态 | 训练 router、偏好数据 |
| E3 | [OpenTelemetry GenAI 语义约定](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/) | T1 | 访问 2026-11-25 | `gen_ai.request.model` 等模型属性 | 成本记录同时落 `model` 与 `policy_version` 的审计形态 | 不引入 OTel SDK |
| E4 | 本仓 `cost_tracker.py` / `hitl/cost_guard.py` | T1（源码） | P-006/Q20 | `cost_log.jsonl` 单一账本；`check_budget` | 复用账本与预算判断 | 不新建第二账本 |

## 4. 事实核验

| 事实 | 证据 |
|---|---|
| 无 `model_policy.yaml` | 全仓 grep `model_policy` 无实现；仅本文档 |
| `LLMResponse.model` 存在 | `llm/client.py:56-66` |
| `CostRecord` 无 `policy_version` | `cost_tracker.py:37-50` |
| runner 超预算停止但非前置拒绝 | `pipeline/runner.py:777-783` |
| 无 `local_only` | 全仓 grep 无配置项 |

## 5. 风险与边界

| 风险 | 处置 |
|---|---|
| 默认路由改变复现性 | 默认 policy all→balanced，tier model 空 → primary；行为不变 |
| 预算误判 | 复用 `CostTracker` 总账；无价格来源时已有 warning；预算 0 = 关闭检查 |
| 本地模型误联外网 | `local_only` 仅允许 loopback/`localhost`；其余 pre-call 拒绝 |
| policy 文件损坏 | 加载即 `ModelPolicyError`，fail-closed；禁用时不加载 |
| 成本记录漂移 | 只加 `policy_version` 字段，默认 0，旧日志可读 |

## 6. 诚实边界

- 不训练 router、不引入 RouteLLM/FrugalGPT 的学习组件。
- `local_only` 只检查 base_url 主机名，不替代网络层防火墙。
- 默认策略不做跨 tier 升级；升级仅在显式 trigger 且策略开启时发生。

## 7. Review 记录（Step 4）

- E1/E2 支持「显式、可测的 tier 与阈值」；E3 支持审计字段；E4 是本仓单一账本。
- 四项事实逐条 grep/读码可复核。
