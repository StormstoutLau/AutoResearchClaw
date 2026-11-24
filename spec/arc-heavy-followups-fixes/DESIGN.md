---
id: arc-heavy-followups-fixes-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-17
depends: [arc-heavy-followups-fixes-RESEARCH]
upstream: null
---

# 设计：U-3/U-2 最小修复（P-139）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **变更面**：3 产品文件 + 3 测试文件；零 workflow、零 heavy marker、零 `ci_exclusions.yaml`。

---

## 1. 决策

| 决策 | 内容 | 依据 |
|---|---|---|
| D-1 | `write_waiting` 改用 `atomic_write_text` | RESEARCH §1 U-3a |
| D-2 | `read_feedback_response` 去掉 `exists()` 预检，新增 `except FileNotFoundError: return None` | RESEARCH §1 U-3b |
| D-3 | `renew` 锁内条件加 `current.released` | RESEARCH §1 U-2 |
| D-4 | 新增 4 条回归（原子写、TOCTOU、released 不可复活、正常续约） | RESEARCH §5 |
| D-5 | 本批只推分支，合并押后到窗口 2 结束 | 用户裁决 |

## 2. 目标形态

### 2.1 waiting 原子写

```python
def write_waiting(hitl_dir: Path, waiting: WaitingState) -> Path:
    hitl_dir.mkdir(parents=True, exist_ok=True)
    path = hitl_dir / "waiting.json"
    atomic_write_text(path, json.dumps(waiting.to_dict(), indent=2))
    return path
```

### 2.2 feedback 读方

```python
try:
    data = json.loads(response_path.read_text(encoding="utf-8"))
    ...
except FileNotFoundError:
    return None
except (json.JSONDecodeError, TypeError, ValueError) as exc:
    logger.warning(...)
    return None
```

### 2.3 renew 终态校验

```python
if (current is None
        or current.released
        or current.owner != lease.owner
        or current.fencing != lease.fencing):
    raise LeaseLost(...)
```

## 3. 验收不变式

| 编号 | 不变式 | 用例 |
|---|---|---|
| J-1 | waiting 走原子发布 | `test_write_waiting_uses_atomic_publish` |
| J-2 | 文件消失时 feedback 返回 `None` | `test_read_feedback_response_handles_disappearing_file` |
| J-3 | released 不可复活 | `test_renew_after_release_raises_lease_lost` |
| J-4 | 正常续约不受影响 | `test_renew_before_release_extends` |

## 4. 不采用形态

- 全部 IPC 加锁：过度设计。
- `release` 负责停 keeper：跨模块耦合，且 supervisor 路径仍漏。
- 只改 `atexit` 顺序：覆盖不全。

## 5. 风险与回退

| 风险 | 缓解 | 回退 |
|---|---|---|
| feedback 读方暴露其他异常 | 只新增 `FileNotFoundError` 捕获 | 恢复 `exists()` 预检 |
| `renew` 拒绝 released 影响正常退出 | 正常路径 keeper 先停；J-4 回归 | 移除 `released` 条件 |
| waiting 原子写引入临时文件残留 | `atomic_write_text` 的 `finally` 清理 | 恢复 `write_text` |

## 6. 外部契约

- `waiting.json`、`copilot_feedback_response.json`、`lease.json` 的文件名与字段不变。
- 错误语义：feedback 缺失返回 `None`；租约释放后 `renew` 抛 `LeaseLost`（与既有丢失所有权语义一致）。

## 7. 接缝

- 本批合并后，P-140（移出 heavy）的 U-1 条件才具备完整代码基线。
- 若窗口 2 出现同模块失败，先回退本批再排查。
