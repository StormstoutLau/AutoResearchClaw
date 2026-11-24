---
id: arc-action-ledger-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-action-ledger-DESIGN]
upstream: null
---

# 实施：动作级证据账本（P-143）

> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **变更面**：3 个文件；零 workflow、零 CLI、零事件 schema 变更。

---

## 1. 变更清单

| 文件 | 动作 | 内容 |
|---|---|---|
| `researchclaw/runtime/action_ledger.py` | 新增 | `ActionLedger`、`ActionRecord`、`hash_path`、链式校验 |
| `researchclaw/tools/invoker.py` | 修改 | 可选 `action_ledger`；`tool.result` 后写入动作；`_approver` 读审批人 |
| `tests/test_action_ledger.py` | 新增 | 10 条用例（账本 6 + 集成 4） |

## 2. 读数

```text
$ python -m pytest tests/test_action_ledger.py -q
..........                                                               [100%]
10 passed in 0.33s

$ python -m pytest tests/test_tool_events.py tests/test_tool_registry.py tests/test_mcp_dynamic_tools.py -q
58 passed, 1 warning in 2.84s
```

- 账本用例覆盖：链式追加、输入/输出哈希、缺失输入拒绝、env/seed/审批人、篡改检测、撕裂尾 fail-closed。
- 集成用例覆盖：`event_seq_call/result` 关联、失败状态、审批人身份、未启用账本时零副作用。

## 3. 关键实现

### 3.1 链式写入

`record()` 以「去掉 `record_sha256` 的 canonical JSON」求摘要，写入后再更新 `prev_sha256` 指针；`verify_chain()` 逐行重算 seq、指针与摘要。

### 3.2 生产者接入

`ToolInvoker.invoke` 在 `tool.result` 之后调用 `_record_action`：

```python
self.action_ledger.record(
    name, arguments, action_id=call_id,
    approver=self._approver(name),
    status="ok" if result.get("success") else "error",
    exit_code=exit_code,
    event_seq_call=getattr(call_event, "seq", None),
    event_seq_result=getattr(result_event, "seq", None),
)
```

写入失败只记 warning，不影响已完成的工具返回（DESIGN D-6）。

### 3.3 审批人

`_approver()` 从 `approvals.json` 读 `by`，仅在 `approved is True` 时返回；否则 `None`。

## 4. 门禁读数

| 门禁 | 读数 |
|---|---|
| dc_validator（本批 feature） | 0 违规（全仓 148 条存量） |
| grandfather_gate | 0/0/0 |
| step-gate | 5/5 pass |
| verify-anchor | 10 真实 / 0 硬性 / 0 软性 |
| step_enforce | `mode=batch pid=P-143 digest_bound=1` |
| pre-commit | 适用钩子全绿 |
| PR CI | 8/8 success |

## 5. 未做与边界

- 未做 CLI 查询与 dashboard 时间线（DESIGN §5）。
- 未接入 23 个阶段，只以 `ToolInvoker` 证明账本可用。
- 未做跨 run 聚合与保留策略；`actions.jsonl` 随 run 目录生命周期。
- 未自动采集全量环境变量，避免把密钥写进账本。
