---
id: arc-g1c-event-protocol-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-10
depends: [arc-g1c-event-protocol-IMPLEMENTATION]
upstream: arc-g1c-event-protocol-IMPLEMENTATION
---

# 验收清单：事件协议面（A1-2）

## 1. 交付物

- [x] `runtime/event_stream.py`（纯函数核心）
- [x] `server/routes/events.py`（游标页 + SSE + WS subscribe）
- [x] `app.py` 注册路由
- [x] `tests/test_event_stream.py` 7 用例
- [x] `tests/test_events_api.py` 4 用例（fastapi 缺失时 skip）

## 2. A1-2 验收

- [x] 游标分页无重复（`after` 之后的严格大于）
- [x] `Last-Event-ID` 优先于 `after`
- [x] 缺口显式：`gap=true` + `older_seq` + SSE `stream.gap`
- [x] 终止事件后关流
- [ ] 真实浏览器 EventSource 自动重连（U-1，待前端接入）
- [ ] 归档段删除后的旧游标实测（U-2，待真实归档）

## 3. 机检

- [x] V1 核心 7 passed
- [x] V2 API 用例本机 skip（环境无 fastapi；CI 覆盖）
- [x] V3 `pre-commit run --all-files` 9/9
- [x] V4 `step_enforce --base HEAD` exit 0
- [x] V5 既有测试无回归

## 4. 收口

- [x] PROGRESS P-031
- [x] session 5/5
- [x] CONSOLE 派生刷新
- [ ] 总纲 G1 状态更新（A1 全部完成后）

## 5. 遗留

- [ ] U-1 前端 EventSource 集成验证
- [ ] U-2 SSE 单 run 并发连接上限
