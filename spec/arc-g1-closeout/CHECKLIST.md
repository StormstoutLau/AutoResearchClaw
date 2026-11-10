---
id: arc-g1-closeout-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-10
depends: [arc-g1-closeout-IMPLEMENTATION]
upstream: arc-g1-closeout-IMPLEMENTATION
---

# 验收清单：G1 遗留收口

## 1. 遗留项

- [x] P-027 U-1 异常路径租约释放（atexit，幂等）
- [x] P-029 U-1 真实子进程重启（非 mock）
- [x] P-029 U-2 会话续接显式降级 + 防回退测试
- [x] P-029 U-3 残留租约按 pid 判定
- [x] P-031 U-2 SSE/WS 并发上限
- [ ] P-031 U-1 前端 EventSource 联调（消费方，非本仓）

## 2. 安全

- [x] Windows 探活不再使用 `os.kill(pid, 0)`
- [x] pid 不确定时视为存活（不偷活租约）
- [x] 限流在 finally 中释放，异常不泄漏计数

## 3. 机检

- [x] V1 32 passed（closeout + supervisor + g1b + stream）
- [x] V2 runner/CLI 回归 99 passed
- [x] V3 `pre-commit run --all-files` 9/9
- [x] V4 `step_enforce --base HEAD` exit 0

## 4. 收口

- [x] PROGRESS P-033
- [x] session 5/5
- [x] CONSOLE 刷新
- [ ] 总纲 v1.2（G1 遗留状态：仅 A1-9 backend 能力与前端联调未闭合）
