---
id: arc-g3-handback-scope-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-13
depends: [arc-g3-handback-scope-RESEARCH]
upstream: arc-g3-handback-scope-RESEARCH
---

# 设计：Handback scope 范围语义修复

> 基于 [RESEARCH.md](RESEARCH.md) 与 [P-090 复评](../../docs/arc-g3-recheck-20261113.md)。只改判定函数，不改数据形态。

## 1. 语法与包含规则

| 条目形态 | 解析 | 覆盖规则 |
|---|---|---|
| `stage:N` | `[N, N]` | 被 `stage:A-B` 覆盖当且仅当 `A ≤ N ≤ B` |
| `stage:A-B`（A≤B） | `[A, B]` | 被 `stage:C-D` 覆盖当且仅当 `C ≤ A` 且 `B ≤ D` |
| `tool:X` | 精确字符串 | 仅 `X == Y` 时被 `tool:Y` 覆盖 |
| 非法（`stage:A-x`、`stage:5-3`、空串） | 不解析为 stage | 不匹配任何 stage；仅按精确字符串匹配（通常拒绝） |

- 默认 mandate `("stage:1-23", "tool:literature")` 覆盖 Stage 17 的 `stage:12-14`。
- 越界示例：mandate `stage:1-11` 不覆盖 `stage:12-14`。

## 2. 接口

```python
_stage_bounds(entry: str) -> tuple[int, int] | None
_scope_covered(requested: str, allowed: Iterable[str]) -> bool
validate_handback(handback: StageHandback, mandate: RunMandate) -> None
```

- `validate_handback` 的签名、异常类型、错误消息前缀 `E_HANDBACK_SCOPE` 不变。
- `RunMandate` / `StageHandback` 字段不变。

## 3. 决策表

| # | 决策 | 依据 | 拒绝方案 |
|---|---|---|---|
| D-1 | 范围包含判定 | R-1..R-3 | 拒绝改 Stage 17 的 `stage:12-14` 为 `stage:1-23`：丢失粒度 |
| D-2 | `tool:*` 精确匹配 | 工具权限无范围语义 | 拒绝前缀/通配：会扩大权限 |
| D-3 | 非法格式 fail-closed | 安全默认 | 拒绝「未知格式放行」 |
| D-4 | 只改 `validate_handback` | 零迁移 | 拒绝改 mandate 数据结构：影响已落盘文件 |

## 4. 不变式

- I-1 合法子范围放行；越界仍拒绝。
- I-2 `tool:*` 权限不因本修复扩大。
- I-3 非法格式不获得任何 stage 权限。
- I-4 mandate/handback 文件形态不变。
- I-5 错误码与消息前缀不变。

## 5. 非目标

- 不支持 `stage:*` 通配（未在契约中定义）。
- 不支持跨类型推导（`tool:` 不覆盖 `stage:`）。
- 不改变 Stage 17 的 requested_scope 值。

## 6. 验收映射

| 验收 | 落点 |
|---|---|
| 子范围放行 | F-1/F-2 |
| 越界拒绝 | F-3 |
| 工具精确匹配 | F-4 |
| 非法格式拒绝 | F-5 |
| 端到端不误阻断 | F-6 |
