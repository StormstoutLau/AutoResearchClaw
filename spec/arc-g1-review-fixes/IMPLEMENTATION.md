---
id: arc-g1-review-fixes-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1-review-fixes-DESIGN]
upstream: arc-g1-review-fixes-DESIGN
---

# 实施记录：D-1/D-2/D-3 修复

## 1. 改动

| 文件 | 变更 |
|---|---|
| `researchclaw/runtime/event_log.py` | `verify_chain` 增 `payload_sha256` 校验；新增 `_verify_summary_tail` 尾闭合（summary 落后即跳过）；`EVENT_TYPES` 补 `effect.started` |
| `researchclaw/server/routes/events.py` | 新增 `_has_event_log` / `_require_event_log`；SSE 预检返回 404、WS 预检 close 1008；流循环每轮复查日志存在性 |
| `frontend-legacy/src/services/api.js` | 事件类型常量补 `effect.started`（18 类） |
| `tests/test_event_log.py` | 中间行负向断言放宽；新增末行 payload、末行元数据（summary）、summary 落后三用例 |
| `tests/test_event_stream.py` | 新增 outbox 类型登记与前端常量机械对齐用例 |
| `tests/test_events_api.py` | 新增 SSE 404（且不建目录）与 WS 1008 用例 |

## 2. 验证

| # | 检查 | 结果 |
|---|---|---|
| V1 | `pytest tests/test_event_log.py tests/test_event_stream.py tests/test_events_api.py` | **30 passed** |
| V2 | G1 范围回归（runner_events/g1b/g1_closeout/supervisor/lease/checkpoint/wiring/retries） | **84 passed** |
| V3 | 末行 payload 篡改探针 | 修复前 `verify_chain=True`；修复后 `payload_sha256 mismatch` |
| V4 | 不存在的 run SSE/WS | 404 / close 1008；目录**未创建** |
| V5 | 前端常量对齐 | `set(api.js) == set(EVENT_TYPES)`（18/18） |

## 3. 鸿沟（诚实声明）

- **U-1 未接线**：`verify_chain` 仍未进入 resume 热路径——归档删段会导致 seq gap 误报，需先定义部分校验语义。
- **末行非 payload 字段**在 summary 缺失或落后时不可检；这是指针链方向的固有性质。
- 归档后的链完整性仍只能部分校验（O-1），本批未改 `apply_retention` 行为。
