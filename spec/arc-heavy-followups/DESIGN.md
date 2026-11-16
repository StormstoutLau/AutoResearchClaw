---
id: arc-heavy-followups-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-heavy-followups-RESEARCH]
upstream: null
---

# 设计：heavy 邻近两项缺陷的修复方案（P-136 调研批产出，供后续实施批）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **本批不含实施**：只给方案与验收口径；任何代码改动押后到观察窗口 2 之后。
> **上游**：[P-133 DESIGN](../arc-ci-heavy-rootcause/DESIGN.md) §7 U-2/U-3。

---

## 1. 目标与非目标

**目标**

1. U-3：消除 `waiting.json` 的非原子写与 copilot feedback 读方的 TOCTOU。
2. U-2：让 `released` 成为不可被续约逆转的终态。
3. 两项修复都有确定性回归用例。

**非目标**

- 本批不改任何代码、测试、workflow 或 `ci_exclusions.yaml`。
- 不重构外部 UI 对 `copilot_feedback_response.json` 的写入。
- 不动 `response.json`（P-134 已修）。

## 2. 决策

| 决策 | 内容 | 依据 |
|---|---|---|
| D-1 | 本批零实施；修复由后续实施批执行 | 调研批边界 + 用户裁决 |
| D-2 | U-3 采纳方案 A：`write_waiting` 改 `atomic_write_text`；feedback 读方去掉 `exists()` 预检并捕获 `FileNotFoundError` | RESEARCH §5.1 |
| D-3 | U-2 采纳方案 A：`renew` 锁内校验 `current.released`，为 `True` 时 `LeaseLost` | RESEARCH §5.2 |
| D-4 | U-3 与 U-2 合并为一个实施批（同属 heavy 邻近、改动面小） | RESEARCH §6 U-1 |
| D-5 | 本批与后续实施批的合并都押后到窗口 2 结束 | 用户裁决 |

## 3. 验收不变式（后续实施批口径）

| 编号 | 不变式 | 可观测读数 |
|---|---|---|
| J-1 | `waiting.json` 写入原子化 | 写方走 `atomic_write_text`；读方在写入中途不再看到 0 字节 |
| J-2 | feedback 读方无 TOCTOU | 删除文件后调用 `read_feedback_response` 返回 `None`，不抛 `FileNotFoundError` |
| J-3 | released 不可复活 | `release()` 后 `renew()` 抛 `LeaseLost`；磁盘 `released` 保持 `True` |
| J-4 | 正常续约不受影响 | 未释放时 `renew` 成功、fencing 不变 |
| J-5 | 外部契约零变更 | 文件名/字段不变；`waiting.json` 结构不变 |

## 4. 目标形态（示意，不实施）

### 4.1 U-3

```python
# write_waiting
atomic_write_text(path, json.dumps(waiting.to_dict(), indent=2))

# read_feedback_response
try:
    data = json.loads(response_path.read_text(encoding="utf-8"))
except FileNotFoundError:
    return None
except (json.JSONDecodeError, TypeError, ValueError) as exc:
    logger.warning(...)
    return None
```

### 4.2 U-2

```python
with _lease_lock(run_dir, lease.owner, ttl=ttl, now=now):
    current = read_lease(run_dir)
    if current is None or current.released or current.owner != lease.owner \
       or current.fencing != lease.fencing:
        raise LeaseLost(...)
    ...
```

## 5. 不采用形态

- **U-3 全部 IPC 加锁**：过度设计；原子发布已足够。
- **U-2 `release` 停 keeper**：跨模块耦合高，且 supervisor 路径仍会漏。
- **只改 atexit 顺序**：覆盖不全，不能替代 `renew` 的终态校验。

## 6. 风险与回退

| 风险 | 缓解 | 回退 |
|---|---|---|
| feedback 读方改为直接读后，其他异常暴露 | 只新增 `FileNotFoundError` 捕获，其他保持原样 | 恢复 `exists()` 预检 |
| `renew` 拒绝 released 影响正常退出 | 正常路径 keeper 先停，不会触发 | 移除 `released` 条件 |
| 窗口内合并污染观测 | 合并押后至窗口 2 | 保持本批文档不合并 |

## 7. 后续接口

- 后续实施批（编号待定）按 §4 实施并验收 J-1..J-5。
- 与 P-135 一样，PR 可先开、CI 可先跑，合并统一押后。
