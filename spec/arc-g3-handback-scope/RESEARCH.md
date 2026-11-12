---
id: arc-g3-handback-scope-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-13
depends: [arc-g3-recheck]
upstream: arc-g3-recheck
---

# 调研文档：Handback scope 范围语义修复（P-091）

> **Feature**：P-091，P-090 复评 D-1 P2 修复。
> **Spec 步骤**：Step 1-2。
> **输入**：[P-090 复评](../../docs/arc-g3-recheck-20261113.md)；[mandate.py](../../researchclaw/runtime/mandate.py)。

## 1. 调研目标

1. **语义缺口**：mandate 的 `stage:1-23` 与 handback 的 `stage:12-14` 应如何判定包含关系？
2. **最小修法**：只改 `validate_handback` 是否足够？是否需要改 `RunMandate`/`StageHandback` 数据形态？
3. **CI 盲区**：为何 93 项既有测试全绿仍未发现？

## 2. 调研方法

| 通道 | 用途 | 结果 |
|---|---|---|
| P-090 探针（E2） | 真实 Stage 17 → runner guard 复现 | ✅ D-1 复现 |
| 仓内读码（E1） | `validate_handback`、`ensure_run_mandate`、Stage 17 scope | ✅ 定位 |
| 既有测试审阅 | 为何未报警 | ✅ 盲区确认 |

## 3. 调研发现

| # | 事实 | 位置 | 影响 |
|---|---|---|---|
| R-1 | mandate 默认 scope 为 `stage:1-23`、`tool:literature` | `mandate.py` | 范围记法 |
| R-2 | Stage 17 阻断分支写 `stage:12-14` | `_paper_writing.py` | 子范围请求 |
| R-3 | `validate_handback` 用 `item not in set(mandate.scope)` | `mandate.py` L153-L162 | 离散匹配，子范围必拒 |
| R-4 | 既有测试用 `stage:1-23` 字面量或只测 Stage 17 函数层 | 测试套件 | 不经过真实子范围 + runner guard 组合 |
| R-5 | CI 回归 93 passed | P-090 复跑 | 盲区确证 |

## 4. 综合分析

1. **范围包含是正确语义**：`stage:A-B` 覆盖 `stage:C-D` 当且仅当 `[C,D] ⊆ [A,B]`；`stage:N` 视为 `[N,N]`。[★★★★★]
2. **`tool:*` 应保持精确匹配**：工具权限没有范围概念，放宽会扩大权限。[★★★★★]
3. **非法格式必须 fail-closed**：`stage:1-x` 不解析为范围，也不匹配任何工具条目 → 拒绝。[★★★★☆]
4. **只需改 `validate_handback`**：数据形态不变，迁移面为零。[★★★★★]
5. **CI 盲区可通过端到端测试封堵**：真实 Stage 17 handback + `_apply_handback_guard`。[★★★★★]

## 5. 幻觉抑制审查（Step 2 Review）

| 声明 | 来源 | 状态 |
|---|---|---|
| 当前实现为离散匹配 | R-3 读码 | ✅ E1 |
| Stage 17 请求子范围 | R-2 读码 + P-090 探针 | ✅ E1/E2 |
| 既有测试未覆盖组合 | R-4/R-5 读码 + 复跑 | ✅ E1 |
| 范围包含是集合包含 | 数学定义 | ✅ |

## 6. 对设计的输入

- 只改 `validate_handback` 的判定；`RunMandate`/`StageHandback` 字段不变。
- 非法/未知格式拒绝。
- 补 4 项单元测试 + 1 项端到端回归。

## 7. 参考文献

- P-090 复评：`docs/arc-g3-recheck-20261113.md`。
- M0 治理设计：`spec/arc-g3-m0-design/DESIGN.md` §7.2。

---

**Review 签字**: 自查（单视角）+ 机械核验 日期: 2026-11-13
