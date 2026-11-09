---
id: arc-cli-agent-wiring-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-master-roadmap, arc-b-station-endpoint]
upstream: arc-master-roadmap
---

# 调研：CLI 代码代理接线断裂

> **Feature**: `experiment.cli_agent` 与 `experiment/code_agent.py` 的配置面/执行面/验证面断裂。
> **创建日期**: 2026-11-10
> **状态**: verified（调研完成，结论可复核）
> **Spec 步骤**: Step 1-2

---

## 1. 调研目标

**核心问题**:

1. 为什么 `experiment.cli_agent.provider` 与 `create_code_agent()` 存在、能通过校验、有单元测试，却不会在 Stage 10/13 生效？完整问题链与影响面是什么？
2. 外部项目与社区如何把 Claude Code / Codex 等 CLI 代理接入编排器？哪些接法在跨平台、可测性、可审计性上更稳？
3. ARC 应选择哪条路线：补接线、收口删除、统一接缝，还是先做最小真相修正？

**不在本批**: 实际接线与删除代码（需裁决后另开批次）；B 站端点本身的可用性（已在 P-007/P-008 验证）。

## 2. 调研方法

| 工具 | 用途 | 查询 |
|---|---|---|
| SearchCodebase（Grep/Read） | 代码事实、调用方、配置解析、测试覆盖 | `create_code_agent`、`cli_agent`、`CodeAgentConfig`、`_execute_code_generation` |
| git log / git show | 历史追溯与引入时间 | `-S create_code_agent`、`--follow experiment/code_agent.py` |
| WebSearch | 官方文档与社区实践 | Claude Code headless、Agent SDK、ACP、Codex exec、Node .cmd |
| WebFetch | 官方页面取证 | Claude CLI reference、Agent SDK Python、ACP、Node child_process |
| mcp_paper-search/WebSearch | 学术锚点 | SWE-agent、Agentless、MAST |

## 3. 调研发现

### 3.1 代码事实与问题链

#### 3.1.1 三条并行的“代理”路径

| 路径 | 入口配置 | 实现 | 是否接线 | 作用层 |
|---|---|---|---|---|
| ACP | `llm.provider: acp` | `researchclaw/llm/acp_client.py`（经 `acpx`） | **是**：`create_llm_client` 返回 `ACPClient` | LLM 层，贯穿 23 阶段 |
| OpenCode Beast Mode | `experiment.opencode.*` | `pipeline/opencode_bridge.py` | **是**：Stage 10 优先尝试 | 代码生成 |
| CLI 代码代理 | `experiment.cli_agent.provider` | `experiment/code_agent.py::create_code_agent` | **否**：生产代码零调用 | Stage 10/13（文档声称） |

同一仓内还存在第四种“代理式”路径 `experiment.agentic`（Stage 12 的 agentic sandbox），与本题无关，但说明“代理”概念在配置面已分裂为至少四套词汇。

#### 3.1.2 配置面事实

| 配置块 | 定义 | 解析 | 校验 | 真实消费者 |
|---|---|---|---|---|
| `experiment.code_agent` | `config.py:466-487`（阶段开关） | `_parse_code_agent_config`（`config.py:1546-1566`） | 只校验类型 | Stage 10 多阶段 LLM 代理 |
| `experiment.cli_agent` | `config.py:573-593`（provider/binary/model/budget/env_extra） | `_parse_cli_agent_config`（`config.py:1529-1543`） | provider 枚举（`config.py:1214-1219`） | 仅 `runner.py:482` 读 `max_budget_usd`；provider 无消费者 |
| `llm.acp` | `config.py:190-196` | `config.py:1261-1268` | 间接 | `ACPClient` |

关键事实：

