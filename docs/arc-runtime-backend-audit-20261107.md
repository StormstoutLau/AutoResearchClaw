---
id: arc-runtime-backend-audit-20261107
type: design
version: 0.1
status: draft
date: 2026-11-07
depends: [arc-master-roadmap]
upstream: arc-master-roadmap
---

# ARC 运行时后端与可审计性 · 审计备忘

> **问题**：运行 ARC 需要 LLM API 还是 agent CLI（Claude Code / OpenCode）？仅用 API 时 ARC 是否具备工具调用、上下文压缩、记忆等 agent 能力？接入外部 agent 时如何保证结果可追溯、推理链可审计？
> **性质**：对**当前实现**的静态审计，不改动任何代码与设计。结论按 `7d0e70a` 之后的 `d47d9c7` 工作树读取。
> **去向**：作为 G-1 与 G1 的输入依据（见 [总纲](../arc-master-roadmap.md) §11），缺口登记在 §5，不在本文排期。

---

## 0. 取证矩阵

| 手段（等级） | 覆盖项 | 结果 |
|---|---|---|
| 静态读码（E3） | `llm/`、`pipeline/`、`memory/`、`mcp/`、`experiment/` 关键类与调用点 | ✅ 行号语义匹配 |
| `rg` 全仓检索（E1） | `tools=` / `tool_choice` / 压缩器 / 事件日志 | ✅ 主链路零结果（见 §2.1） |
| 文档与配置比对（E2） | `README.md`、`config.researchclaw.example.yaml`、`config.py` | ✅ 三处口径一致 |

---

## 1. 接入层：三种关系，只有第一种是必需

