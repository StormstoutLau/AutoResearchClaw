# 多模型 / 多工作站 Agent 编排的可行性与路线（调研）

> 状态：**调研草案 v0.1**（2026-11-27）。触发：Stage 10 三次 attempt 连续失败（运行 I，12 541.6 s，`exit_code=75`），单端点单调用链已接近其收益上限；用户提出「用多 LLM API 或 ACP 调其他工作站 agent CLI 加速科研推理」。
> 定位：本文只做**可行性与路线判定**，不实施。实施按 §5 分级另开批次。

---

## 0. 结论摘要

1. **可行，但收益高度依赖"有没有可判定的选择器"**。ARC 已具备四类可验证判据（代码校验、沙箱执行、符号契约、证据门），因此「并行生成 + 判据筛选」是当前最匹配的拓扑；没有判据的并行只是抽奖 + 成本爆炸。
2. **并发本身不解决当前瓶颈**。运行 I 的直接失败是「repair 响应 3k 字符被截断 → 不可解析 → 2 次 abort」，这是**单次调用预算与错误闭环**问题，多开几路只会并行地失败。
3. **框架已有大半积木，缺的是"编排"**：`reviewer_model`（独立判审）、`debate`（深度）、`tournament`（广度）、`ACPClient`（acpx 持久会话）、`cli_agent`（claude_code / codex 子进程）均已实现，但 `debate`/`tournament` 是**顺序循环**，全仓唯一的业务级并行在 `metaclaw_bridge/prm_gate.py`（多票 judge）。
4. **协议层窗口已打开**：ACP v2 于 2026-11-20 进入 Preview，把 **subagents（child sessions）、background work、replay、idempotencyKey** 纳入基线，Claude / Codex 适配器均已提供；但 remote transport 与 steering 仍未定，不宜绑死。
5. **建议顺序**：P0 Stage 10 模块级 best-of-2（带判据）→ P1 跨站路由（机械模块下沉）→ P2 ACP/CLI 子会话并行 + 分支可观测 → P3 Stage 8/9 的 debate/tournament 并行化。**不建议**全局 Mixture-of-Agents 化。

---

## 1. 当前编排能力盘点（代码事实）

