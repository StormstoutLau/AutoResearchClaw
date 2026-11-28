---
id: arc-stage10-split-rejection-accounting-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-29
depends: [arc-stage10-split-rejection-accounting-RESEARCH]
upstream: arc-stage10-split-rejection-accounting-RESEARCH
---

# 设计：拆分修复的拒收记账（P-233）

## 1. 决策

| ID | 决策 | 依据 |
|---|---|---|
| K-1 | `_repair_files_individually` 的兜底拒因改为「既不在 `fixed` 也不在 `rejected` 才记 `not_returned`」 | L-1/L-2 |
| K-2 | 不改 P-226 的计数语义：同 `(file, reason)` 连续两次仍应停止，只是不再收到假的拒因 | L-3 |
| K-3 | 不加新的遥测字段：`accepted` 与 `rejected_reasons` 互斥本身就是可核对的不变式 | 最小改动 |

## 2. 被拒绝的替代方案

| 方案 | 拒绝理由 | 代价 |
|---|---|---|
| 在父函数过滤掉与 `fixed` 重叠的拒因 | 掩盖来源，`_repair_files_individually` 自身的返回值仍然是错的 | 问题后移 |
| 拆分模式不向 P-226 计数 | 会让真正连续失败的拆分轮永不停止 | 回退 P-226 的价值 |
| 把 `not_returned` 改名以避开止损 | 语义未变，止损误触发照旧 | 无收益 |

## 3. 接口

```python
if accepted:
    fixed.update(accepted)
if why:
    rejected.update(why)
if name not in fixed and name not in rejected:
    rejected[name] = "not_returned"
```

不变式：`set(fixed) & set(rejected) == empty`。

## 4. 验收

- 单文件拆分修复成功 → `rejected == {}`，父 trace 的 `rejected_reasons` 不含该文件，`_repeated_rejection()` 为 `None`；
- 拆分轮中一个文件截断、另一个成功 → 只有截断文件进入 `rejected_reasons`；
- P-226 仍能在同一文件连续两次真实失败时停止；
- 既有 P-231 拆分用例不变。

## 5. 非目标

- 不改拆分阈值、预算或 prompt；
- 不改 `_accept_repair_files` 的判定；
- 不部署（部署与重跑随本批执行）。
