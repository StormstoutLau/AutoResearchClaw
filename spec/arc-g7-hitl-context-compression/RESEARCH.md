---
id: arc-g7-hitl-context-compression-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-g7-run-id-stability-RESEARCH]
upstream: arc-master-roadmap
---

# 调研：HITL 上下文压缩接线（P-175）

> **范围**：裸 API 场景下，HITL 聊天与阶段上下文如何在不新增 LLM 调用的前提下受预算约束。
> **不在本批**：23 个 stage 的无状态 prompt 架构改造；token 级（而非字符级）预算。

## 1. 本仓现状（T1）

| 事实 | 证据 |
|---|---|
| `ContextManager` 已存在但**从未实例化**（全仓 grep 仅定义与 import 命中） | [context_manager.py L31](../../researchclaw/hitl/context_manager.py#L31) |
| 预算常量按用途分档：system 4000 / history 8000 / stage 6000 / cross-stage 3000 / guidance 1000，总预算 24000 字符 | [context_manager.py L22-L28](../../researchclaw/hitl/context_manager.py#L22-L28) |
| 已有 `build_context()`、抽取式 `summarize_artifact()`、`_trim_chat_history()`（保留最近消息并插入省略提示） | [context_manager.py L46-L115](../../researchclaw/hitl/context_manager.py#L46-L115)、[L152-L208](../../researchclaw/hitl/context_manager.py#L152-L208)、[L278-L312](../../researchclaw/hitl/context_manager.py#L278-L312) |
| `ChatSession.build_llm_messages()` 全量转写，无任何裁剪 | [chat.py L99-L113](../../researchclaw/hitl/chat.py#L99-L113) |
| `get_ai_response()` 直接 `llm_client.chat(messages)`，请求前无预算处理 | [chat.py L116-L146](../../researchclaw/hitl/chat.py#L116-L146) |
| `build_stage_context()` 对 >3000 字符产物做**字符硬截断**（`content[:3000]`） | [chat.py L213-L224](../../researchclaw/hitl/chat.py#L213-L224) |
| `CollaborationSession.initialize()` 只注入一条 system 消息，无压缩器 | [collaboration.py L63-L70](../../researchclaw/hitl/collaboration.py#L63-L70) |
| 管线 stage prompt 为无状态单次请求，`_build_context_preamble` 按字段硬截断（goal/hypotheses/synthesis 2200、plan 2000、analysis 2500、decision 1500、guidance 1000） | [_helpers.py L1101-L1172](../../researchclaw/pipeline/_helpers.py#L1101-L1172) |
| `LLMClient` 请求体只有 `model/messages/temperature/max_tokens/response_format`：不数输入 token，`max_tokens` 只限输出 | [client.py L700-L747](../../researchclaw/llm/client.py#L700-L747) |
| `LLMClient` 不发 `tools/tool_choice`；工具由框架确定性执行或外部 agent 提供 | 同上；[invoker.py](../../researchclaw/tools/invoker.py) |

**关键约束**：

1. 全量聊天历史必须保留在磁盘（`hitl/chat_stage_NN.jsonl`），压缩只作用于**单次请求 payload**。
2. 不新增 LLM 调用：摘要必须是抽取式的，否则每轮多一次计费与失败面。
3. 既有 `ChatSession()` / `build_stage_context(...)` 调用方零改动，新能力必须可选。
4. 裸 API 不返回可靠 token 计数，字符预算是当前唯一不引入 tokenizer 依赖的可行口径。

## 2. 外部证据

| # | 来源 | 关键结论 | 本批借用 | 等级 |
|---|---|---|---|---|
| E1 | [Anthropic Engineering — Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)（2025-09） | 上下文是有限资源；长任务应使用 **compaction**（压缩历史）与外部笔记，而不是无限追加 | 请求时压缩 + 磁盘全量历史 | T2，摘要级 |
| E2 | [Chroma Research — Context Rot](https://research.trychroma.com/context-rot)（2025-07） | 输入变长本身会降低模型在简单任务上的表现；干扰项加剧退化 | 设总预算上限，而不是「能塞就塞」 | T3，摘要级、未回原文 |
| E3 | [LangChain — How to trim messages](https://python.langchain.com/docs/how_to/trim_messages/) | 业界通用形态 = 保留 system + 从尾部保留最近轮 + 超限插入省略标记 | 复用 `_trim_chat_history` 的滑动窗口 | T2 |

> 降级链：E1/E3 官方文档可直接访问；E2 未回原文，仅作方向性佐证，不参与任何数值判据。

## 3. 综合分析

1. **压缩器已经写好，缺的是接线**（T1）：`ContextManager` 的预算、摘要、滑动窗口三件套齐全，本批只补一个「对已构造 messages 压缩」的入口并接进 ChatSession。[★★★★★]
2. **压缩应发生在请求时而非写入时**（E1）：全量历史是审计与恢复的真值源；压缩后写盘会不可逆丢信息。[★★★★★]
3. **抽取式摘要优于 LLM 摘要**（本仓约束）：管线已在运行中，HITL 每轮再加一次摘要调用会放大延迟与失败面；`summarize_artifact` 已按结构/关键词抽行。[★★★★☆]
4. **字符预算不是 token 预算**（E3）：与 provider tokenizer 有偏差，但方向正确且零依赖；偏差留给未决项 U-1。[★★★★☆]

## 4. 未决项

- **U-1 token 级预算**
  - 判据：压缩后请求的实测输入 token 与字符预算偏差 ≤ 20%，或接入 provider 的 token 计数接口
  - 触发条件：出现 ≥1 次因输入超窗导致的上游 4xx
  - 当前倾向：维持字符预算（24000），不引入 tokenizer 依赖
  - 证据等级：E3

- **U-2 管线 stage prompt 复用压缩器**
  - 判据：`_build_context_preamble` 的硬截断被 `summarize_artifact` 替换且 stage 回归全绿
  - 触发条件：出现 stage prompt 超窗或截断导致的质量问题（≥1 次可复现）
  - 当前倾向：本批不动；23 个 stage 的无状态 prompt 是独立架构面
  - 证据等级：E3