- **F-1** `create_code_agent()` 除自身定义与测试外，全仓零调用（`grep -rn "create_code_agent"` 仅命中 `experiment/code_agent.py` 与文档字符串）。
- **F-2** Stage 10 的分支顺序是 Beast Mode → 多阶段 `CodeAgent` → 单发 LLM（`pipeline/stage_impls/_code_generation.py:640-770`），没有任何分支读取 `config.experiment.cli_agent.provider`。
- **F-3** Stage 13 的迭代改进只调用 `_chat_with_prompt`（`_execution.py:1366`、`:1441`、`:1566`），同样不读取 CLI provider。
- **F-4** `_parse_code_agent_config` **不解析** `provider` 字段；用户若把 `provider` 写在 `experiment.code_agent` 下，会被静默丢弃。
- **F-5** `create_code_agent` 的报错文案指向错误路径：`set experiment.code_agent.binary_path`（实际字段在 `experiment.cli_agent.binary_path`），见 `experiment/code_agent.py:790-793`、`:805-808`。
- **F-6** `CodeAgentConfig` 在 `config.py:466` 与 `pipeline/code_agent.py:41` 各定义一次，字段相同但无继承/引用关系；Stage 10 用鸭子类型把前者传给后者的构造器。
- **F-7** `cli_agent.max_budget_usd` 被 `runner.py:482` 当作**整条 run 的预算**读取；Q20 已裁决分层账本，但 `run_budget_usd` 在代码中零命中，说明该字段当前同时承担“死 provider 配置”和“活预算来源”两种语义。
- **F-8** `config.researchclaw.example.yaml:166-179` 公开了 `cli_agent` 示例（含 `provider: "claude_code"` 与 `env_extra`），用户可据此配置，但运行结果会静默走 LLM 路径。
- **F-9** `domains/deploy.py:198-206` 把 `cli_agent` 列为可部署的嵌套配置块，进一步强化“该功能可用”的外部印象。

#### 3.1.3 历史追溯

| 时间线 | 提交 | 事实 |
|---|---|---|
| F-02 引入期 | `f75f7d3` | `pipeline/code_agent.py` 以“4-phase advanced code agent”身份进入主线，是 Stage 10 的真实实现 |
| v0.3.2 | `a055693` | 新增 `experiment/code_agent.py`（776 行）与 `CliAgentConfig`；`create_code_agent` 自引入起即无调用方 |
| P-007 | `b67a2b6` | 为 `CliAgentConfig` 增加 `env_extra`，并让 `_CliAgentBase` 注入环境变量；仍未接线 |
| 本会话 | 未提交 | 发现多行 prompt 经 Windows `.CMD` 被截断，修复为 stdin 传递；该问题只能由端到端测试暴露 |

结论：这不是“实现写错了”，而是**实现与接线同时存在、但接线从未发生**。文档、配置、测试、部署四处都把它当作已存在的能力描述，形成“文档先于实现”的漂移。

#### 3.1.4 验证面事实

- `tests/test_b_station_provider.py:243-297` 只验证 `_run_subprocess` 与 `create_code_agent` 的局部行为；没有断言“Stage 10 会使用该 provider”。
- `tests/test_code_agent.py` 验证的是 `pipeline/code_agent.py` 的多阶段代理，与 CLI 代理无关。
- P-007 的验收以“live 双 wire 实测”通过，但 live 用例打的是 **LLM API**，没有打 Claude Code CLI；因此“Claude Code 接入”在验收层面从未被证明。
- 结果是**测试全绿 + 功能不可达**，即 MAST 分类中的“任务验证失败”（见 X-10）。

#### 3.1.5 影响面

| 维度 | 影响 |
|---|---|
| 用户 | 配置被接受但不生效；成本/延迟预期错误；排障无日志 |
| 维护 | 三套代理抽象、两个同名配置类、两套预算语义；任一侧改动会静默漂移 |
| 审计 | CLI 原始输出只保留 3000 字符，无工具调用轨迹；与 Q17“审计要求高的 run 禁用 ACP”不衔接 |
| 测试 | 单元测试无法证明接线；端到端缺口导致 Windows prompt 截断直到人工实测才暴露 |

### 3.2 外部锚点

#### 3.2.1 CLI / SDK 接入

