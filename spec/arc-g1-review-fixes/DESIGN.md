---
id: arc-g1-review-fixes-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1-review-fixes-RESEARCH]
upstream: arc-g1-review-fixes-RESEARCH
---

# 设计：链完整性、事件类型登记与流端点预检

## 1. 决策

| ID | 决策 |
|---|---|
| D-1 | `verify_chain` 每行做三项校验：seq 连续、`prev_sha256` 指针、**`payload_sha256` 摘要** |
| D-2 | summary 尾闭合：仅当 `summary.last_seq == 当前末行 seq` 时比较 `chain_tail`；落后即跳过（合法中间态） |
| D-3 | `effect.started` 登记进 `EVENT_TYPES` 与 `api.js` 常量（第 18 类），并加机械对齐用例 |
| D-4 | SSE/WS 在读日志前复用 `_require_event_log`；缺失返回 404 / WS close 1008，且**不得创建目录** |
| D-5 | 流循环内每轮复查日志存在性，日志被删/移走即终止，不复用 mkdir 副作用 |

## 2. 校验语义

```
verify_chain()
  for each event:
    seq == expected                 else "seq gap"
    prev_sha256 == hash(prev line)  else "prev_sha256 mismatch"
    payload_sha256 == hash(payload) else "payload_sha256 mismatch"
  if summary exists and summary.last_seq == last event seq:
    summary.chain_tail == hash(last line) else "chain_tail mismatch"
```

- 中间行篡改：摘要校验先命中（指针校验也会命中下一行）。
- 末行 payload 篡改：摘要校验命中。
- 末行非 payload 字段篡改：仅在 summary 当前时由尾闭合命中。
- 归档删段：仍报 seq gap（既有行为，本批不改）。

## 3. 验收映射

| 验收 | 落点 |
|---|---|
| A1-1 负向补末行 payload | `test_tail_payload_tamper_is_detected` |
| A1-1 尾闭合 | `test_tail_metadata_tamper_is_detected_by_summary` |
| 活 run 不误判 | `test_stale_summary_does_not_block_verification` |
| 既有中间行负向保持 | `test_tamper_breaks_chain`（断言放宽为任一 mismatch） |
| D-2 登记与对齐 | `test_outbox_started_type_is_registered`、`test_frontend_event_types_match_runtime` |
| D-3 无副作用 404 | `test_stream_missing_event_log_is_404_without_creating_a_dir`、`test_ws_missing_event_log_closes_1008` |

## 4. 回滚

四处独立改动可分别回滚：删三项校验中的摘要/尾闭合、删 `effect.started`、删预检与循环复查。前端常量与后端白名单须成对回滚，测试会立即报红。

## 5. 与既有契约的关系

- 不改变 `append` 的写语义与链方向；只增强校验。
- 不改变事件类型集合的语义，只补一个设计内类型。
- 不改变 SSE/WS 的正常帧格式；仅把「不存在的 run」从 200/挂死改为 404/1008。
