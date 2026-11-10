---
id: arc-g1-residual-analysis-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1b-supervisor-protocol-DESIGN, arc-g1c-event-protocol-DESIGN, arc-g1-closeout-RESEARCH]
upstream: arc-g1-closeout-RESEARCH
---

# 调研：G1 两项「外部条件」遗留的目的与可解性

> **问题**：框架已能接入 B 站与主控站的 Claude Code（均为本地模型），那 G1 剩余两项遗留（A1-9 会话续接、P-031 前端 EventSource）到底在解决什么？现在能否关闭？
> **Spec 步骤**：T3 轻批（Layer-0：本文档 + session + PROGRESS 行，零代码/零门禁）。

## 1. 先纠正前提：两项遗留都不是「能否接入 Claude Code」

| 遗留 | 缺的**不是** | 真正缺的是 |
|---|---|---|
| A1-9 | LLM 会话能力——`acp_client.py` 已实现常驻命名会话（`session_name="researchclaw"`，跨调用保持上下文） | **Stage attempt 级**的 agent 子进程续接：`claude -p` 每次都是全新进程 |
| P-031 前端 | 服务端 SSE（已实现并测试） | **消费方**：浏览器 `EventSource` 自动携带 `Last-Event-ID` 重连的那一半 |

## 2. A1-9 的目的（四层，逐层递减）

| # | 目的 | 说明 |
|---|---|---|
| P-1 | 不重放上下文 | Stage 12 重试若重跑全部实验上下文，本地模型也要重吃一遍 prompt；成本从「钱」转为「时延 + 上下文窗口占用」 |
| P-2 | 保留探索状态 | agent 已读文件、已跑命令、已排除假设；从零开始会降低第二次尝试质量，甚至结论漂移——这正是负向用例「第二次 attempt 从零开始即失败」的含义 |
| P-3 | 与 A1-12 分工 | `resume_note` = 「先查什么」（跨机可用）；`session_id` = 「记得做过什么」（**仅同机同 CLI**） |
| P-4 | 可解释性 | attempt 记录能区分「续接」与「重放」，不混淆两种语义 |

## 3. 本地模型 + 双站接入的实际影响

| 事实 | 证据 | 推论 |
|---|---|---|
| `claude` 支持 `--session-id <uuid>` 与 `-r/--resume <id>` | `claude --help` 本地实测（T1 本地工具） | 续接在 CLI 层可行，与模型在哪无关 |
| 会话是 CLI 本地状态：`~/.claude/projects` 下 196 个 `*.jsonl` | 本地实测（T1 本地事实） | 会话库随机器走，不随 run 走 |
| ACP 通道已有常驻会话 | `llm/acp_client.py:4-6,43,65` | LLM 层上下文已连续；A1-9 只补 code agent 子进程层，不重复建设 |

| 场景 | A1-9 是否有效 |
|---|---|
| 主控站 supervisor 重启同一 run | ✅ 有效（同机同 CLI 同会话库） |
| B 站 supervisor 重启 | ✅ 有效（B 站自己的会话库） |
| 主控站跑一半切到 B 站续跑 | ❌ **不可续接**——两套 CLI、两套本地状态，session id 不通用 |
| B 站走 ACP 通道 | ⚠️ LLM 层已连续；A1-9 仅覆盖子进程层 |

**结论**：本地模型把重放成本从金钱转为时延与上下文窗口，A1-9 仍有价值但**优先级下调为 P2**，且必须显式接受「跨机降级」。

## 4. P-031 前端的目的（三层）

1. **唯一真实消费方**：服务端「无缺口、无重复」的契约，只有浏览器 `EventSource` 在断线时自动带 `Last-Event-ID` 才算被真正消费；否则只是自测。
2. **长任务/审批门可观测性**：Stage 5/9/20 挂起时，UI 需要知道「停在哪、为什么」。
3. **产品面 vs 契约面**：若近期不投 UI，其价值仅剩契约验证，可继续挂起而不影响地基。

## 5. 判断

| 项 | 性质 | 建议优先级 |
|---|---|---|
| A1-9 | 能力增强（性能/重试质量），非正确性 | **P2**，可做「同机续接 + 跨机显式降级」 |
| P-031 前端 | 产品面，非地基 | 挂起，等 UI 排期 |

**两者都不阻塞 G2/G3**——「不产出假结果」不依赖它们。

## 6. 若实施：最小正确做法与陷阱

1. `code_agent` 首跑传 `--session-id <uuid5(run_id, stage, attempt)>`；重试传 `--resume <id>`；attempt 记录该 id。
2. `SESSION_RESUME_BACKENDS` 登记 `claude_code`（当前为空集）。
3. **关键陷阱**：session 过期或不存在时 CLI 会**静默从零开始**——必须解析输出确认会话确实被续上（如 `--output-format json` 中的 session 字段），否则 A1-9 的负向用例会**假通过**。
4. 单测只验证命令构造，不烧配额；真实 round-trip 作为可选项。
5. 前端：装 `fastapi/httpx` 后可跑 4 个 API 用例，再在 `frontend-legacy/src/services/api.js` 增加 `EventSource` 客户端。

## 7. 未决项

- **U-1 续接确认信号**：判据 = CLI 输出中是否有可机械判定「已续接」的字段；触发 = 实施批；倾向 = JSON 输出的 session 字段 + 首次 prompt 自证；E2。
- **U-2 跨机语义是否要支持**：判据 = 是否出现「换机续跑」的真实需求；触发 = 多机调度（G7）；倾向 = 明确不支持，改走「新建 attempt + resume_note」；E2。
- **U-3 前端是否纳入本期**：判据 = UI 排期；触发 = 产品排期；倾向 = 挂起；E3。

## 8. 引用

1. 本地：`claude --help`（`--session-id`、`-r/--resume`、`--fork-session`）。
2. 本地：`~/.claude/projects` 会话库（196 个 jsonl）。
3. 仓内：`researchclaw/llm/acp_client.py`（常驻命名会话）。
4. 仓内：[P-028 DESIGN §4](../arc-g1b-supervisor-protocol/DESIGN.md)（attempt 模型）、[P-033](../arc-g1-closeout/IMPLEMENTATION.md)（会话白名单现状）。