**X-1 Claude Code CLI reference（官方）**

- **来源**: https://code.claude.com/docs/en/cli-reference
- **验证状态**: ✅ 已抓取
- **关键结论**: `claude -p "query"` 为非交互模式；`cat file | claude -p "query"` 支持管道输入；`-p` 同时读写 stdin/stdout。
- **相关性**: 说明 prompt 应走 stdin 或 SDK，而不是把长文本塞进 argv。

**X-2 Claude Agent SDK（Python，官方）**

- **来源**: https://docs.claude.com/en/api/agent-sdk/python
- **验证状态**: ✅ 已抓取
- **关键结论**: `pip install claude-agent-sdk`；`query()` 返回异步消息迭代器；`ClaudeSDKClient` 支持多轮会话、中断、Hooks 与自定义工具。
- **相关性**: 提供“进程内、结构化消息”的接法，绕开 shell/argv/编码问题，并可保留工具调用轨迹。

**X-3 Agent Client Protocol（ACP）**

- **来源**: https://agentclientprotocol.com/
- **验证状态**: ✅ 已抓取
- **关键结论**: 标准化编辑器与编码代理的通信；本地代理以 JSON-RPC over stdio 运行，远程走 HTTP/WebSocket（进行中）。
- **相关性**: ARC 已有 `ACPClient`/`acpx` 路径；这是“结构化 stdio”而非“文本 argv”的社区标准解。

**X-4 Zed 的 Claude Code ACP 适配器**

- **来源**: https://zed.dev/blog/claude-code-via-acp
- **验证状态**: ⚠️ 仅搜索摘要，未直接抓取
- **关键结论**: 适配器包裹 Claude Code SDK，把交互翻译为 ACP JSON-RPC；以 Apache 许可证开源。
- **相关性**: 证明“CLI/agent → 标准协议 → 编排器”是可行且已被编辑器采用的三方模式。

**X-5 Codex CLI 的 stdin 模式**

- **来源**: https://codex.danielvaughan.com/2026/04/15/codex-exec-unix-pipelines-prompt-plus-stdin/
- **验证状态**: ⚠️ 社区文档；官方 `docs/exec.md` 存在但内容已迁移
- **关键结论**: `codex exec -` 从 stdin 读取完整 prompt；stdin 为打开管道且无 prompt 时会等待（openai/codex#27019）。
- **相关性**: 与 Claude Code 同理：多行/大 prompt 走 stdin 更稳；同时必须显式关闭 stdin 防止挂起。

**X-6 Node.js `child_process` 的 Windows `.cmd` 语义（官方）**

- **来源**: https://nodejs.org/api/child_process.html#spawning-bat-and-cmd-files-on-windows
- **验证状态**: ✅ 已抓取
- **关键结论**: Windows 上 `.bat`/`.cmd` 不能由 `execFile` 直接启动；必须经 `spawn(shell:true)`、`exec()` 或 `cmd.exe`，且文件名/参数需要按 shell 规则引用。
- **相关性**: npm 安装的 `claude.CMD` 正属于此类；任何经 `cmd.exe` 的 argv 都会二次解析，换行/引号/长度均可能失真。

**X-7 Node.js DEP0190 与 CVE-2024-27980（社区转述）**

- **来源**: https://nodejs.org/api/deprecations.html#DEP0190 ；https://dev.to/nicholasflemmer/spawning-a-cli-from-node-on-windows-is-not-the-same-as-on-a-mac-4ilm
- **验证状态**: ⚠️ DEP0190 页面存在；CVE 影响为社区说明
- **关键结论**: 2024-04 安全修复后，`.cmd` 需 `shell:true` 才能启动；开启 shell 意味着所有参数再经 cmd.exe 转义。
- **相关性**: 解释本仓为何在 Windows 上出现“只收到第一行 prompt”的截断，而非模型能力问题。

#### 3.2.2 代理架构与验证

**X-8 SWE-agent：Agent-Computer Interface**

