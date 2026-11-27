---
id: arc-stage10-generation-budget-contract-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-27
depends: [arc-stage10-module-extraction-fallback]
upstream: arc-master-roadmap
---

# 调研：Stage 10 生成预算分档、文件预算与符号契约（B-34 M4）

> **背景**：运行 F（[postmortem §2.4](../../docs/arc-b-site-stage10-postmortem-20261126.md)）证明 M1-b 已能把失败提前到模块边界，但 `data.py` 仍在 32768 触顶。§F-7b.9 的 Phase 0 探针把根因拆成两条：① 32768 是自设（引擎 cap=65536）；② 默认 `xhigh` 把 **76–85%** 的输出预算花在 reasoning 上（§F-7b.10）。本批按 §F-7b.8 的 C+ 方案落地「思考预算分档 + 文件预算 + 符号契约」。

## 0. 结论

1. **思考与代码共用同一输出预算**：同一 `data.py` 提示词，默认模式 reasoning 3 097/4 068 与 6 989/8 175；`reasoning_effort=low` 降到 114；`reasoning.max_tokens=2048` 封顶 2 073；`enable_thinking=false` 为 0（§F-7b.10）。
2. **关闭思考有质量风险**：Qwen3 官方把 `enable_thinking=False` 定义为 hard switch（与 Qwen2.5-Instruct 对齐），vLLM 与 Qwen3 技术报告都把「思考预算」作为一等能力；因此策略是**分档限流**而非全局关闭。
3. **ARC 客户端没有透传通道**：[`LLMClient.chat`](../../researchclaw/llm/client.py#L302-L316) 只构造 `model/messages/temperature/max_tokens`，供应商专有字段（`reasoning_effort`、`chat_template_kwargs`、`reasoning.max_tokens`）无法下发。
4. **没有文件规模约束**：模块 prompt 不携带行数上限，蓝图也不消费 `max_lines`；`data.py` 可以无限膨胀而不被任何结构判据发现。
5. **没有符号级契约**：B-32 M2 只比对**文件集合**，无法区分「文件在但内容是空壳」；RPG 论文（§F-7b.8 E-11）指出规划应到函数/符号粒度。

## 1. 现场与代码证据

| 项 | 读数 | 证据 |
|---|---|---|
| 引擎上限 | `max_tokens_cap=65536`、`max_tokens_default=8192`；`70000` 被 400 拒绝 | §F-7b.9 P-1/P-3 |
| reasoning 占比 | 默认 76% / 85%（两轮） | §F-7b.10 表 |
| 限流效果 | `low` → 114；`max_tokens=2048` → 2 073 | 同上 |
| 客户端字段 | `body` 只含 `model/messages/temperature/max_tokens/response_format` | [client.py L700-712](../../researchclaw/llm/client.py#L700-L712) |
| 文件门粒度 | `check_declared_files` 只比 basename | [codegen_evidence.py L211-L226](../../researchclaw/pipeline/codegen_evidence.py#L211-L226) |
| 模块 prompt | 无行数上限；`file_spec` 只透传蓝图原文 | [code_agent.py L861-L903](../../researchclaw/pipeline/code_agent.py#L861-L903) |

## 2. 外部锚点

| ID | 来源（层） | 要点 | 用法 |
|---|---|---|---|
| R-1 | [Qwen3 博客](https://qwenlm.github.io/zh/blog/qwen3/)（T2） | 思考模式面向复杂问题；性能随预算平滑变化 | 分档而非关闭 |
| R-2 | [Qwen 快速开始](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html)（T2） | `enable_thinking=False` 是 hard switch | 仅作最后手段 |
| R-3 | [vLLM Reasoning Outputs](https://docs.vllm.ai/en/stable/features/reasoning_outputs/)（T2） | `thinking_token_budget` 达到即强制结束思考 | 与 `reasoning.max_tokens` 同向 |
| R-4 | [RPG](https://arxiv.org/abs/2509.16198)（T1） | 规划粒度应到 function 级；整仓生成仍难 | 符号契约 |
| R-5 | [Aider 编辑格式](https://aider.chat/docs/more/edit-formats.html)（T2） | 整文件生成可靠但成本随文件线性增长 | 文件行数上限 |

## 3. 范围

- **思考分档**：`CodeAgentConfig.thinking_policy ∈ {off, tiered}`；`tiered` 时机械模块发 `reasoning_effort`，设计模块可选 `reasoning.max_tokens`。默认 `off`，保证对严格 provider 字节不变。
- **文件预算**：`file_max_lines`（默认 300）+ 蓝图 `max_lines` 覆盖；写入模块 prompt。
- **符号契约**：蓝图 `symbols`/`required_symbols`/`classes`/`functions` 声明的名字必须出现在对应文件 AST 中；缺失 → `blueprint_symbols_missing`。

## 4. 非目标

- 不提高全局 max_tokens（A' 仍为条件启用，见 §F-7b.8）。
- 不做 C++（函数级分块生成）。
- 不启用 `enable_thinking=false`（仅保留为人工兜底）。
- 不改对齐门（B-35 P1 才做确定性证据）。
- 不自动拆分超预算文件（本批只测量与提示）。

## 5. 未决项（四元块）

| 判据 | 触发条件 | 当前倾向 | 证据等级 |
|---|---|---|---|
| 分档是否真的降低截断率 | B 站下一次 Stage 10 重跑 | 是（reasoning 从 3–7k 降到 ~0.1k） | 待现场 |
| 机械模块清单是否够用 | 出现被误分档的模块 | 先按文件名子串，后续可按蓝图 role 字段 | E1（6 个用例） |
| 符号契约的误杀面 | 蓝图声明了抽象方法/外部符号 | 只校验**已交付文件**中的顶层与嵌套定义名；缺文件交给文件门 | E1（7 例） |
| 是否把 `max_lines` 升级为硬门 | 提示被无视 | 先只提示 + 记账，硬门需度量 | — |