| 能力 | 实现 | 锚点 | 限制 |
|---|---|---|---|
| 多模型 fallback | `LlmConfig.primary_model` / `fallback_models` | [config.py L201-L241](../../researchclaw/config.py#L201-L241) | 同一 endpoint 内的顺序降级，无并发 |
| 独立判审模型 | `reviewer_model` / `reviewer_provider` / `reviewer_base_url` | [config.py L213-L224](../../researchclaw/config.py#L213-L224) | 已破解「生成者=评审者」，但默认空 |
| 多模型辩论 | `pipeline/debate.py`；`build_panel_llms` 组 panel | [debate.py L1-L20](../../researchclaw/pipeline/debate.py#L1-L20)、[llm/__init__.py L115-L157](../../researchclaw/llm/__init__.py#L115-L157) | **顺序**逐角色调用；`provider=acp` 时禁用 |
| 广度锦标赛 | `pipeline/tournament.py`：N 候选 + 独立 judge | [tournament.py L1-L21](../../researchclaw/pipeline/tournament.py#L1-L21) | 候选生成是 `for` 循环（约 L144-L170），非并行；仅用于 Stage 8 合成 |
| ACP 客户端 | `ACPClient` 经 `acpx` 持久命名会话 | [acp_client.py L62-L100](../../researchclaw/llm/acp_client.py#L62-L100)、[L208-L241](../../researchclaw/llm/acp_client.py#L208-L241) | 作为**整管线 LLM 后端**替换，非编排器；`max_turns=1`，无并发会话池 |
| 外部 CLI Agent | `CliAgentConfig`：`claude_code` / `codex` 子进程 | [config.py L592-L612](../../researchclaw/config.py#L592-L612)、[_code_generation.py L650-L714](../../researchclaw/pipeline/stage_impls/_code_generation.py#L650-L714) | 仅 Stage 10/13；失败回退 LLM 路径；无并行分支 |
| 并行先例 | PRM 多票 judge | [prm_gate.py L176-L204](../../researchclaw/metaclaw_bridge/prm_gate.py#L176-L204) | 唯一 `ThreadPoolExecutor` 业务用法；默认关 |
| 远端算力 | `ssh_remote` 沙箱 | [config.py L632](../../researchclaw/config.py#L632) | 只分发**实验执行**，不分发 LLM 调用 |
| 分支可观测 | 心跳 / 步骤账本 / repair trace | [runtime/progress.py](../../researchclaw/runtime/progress.py)、[step_journal.py](../../researchclaw/pipeline/step_journal.py)、[repair_trace.py](../../researchclaw/pipeline/repair_trace.py) | 均为**单分支**语义，无 `branch_id` |

结论：ARC 的骨架是「线性管线 + 单一 canonical 产物」，多模型能力以**顺序**方式嵌入。要做并行编排，缺的不是客户端能力，而是三样：**（a）分支标识与归因，（b）选择器协议，（c）跨端点调度**。

---

## 2. 现场约束（运行 I / 运行 J）

| 事实 | 读数 | 对编排的含义 |
|---|---|---|
| 单端点吞吐 | B 站 nemotron 单机 decode ≈ 20.9 t/s（[集群手册](file:///D:/RPC/docs/三机推理集群使用手册.md) L235） | 同一端点并发 = 排队，wall-clock 不降 |
| Stage 10 单次 attempt | 2 405–2 465 s / 12–13 次调用 | 单次调用占主导，fan-out 需跨端点才有真收益 |
| 失败形态 | `data.py` repair 响应 3 003 / 3 108 字符均 `truncated=true` → abort | 预算/错误闭环问题，并发无关 |
| 端点异构 | A 站 gpt-oss-120b（速度档）、B 站 nemotron（1M ctx）、C 站可换 nemotron/gpt-oss | 天然形成「强-快-独立」三档池，适合路由与交叉判审 |
| 引擎输出上限 | halogen `--max-tokens-cap 65536`，默认 `n_predict=8192` | 大模块单调用受限，正是 fan-out 或分块的动机 |
| 成本纪律 | debate/tournament/PRM 默认全关；`max_budget_usd` 默认 5.0 | 任何 N 倍方案必须自带预算门与中止 |
| 可观测前置 | B-31b 心跳、B-33 步骤账本、B-36 trace 已落地 | 并行前必须先给这些记录加分支维度，否则无法归因 |

---

## 3. 外部证据

### 3.1 协议层：ACP

- ACP 由 Zed 提出，用**最小 JSON-RPC 端点**替代 ANSI 终端抓取，让任意 client 与任意 agent 通信（[Zed 博客](https://zed.dev/blog/bring-your-own-agent-to-zed)）。
- **ACP v2 于 2026-11-20 进入 Preview**，关键增量（[官方公告](https://agentclientprotocol.com/announcements/acp-v2-preview)）：
  - **subagents 进基线**：agent 把委派的工作暴露为 child session，消息/计划/工具调用以普通 session update 到达；
  - **background work 列表**：session idle 时仍可知道哪些 terminal / tool call / subagent 在跑；
  - **重连语义**：`replay_complete` 标记历史回放结束，`idempotencyKey` 让重试不重复插入消息；
  - 未定项：**remote transport**（Streamable HTTP/WebSocket）与 prompt steering/queueing。
- 已有 Claude / Codex 的 ACP 适配器，Rust/TS/Kotlin/Python SDK 均提供 v2 API。
- 判读：ARC 不是编辑器，**不应自造 agent 协议**；ACP 适合作为「调用外部 agent 的标准接口」，尤其 `idempotencyKey` + `replay` 正好补 ARC 断点重入的语义缺口。但 v2 仍是 Preview，接入需能力探测 + v1 并存。

### 3.2 CLI Agent 的无人值守形态（社区事实）

| 工具 | 非交互入口 | 结构化输出 | 关键约束 |
|---|---|---|---|
| Claude Code | `claude -p` / `--print`，2026-03 起有 `--bare` | 文本 / JSON | 需自管环境与预算（[Claude Academy](https://academy.claude.com/courses/claude-code-in-action/routines-and-headless)、[官方最佳实践](https://www.anthropic.com/engineering/claude-code-best-practices)） |
| Codex CLI | `codex exec` | `--json` → JSONL 事件流 | **exec 模式强制 approval=never**，须预先设定 sandbox policy；默认要求 Git 仓库（[JSONL 参考](https://codex.danielvaughan.com/2026/04/08/codex-exec-jsonl-reference/)、[headless 指南](https://codex.danielvaughan.com/2026/04/18/codex-cli-headless-batch-mode-automation/)） |
| Gemini CLI | `-p` / `--prompt` | `--output-format json`（`response` / `stats` / `error`） | 非 TTY 自动进入 headless（[官方文档](https://geminicli.com/docs/cli/headless/)） |

判读：三者都已是「可被当函数调用」的形态，且都有结构化输出与明确的沙箱/审批约束——这正是 ARC `CliAgentConfig`（`timeout_sec` / `max_budget_usd` / `env_extra`）已在建模的接口。真正的缺口是**产物协议**（文件树 diff + 可验证摘要），否则无法与 ARC 的 `steps.jsonl` / 证据门对齐。

### 3.3 学术

| 工作 | 机制 | 对本项目的启示 |
|---|---|---|
| AI Scientist-v2（[2504.08066](https://arxiv.org/pdf/2504.08066)） | agentic tree search，多分支实验 + 剪枝 | 与 ARC 的 `_phase3_tree_search` 同构；需要**沙箱判据**才能剪枝 |
| Agent Laboratory（[2501.04227](https://arxiv.org/pdf/2501.04227)） | 三角色（PhD / ML Engineer / Professor）+ 人工反馈 | 角色分工比"同质多采样"更省；ARC 的 reviewer 已是一半 |
| AI co-scientist（[2502.18864](https://arxiv.org/abs/2502.18864)） | generate → debate → evolve + test-time compute scaling | 辩论用于**假设**层收益最大，用于长代码收益不确定 |
| AgentRxiv（[2503.18102](https://arxiv.org/abs/2503.18102)） | 共享 preprint 服务器，实验室间继承成果 | 对应 ARC 的跨 run 产物复用（B-33 L2 的自然延伸） |
| Multi-agent debate（[2305.14325](https://arxiv.org/pdf/2305.14325)） | 多实例互相看答案后修正 | 提升事实性/推理，但成本×轮数 |
| 辩论失败模式（[2509.05396](https://arxiv.org/html/2509.05396)） | 趋同、被错误共识带偏 | **必须**配独立 judge 与可验证判据，否则辩论会放大错误 |
| Mixture-of-Agents（[2406.04692](https://arxiv.org/html/2406.04692)） | 分层聚合上一层输出，AlpacaEval 2.0 SOTA | 适合"生成一句答案"；ARC 产物是长文档/代码，聚合成本高 |
| 测试时计算（[2408.03314](https://arxiv.org/pdf/2408.03314)） | 并行采样 + verifier 选择优于单纯加参数 | 支持「N 候选 + 判据」；也指出**验证器质量决定收益** |
| 路由成本（[RouteLLM 综述](https://agentropic.ai/blog/llm-model-routing-cost/)、[FrugalGPT](https://arxiv.org/pdf/2609.22951)） | 按难度路由：RouteLLM 报告最高约 85% 降本且保留约 95% 质量 | ARC 的「机械模块 vs 设计模块」分档已有雏形（B-34 M4） |
| 多步 agent 路由（[AgentRouter, 2609.22951](https://arxiv.org/pdf/2609.22951)） | 异构模型路由，52.7% 降本 / 95.6% 质量；纯级联（FrugalGPT）44.1% / 96.8% | 多步工作流更适合**预算感知路由**而非纯级联 |

---

## 4. 可行性矩阵（拓扑 × ARC 适配）

| 拓扑 | 适用阶段 | 需新增 | 收益 | 风险 | 判定 |
|---|---|---|---|---|---|
| **A. 扇出 + 判据筛选**（best-of-N / 树搜索） | Stage 10 模块级、Stage 8 假设 | 分支标识、选择器协议、并发调度 | 高：直接提高"至少一版通过校验"的概率 | N 倍成本；判据弱则抽奖 | **P0 首选**（限 Stage 10，N=2） |
| **B. 跨站模型路由**（机械→A/C，核心→B） | 全阶段 | 路由表、端点健康检查、成本归因 | 中高：便宜模块降本、核心模块用强模型 | 一致性、跨站延迟、密钥管理 | **P1** |
| **C. 角色分工**（生成/评审/裁判不同模型） | Stage 8/10/14/18 | 现成（`reviewer_model`） | 中：降低自我偏好 | 需保证 judge 独立性 | **P1 随 B 一起做** |
| **D. 外部 CLI Agent 专家分支** | Stage 10/13 | 产物协议（文件树 + 摘要）、预算/超时门 | 中：借用 Claude/Codex 的长上下文与工具循环 | 不可预测 token、行为不可复现、审计难 | **P2** |
| **E. ACP 子会话并行** | Stage 10、跨站 agent | ACP v2 适配、child session 追踪 | 中：标准化接口 + replay/idempotency | v2 仍 Preview，remote transport 未定 | **P2**（先能力探测） |
| **F. 全局 MoA / 多轮辩论** | 全阶段 | 无（已有 debate） | 低-中：短答案有效，长产物代价高 | 成本×轮×模型；辩论趋同 | **不建议**（仅 Stage 8/9 试点） |

关键判读：**A 的收益上限由选择器决定**。ARC 恰好有三层可验证判据（`validate_code` → 沙箱执行 → `codegen_evidence` 符号契约），这在社区案例里是稀缺条件——多数 agent 系统只能靠 LLM-as-judge。

---

## 5. 建议路线（P0..P3，均带验收）

| 级别 | 动作 | 可测量验收 |
|---|---|---|
| **P0** | Stage 10 模块级 **best-of-2**：同一模块两次生成（同模型不同温度，或 B/A 双端点），选择器 = 现有 `validate_code` + 沙箱 exec + 符号契约；**仅在有判据时启用**，默认关 | 同一 `data.py` fixture 下「至少一版通过校验」的比例；单模块 wall-clock 上限；单模块成本上限；无判据时不触发 |
| **P1** | **路由表**：`mechanical → A/C`、`core → B`、`review → 独立模型`；随 P0 一起记录每分支 token/耗时 | 机械模块成本下降 ≥30% 且失败率不升；`reviewer != generator` 恒成立 |
| **P2** | **外部 agent 分支**：`cli_agent` / ACP 作为可选分支，产物走「文件树 + sha256」协议；ACP 先做 v1 能力探测，v2 仅实验 | 子会话可被 `steps.jsonl` 以 `branch_id` 追溯；超时/预算可中断；失败可回退且留证据 |
| **P3** | **并行化现有 debate/tournament**（当前为顺序循环），先 Stage 8/9 | 同一 fixture 质量分不降、wall-clock 下降；成本增幅有上限 |

**每级的前置条件**：分支维度进入 `steps.jsonl` / `heartbeat.json` / `repair_trace.jsonl`（当前均单分支）。没有这一步，并行会让 B-31b/B-36 的取证能力失效。

---

## 6. 风险与反例

1. **无判据并行 = 抽奖**：N 倍成本换不确定收益；`2408.03314` 的结论是验证器质量决定收益，不是采样数量。
2. **同端点并发不加速**：llama.cpp 批 1 下并发即排队；必须跨站（A/B/C）或跨进程。
3. **辩论会放大错误**：`2509.05396` 记录的趋同/错误共识，正是 ARC 用「独立 reviewer + 结构门」规避的；并行化不能破坏这条纪律。
4. **行为不可复现**：CLI agent 自带工具循环，token 与时序不可预测；必须用 `max_budget_usd` / `timeout_sec` 硬门，并保留原始输出摘要（与 B-36 同纪律）。
5. **协议风险**：ACP v2 Preview 明确可能小幅破坏性变更，remote transport 未定；接入须版本协商 + v1 并存。
6. **产物必须收敛**：ARC 每阶段只允许**一个** canonical artifact（`tournament` 已确立此语义）；并行分支只能在选择阶段存在。
7. **观测必须先行**：否则失败时无法回答「哪个分支、哪次调用、为什么被拒」——这正是运行 I 花 3.5 h 才定位的教训。

---

## 7. 非目标

- 不做全局 Mixture-of-Agents 或逐 token 聚合。
- 不在无判据的环节引入 N 倍采样（如论文写作、综述）。
- 不把 ACP 当作内部阶段间通信协议（阶段间仍是文件 + 事件）。
- 不做「多 agent 自由对话」式自治循环；ARC 的线性产物语义不变。
- 不在本批改任何代码。

---

## 8. 复现与证据清单

```bash
# 本地能力盘点（可重放）
rg -n "reviewer_model|debate_enabled|tournament_enabled" researchclaw/config.py
rg -n "ThreadPoolExecutor" researchclaw
rg -n "class ACPClient|acpx" researchclaw/llm/acp_client.py
rg -n "CliAgentConfig|cli_agent" researchclaw/config.py researchclaw/pipeline/stage_impls/_code_generation.py
rg -n "for i, \(system, user\) in enumerate\(candidate_prompts\)" researchclaw/pipeline/tournament.py

# 现场读数（B 站）
ssh <B_HOST> "sed -n '1,40p' ~/arc-runs/g7-baseline/stage-10/stage_health.json"
ssh <B_HOST> "grep -c truncated ~/arc-runs/g7-baseline/stage-10/repair_trace.jsonl"
```

**外部来源**：[Zed ACP 发布](https://zed.dev/blog/bring-your-own-agent-to-zed)、[ACP v2 Preview](https://agentclientprotocol.com/announcements/acp-v2-preview)、[ACP 规范总览](https://agentclientprotocol.com/protocol/v2/draft/overview)、[Claude Code 最佳实践](https://www.anthropic.com/engineering/claude-code-best-practices)、[Gemini CLI headless](https://geminicli.com/docs/cli/headless/)、[Codex exec JSONL](https://codex.danielvaughan.com/2026/04/08/codex-exec-jsonl-reference/)、[AI Scientist-v2](https://arxiv.org/pdf/2504.08066)、[Agent Laboratory](https://arxiv.org/pdf/2501.04227)、[AI co-scientist](https://arxiv.org/abs/2502.18864)、[AgentRxiv](https://arxiv.org/abs/2503.18102)、[Multi-agent debate](https://arxiv.org/pdf/2305.14325)、[Debate failure modes](https://arxiv.org/html/2509.05396)、[Mixture-of-Agents](https://arxiv.org/abs/2406.04692)、[Test-time compute](https://arxiv.org/pdf/2408.03314)、[AgentRouter](https://arxiv.org/pdf/2609.22951)、[RouteLLM 成本数据](https://agentropic.ai/blog/llm-model-routing-cost/)。