- **来源**: https://arxiv.org/abs/2405.15793（NeurIPS 2024）
- **验证状态**: ✅ 标题/摘要命中
- **关键结论**: 代理效果主要来自为 LM 设计的窄接口（查看/搜索/编辑/执行），而非直接复用人类 shell。
- **相关性**: CLI 代理的接口面（prompt、工具白名单、输出格式）应按代理设计，不应把整个 shell 语义暴露给编排器。

**X-9 Agentless：简单管线可胜过复杂代理**

- **来源**: https://arxiv.org/abs/2407.01489
- **验证状态**: ✅ 标题/摘要命中
- **关键结论**: 三阶段“定位 → 修复 → 验证”的简化管线在 SWE-bench Lite 上达到当时最高水平之一（摘要口径 27.3%）。
- **相关性**: 在未证明 CLI 代理带来质量收益前，不应为“多一种后端”承担接线与维护成本。

**X-10 MAST：多代理失败分类**

- **来源**: https://arxiv.org/pdf/2503.13657
- **验证状态**: ✅ 摘要命中
- **关键结论**: 14 种失败模式归为三类：规格与系统设计、代理间错位、任务验证与终止。
- **相关性**: “配置存在但无消费者、测试不证明接线”属于典型的验证/终止类失败。

**X-11 架构适应度函数**

- **来源**: https://www.infoq.com/articles/ai-speed-context-store-architecture/（引 Ford/Parsons/Kua；ArchUnit、dependency-cruiser）
- **验证状态**: ⚠️ 工程实践来源，非同行评审
- **关键结论**: 用可执行检查断言架构属性（依赖方向、命名、无环），并放进 CI，使“文档规则”变成“构建失败”。
- **相关性**: 可用一条静态检查断言“配置声明的 provider 必须存在消费者”，防止再次漂移。

**X-12 Vulture：Python 死代码检测**

- **来源**: https://pypi.org/project/vulture/
- **验证状态**: ✅ 页面存在
- **关键结论**: 基于 AST 找未使用代码，带置信度；动态调用会误报。
- **相关性**: 可作为发现“工厂无调用方”的辅助工具，但不能替代接线契约测试。

**X-13 Anthropic：Building effective agents**

- **来源**: https://www.anthropic.com/engineering/building-effective-agents
- **验证状态**: ✅ 页面存在
- **关键结论**: 保持简单、显式展示规划步骤、精心设计 ACI；框架抽象不宜过多。
- **相关性**: 支持“先收口、按证据接线”，而不是同时维护三条代理路径。

### 3.3 社区解法矩阵

| # | 接法 | 机制 | 优点 | 代价/风险 | 证据 |
|---|---|---|---|---|---|
| S-1 | CLI + stdin 文本 | `claude -p` 无 prompt 参数，prompt 写 stdin | 改动最小；跨平台；保留 CLI 全部工具 | 仍是文本协议；无结构化工具轨迹 | X-1、X-6 |
| S-2 | 官方 Agent SDK | 进程内 `query()`/`ClaudeSDKClient` | 结构化消息、Hooks、会话复用；无 shell 转义 | 新增 Python 依赖；版本绑定 | X-2 |
| S-3 | ACP JSON-RPC | 适配器把代理包成 stdio JSON-RPC | 标准协议、可持久会话；ARC 已有 acpx | 需要适配器；Windows 仍有进程管理问题 | X-3、X-4 |
| S-4 | Codex stdin | `codex exec -` + `--json` | 与 Claude Code 对称；可复用同一 stdin 管 | 需显式关 stdin；JSON 结构差异 | X-5 |
| S-5 | OpenCode Server | 外部 server + HTTP/工作区 | 已有 Beast Mode 实践 | 进程/端口生命周期；额外依赖 | 本仓 `opencode_bridge.py` |
| S-6 | 容器化代理运行时 | 代理跑在容器内，编排器只传任务 | 隔离好；可复现 | 重；与本地 CLI 测试基座冲突 | X-8 |

