---
id: arc-g4-m3-tool-events-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-13
depends: [arc-g4-m2-dynamic-tools, arc-g4-m2-review]
upstream: arc-g4-m2-review
---

# 调研：G4-M3 tool 事件 + orphan_call + 审批门（P-104）

> **Feature**：P-104，G4-M3（A4-4：每个 `tool.call` 有配对 `tool.result`，缺失标记 orphan；A4-5：`risk=high` 未审批拒绝执行）。
> **Spec 步骤**：Step 1-2（T1 实施批）。**输入**：[P-103 复核 §7](../../docs/arc-g4-m2-review-20261114.md)（O-10/O-11）、决策备忘录（工作区根 `p104-m3-decision-research.md`，不入仓）。
> **结论先行**：事件采用 **run-scoped 显式注入**（不推断 run_id）；orphan 采用**新增顶层类型 `tool.orphan_call`**；审批门配套**最小写通道**（`approvals.py` + CLI）；handler 改 **per-tool 模块级函数 + 构造注入**，删除 `dispatch_tool`/`_default_server` 单例绕行。

## 1. 现状（E1/E3，HEAD `9bb829a`）

| # | 事实 | 证据 |
|---|---|---|
| 1 | `tool.call`/`tool.result`/`approval.required` 类型已存在，但**无生产者** | `runtime/event_log.py` L37-44；全仓 grep 仅类型定义 |
| 2 | `approvals.json`、`E_APPROVAL_REQUIRED` **不存在** | 全仓 grep 零命中 |
| 3 | `researchclaw/tools/` 只有 `registry.py`/`__init__.py`；无 invoker/approvals | glob |
| 4 | registry 6 条 handler 均指 `researchclaw.mcp.server:dispatch_tool` → `_default_server().handle_tool_call` | `tools/registry.yaml`；`mcp/server.py` L631-650 |
| 5 | `EventLog` 单写者：append 用内存 `_last_seq`/`_last_hash`；`read_all()` 支持分段 + gzip | `runtime/event_log.py` L124-153/L236-262/L289-319 |
| 6 | `pipeline.summary` 锚点在 `_emit_summary_anchor` 追加；`summary_check` 按 `run.started` 分段、每段至多一个锚，**不要求 summary 是末事件** | `pipeline/runner.py` L105-126；`evidence/summary_check.py` L69-115/L118-172 |
| 7 | `run_pipeline` 的 pipeline 在 MCP server **同进程**以 `asyncio.to_thread` 执行 | `mcp/server.py` L266-278 |
| 8 | CLI 已有 argparse 子命令骨架（`build_parser` L1327+，dispatch L1685+） | `cli.py` |

## 2. 外部锚点（T1，已回原文；检索日期 2026-11-13）

| # | 锚点 | 事实 | 对设计的含义 |
|---|---|---|---|
| 1 | **MCP 规范 2025-03-26 Tools** | 工具 model-controlled；「SHOULD always be a human in the loop with the ability to deny tool invocations」；`listChanged` 为 capability + notification（subscriptions 是 2026-07-28 草案） | 审批是协议级安全期望；审计落点由实现决定 |
| 2 | **arXiv 2611.02527**（2026-11-02） | 90% destructive tools 无服务端确认；32/41 hosts 默认无审批；60.7% pairs 无强制审批；结论「Applications should configure approval」；全量提示可把未批准率降到 5.4% | fail-closed 门必须可被显式打开，否则等于永久禁用 |
| 3 | **KIP-98 / Kafka Message Format 4.2** | 事务结局以**独立控制记录**（commit/abort marker）写入；但两源数字编码**相反**（KIP-98 0=COMMIT/1=ABORT；4.2 0=abort/1=commit） | 只采用「独立控制记录」概念，**禁止硬编码数字** |
| 4 | **Oracle/IBM 2PC in-doubt** | `DBA_2PC_PENDING`、`LIST INDOUBT TRANSACTIONS`；无 COMMIT/ABORT/PREPARE → presume abort | 未配对调用 = in-doubt，独立标记而非篡改结果 |
| 5 | **Temporal Event History** | 事件历史属于单个 Workflow Execution；`ActivityTaskScheduled/Started/Completed/Failed` 逐项；Event History 同时「serves as an audit log」 | 工具事件 = 工作流历史；run 外调用不塞入 |
| 6 | **Kubernetes Auditing / AWS CloudTrail** | 审计写入独立后端（log/webhook）；organization trail 覆盖全账号 | 基础设施级调用用全局审计流（本批不实现，登记后续） |
| 7 | **Claude Permission policies** | MCP toolsets 默认 `always_ask` | 默认询问 + 显式授予是工业实践 |
| 8 | **LangGraph interrupts / Argo suspend** | `interrupt()`+`Command(resume=...)`；`suspend` + `argo resume` | 审批 = 持久化决定 + 恢复通道 |

