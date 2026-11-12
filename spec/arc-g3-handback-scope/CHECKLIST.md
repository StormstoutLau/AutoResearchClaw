---
id: arc-g3-handback-scope-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-13
depends: [arc-g3-handback-scope-IMPLEMENTATION, arc-g3-handback-scope-DESIGN]
upstream: arc-g3-handback-scope-IMPLEMENTATION
---

# 验收清单：Handback scope 范围语义修复（P-091）

> **Spec 步骤**：Step 7-8, 10。
> **基于实施**：[IMPLEMENTATION.md](IMPLEMENTATION.md)　**基于设计**：[DESIGN.md](DESIGN.md)

## 1. 文档一致性（Step 8）

| # | 检查项 | 状态 | 说明 |
|---|---|---|---|
| DC-1 | RESEARCH 结论在 DESIGN 被使用（R-3→D-1、R-1→D-2、R-4→D-4） | ✅ | DESIGN §3 |
| DC-2 | DESIGN 模块在 IMPLEMENTATION 有实施 | ✅ | DESIGN §2 ↔ IMPL §1/§2 |
| DC-3 | IMPLEMENTATION 功能点在 CHECKLIST 有验收项 | ✅ | F-1..F-6 |
| DC-4 | 无文档矛盾（范围语法、tool 精确、错误码） | ✅ | 四文档互查 |
| DC-5 | 术语一致（范围包含 / 精确匹配 / fail-closed） | ✅ | 四文档 |
| DC-6 | 诚实边界已声明 | ✅ | IMPL §5/§6 |

## 2. 功能验收

| # | 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|---|---|---|---|---|---|
| F-1 | 子范围放行 | `test_handback_stage_subrange_is_covered` | `stage:12-14` 在 `stage:1-23` 内可写 | ✅ | 15 passed |
| F-2 | 单 stage 放行 | `test_handback_single_stage_is_covered` | `stage:5` 在 `stage:1-23` 内 | ✅ | 同上 |
| F-3 | 子范围越界拒绝 | `test_handback_subrange_outside_mandate_is_rejected` | `stage:1-11` 拒绝 `stage:12-14` | ✅ | 同上 |
| F-4 | 工具精确匹配 | `test_handback_out_of_scope_is_rejected` | `tool:shell` 被拒 | ✅ | 同上 |
| F-5 | 非法格式拒绝 | `test_handback_unknown_scope_format_is_rejected` | `stage:1-x` 被拒 | ✅ | 同上 |
| F-6 | 端到端不误阻断 | `test_paper_draft_blocked_no_metrics` 内 guard 断言 | 真实 Stage 17 handback → PAUSED | ✅ | `test_rc_executor` |

## 3. 接口验收

| # | 接口 | 通过条件 | 状态 |
|---|---|---|---|
| API-1 | `_stage_bounds` | 合法范围返回 `(lo,hi)`；非法返回 None | ✅ |
| API-2 | `_scope_covered` | 范围包含 + 工具精确 | ✅ |
| API-3 | `validate_handback` | 签名/异常/错误前缀不变 | ✅ |

## 4. 不变式验收

| # | 不变式（DESIGN §4） | 验证方法 | 状态 |
|---|---|---|---|
| INV-1 | I-1 合法子范围放行、越界拒绝 | F-1..F-3 | ✅ |
| INV-2 | I-2 工具权限不扩大 | F-4 | ✅ |
| INV-3 | I-3 非法格式无权限 | F-5 | ✅ |
| INV-4 | I-4 数据形态不变 | diff 仅 mandate.py 判定段 | ✅ |
| INV-5 | I-5 错误码不变 | grep `E_HANDBACK_SCOPE` | ✅ |

## 5. 错误处理验收

| # | 场景 | 触发 | 预期 | 状态 |
|---|---|---|---|---|
| E-1 | 子范围越界 | `stage:12-14` vs `stage:1-11` | `HandbackScopeError` | ✅ |
| E-2 | 工具越界 | `tool:shell` | 拒绝 | ✅ |
| E-3 | 非法范围 | `stage:1-x` / `stage:5-3` | 拒绝 | ✅ |

