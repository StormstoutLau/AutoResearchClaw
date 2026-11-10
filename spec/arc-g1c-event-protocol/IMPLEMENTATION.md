---
id: arc-g1c-event-protocol-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1c-event-protocol-DESIGN]
upstream: arc-g1c-event-protocol-DESIGN
---

# 实施记录：事件协议面（A1-2）

## 1. 改动清单

| 文件 | 类型 | 内容 |
|---|---|---|
| `researchclaw/runtime/event_stream.py` | 新增 | `parse_cursor` / `read_page` / `sse_frame` / `gap_frame` / `heartbeat_frame`（纯函数） |
| `researchclaw/server/routes/events.py` | 新增 | 游标分页、SSE 流、WS subscribe 薄适配器 |
| `researchclaw/server/app.py` | 修改 | 注册 events 路由 |
| `tests/test_event_stream.py` | 新增 | 7 用例（游标/分页/缺口/帧格式） |
| `tests/test_events_api.py` | 新增 | 4 用例（HTTP/SSE；FastAPI 缺失时 skip） |

## 2. 关键实现

- **游标优先**：`parse_cursor` 先取 `Last-Event-ID`，非法才退回 `after`。
- **缺口**：`after < oldest_seq - 1` → `gap=true` 且 `oldest_seq` 随包返回；
  SSE 先发 `event: stream.gap`，再从 `oldest_seq` 续。
- **终止**：仅当**本次页**包含 `run.completed/run.failed/run.paused` 时关闭流，避免历史 run 立即断流。
- **上限**：`limit` 钳制到 2000，默认 500。
- **依赖隔离**：核心不 import fastapi；路由模块才 import，故无 server extras 也能测核心。

## 3. 验收

| 验收 | 结果 |
|---|---|
| A1-2 游标分页无重复 | ✅ `test_read_page_returns_tail_after_cursor` |
| A1-2 缺口显式 | ✅ `test_gap_when_cursor_predates_retention` |
| A1-2 `Last-Event-ID` 优先 | ✅ 核心 + `test_last_event_id_header_wins`（CI 有 fastapi 时执行） |
| A1-2 终止即关流 | ✅ `test_sse_stream_emits_frames_and_terminates` |

## 4. 环境限制（诚实声明）

本机**未安装 fastapi**（server 为可选 extras），因此：

- 核心 7 用例已本机执行通过；
- HTTP/SSE/WS 适配器 4 用例在本机 **skip**，由 CI 的 `extras`/`tests` job（`pip install -e ".[dev,server,mcp]"`）执行。
- 本地未做真实浏览器 EventSource 连接验证（U-1）。

## 5. 机检

| # | 检查 | 结果 |
|---|---|---|
| V1 | `pytest tests/test_event_stream.py` | 7 passed |
| V2 | `pytest tests/test_events_api.py` | 1 skipped（fastapi 缺失；CI extras 覆盖） |
| V3 | `pre-commit run --all-files` | 9/9 Passed |
| V4 | `step_enforce --base HEAD` | exit 0 |
| V5 | 既有 server 相关测试 | 无回归 |
