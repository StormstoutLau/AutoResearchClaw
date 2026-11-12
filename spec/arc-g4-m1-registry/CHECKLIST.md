---
id: arc-g4-m1-registry-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-14
depends: [arc-g4-m1-registry-IMPLEMENTATION]
upstream: arc-g4-m1-registry-IMPLEMENTATION
---

# 检查清单：G4-M1 工具注册表与启动校验（P-101）

## 1. 文档一致性（Step 8）

| # | 检查项 | 状态 | 说明 |
|---|---|---|---|
| DC-1 | RESEARCH Q-1..Q-5 裁决在 DESIGN 被使用（§3→§2/§3） | ✅ | DESIGN §6 挂来源 |
| DC-2 | DESIGN 模块在 IMPLEMENTATION 有对应实施 | ✅ | §1 边界 ↔ §2 记录 |
| DC-3 | IMPLEMENTATION 功能点在 CHECKLIST 有验收项 | ✅ | §2 A4-1 + §4 不变式 |
| DC-4 | 无文档间矛盾（错误码 9 个、迁移表、V-5a/b） | ✅ | 与 M0 DESIGN（已回边）互查一致 |
| DC-5 | P-100 D-1/D-2 修正输入显式落地 | ✅ | V-8（T-6 实证）+ Q-1（pyproject diff） |

## 2. A4-1 验收（本批核心）

| # | 验收项 | 测试方法 | 通过条件 | 状态 |
|---|---|---|---|---|
| A4-1 正向 | 100% 工具有 schema 且可装载 | T-1 | 6 工具装载、名称集合相等 | ✅ |
| A4-1 等价 | schema 与迁移前逐字段相等（INV-4） | T-2 deep equality | 全 6 工具相等 | ✅（主环境；轻量环境 skip） |
| A4-1 负向 | 缺 `inputSchema` 启动即失败 | T-3 | `E_REGISTRY_SCHEMA_MISSING`，无 fallback | ✅ |
| A4-1 负向 | 非法 schema | T-4 + draft violation | `E_REGISTRY_SCHEMA_INVALID` | ✅ |
| D-1 关闭 | `risk=high + approval=never` 被拒 | T-6 | `E_REGISTRY_APPROVAL` | ✅ |
| D-2 落地 | `jsonschema` 升核心依赖 | pyproject diff | dependencies 含条目 | ✅ |

## 3. 规则矩阵（9 条校验全覆盖）

| 规则 | 负向用例 | 状态 |
|---|---|---|
| V-1 | T-8（字符串 "1"） | ✅ |
| V-2 | T-7（重名）+ T-name（非法模式） | ✅ |
| V-3 | T-3/T-4/draft | ✅ |
| V-4 | T-5（3 参数化） | ✅ |
| V-5a | T-9（无冒号 handler） | ✅ |
| V-5b | T-12（不存在 attr） | ✅ |
| V-6 | T-10（未定义 profile） | ✅ |
| V-7 | T-11（缺 pids） | ✅ |
| V-8 | T-6 | ✅ |

## 4. 不变式验收（DESIGN §8）

| # | 不变式 | 验证方法 | 状态 |
|---|---|---|---|
| INV-1 | 注册表唯一真值源（双源 + T-2 锁定） | 读码 + T-2 | ✅ |
| INV-2 | fail-closed 无 fallback | 9 条负向用例 | ✅ |
| INV-3 | 首错即抛 | 实现读码 | ✅ |
| INV-4 | 6 工具名称/参数不变 | T-2 | ✅ |
| INV-5 | 核心路径不 import `mcp.*` | registry.py 读码（仅 yaml/jsonschema/importlib） | ✅ |
| INV-6 | `Registry` 不可变；reload 失败旧实例不变 | T-13 | ✅ |

## 5. 回归与门禁

| # | 检查 | 结果 |
|---|---|---|
| R-1 | 3.13.5 套件（registry+MCP+claim 七文件） | 194 passed |
| R-2 | 3.11.15（registry+MCP 三文件） | 18 passed / 3 skipped（mcp 缺席诚实 skip） |
| R-3 | 十五文件宽回归 | 278 passed |
| R-4 | 扩展组（rc_executor 等十文件） | 348 passed |
| R-5 | MCP 42 项 | 含于 R-1/R-3，零失败 |
| R-6 | 门禁链（DC/step-gate/step-enforce/pre-commit） | 待回填 |

## 6. 遗留登记

| # | 项 | 处置 |
|---|---|---|
| U-1 | T-2 在无 mcp extra 环境为 skip | CI tests job 装含 extras 实跑 |
| U-2 | `mcp/tools.py` 双源保留 | M2 迁移后移除 |
| U-3 | `sandbox_profiles.default` 占位 | M4 消费 |
| U-4 | 审批门运行时保险分支（V-8 之运行时层） | M3（P-103） |

---