## 6. 兼容性验收

| # | 环境 | 状态 | 说明 |
|---|---|---|---|
| C-1 | Python 3.13.5 | ✅ | 关键集 15 passed；回归 361 passed |
| C-2 | Python 3.11.15 | ✅ | 关键集 14 passed |
| C-3 | 既有 P-089 handback 测试 | ✅ | 全部保持通过 |

## 7. ADD 审计

### 7.1 四阶段

| # | 阶段 | 结果 | 状态 |
|---|---|---|---|
| ADD-1 | Phase 1 完整性 | 范围解析、包含判定、非法拒绝均有实现 | ✅ |
| ADD-2 | Phase 2 忠实度 | 仅改判定；数据形态与错误码不变 | ✅ |
| ADD-3 | Phase 3 必要性 | 每项行为有 R-1..R-5 依据 | ✅ |
| ADD-4 | Phase 4 语义 | 真实 Stage 17 暂停不再被误升级 | ✅ |

### 7.2 审计发现

| 严重性 | 发现 | 证据 | 建议 |
|---|---|---|---|
| P3 | 本批测试在实现后补齐，非严格先红后绿 | IMPL §5 | 红态由 P-090 探针提供；后续批保持先红 |
| P3 | 不支持 `stage:*` / `tool:*` 通配 | IMPL §6 | 需要时显式扩展 |

### 7.3 取证矩阵

| 取证手段（等级） | 覆盖项 | 结果 |
|---|---|---|
| pytest 双环境（E1） | F-1..F-5、C-1/C-2 | ✅ 15/14 passed |
| pytest 回归（E1） | F-6、C-3 | ✅ 361 passed |
| 运行时探针（E2） | F-1/F-6 | ✅ 子范围放行、guard 保持 PAUSED |
| 静态读码（E3） | API-1..3、INV-2..5 | ✅ |
| 盲区扫描（E4，扫描范围：30 项 + 2 边界） | 全部 | **发现 2 项 P3**（§7.2） |

## 8. 文档完整性

| 文档 | 存在 | 与实现一致 |
|---|---|---|
| RESEARCH.md | ✅ | ✅ |
| DESIGN.md | ✅ | ✅ |
| IMPLEMENTATION.md | ✅ | ✅ |
| CHECKLIST.md（本文件） | ✅ | ✅ |
| ADR | 不适用 | — |
| 开发日志 | PROGRESS P-091 行 | ✅ |

## 9. 验收结论

### 9.1 统计

| 类别 | 总数 | 通过 | 失败 |
|---|---|---|---|
| 文档一致性 | 6 | 6 | 0 |
| 功能 | 6 | 6 | 0 |
| 接口 | 3 | 3 | 0 |
| 不变式 | 5 | 5 | 0 |
| 错误处理 | 3 | 3 | 0 |
| 兼容性 | 3 | 3 | 0 |
| ADD 审计 | 4 | 4 | 0 |
| **总计** | 30 | 30 | 0 |

> 统计口径（RULE-2）：逐项勾选，非事后推算。

### 9.2 决定

- [x] **验收通过**（P1/P2 零缺陷；2 项 P3 登记）
- [ ] 有条件通过
- [ ] 验收失败

### 9.3 签字

| 角色 | 签字 | 日期 |
|---|---|---|
| 实施者 | DeepSeek-V4.1-Flash（本会话） | 2026-11-13 |
| 审查者 | 自查（单视角）+ 机械核验；P-092 复评待后续 | 2026-11-13 |

## 10. 后续行动

| 行动 | 责任人 | 期限 | 状态 |
|---|---|---|---|
| P-092 复评 D-1 | 后续批次 | 收口前 | pending |
| 通配语法扩展 | 后续裁决 | 需要时 | pending |
