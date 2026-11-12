---
id: arc-g3-handback-scope-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-13
depends: [arc-g3-handback-scope-DESIGN]
upstream: arc-g3-handback-scope-DESIGN
---

# 实施记录：Handback scope 范围语义修复（P-091）

> **状态**：施工完成；读数见 §5。

## 1. 改动清单

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `researchclaw/runtime/mandate.py` | 修改 | `_STAGE_SCOPE_RE`、`_stage_bounds`、`_scope_covered`；`validate_handback` 改用包含判定 |
| 2 | `tests/test_mandate.py` | 修改 | +4：子范围放行、单 stage 放行、子范围越界拒绝、非法格式拒绝 |
| 3 | `tests/test_rc_executor.py` | 修改 | 真实 Stage 17 阻断后走 `_apply_handback_guard`，断言仍为 PAUSED |

**不改**：`RunMandate`/`StageHandback` 字段、Stage 17 的 scope 值、错误码。

## 2. 接口与回退点

| 接口 | 签名 | 回退点 |
|---|---|---|
| `_stage_bounds` | `(entry: str) -> tuple[int,int] \| None` | 纯函数；非法返回 None |
| `_scope_covered` | `(requested, allowed) -> bool` | 纯函数 |
| `validate_handback` | 签名不变 | 回退 = 恢复离散集合匹配 |

## 3. 关键行为

- `stage:1-23` 覆盖 `stage:12-14` 与 `stage:5`。
- `stage:1-11` 不覆盖 `stage:12-14`。
- `tool:literature` 仅匹配自身；`tool:shell` 拒绝。
- `stage:1-x`、`stage:5-3` 不解析为 stage，拒绝。
- 真实 Stage 17 `blocked_no_metrics` → handback → runner guard 保持 PAUSED。

## 4. 版本与 API 兼容性核验（Step 6）

| 依赖 | 用法 | 下限可用性 | 状态 |
|---|---|---|---|
| `re` | 范围解析 | 3.11 全有 | ✅ |
| `typing.Iterable` | 判定入参 | 3.11 全有 | ✅ |
| 3.12+ stdlib API | 无 | — | ✅ |

## 5. 读数（Step 9-10 回填）

| 项 | 读数 |
|---|---|
| 新增/修改测试 | 新增 4 项；修改 1 项既有测试（端到端 guard 断言） |
| 双环境 | 3.13.5 关键集 **15 passed**；3.11.15 **14 passed**（筛选用例集差异） |
| 相关回归 | 11 文件 **361 passed**（119.92s） |
| 门禁 | DC 0 违规；step-gate 5/5；step-enforce `digest_bound=2`；pre-commit **9/9 Passed** |
| 红→绿 | 红态由 P-090 D-1 探针提供（`stage:12-14` 被判越界、runner 升级 FAILED）；本批先在 `mandate.py` 落地范围判定、后补测试，**非严格先红后绿**，属受控例外；绿态 15 passed → 361 passed |

## 6. 验收边界（诚实口径）

- 只支持 `stage:N` / `stage:A-B`；不支持 `stage:*`。
- 非法格式按精确字符串匹配（通常拒绝），不抛解析异常。
- 不改变 Stage 17 的 `requested_scope` 值。

## 7. 风险

- 若未来引入 `stage:*` 或 `tool:*` 通配，需要显式扩展语法与测试。
- 端到端回归依赖 Stage 17 阻断 fixture；其他阶段的 handback 生产面仍有限。
