---
id: arc-context-governance-RESEARCH
type: design
version: 1.0
status: draft
date: 2026-11-25
depends: [arc-g7-hitl-context-compression-RESEARCH]
upstream: arc-master-roadmap
---

# 调研：上下文治理的三个遗留面（U-1 / U-2 / P3-2）

> **范围**：为 P-175 登记的三处边界寻找社区与学术解法：① 字符预算 → token 预算（U-1）；② 管线 23 stage 的 `_build_context_preamble` 硬截断（U-2）；③ 「web dialog 绕过压缩」（P3-2）。
> **不在本批**：不改代码；不引入模型依赖；不承诺质量提升，只约束形态与可核验读数。
> **状态**：Step 1 调研 + Step 2 自查（单视角，RULE-4），未进入设计与实施。

## 1. 本仓现状（T1，回原文）

| # | 事实 | 证据 |
|---|---|---|
| F-1 | 预算全部是字符：`chat_system 4000 / chat_history 8000 / stage_output 6000 / cross_stage 3000 / guidance 1000`，总量 24000 字符 | [context_manager.py L22-L28](../../researchclaw/hitl/context_manager.py#L22-L28) |
| F-2 | 压缩入口只按 `len(content)` 计费，无 token 概念 | [context_manager.py L117-L150](../../researchclaw/hitl/context_manager.py#L117-L150) |
| F-3 | 核心依赖与 extras 均无 tokenizer（无 `tiktoken`、无 `tokenizers`、无 `transformers`） | [pyproject.toml L6-L41](../../pyproject.toml#L6-L41) |
| F-4 | 配置里没有 `context_window` / `max_context_tokens` 字段（全仓仅 vendor 的 auto_prover 有 `max_context_tokens`） | 全仓 grep 唯一命中 `researchclaw/vendor/auto_prover/datatypes/config.py` |
| F-5 | 请求体只发 `model/messages/temperature/max_tokens/response_format`（或 `max_completion_tokens`），不声明上下文窗口 | [client.py L700-L712](../../researchclaw/llm/client.py#L700-L712) |
| F-6 | 供应商返回的 `prompt_tokens` 已落盘到 `cost_log.jsonl`（每条记录含 prompt/completion/total） | [client.py L873-L875](../../researchclaw/llm/client.py#L873-L875)、[cost_tracker.py L45-L49](../../researchclaw/cost_tracker.py#L45-L49)、[L234](../../researchclaw/cost_tracker.py#L234) |
| F-7 | 400 默认**不重试**（仅当 body 含 rate limit/overloaded 等瞬时词才重试）；上下文超窗属于「genuine bad request」，直接抛出 | [client.py L591-L606](../../researchclaw/llm/client.py#L591-L606) |
| F-8 | 管线 prompt 按字段**只留头部**：goal/hypotheses/synthesis 2200、exp_plan 2000、analysis 2500、decision 1500、guidance 1000 字符 | [_helpers.py L1121-L1141](../../researchclaw/pipeline/_helpers.py#L1121-L1141)、[L1172](../../researchclaw/pipeline/_helpers.py#L1172) |
| F-9 | 全仓约 30 处 `llm.chat()` 直连；HITL 只覆盖 `ChatSession` 一处 | grep `llm.chat(`：`agents/`、`pipeline/stage_impls/`、`hitl/workshops/` 等 |
| F-10 | **修正 P-175 的 P3-2 断言**：`server/dialog` 的 web dialog 是**规则式**应答，从不调用 LLM；`ChatSession.get_context()` 是死代码 | [router.py L145-L166](../../researchclaw/server/dialog/router.py#L145-L166)、[session.py L47-L52](../../researchclaw/server/dialog/session.py#L47-L52) |
| F-11 | 真实旁路在 HITL workshops：paper 生成按 `outline[:2000]` / `context[:2000]`、`polish_section` 直接送整节正文 | [paper.py L98-L111](../../researchclaw/hitl/workshops/paper.py#L98-L111) |
| F-12 | 场景是中文 topic + 英文 prompt 混合（G7 现场 topic 为中文），CJK 与 ASCII 的 chars/token 差异可达数倍 | [arc-g7-run-id-stability/RESEARCH.md §1](../arc-g7-run-id-stability/RESEARCH.md) |

## 2. 外部方案

### 2.1 token 计数（对应 U-1）

| # | 来源 | 机制 | 层 | 本仓可用性 |
|---|---|---|---|---|
| E1 | [Anthropic — Token counting](https://docs.anthropic.com/en/docs/build-with-claude/token-counting) | `POST /v1/messages/count_tokens`，接受与创建消息相同的结构（system/tools/images/PDF），**免费**、独立限流；官方明示结果**是估计值**，可能含系统优化 token | T1 | 仅 anthropic adapter 路径可用；需一次额外 HTTP |
| E2 | [llama.cpp server README](http://raw.githubusercontent.com/ggml-org/llama.cpp/HEAD/tools/server/README.md) | `POST /tokenize`，入参 `content`，可选 `add_special` / `with_pieces` | T1 | 若 B 站模型服务是 llama.cpp 系，可**本地精确**计数、零新增依赖 |
| E3 | [vLLM — OpenAI-Compatible Server](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html) | 自定义 `Tokenizer API (/tokenize, /detokenize)`，适用任何带 tokenizer 的模型 | T1 | 同上；SGLang/NIM 亦提供 `/tokenize` |
| E4 | [LiteLLM — Token Counting](https://docs.litellm.ai/docs/count_tokens) / [Unified tokenization](https://docs.litellm.ai/docs/tokenize) | `litellm.acount_tokens()`：**优先调供应商计数 API**，否则退回本地 tokenizer（默认 tiktoken） | T2 | 社区已把「精确 API → 本地 tokenizer → 估算」写成降级链，可直接照搬形态 |
| E5 | [LlamaIndex ChatMemoryBuffer](https://developers.llamaindex.ai/python/framework/module_guides/deploying/agents/memory/) | `token_limit` + `tokenizer_fn` 注入；默认 tiktoken，可换成任意 `str -> list` 可调用 | T1 | 与我们 `ContextManager(budget)` 形态同构，只差一个 `tokenizer_fn` 参数 |
| E6 | [LangChain trim_messages](https://python.langchain.com/docs/how_to/trim_messages/) | `max_tokens` + `token_counter`（函数或模型）+ `strategy="last"` + `include_system=True` + `start_on` / `ends_on` | T1 | 与我们滑动窗口同构；其「结果必须是合法对话序列」约束值得照搬（tool 消息配对） |
| E7 | [Mason AI Lab — Chinese token efficiency](https://masonailab.com/en/insights/token-efficiency/) | cl100k 下中文平均为英文的 **2.08×** token（测试集特定） | T3 | 说明「4 字符≈1 token」对中文严重低估；数字未回原文，仅作方向 |
| E8 | [阿里云 — tiktoken 中文压缩率实证](https://developer.aliyun.com/article/1715500) | 中文系数约 1.16（与经验公式 1.6 差 20.9%） | T3 | 与 E7 口径不同，进一步说明「单一系数不可移植」 |

### 2.2 压缩策略（对应 U-2）

| # | 来源 | 机制 | 层 | 代价 |
|---|---|---|---|---|
| E9 | [OpenRouter — Message Transforms](https://openrouter.ai/docs/guides/features/message-transforms) | `context-compression` 插件：**从中间**删除/截断消息直到装进窗口；消息数超限时「前半一半 + 后半一半」；≤8k 窗口默认开启；官方理由直接引用 Lost in the Middle | T1 | 无损？不，是有损；但保头保尾 |
| E10 | [Lost in the Middle (arXiv:2307.03172)](https://arxiv.org/pdf/2307.03172) | 相关信息位于**开头或结尾**时表现最好，位于中部显著退化，长上下文模型亦然 | T1 | 学术依据：只留头（现状 F-8）会系统性丢掉「结论/总结」段 |
| E11 | [Anthropic — Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | 三杠杆：compaction（接近上限时摘要并重开）、structured note-taking（外部笔记）、sub-agent（隔离子上下文）；只把摘要回传主上下文 | T2 | compaction 需额外 LLM 调用；note-taking 需 agent 配合 |
| E12 | [Claude — Context editing / compaction](https://platform.claude.com/docs/en/build-with-claude/context-editing) | 超阈值注入摘要请求 → 用 `<summary>` 替换整段历史 → 从 ~2–3k token 继续 | T1 | 每轮多一次生成调用与失败面 |
| E13 | [LLMLingua-2 (ACL 2024 Findings)](https://aclanthology.org/2024.findings-acl.57/) | 任务无关的 token 级压缩，压缩率 2×–5×，端到端延迟 1.6×–2.9× 加速；比前代快 3×–6× | T1 | 需外挂压缩模型（本地/远程），与「不新增模型依赖」冲突 |
| E14 | [LangChain ConversationSummaryBufferMemory 形态](https://python.langchain.com/docs/how_to/trim_messages/) | 窗口内保留原文、窗口外折叠为滚动摘要 | T1 | 摘要仍需 LLM，或退回抽取式 |

### 2.3 超窗兜底（U-1/U-2 的共同风险）

| # | 来源 | 机制 | 层 |
|---|---|---|---|
| E15 | [LiteLLM — Reliability / Context Window Fallbacks](https://docs.litellm.ai/docs/proxy/reliability) | `context_window_fallbacks=[{"model": ["bigger-model"]}]`：撞窗时自动换更大窗口模型 | T1 |
| E16 | [FastMetal — context_length_exceeded](https://fastmetal.ai/blog/context-length-exceeded) / [PolarGrid — Context management](https://polargrid.mintlify.app/guides/context-management) | 400 超窗**原样重试必然再失败**；四条出路：降 `max_tokens`、丢旧历史、摘要、换更大窗口模型 | T3 |
| E17 | [Claude — handling stop reasons](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons) | 新增 `model_context_window_exceeded` stop reason，允许请求满额输出而不必预知输入长度 | T1 |

## 3. 综合分析

1. **U-1 的正确形态是「分层 + 可替换计数器」，不是「换一个更准的常数」**。LiteLLM（E4）与 LlamaIndex（E5）都把「计数」抽象成可注入函数，默认本地 tokenizer，能拿到精确 API 就用精确值。本仓零 tokenizer 依赖（F-3），因此合理顺序是：**校准字符启发式（默认）→ 本地 `/tokenize`（若端点支持）→ 观测回填校准（用 F-6 的 `prompt_tokens`）**。[★★★★☆]
2. **中文场景禁止用 4 chars/token**。E7/E8 两个 T3 源方向一致（中文 token 密度显著更高，系数在 1.16–2.08 区间且依赖测试集），说明单一系数误差可达 2× 以上；必须按脚本分档（ASCII / CJK / 混合）并留 15% 安全边际。[★★★★☆]
3. **U-2 的硬截断问题不是「截多少」，而是「只截尾」**。E9/E10 一致指向保头保尾：现状 `content[:2200]`（F-8）会丢掉 analysis/paper 的结论段，而结论恰是下游 stage 最需要的。最小修复 = 预算内「头部 + 结构行 + 尾部」，无需 LLM。[★★★★★]
4. **超窗必须有一次「降预算重试」**。F-7 显示当前 400 直接抛；E15/E16 说明社区把它当可恢复信号处理（降级或换模型）。不处理会让长 guidance 或大 analysis 直接终止 run。[★★★★★]
5. **LLMLingua 类方案不划算**（E13）：2×–5× 压缩确实强，但要外挂模型、引入离线失败面，与本仓「确定性、可离线、零新依赖」的取向冲突；登记为远端选项即可。[★★★☆☆]
6. **P3-2 需要更正，而不是修复**（F-10/F-11）：web dialog 没有 LLM 调用，删掉这条边界；真实的旁路是 HITL workshops 与 30 处 stage 直连（F-9），应另立「入口统一」议题，而不是塞进 P-175 的收尾。[★★★★★]

## 4. 方案对比（供裁决）

| 方案 | 内容 | 改动面 | 风险 | 建议 |
|---|---|---|---|---|
| **A 最小** | U-1 校准字符估算器（脚本分档 + 15% 边际，接口留 `tokenizer_fn`）；U-2 头+结构+尾替换 `[:N]`；超窗 400 捕获后降 25% 预算重试一次 | `ContextManager` + `_helpers` + `client` 各一小块 | 中低：不改变成功路径行为，只在超窗时多一次尝试 | **推荐先做** |
| **B 中** | A + 端点能力探测（`/tokenize` 或 `count_tokens`）+ 结果缓存 + 失败回退 A | 新增 `llm/token_counter.py` + 探测缓存 | 中：多一次探测请求；需处理端点不支持 | 第二批（拿到现场端点后） |
| **C 大** | B + 把压缩下沉到 `LLMClient.chat()` 统一入口，覆盖全部 ~30 处调用 | 全局请求路径 | 高：改变所有 stage 的 prompt 形态，回归面最大 | 不建议现在做 |
| D 备选 | 接入 LLMLingua-2 本地模型 | 新模型依赖 | 高：离线/体积/许可证 | 仅登记 |

## 5. 未决项（四元块）

| ID | 判据 | 触发条件 | 当前倾向 | 证据等级 |
|---|---|---|---|---|
| U-176-1 B 站端点是否支持 `/tokenize` | `curl -X POST <base>/tokenize -d '{"content":"test"}'` 返回 200 且含 tokens | 下一批开始前一次性探测 | 大概率支持（llama.cpp/vLLM 系）；不支持则只用 L0 | 待核（E2/E3 仅证明存在性） |
| U-176-2 校准系数的可接受误差 | 用 `cost_log.jsonl` 的 `prompt_tokens` 对估算做回测，MAPE ≤ 20% | 有 ≥30 条同模型记录后 | 先按 ASCII 4.0 / CJK 1.2 起步，回测后按模型落一份系数表 | 待核 |
| U-176-3 统一入口（全 stage）何时做 | C 方案的回归面收敛到可接受（新增用例覆盖 ≥ 主要 stage 的 prompt 组装） | 出现 ≥1 次现场超窗/截断导致的质量事故 | 暂不做，先 A 再 B | E3 |

## 6. 来源与分级

- **T1（一手，已读原文）**：E1、E2、E3、E5、E6、E9、E10、E12、E13、E15、E17。
- **T2（官方二手）**：E4、E11、E14。
- **T3（社区/转述，仅作方向）**：E7、E8、E16。
- **降级链**：`WebSearch → 官方文档直读（WebFetch）→ 未取到原文的条目一律标 T3`。E7/E8 的具体系数未回原始报告，不参与任何门禁判据。

## 7. Review（Step 2 自查）

> **[自查·单视角]（RULE-4）**：本文件由同一 agent 编写与复核，未引入异构第二会话（RULE-5）。

| 检查 | 结果 |
|---|---|
| 本仓事实逐条有文件/行锚点 | 12 条（F-1..F-12），其中 F-10/F-11 为本次新增的**反向证据**（推翻 P-175 的 P3-2 表述） |
| 外部结论 ≥2 独立来源 | U-1：E4/E5/E6；U-2：E9/E10；兜底：E15/E16 |
| 未把 T3 数字当判据 | E7/E8/E16 均标 T3 且注明「不参与判据」 |
| 归因扭曲检查 | 未把「社区都在做 middle-out」写成「middle-out 必然更好」；E9 明示「perfect recall 不适用时才有用」 |
| 边界声明 | §5 三项未决全部带触发条件；§4 明确不建议现在做 C |

## 8. 诚实边界

1. 本文件**零代码改动**，不改变 P-175 已合并行为。
2. 未实测任何端点：E2/E3 只证明「这类服务提供 `/tokenize`」，不证明 B 站当前端点具备。
3. E7/E8/E16 为转述级读数，可能随测试集偏移。
4. 「压缩改善质量」未被任何本仓实验验证；本文件只主张「不丢结论段 + 不超窗」两个可机械核验的目标。