## 3. 关键结论（对设计的输入）

1. **D-Q1**：`ToolInvoker` 构造参数显式 `event_log: EventLog | None`；MCP 外部调用传 `None`（不写 run 事件）；A4-4 覆盖边界写入 DESIGN。
2. **D-Q2**：新增 `tool.orphan_call` 顶层类型；payload `{call_id, tool}`；扫描幂等。
3. **D-Q3**：`approvals.py`（读 fail-closed + 原子 grant）+ CLI `approvals grant`；不接 REST/UI。
4. **D-Q4**：`mcp/handlers.py` 6 个 per-tool 函数 + `HANDLERS`；server 构造注入；删除 `dispatch_tool`/`_default_server`。
5. **O-10**：invoker 用 `Draft202012Validator` 校验 args，失败 → `E_INVALID_ARGUMENTS`。
6. **事件配对策略**：审批拒绝/校验失败**不写** `tool.call`（只写 `approval.required` 或仅返回错误），确保「有 call 必有 result」。

## 4. 幻觉抑制审查（Step 2 Review）

| 声明 | 来源 | 验证方式 | 状态 |
|---|---|---|---|
| 事件类型已存在但无生产者 | 仓内源码 | E1 grep + 读码 | ✅ |
| approvals 不存在 | 仓内源码 | E1 grep | ✅ |
| EventLog 单写者/内存 seq | 仓内源码 | E3 读码 | ✅ |
| summary_check 不要求末事件 | 仓内源码 | E3 读码 L118-172 | ✅ |
| MCP human-in-the-loop 引文 | 规范页 | WebFetch 原文逐字 | ✅ T1 |
| arXiv 2611 数字 | abs 页 | WebFetch 原文 | ✅ T1 |
| Kafka 控制记录概念 | KIP-98 + 4.2 | 两源对读；数字相反已标注 | ✅（概念）；数字 ❌ 不采用 |
| 2PC in-doubt | Oracle/IBM/UW | 多源 | ✅ T1 |
| Temporal 活动事件 | 官方页 | WebFetch 原文 | ✅ T1 |
| Osprey HITL | arXiv 2508.15066 **v2** | abs v2 原文 | ✅ T1（v3 已改名） |

### 待修正项

- [x] P-103 复核 O-10/O-11 纳入本批验收（T-13/T-14/T-19）。
- [x] Kafka 数字编码不进入实现（仅概念）。
- [x] 外部调用无 run 上下文的审批边界登记（DESIGN §7 F-3/F-4/F-5）。

## 5. 参考来源

1. MCP Tools 2025-03-26：https://modelcontextprotocol.io/specification/2025-03-26/server/tools
2. arXiv 2611.02527：https://arxiv.org/abs/2611.02527
3. KIP-98：https://cwiki.apache.org/confluence/pages/viewpage.action?pageId=66854913
4. Kafka Message Format 4.2：https://kafka.apache.org/42/implementation/message-format/
5. Oracle in-doubt：https://www.oracledaybyday.com/oracle-errors/ora-02050/
6. IBM LIST INDOUBT：https://public.dhe.ibm.com/ps/products/db2/info/vr6/htm/db2d0/db2d097.htm
7. UW 2PC：https://courses.cs.washington.edu/courses/cse444/23sp/lectures/lecture24-2PC.pdf
8. Temporal Events：https://docs.temporal.io/workflow-execution/event
9. Kubernetes Auditing：https://v1-32.docs.kubernetes.io/docs/tasks/debug/debug-cluster/audit/
10. AWS CloudTrail organization trail：https://docs.aws.amazon.com/awscloudtrail/latest/userguide/creating-trail-organization.html
11. Claude Permission policies：https://platform.claude.com/docs/en/managed-agents/permission-policies
12. LangGraph Interrupts：https://docs.langchain.com/oss/python/langgraph/interrupts
13. Argo suspend：https://argo-workflows.readthedocs.io/en/latest/cli/argo_suspend/
14. arXiv 2508.15066 v2（Osprey）：https://arxiv.org/abs/2508.15066v2

---