**社区共识（跨来源）**：长 prompt 不应走 argv；代理接入应有结构化边界（SDK/ACP/stdin-json）；接线必须由端到端测试证明。三条独立来源（X-1/X-2/X-3）与 Windows 进程语义（X-6）一致。

## 4. 综合分析

### 4.1 关键发现总结

1. **问题链是“配置先于接线”**：配置、示例、部署映射、单元测试、文档五处都先于执行面存在。[置信度: ★★★★★]
2. **失效模式是静默的**：provider 被校验但不被消费，用户不会收到任何错误。[置信度: ★★★★★]
3. **测试证明的是局部行为，不是接线**：现有 23 个离线用例无法发现“无调用方”。[置信度: ★★★★★]
4. **外部主流接法是结构化通道**：SDK 或 ACP 优于长文本 argv；Windows 上 `.CMD` 会把 argv 再交给 cmd.exe。[置信度: ★★★★☆]
5. **是否值得接线尚无证据**：Agentless 表明简化管线可能已足够；需 A/B 才能证明 CLI 代理的边际收益。[置信度: ★★★☆☆]

### 4.2 技术 landscape

- **API-first（现状默认）**：LLM 多阶段 `CodeAgent` + legacy 单发；可审计、可计费、跨平台。
- **结构化代理（ACP/SDK）**：能保留工具轨迹与会话，适合“代理即后端”。
- **CLI 文本代理（stdin）**：最轻的异构后端，但输出是文本，审计粒度依赖解析。
- **外部代理服务（OpenCode/容器）**：能力强、隔离好，但生命周期与成本更重。

### 4.3 研究空白

- 没有跨后端的**质量/成本 A/B**：同一任务在 LLM 多阶段、Claude Code CLI、ACP 三种后端下的成功率、耗时、token/成本、可复现性。
- 没有**接线适应度函数**：配置声明与实际消费者之间没有机械约束。
- 没有 **Windows 支持基线**：`.CMD`、PowerShell、路径空格、编码（UTF-8/GBK）未成文。

### 4.4 路线选项与建议

| # | 路线 | 成本 | 收益 | 兼容/维护 | 风险 | 结论 |
|---|---|---|---|---|---|---|
| R-1 | 直接把 CLI 接进 Stage 10/13 | 中 | 配置立即生效 | 三路径并存，维护上升 | 审计/回退不完整 | 暂不单独采用 |
| R-2 | 收口删除 CLI 代理与 `cli_agent.provider` | 低 | 消除漂移；与 Q17 API-first 一致 | 破坏已写配置（可 fail-fast 提示） | 放弃异构后端 | 作为无收益时的兜底 |
| R-3 | 统一接缝：单 Protocol + 单配置 + 三种传输 | 中高 | 长期可扩展；测试/审计统一 | 需迁移与兼容层 | 设计过度风险 | **目标态（分阶段）** |
| R-4 | 最小真相修正：fail-fast + 文档订正 + 标注实验态 | 低 | 立即止血；用户不再被静默误导 | 零行为变更 | 功能仍不可用 | **立即执行（下一批）** |

**建议**（供 DESIGN 采纳）：

1. **先 R-4**：在 `validate_config`/`doctor` 中对 `cli_agent.provider != "llm"` 且未接线的事实 fail-fast（或显式 `experimental: true` 才放行），并订正 P-007 文档中“Claude Code 接入”的表述。
2. **以 R-3 为目标**：单一 `CodeAgentProvider` 协议 + 单一配置块 + 传输适配（LLM HTTP / ACP / CLI-stdin）；默认 API-first，CLI 仅在显式开启时生效。
3. **R-3 的开工门槛 = U-1 的 A/B 证据**：若 CLI 代理在成功率/成本上无显著优势，直接执行 R-2（删除），避免为不存在的收益维护第三条路径。

该建议同时满足：Q17（API-first）、X-9（不为复杂度付费）、X-13（减少抽象层）、X-11（用可执行检查固化接线）。

## 5. 幻觉抑制审查

### 5.1 文献验证

