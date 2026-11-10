---
id: arc-g1c-frontend-closure-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1c-frontend-closure-DESIGN]
upstream: arc-g1c-frontend-closure-DESIGN
---

# 实施记录：SSE 消费方与 HTTP 验证

## 1. 改动

| 文件 | 变更 |
|---|---|
| `frontend-legacy/src/services/api.js` | 新增 `listEvents`、`streamEvents`、`EVENT_TYPES`（17）、`TERMINAL_EVENTS`（3） |
| `researchclaw/server/routes/events.py` | JSON 游标端点读取 `Last-Event-ID`（D-5） |
| `tests/test_events_api.py` | 新增 `test_gap_is_reported_over_http` |
| 环境 | `pip install fastapi httpx`（本地，未改 `pyproject`） |

## 2. 发现的真实缺陷

**JSON 游标端点忽略 `Last-Event-ID`**：D-3 规定该头优先，但只有流端点实现了。装上 fastapi 后首个失败用例即为 `test_last_event_id_header_wins`（期望 `[3]`、实际 `[1,2,3]`）。已修正为两端一致。

## 3. 验证

| # | 检查 | 结果 |
|---|---|---|
| V1 | `pytest tests/test_events_api.py` | **5 passed**（原 4 + 新缺口用例，不再 skip） |
| V2 | `pytest tests/test_event_stream.py` | 7 passed |
| V3 | `node --check frontend-legacy/src/services/api.js` | exit 0 |
| V4 | 事件类型常量对齐 | 17/17 与 `EVENT_TYPES` 一致 |

## 4. 鸿沟（诚实声明）

浏览器级 `EventSource` **自动重连**未验证——需真实服务与人工观察。协议层证据：`Last-Event-ID` 优先（HTTP 用例）+ 缺口显式（HTTP 用例）+ 终止关流（流用例）。登记 U-1。
