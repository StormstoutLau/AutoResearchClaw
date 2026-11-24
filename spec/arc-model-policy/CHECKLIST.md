---
id: arc-model-policy-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-25
depends: [arc-model-policy-IMPLEMENTATION, arc-model-policy-DESIGN]
upstream: null
---

# 审查验收 Checklist：G6 模型分层与预算治理（P-158）

> **Feature**：P-158（G6 单批，含 Q12）。
> **基于实施**：[IMPLEMENTATION.md](./IMPLEMENTATION.md)（v1.0 / verified）。
> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **状态**：验收完成；34/34 通过，读数见 §10。

---

## 1. 文档一致性验收

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN 可追溯到 RESEARCH | ✅ | D-1..D-8 对应 RESEARCH §2/§3 |
| Q12 裁决一致 | ✅ | 「接受 P2 + 默认单层」四处一致 |
| DESIGN ↔ IMPLEMENTATION 变更面一致 | ✅ | 2 新增 + 4 修改 + 2 测试 |
| 术语一致 | ✅ | tier/role/escalation/policy_version/local_only 互查一致 |

## 2. 功能验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| A6-1 路由确定性 | 同输入两次 | tier 相同 | ✅ | T01-T03 passed |
| A6-2 升级触发器 | 无/有 trigger | 仅显式 trigger 升级 | ✅ | T04/T05 passed |
| A6-3 预算前置拒绝 | 已花=预算 | 调用前拒绝 + 事件 | ✅ | T09/T13 passed |
| A6-4 审计字段 | 启用策略 | `model` + `policy_version` | ✅ | T14 passed |
| A6-5 本地禁网 | 远程 base_url | 调用前拒绝 | ✅ | T12 passed |

## 3. 接口验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| `load_model_policy` | 默认/非法文件 | 默认单层 / fail-closed | ✅ | T01/T06 passed |
| `route` | 四 role + trigger | 表驱动、确定 | ✅ | T02-T04 passed |
| `resolve_model` | tier model 空/非空 | primary / 指定模型 | ✅ | T07/T15 passed |
| `policy_digest` | 同/改 | 稳定/变化 | ✅ | T08 passed |
| `pre_call_budget_check` | 0/边界/超 | 仅 >= 抛 | ✅ | T09 passed |
| `check_local_only` | loopback/远程 | 允许/拒绝 | ✅ | T12 passed |
| `LLMClient.chat` 默认参数 | 不传 role | 行为同旧版 | ✅ | T10 passed |
| `CostRecord` | 启用策略 | 含 `policy_version` | ✅ | T14 passed |

## 4. 不变式验收

| 不变式 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| J-1 默认行为不变 | 默认配置 | 模型链同旧版 | ✅ | T10 passed |
| J-2 路由确定 | 同输入 | 结果一致 | ✅ | T02 passed |
| J-3 升级受控 | 无 trigger | 不升级 | ✅ | T04 passed |
| J-4 预算 0 = 关闭 | budget=0 | 不抛 | ✅ | T09 passed |
| J-5 本地检查先于 HTTP | 远程 | HTTP 未调用 | ✅ | T12 passed |
| J-6 旧成本日志可读 | 默认字段 | 默认 0 | ✅ | T14 + 431 回归 |
| J-7 policy fail-closed | 非法文件 | `ModelPolicyError` | ✅ | T06 passed |
| J-8 无 run 不写事件 | 未 begin_run | 仅抛异常/不写 | ✅ | T13 边界读码 |

## 5. 错误处理验收

| 场景 | 测试方法 | 通过条件 | 状态 | 证据 |
|------|---------|---------|------|------|
| 未知 role/tier/trigger | 非法 policy | `ModelPolicyError` | ✅ | T06 passed |
| 预算耗尽 | spent>=budget | `BudgetExhausted` | ✅ | T09/T13 passed |
| 远程端点 + local_only | 远程 URL | `LocalOnlyViolation` | ✅ | T12 passed |
| 事件写入失败 | 无 run_dir | 不阻断主调用 | ✅ | 读码：`_emit_budget_event` 吞异常 |
| 模型名解析 | tier 空 | 回退 primary | ✅ | T07 passed |
| 配置缺省 | 无 `model_policy` | 默认关闭 | ✅ | T10 passed |

## 6. 性能验收

纯字典查找与一次字符串解析，无门槛；不新增网络/磁盘读。

## 7. 兼容性验收

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 既有 LLM 测试 | 回归 | 全绿 | ✅ | 431 passed |
| 成本日志旧格式 | 旧记录读取 | 不报错 | ✅ | T14 + `policy_version` 默认 0 |
| 默认关闭 | 不启用 | 零行为差异 | ✅ | T10 passed |

## 8. ADD 审计

本批无 ADD 新增或修订。

## 9. Review 记录（Step 8）

- Q12 裁决 ↔ DESIGN D-1 ↔ CHECKLIST §2 一致。
- 外部证据 E1-E4 均为 T1；算法锚点见 IMPLEMENTATION §4。
- 实施完成：17 passed（一次通过）；回归 431 passed；红相 2 个 `ModuleNotFoundError`（IMPLEMENTATION §8）。

## 10. 统计与结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|------|------|------|------|------|
| 文档一致性 | 4 | 4 | 0 | 0 |
| 功能 | 5 | 5 | 0 | 0 |
| 接口 | 8 | 8 | 0 | 0 |
| 不变式 | 8 | 8 | 0 | 0 |
| 错误处理 | 6 | 6 | 0 | 0 |
| 性能 | 0 | 0 | 0 | 0 |
| 兼容性 | 3 | 3 | 0 | 0 |
| ADD 审计 | 0 | 0 | 0 | 0 |
| **总计** | **34** | **34** | **0** | **0** |

算术自洽：34 = 4+5+8+8+6+0+3+0；通过 34 = 总数 34。

### 10.2 验收结论

- [x] 验收通过：17 passed；回归 431 passed。
- [ ] 验收不通过：无。

### 10.3 默认行为

`model_policy.enabled` 默认 `false`；即使启用，默认 policy 四 role→balanced 且 tier model 为空，模型链仍为 `primary_model`。分层与升级需要显式修改 policy。

## 11. 行动与遗留

| 事项 | 状态 | 说明 |
|------|------|------|
| 代码实施 | 已完成 | `model_policy.yaml` + 纯函数模块 + client/config/cost/event 接线 |
| 测试与验收 | 已完成 | 17 passed；34/34 |
| Q12 | 已裁决 | 接受 P2 + 默认单层（用户确认） |
| 学习式 router | 未做 | RouteLLM 类方案留后续 |
| G7 | 未开始 | 另立批次 |