| 引用 | ID/URL | 验证方式 | 状态 |
|---|---|---|---|
| X-1 Claude Code CLI reference | code.claude.com/docs/en/cli-reference | WebFetch 正文 | ✅ |
| X-2 Claude Agent SDK Python | docs.claude.com/en/api/agent-sdk/python | WebFetch 正文 | ✅ |
| X-3 Agent Client Protocol | agentclientprotocol.com | WebFetch 正文 | ✅ |
| X-4 Zed Claude Code ACP | zed.dev/blog/claude-code-via-acp | WebSearch 标题/摘要 | ⚠️ 未抓正文 |
| X-5 Codex stdin | codex.danielvaughan.com/... | WebSearch 摘要 | ⚠️ 社区来源 |
| X-6 Node child_process | nodejs.org/api/child_process.html | WebFetch 正文 | ✅ |
| X-7 DEP0190 / CVE | nodejs.org/api/deprecations.html#DEP0190 | WebSearch 摘要 | ⚠️ CVE 为社区说明 |
| X-8 SWE-agent | arXiv:2405.15793 | 标题/摘要命中 | ✅ |
| X-9 Agentless | arXiv:2407.01489 | 标题/摘要命中 | ✅ |
| X-10 MAST | arXiv:2503.13657 | PDF 摘要命中 | ✅ |
| X-11 适应度函数 | InfoQ 文章 | WebSearch 摘要 | ⚠️ 工程实践 |
| X-12 Vulture | pypi.org/project/vulture | 页面摘要 | ✅ |
| X-13 Building effective agents | anthropic.com/engineering/... | WebSearch 摘要 | ✅ |

### 5.2 技术声明验证

| 声明 | 来源 | 验证状态 |
|---|---|---|
| 多行 prompt 经 Windows `.CMD` 会在首个换行处截断 | 本机实测（P-007 后诊断）+ X-6 | ✅ 实测复现 |
| `create_code_agent` 无生产调用方 | `grep -rn` 全仓 | ✅ 可重放 |
| Stage 10/13 不读取 `cli_agent.provider` | 静态读码 | ✅ 可重放 |
| `experiment.code_agent.provider` 被静默丢弃 | `_parse_code_agent_config` 读码 | ✅ |
| Q20 分层账本尚未落到 `run_budget_usd` | 全仓搜索零命中 | ✅ |
| Agentless 的 27.3% 数字 | arXiv 摘要 | ⚠️ 不同版本口径可能不同，仅作方向证据 |

### 5.3 待修正项

- [ ] P-007/IMPLEMENTATION §1 的“Claude Code 接入”应改为“主控 CLI + B 站端点作为测试基座；CLI 后端尚未接入 Stage 10/13”。
- [ ] 示例配置 `cli_agent` 段应标注“实验态/未接线”，直到 R-4 或 R-3 落地。
- [ ] X-4/X-5/X-11 的正文未抓取，引用时只使用摘要级结论。

## 6. 对设计的输入

### 6.1 可用的技术方案

- 传输：stdin 文本（S-1）、Agent SDK（S-2）、ACP（S-3）、Codex stdin（S-4）。
- 接线：Stage 10 生成、Stage 13 改进/修复共用同一 `CodeAgentProvider` 协议。
- 治理：适应度函数（X-11）+ 契约测试（X-10 的验证类失败）。

### 6.2 关键约束

1. 默认后端保持 API-first，不改变 Q17 与现有阶段出口。
2. 任何 CLI 传输不得把 prompt 放进 argv；Windows 必须走 stdin/SDK/ACP。
3. 进程超时必须杀进程树（Windows `taskkill /T`），否则管道悬挂。
4. 配置必须有唯一真值源；不允许两个同名 `CodeAgentConfig`。
5. 失败必须可回退到 LLM 路径，并写入可审计日志。

### 6.3 风险

