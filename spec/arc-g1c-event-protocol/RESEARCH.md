---
id: arc-g1c-event-protocol-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1b-supervisor-protocol-DESIGN, arc-g1a-event-core-DESIGN]
upstream: arc-g1b-supervisor-protocol-DESIGN
---

# 调研：事件协议面（A1-2）的实施前提

> **Feature**：P-031，补齐 G1 最后一项 A1-2（SSE 补拉 / 游标分页 / WS 首帧 subscribe）。
> **Spec 步骤**：Step 1-2（T1：新增公开 HTTP/WS 接口 + 测试）

## 1. 现状

| # | 事实 | 证据 |
|---|---|---|
| F-1 | 已有 `EventLog.read_after(seq)` 与 `events_summary.json.first_seq` | `runtime/event_log.py` |
| F-2 | 无 `/events`、`/events/stream` 路由 | `server/routes/pipeline.py` |
| F-3 | WS 仅 `/ws/chat` | `routes/chat.py:34` |
| F-4 | 服务端依赖为可选 extras；**本机未安装 fastapi** | `import fastapi` → ModuleNotFoundError |
| F-5 | 路由约定：`APIRouter(prefix="/api")`，run_id 正则校验后映射 `artifacts/<run_id>` | `routes/pipeline.py:17-30` |

**关键约束（F-4）**：若把逻辑写进路由模块，本机无法执行任何验证。因此必须**传输无关核心 + 薄适配器**。

## 2. 方案

| 方案 | 评价 |
|---|---|
| **A 核心模块 + 薄路由** | `runtime/event_stream.py` 纯函数（分页/缺口/SSE 帧），路由只做 IO；核心 100% 可本机测 |
| B 全写在路由里 | 本机不可测；SSE 与 WS 会各写一套语义 |
| C 只做 WS 不做 SSE | 不符合 WHATWG `Last-Event-ID` 的浏览器原生重连 |

**裁决 A**（同时满足 P-028 D-7「SSE 与 WS 共用同一序列化器」）。

## 3. 外部锚点

沿用 [P-028 RESEARCH §4](../arc-g1b-supervisor-protocol/RESEARCH.md)：
- X-6 WHATWG HTML §9.2：`event:` / `id:` / `data:` / `retry:` 字段与 `Last-Event-ID` 重连语义（T1）。

## 4. 未决项

- **U-1 SSE 长连接上限**：判据 = 单 run 并发连接数；触发 = 前端接入；倾向 = 单 run ≤ 5；E3。
- **U-2 归档段的 `oldest_seq` 语义**：判据 = 归档后 `first_seq` 是否连续；触发 = 首次归档；倾向 = 用 `summary.first_seq`；E2。

## 5. 引用

1. [P-028 DESIGN §6](../arc-g1b-supervisor-protocol/DESIGN.md)
2. WHATWG HTML Standard §9.2. https://html.spec.whatwg.org/multipage/server-sent-events.html
