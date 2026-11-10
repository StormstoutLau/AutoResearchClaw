---
id: arc-g1c-event-protocol-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1c-event-protocol-RESEARCH]
upstream: arc-g1c-event-protocol-RESEARCH
---

# 设计：事件协议面（A1-2）

## 1. 决策

| ID | 决策 |
|---|---|
| D-1 | 核心在 `runtime/event_stream.py`：分页、缺口判定、SSE 帧格式化，全部纯函数 |
| D-2 | 路由 `server/routes/events.py` 为薄适配器，fastapi 延迟导入（未安装不影响核心与测试） |
| D-3 | `Last-Event-ID` 头优先于 `after` 查询参数 |
| D-4 | 请求游标早于 `oldest_seq` → 先发 `stream.gap{oldest_seq}`，随后从 `oldest_seq` 续 |
| D-5 | 终止事件（`run.completed` / `run.failed` / `run.paused`）后关闭流 |
| D-6 | WS 首帧 `{type:"subscribe", run_id, after}`；后续帧与 SSE `data` 同构 |

## 2. 核心 API

```python
read_page(run_dir, run_id, *, after=None, limit=500) -> {
    "run_id", "events", "oldest_seq", "gap": bool,
    "next_after": int|None, "has_more": bool, "terminal": bool,
}
parse_cursor(last_event_id: str|None, after: int|None) -> int|None
sse_frame(event: dict) -> str          # id/event/data 三行 + 空行
```

- `limit` 上限 2000（超出截断）。
- `gap` 仅当 `after < oldest_seq - 1` 时为真。
- `terminal` 扫描本次返回的 events（不看历史，避免旧 run 立即断流）。

## 3. 路由

| 接口 | 行为 |
|---|---|
| `GET /api/runs/{run_id}/events` | 返回 `read_page` 结果（JSON） |
| `GET /api/runs/{run_id}/events/stream` | SSE；首帧 `retry: 3000`；有缺口先发 gap；空闲 15s 发 `: ping` |
| `WS /api/runs/{run_id}/events/ws` | 首帧 subscribe；按 `after` 推送；终止事件后关闭 |

## 4. 验收映射

| 验收 | 落点 |
|---|---|
| A1-2 无缺口/无重复 | `read_page` 的 `gap` 与 `next_after`；`Last-Event-ID` 优先 |
| A1-2 负向 | 游标落在归档区间 → 必须返回 `gap=true` 且 `oldest_seq` 正确 |

## 5. 回滚

路由为新增，删除 `include_router(events_router)` 即回退；核心模块无副作用。
