---
id: arc-g4-m3-tool-events-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-13
depends: [arc-g4-m3-tool-events-RESEARCH]
upstream: arc-g4-m3-tool-events-RESEARCH
---

# 设计：G4-M3 tool 事件 + orphan_call + 审批门（P-104）

> 基于 [RESEARCH.md](RESEARCH.md)。**批内关闭** P-103 复核 O-10（运行时 schema 校验）与 O-11（handler 单例绕行）。

## 1. 交付范围

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `researchclaw/tools/invoker.py` | 新增 | `ToolInvoker`：schema 校验 → 审批门 → `tool.call` → handler → `tool.result`；orphan 扫描 |
| 2 | `researchclaw/tools/approvals.py` | 新增 | `read_approvals`（fail-closed）+ `grant`（filelock + 原子写） |
| 3 | `researchclaw/mcp/handlers.py` | 新增 | 6 个 per-tool 模块级函数 + `HANDLERS` 映射 |
| 4 | `researchclaw/mcp/server.py` | 修改 | 构造注入 handlers/invoker；删除 `dispatch_tool`/`_default_server`；`_dispatch_tool` → invoker |
| 5 | `researchclaw/tools/registry.yaml`（双副本） | 修改 | handler → `researchclaw.mcp.handlers:<fn>` |
| 6 | `researchclaw/runtime/event_log.py` | 修改 | `EVENT_TYPES` + `tool.orphan_call` |
| 7 | `researchclaw/pipeline/runner.py` | 修改 | summary 锚点前调用 orphan 扫描 |
| 8 | `researchclaw/cli.py` | 修改 | `approvals grant` 子命令 |
| 9 | `tests/test_tool_events.py` | 新增 | T-1..T-19 |
| 10 | `spec/arc-g4-m3-tool-events/` 四文档 | 新增 | 本批 spec |
| 11 | `spec/arc-g4-m0-design/DESIGN.md` + P-099 session | 修改 | M3 状态 + I-5 裁决；受控回边 rebind |
| 12 | `arc-master-roadmap.md` / `docs/PROGRESS.md` | 修改 | v1.4q + P-104 行 |

## 2. 决策表（含被拒方案与代价）

| # | 决策 | 依据 | 被拒方案 / 代价 |
|---|---|---|---|
| D-1 | 事件 **run-scoped 显式注入**：`ToolInvoker(event_log=None)`，不从 args.run_id 推断 | 单写者/链式 hash；Temporal 工作流历史 | 按 run_id 自动写：活跃 run 并发断链 + 生命周期污染；全局审计 sink：越出 M0 §4，需回边 |
| D-2 | orphan = **新增顶层类型 `tool.orphan_call`** | M0 §4 字面；Kafka 控制记录/2PC in-doubt | 派生字段 `orphan_call=true`：需改写不存在的 result，语义矛盾 |
| D-3 | 审批门 + **最小写通道**（`approvals.py` + CLI grant） | MCP 规范 human-in-loop；Claude always_ask；arXiv 2611 | 只读不写：fail-closed 门永久关闭，A4-5 只有拒绝半条腿 |
| D-4 | handler = **per-tool 模块级函数 + 构造注入**；删除 `dispatch_tool`/`_default_server` | O-11；registry 正则不支持 `Class.method`；Fowler DI | 保留单例：生命周期分裂（`stop()` 取消不到实际任务）；运行时按名查表：Service Locator |
| D-5 | **事件配对策略**：审批拒绝/校验失败**不写** `tool.call`；成功执行才写 call+result | A4-4「有 call 必有 result」 | 写 call+result(error)：拒绝也产生业务结果，混淆审计语义 |
| D-6 | schema 校验在 invoker：`Draft202012Validator(unfreeze(input_schema)).validate(args)` | O-10；MCP 规范「MUST validate all tool inputs」 | 只靠 SDK 合成签名：类型/anyOf/必填 null 不校验（P-103 复核实证） |
| D-7 | orphan 扫描挂在 `_emit_summary_anchor` 开头（`owns=True`） | M0 §4「summary 前」；summary_check 按段计数 | 独立后置任务：进程退出时可能来不及，且顺序不可证 |

## 3. 接口

