---
id: arc-action-ledger-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-action-ledger-RESEARCH]
upstream: null
---

# 设计：动作级证据账本（P-143）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **变更面**：1 个新模块、1 个新测试、1 个既有模块的最小接入；无 workflow、无 CLI、无事件 schema 变更。

---

## 1. 决策

| 决策 | 内容 | 依据 |
|---|---|---|
| D-1 | 独立文件 `actions.jsonl`，append-only、逐条 fsync | RESEARCH §3 方案 A |
| D-2 | 每条记录含 `seq/ts/run_id/action_id/tool/params_sha256/env/seed/inputs/outputs/approver/status/exit_code/event_seq_call/event_seq_result/prev_sha256/record_sha256/schema` | RESEARCH §1 六项要求 |
| D-3 | 参数与文件统一用 `sha256:<hex>`；`record_sha256` 对「去掉自身摘要后的 canonical JSON」求值 | 与 `artifact_node` 约定一致 |
| D-4 | 生产者唯一：`ToolInvoker` 在 `tool.result` 之后写入；构造参数可选，默认关闭 | 避免死代码，且不触碰 23 阶段 |
| D-5 | 审批人取 `approvals.json` 的 `by`；未审批为 `null` | 复用既有审批源 |
| D-6 | 账本写入失败只告警，不阻断工具返回 | 动作已发生，与 `tool.result` 策略一致 |
| D-7 | 不做 CLI、dashboard、跨 run 聚合 | 用户裁决「只做账本」 |

## 2. 记录格式

```json
{
  "schema": 1,
  "seq": 1,
  "ts": "2026-11-24T05:20:00+00:00",
  "run_id": "run-1",
  "action_id": "b3c1...",
  "tool": "echo",
  "params_sha256": "sha256:...",
  "env": {"CUDA_VISIBLE_DEVICES": "0"},
  "seed": 42,
  "inputs": {"data/in.csv": "sha256:..."},
  "outputs": {"out/result.json": "sha256:..."},
  "approver": "peng",
  "status": "ok",
  "exit_code": 0,
  "event_seq_call": 1,
  "event_seq_result": 2,
  "prev_sha256": "0000...",
  "record_sha256": "sha256:..."
}
```

- `inputs`：文件必须存在，缺失即抛 `FileNotFoundError`。
- `outputs`：不存在的文件跳过（失败动作可能没有产物）。
- `env`：调用方显式传入，不自动采集全量环境，避免泄漏。

## 3. 不变式

| 编号 | 不变式 | 用例 |
|---|---|---|
| J-1 | 记录按 seq 连续、`prev_sha256` 成链 | `test_record_appends_and_verifies` |
| J-2 | `record_sha256` 覆盖除自身外的全部字段 | `test_tamper_is_detected` |
| J-3 | 输入缺失即拒绝写入 | `test_missing_input_raises` |
| J-4 | 解析失败（撕裂尾/手改）必须判红 | `test_malformed_tail_fails_closed` |
| J-5 | 动作与事件流通过 `event_seq_call/result` 双向可查 | `test_invoker_writes_action_with_event_seq` |

## 4. 接入点

```python
ledger = ActionLedger(run_dir, run_id)
invoker = ToolInvoker(registry, handlers, event_log=log, action_ledger=ledger)
```

`ToolInvoker.invoke` 在 `tool.result` 之后调用 `_record_action`：

- `action_id` = `call_id`（与事件流同值）；
- `status` = `"ok"` / `"error"`（取 `result["success"]`）；
- `approver` = 审批表中的 `by`；
- `event_seq_call/result` = 两条事件的 seq。

## 5. 非目标

- 不做 `actions.jsonl` 的 CLI 查询（`P-145` 候选）。
- 不做 dashboard 时间线。
- 不修改 `events.jsonl` 的事件类型集合。
- 不接入 23 个阶段。

## 6. 兼容性

| 维度 | 影响 |
|---|---|
| `ToolInvoker` 公开签名 | 新增关键字参数 `action_ledger=None`，默认行为不变 |
| 现有 `tool.call` / `tool.result` | 完全不变 |
| `actions.jsonl` 缺失 | 所有读取返回空、校验返回 ok(0) |
| 性能 | 每条动作一次小文件追加 + fsync；未启用时零开销 |
