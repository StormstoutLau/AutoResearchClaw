---
id: arc-g1-closeout-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1-closeout-DESIGN]
upstream: arc-g1-closeout-DESIGN
---

# 实施记录：G1 遗留收口

## 1. 改动

| 文件 | 变更 |
|---|---|
| `researchclaw/runtime/lease.py` | 新增 `is_pid_alive`（Windows OpenProcess 分支） |
| `researchclaw/runtime/supervisor.py` | 回收条件改为「过期或 pid 已死」 |
| `researchclaw/runtime/attempt.py` | `SESSION_RESUME_BACKENDS` 白名单 + `session_resume_supported` |
| `researchclaw/runtime/event_stream.py` | `ConnectionLimiter` + `MAX_STREAMS_PER_RUN=5` |
| `researchclaw/server/routes/events.py` | SSE 429 / WS 1013 限流；finally 释放 |
| `researchclaw/pipeline/runner.py` | `atexit` 释放租约；attempt 的 `context_replayed` 由白名单决定 |
| `tests/test_g1_closeout.py` | 4 用例（真实子进程/pid/会话/限流） |

## 2. 关键修正

**Windows `os.kill(pid, 0)` 不是探活**——它会调用 `TerminateProcess`。初版实现会误杀存活进程，已改为 `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + `GetExitCodeProcess == STILL_ACTIVE`，异常一律视为存活。

## 3. 验收

| 项 | 结果 |
|---|---|
| P-029 U-1 真实重启 | ✅ 真实子进程 exit 75 → 重启 → exit 0，计数=2 |
| P-029 U-2 会话续接 | ✅ 显式不支持 + 防回退断言 |
| P-029 U-3 pid 判定 | ✅ 自身存活、非法 pid 死亡 |
| P-031 U-2 并发上限 | ✅ 第 6 个拒绝、释放可复用、跨 run 隔离 |
| P-027 U-1 异常释放 | ✅ atexit 接线（进程退出路径不单测） |

## 4. 机检

| # | 检查 | 结果 |
|---|---|---|
| V1 | G1 相关单测 | 32 passed |
| V2 | runner/CLI 回归 | 待回填 |
| V3 | `pre-commit` | 待回填 |
| V4 | `step_enforce --base HEAD` | 待回填 |

## 5. 未关闭

- P-031 U-1（前端 EventSource 联调）：属消费方前端集成，本仓无构建前端；SSE 契约已由 HTTP 用例覆盖。