```python
# tools/approvals.py
def read_approvals(run_dir: str | Path) -> dict[str, dict]: ...
def is_approved(run_dir: str | Path, tool: str) -> bool: ...
def grant(run_dir: str | Path, tool: str, *, by: str) -> Path: ...

# tools/invoker.py
class ToolInvoker:
    def __init__(self, registry: Registry, handlers: Mapping[str, Callable[..., Awaitable[dict]]],
                 *, event_log: EventLog | None = None,
                 approvals_path: str | Path | None = None) -> None: ...
    async def invoke(self, name: str, args: dict) -> dict: ...
def emit_orphan_markers(event_log: EventLog) -> list[str]: ...

# mcp/handlers.py
async def handle_run_pipeline(server: Any, args: dict) -> dict: ...
# ... 5 more; HANDLERS: dict[str, Callable[[Any, dict], Awaitable[dict]]]
```

**invoker 流程**（严格顺序）：

1. 未知工具 → `{success:false,error_code:"INVALID_TOOL"}`。
2. schema 校验失败 → `E_INVALID_ARGUMENTS`（不写事件、不执行）。
3. 审批判定：`always` 或 `high_only & high` 且未批准 → 写 `approval.required`（仅当注入 sink）→ 返回 `E_APPROVAL_REQUIRED`（不写 call、不执行）。
4. 写 `tool.call`（`call_id`、`tool`、`risk`、`args_digest`、`args_summary`）；写失败 → `E_EVENT_LOG_UNAVAILABLE`，不执行。
5. 执行 handler；异常 → `INTERNAL_ERROR`，`exit_code=1`。
6. 写 `tool.result`（`call_id`、`exit_code`、`result_digest`、`result_summary`、`duration_ms`）；写失败仅 warning（执行已发生，不可回滚）。

**摘要口径（I-3）**：`args_summary` = 排序后的键名列表；`result_summary` = `success/error_code` + 顶层键名；均 ≤200，**不含原始值**。digest 用 `canonical_json` + sha256。

**approvals.json**：`{tool: {approved: true, by: str, ts: ISO}}`；缺失/非 dict/JSON 错误 → 视为无审批（拒绝）；grant 原子写（临时文件 + `os.replace`，`filelock.exclusive_lock`）。

## 4. 事件契约（M0 §4 冻结）

| 事件 | 必填 payload |
|---|---|
| `tool.call` | `tool`、`call_id`、`risk`、`args_digest`、`args_summary` |
| `tool.result` | `tool`、`call_id`、`risk`、`exit_code`、`result_digest`、`result_summary`、`duration_ms` |
| `approval.required` | `tool`、`risk`、`approval`、`call_id` |
| `tool.orphan_call` | `call_id`、`tool`（可选 `detected_at`） |

## 5. 覆盖边界（诚实声明，复核 F-3/F-4/F-5）

- **F-3**：MCP 外部调用无 run 上下文 → `event_log=None`；`approval≠never` 的工具被外部调用时**一律拒绝**（无 run 目录即无 approvals 路径）；全局授予通道登记后续。
- **F-4**：M0 §5 原文「执行前**写** `approval.required` 并拒绝」在本批条件化为「**若注入 sink 则写**；无论如何拒绝」——随 M0 §10 I-5 一并回边。
- **F-5**：M3 无「run 内工具调用」生产者 → 生产环境 `tool.call/result` 为零；A4-4 由**注入式测试**（T-1/T-10/T-12）验证，覆盖声明写入本 DESIGN，不复述为「生产已覆盖」。
- **listChanged**：仍为 P-103 阻塞点，不在本批范围。

## 6. 不变式

- I-1 `EVENT_TYPES` 仅新增 `tool.orphan_call`，其余不变。
- I-2 有 `tool.call` 必有同 `call_id` 的 `tool.result`（除非被杀进程；由 orphan 标记显式化）。
- I-3 事件不含原始参数/结果（键名摘要 + digest）。
- I-4 6 工具名称/参数/返回体不变（MCP 42 项零回退）。
- I-5 未审批的 high-risk 工具 handler **零副作用**。
- I-6 `stop()` 取消实际执行任务的实例（单实例，无 default server）。

## 7. 验收映射

| 验收 | 落点 |
|---|---|
| A4-4 正向 | T-1/T-2/T-3 |
| A4-4 负向 | T-10/T-11/T-12 |
| A4-5 负向/正向 | T-5/T-6/T-8/T-9 |
| 审批文件健壮性 | T-7/T-17/T-18 |
| O-10 | T-13 |
| O-11 | T-14/T-19 |
| I-3 | T-4 |
| 零回退 | T-15 |

## 8. 非目标

- 全局 MCP 调用审计 sink（G4 后续）。
- approvals 的 revoke/过期/REST/UI。
- 真实 listChanged 通知。
- 沙箱 exit_code=137（M4）。

---