- 三路径并存导致维护成本与审计口径分裂（R-1 的直接风险）。
- 删除过早可能丢失未来的异构后端（R-2 的风险，以 A/B 证据缓解）。
- SDK/ACP 引入新依赖与版本绑定（S-2/S-3 的风险）。

### 6.4 未决项登记（四元块）

- **U-1 CLI 代理的边际质量收益**
  - **判据**：同一任务集（≥10 个、含多文件与修复）上，CLI 后端的成功率/耗时/成本相对 LLM 多阶段的提升有统计意义。
  - **触发条件**：出现“LLM 多阶段连续两轮失败、且失败原因是跨文件结构”的真实 run。
  - **当前倾向**：先不接线；用 R-4 止血，A/B 有正收益再进 R-3。
  - **证据等级**：E1（仅外部类比，无本仓实测）。

- **U-2 Windows 支持基线**
  - **判据**：在 Windows 10/11 + PowerShell 5/7 上，`.CMD`、含空格路径、UTF-8 中文 prompt 三类用例全绿。
  - **触发条件**：CI 增加 Windows job，或用户报告第二例 argv/编码问题。
  - **当前倾向**：stdin + `taskkill /T` 作为最低基线。
  - **证据等级**：E2（本机复现，未跨版本矩阵）。

- **U-3 结构化传输选型（SDK vs ACP vs CLI-stdin）**
  - **判据**：三者在本仓的依赖成本、会话复用、工具轨迹、Windows 稳定性四项打分收敛。
  - **触发条件**：R-3 进入设计阶段。
  - **当前倾向**：优先 ACP（已有 acpx 基础设施），SDK 次之，CLI-stdin 作为无依赖兜底。
  - **证据等级**：E1（官方文档，未实测 SDK/ACP 在本仓的完整链路）。

- **U-4 审计口径**
  - **判据**：CLI/ACP 后端能输出归一化的工具调用与文件变更记录，满足 Q17 对高审计 run 的要求。
  - **触发条件**：任何需要“推理链可审计”的 run 选择非 API 后端。
  - **当前倾向**：高审计 run 禁用 CLI/ACP，仅用 API-first。
  - **证据等级**：E1（Q17 已裁决，缺实现验证）。

## 7. 参考文献

1. Anthropic. *Claude Code CLI reference*. https://code.claude.com/docs/en/cli-reference
2. Anthropic. *Agent SDK reference — Python*. https://docs.claude.com/en/api/agent-sdk/python
3. Anthropic. *Building effective agents*. https://www.anthropic.com/engineering/building-effective-agents
4. Agent Client Protocol. *Introduction*. https://agentclientprotocol.com/
5. Zed Industries. *Claude Code: Now in Beta in Zed*. https://zed.dev/blog/claude-code-via-acp
6. Node.js. *Child process — Spawning `.bat` and `.cmd` files on Windows*. https://nodejs.org/api/child_process.html#spawning-bat-and-cmd-files-on-windows
7. Node.js. *DEP0190: Passing args to child_process with shell option*. https://nodejs.org/api/deprecations.html#DEP0190
8. Yang, J. et al. *SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering*. arXiv:2405.15793, 2024.
9. Xia, C. S. et al. *Agentless: Demystifying LLM-based Software Engineering Agents*. arXiv:2407.01489, 2024.
10. Cemri, M. et al. *Why Do Multi-Agent LLM Systems Fail?* arXiv:2503.13657, 2025.
11. Ford, N., Parsons, R., Kua, P. *Building Evolutionary Architectures*（适应度函数）；InfoQ 综述：https://www.infoq.com/articles/ai-speed-context-store-architecture/
12. Vulture. *Find dead code*. https://pypi.org/project/vulture/
13. OpenAI Codex. *exec docs*. https://github.com/openai/codex/blob/main/docs/exec.md
14. Daniel Vaughan. *Codex CLI as a Unix Citizen: Prompt-Plus-Stdin*. https://codex.danielvaughan.com/2026/04/15/codex-exec-unix-pipelines-prompt-plus-stdin/

---

**Review 签字**: 待复核 日期: 2026-11-10
