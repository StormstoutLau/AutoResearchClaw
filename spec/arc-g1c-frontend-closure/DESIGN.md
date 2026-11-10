---
id: arc-g1c-frontend-closure-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1c-frontend-closure-RESEARCH]
upstream: arc-g1c-frontend-closure-RESEARCH
---

# 设计：SSE 消费方与 HTTP 验证

## 1. 决策

| ID | 决策 |
|---|---|
| D-1 | `listEvents(id, after, limit)` 走游标 API |
| D-2 | `streamEvents(id, {after,onEvent,onGap,onClose,onError})` 用原生 `EventSource`，不引入库 |
| D-3 | 事件类型常量与 `runtime/event_log.EVENT_TYPES` 对齐（17 类）；终止事件后主动 `close()` |
| D-4 | `stream.gap` 作为独立监听，交由调用方决定是否从 `oldest_seq` 重拉 |
| D-5 | JSON 游标端点也读取 `Last-Event-ID`（与流端点一致，落实 D-3 of P-031） |

## 2. 客户端契约

```js
const es = API.streamEvents(runId, {
  after: 120,
  onEvent: (evt) => {},
  onGap: ({oldest_seq}) => {},
  onClose: () => {},
  onError: (e) => {},
});
es.closeRun();   // 主动关闭
```

- 浏览器自动重连时由 `EventSource` 自带 `Last-Event-ID`，无需手写。
- 终止事件（`run.completed/failed/paused`）到达后关闭，避免对已结束 run 反复重连。

## 3. 验收映射

| 验收 | 落点 |
|---|---|
| A1-2 游标 + 头优先 | `test_last_event_id_header_wins`（HTTP 层） |
| A1-2 缺口显式 | 新增 `test_gap_is_reported_over_http` |
| A1-2 终止关流 | `test_sse_stream_emits_frames_and_terminates` |
| 客户端可用 | `node --check` + 常量对齐 |

## 4. 回滚

删除 `listEvents/streamEvents` 与两个常量即可；服务端无变更（除 D-5 的一行参数）。