| 关系 | 形态 | 关键证据 |
|---|---|---|
| **A. ARC → LLM API（默认）** | OpenAI-compatible `/chat/completions`；`base_url` + `api_key_env` + fallback 模型链 + 重试 + 成本记账 | [client.py](../researchclaw/llm/client.py#L96-L101)、[config.py](../researchclaw/config.py#L203-L223) |
| **B. ARC → agent CLI 作为 LLM 后端** | `llm.provider: acp`，经 acpx 把 Claude Code / Codex / Gemini / OpenCode 当后端，跨 23 阶段复用同一持久会话 | [README](../README.md#L241-L262)、[acp_client.py](../researchclaw/llm/acp_client.py#L1-L8)、[executor.py](../researchclaw/pipeline/executor.py#L661-L669) |
| **C. 外部 agent → ARC** | Claude Code 读 `RESEARCHCLAW_CLAUDE.md`、OpenCode 读 `.claude/skills/`，或经 ARC 的 MCP server 调 `run_pipeline` 等工具 | [README](../README.md#L269-L278)、[tools.py](../researchclaw/mcp/tools.py#L8-L56) |

另有两个**只用于代码生成阶段**的 CLI 执行器：`ClaudeCodeAgent`、`CodexAgent`（[experiment/code_agent.py](../researchclaw/experiment/code_agent.py#L563-L649)）；它们不参与主线推理。

**结论**：ARC 是「23 阶段流水线 + 可替换的模型后端」，不是「必须挂在某个 agent CLI 上的壳」。API 模式是完整路径；ACP 是可选的免密钥替代；外部 agent 驱动是第三层封装。

---

## 2. 仅用 API 时的 agent 能力盘点

### 2.1 工具调用：有，但不是「模型自主 function-calling」型

- 全仓 `researchclaw/` 中未检索到向 chat 请求传 `tools=` 或 `tool_choice` 的调用点。
- 工具由宿主代码在阶段内直接调用：文献 API、Web 搜索、MCP 客户端（[client.py](../researchclaw/mcp/client.py#L23-L118)）、沙箱执行。
- 真正的多轮工具循环只存在于代码生成子流程（[pipeline/code_agent.py](../researchclaw/pipeline/code_agent.py#L5-L20)）：蓝图 → 顺序生成 → 执行回灌 → 树搜索 → 多 agent 评审，开关在 `CodeAgentConfig`（[同文件](../researchclaw/pipeline/code_agent.py#L58-L96)）。

### 2.2 上下文压缩：无通用压缩器，靠产物交接

- 无 `compress` / `summarize_context` 一类模块；阶段之间通过 `_read_prior_artifact` 读上游文件传递状态（[_helpers.py](../researchclaw/pipeline/_helpers.py#L398-L421)）。
- 只在组装 prompt 时做局部截断（如 synthesis 2,200 字符、decision 1,500 字符，[_helpers.py](../researchclaw/pipeline/_helpers.py#L1101-L1121)），不属于会话级压缩。
- ACP 模式下上下文由外部 agent 的持久会话承担，ARC 不参与管理；API 模式下上下文完全外置到 `stage-XX/` 文件。

### 2.3 记忆：有，三类独立实现

- JSONL 持久存储 + embedding + 余弦相似度 + 时间衰减 + 置信度加权（[store.py](../researchclaw/memory/store.py#L58)、[retriever.py](../researchclaw/memory/retriever.py#L43-L70)）。
- 三个分类：`ideation / experiment / writing`，各自有入口类。
- 跨 run 学习由 MetaClaw 的「失败 → 教训 → 技能」链路承担（技能经 `export_for_prompt` 注入，[_helpers.py](../researchclaw/pipeline/_helpers.py#L890)）。

---

## 3. 可追溯与审计：流程级成立，token 级不成立

一次 run 的权威状态全在 run 目录：

| 产物 | 内容 | 证据 |
|---|---|---|
| `checkpoint.json` | `last_completed_stage` 等；tmp + rename 原子写 | [runner.py](../researchclaw/pipeline/runner.py#L90-L115) |
| `heartbeat.json` | 存活时间戳 | [runner.py](../researchclaw/pipeline/runner.py#L122-L133) |
| `stage-XX/` | 该阶段全部产物，按契约声明 | [executor.py](../researchclaw/pipeline/executor.py#L629-L646)、[contracts.py](../researchclaw/pipeline/contracts.py#L5-L22) |
| `stage-XX/decision.json` | status / decision / `output_artifacts` / `evidence_refs` / error / next_stage | [_helpers.py](../researchclaw/pipeline/_helpers.py#L306-L328) |
| `cost_log.jsonl` | 逐次调用的 token 与成本 | [runner.py](../researchclaw/pipeline/runner.py#L484-L494) |
| `manifest.json` | 导出清单 | [runner.py](../researchclaw/pipeline/runner.py#L1224) |

因此可审计的是：**哪个阶段、以哪些上游产物为输入、产出了什么、引用了哪些证据、花了多少 token**。

不可审计的是：**模型当时看到了什么、说了什么、调了什么工具**。

---

## 4. 外部 agent 接入的审计代价

| 现象 | 后果 | 证据 |
|---|---|---|
| acpx 输出中的 `[tool]` 行被正则剥除 | 外部 agent 的工具轨迹对 ARC 完全不可见 | [acp_client.py](../researchclaw/llm/acp_client.py#L33)、[同文件](../researchclaw/llm/acp_client.py#L523-L536) |
| CLI code agent 只回传最终结果 | 中间的编辑/执行动作不留痕 | [experiment/code_agent.py](../researchclaw/experiment/code_agent.py#L386-L563) |
| prompt / response 不落盘 | 无法事后复算「输入 → 输出」 | 见 §3 产物表，无对应文件 |

即：**ACP / CLI 模式用「外部 agent 的便利」换掉了「token 级可追溯」**。若审计优先级高于免密钥，应选 API 模式。

---

## 5. 缺口清单（移交 G-1 / G1）

| # | 缺口 | 建议归属 | 处置方向 |
|---|---|---|---|
| **GAP-1** | `LLMClient.chat()` 出口不记录 prompt / response / usage span | G1（事件链） | 增加调用 span：`model` + `prompt_sha256` + `response_sha256` + `usage`，写入 run 级 JSONL，复用 G1 的链哈希 |
| **GAP-2** | ACP 模式丢弃 `[tool]` 行 | G-1（可信性） | 至少保留工具名与次数摘要，落 `stage-XX/agent_trace.jsonl` |
| **GAP-3** | CLI code agent 中间动作不可见 | G-1（与 GAP-2 合并） | 复用同一 trace 格式，不自建第二套 |

> 三项都不在本文实施；按总纲规则，须在 G-1 / G1 的 `RESEARCH.md` 中以 H-* / A1-* 编号登记后方可开工。

---

## 6. 结论

1. ARC 默认只需 LLM API；agent CLI 是可替换后端或代码阶段执行器，不是运行前提。
2. 仅用 API 时，ARC 具备**记忆**与**宿主侧工具调用**，但**不具备模型自决的工具循环**与**通用上下文压缩**；它用「产物落盘 + 阶段间文件交接」替代了会话上下文管理。
3. 可追溯性当前只到**流程级**（阶段 / 产物 / 证据引用 / 成本）；**推理链级**审计需要 GAP-1..3 补齐，正好落在 G-1 与 G1 的既有范围内。
