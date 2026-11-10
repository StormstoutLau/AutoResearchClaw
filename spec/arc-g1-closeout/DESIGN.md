---
id: arc-g1-closeout-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1-closeout-RESEARCH]
upstream: arc-g1-closeout-RESEARCH
---

# 设计：G1 遗留收口

## 1. 决策

| ID | 决策 |
|---|---|
| D-1 | `is_pid_alive` 分平台：Windows 用 OpenProcess/GetExitCodeProcess，其他用 `kill(pid,0)`；不确定时**视为存活**（绝不偷活租约） |
| D-2 | supervisor 回收条件 = 过期 **或** pid 已死 |
| D-3 | `atexit` 释放租约；`release` 天然幂等 |
| D-4 | 会话续接采用**白名单**：`SESSION_RESUME_BACKENDS` 为空 ⇒ 一律 `context_replayed=True` |
| D-5 | 并发限流为纯类 `ConnectionLimiter`，按 run 计数；SSE 429、WS 1013 |

## 2. 契约

```python
is_pid_alive(pid) -> bool           # 不确定 → True
session_resume_supported(backend) -> bool   # 白名单为空 → False
ConnectionLimiter(limit=5).acquire(key) -> bool
```

## 3. 验收映射

| 遗留 | 验收 |
|---|---|
| P-029 U-1 | 真实子进程：exit 75 → 重启 → exit 0，count=2 |
| P-029 U-3 | `is_pid_alive` 自身 True、非法 pid False；supervisor 仅在死/过期时回收 |
| P-029 U-2 | 三个 backend 均返回 False（防回退断言） |
| P-031 U-2 | 第 6 个连接被拒、释放后可再取、不同 run 隔离 |
| P-027 U-1 | `atexit.register` 已接线（幂等，不单测进程退出） |

## 4. 回滚

各改动独立：`is_pid_alive` 可退回仅过期判定；限流可把 `MAX_STREAMS_PER_RUN` 调大；会话续接只需在集合中登记 backend。
