---
id: arc-g1-closeout-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1a-event-core-CHECKLIST, arc-g1b-implementation-CHECKLIST, arc-g1c-event-protocol-CHECKLIST]
upstream: arc-g1c-event-protocol-CHECKLIST
---

# 调研：G1 遗留收口（U 项）

> **Feature**：P-033，收口 P-027 / P-029 / P-031 登记的 U 项。
> **Spec 步骤**：Step 1-2（T1：改运行时与测试）

## 1. 遗留清单与处置

| 来源 | U 项 | 处置 |
|---|---|---|
| P-027 | 异常路径租约残留 | `atexit` 注册释放（幂等，已释放则跳过） |
| P-029 | U-1 真实 kill -9 集成 | 真实子进程测试：首个进程 exit 75 → supervisor 重启 → 第二个 exit 0 |
| P-029 | U-2 backend 会话续接 | 显式登记「当前无 backend 支持」→ `context_replayed=True`，并加测试防回退 |
| P-029 | U-3 残留租约按 pid 判定 | `is_pid_alive`：过期 **或** pid 已死才回收 |
| P-031 | U-2 SSE 并发上限 | `ConnectionLimiter`，单 run 默认 5；超限 SSE 429 / WS 1013 |
| P-031 | U-1 前端 EventSource 联调 | **不关闭**：属消费方前端集成，本仓无构建前端；SSE 契约已由 HTTP 测试覆盖 |

## 2. 关键发现

| # | 事实 | 影响 |
|---|---|---|
| F-1 | **Windows 上 `os.kill(pid, 0)` 会调用 TerminateProcess**，不是探活 | 初版 `is_pid_alive` 会**误杀存活进程**；必须用 `OpenProcess + GetExitCodeProcess`（STILL_ACTIVE=259） |
| F-2 | `subprocess` 子进程 killed 后退出的码在 Windows 不是 137 | 分类表对未知码默认 75（可重试），恰好覆盖该场景；测试用显式 exit 75 保证确定性 |
| F-3 | `atexit` 注册无需 unregister：`release` 对已释放租约直接返回 | 避免多 run 场景下 unregister 误删他人注册 |

## 3. 外部锚点

- X-1 Windows `OpenProcess` / `GetExitCodeProcess`（Microsoft Learn，T1 官方）。
- X-2 既有：[P-028 RESEARCH](../arc-g1b-supervisor-protocol/RESEARCH.md) 的 systemd/K8s 重启语义（T1）。

## 4. 未决项

- **U-1 前端 EventSource 联调**：判据 = `frontend-legacy` 接入 SSE；触发 = 前端排期；倾向 = 复用 `EventSource` 原生重连；E2。
- **U-2 SSE 上限是否按用户维度**：判据 = 多用户部署；触发 = 鉴权接入；倾向 = 先按 run；E3。

## 5. 引用

1. Microsoft Learn. *OpenProcess* / *GetExitCodeProcess*.
2. 仓内：[P-027](../arc-g1a-event-core/IMPLEMENTATION.md)、[P-029](../arc-g1b-implementation/IMPLEMENTATION.md)、[P-031](../arc-g1c-event-protocol/IMPLEMENTATION.md)
