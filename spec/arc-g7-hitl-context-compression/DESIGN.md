---
id: arc-g7-hitl-context-compression-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-g7-hitl-context-compression-RESEARCH]
upstream: arc-master-roadmap
---

# 设计：HITL 上下文压缩接线（P-175）

## 1. 决策表

| ID | 决策 | 被拒替代 | 理由与代价 |
|---|---|---|---|
| D-1 | 接入点只在 HITL 层（`ChatSession` / `CollaborationSession` / `build_stage_context`） | 同时改 23 个 stage 的无状态 prompt | 管线 stage 是另一套架构面；同批改动会把回归面从 HITL 扩到全管线。代价：管线仍用字符硬截断（登记 U-2） |
| D-2 | 压缩发生在**请求时**，磁盘保留全量历史 | 写盘前压缩 / 覆盖消息列表 | 压缩写盘不可逆；审计与 `ChatSession.load()` 需要原文。代价：每轮重复计算，量级为 O(消息数) |
| D-3 | system 消息优先保留；仅当 system 自身超预算时按条均分并抽取摘要 | 与历史一起按比例裁剪 | system 携带阶段产物与指令，被裁会直接改变任务语义。代价：system 摘要含 stats 头，单条可能略超均分额 |
| D-4 | 聊天历史用滑动窗口（从尾部向前）+ `[N earlier messages omitted for context limit]` | 按时间等距抽样 | 最近轮决定当前意图；抽样会留下不连续对话。代价：早期轮次在请求中不可见（磁盘仍可查） |
| D-5 | 大产物与 guidance 用抽取式 `summarize_artifact()`（不调 LLM） | LLM 摘要 | 每轮多一次计费/延迟/失败面，且离线不可用。代价：摘要质量低于生成式摘要（保留标题/关键词行/首行） |
| D-6 | 新参数全部可选（`context_manager=None`），`None` 时逐字节走旧逻辑 | 强制全局启用 | 既有调用方与测试零改动；`CollaborationSession.initialize` 负责显式接线。代价：直接 `ChatSession()` 的用户默认不享受压缩 |

## 2. 算法

```
compress_messages(messages, budget=None):
    limit ← budget ?? max_total_chars        # 默认 24000
    system ← messages[role == "system"]
    convo  ← messages[role != "system"]
    system_chars ← Σ len(system.content)
    if system 非空 and system_chars ≥ limit:
        per ← max(1, limit / len(system))
        return [ {role: system, content: summarize_artifact(content, per)} for each ]
    return system + _trim_chat_history(convo, max(0, limit - system_chars))

_trim_chat_history(convo, budget):
    if Σ len(convo) ≤ budget: return convo
    从尾部向前累加，超出 budget 即停
    若有丢弃：在最前插入 {role: system, content: "[N earlier messages omitted for context limit]"}
```

`build_stage_context` 的压缩分支：

```
for 每个 artifact:
    content ← read()
    if len(content) > 3000:
        content ← context_manager ? summarize_artifact(content, 3000)
                                  : content[:3000] + "\n...[truncated]"
guidance 超 CONTEXT_BUDGETS["guidance"]（1000）→ summarize_artifact(guidance, 1000)
```

`CollaborationSession.initialize`：构造 `ContextManager(run_dir)` → 赋给 `chat.context_manager` → 同一实例传入 `build_stage_context`。

## 3. 不变式

| ID | 不变式 |
|---|---|
| J-1 | 输入含 system 时，压缩结果首条为 system（顺序与条数不变，除非 system 自身超预算） |
| J-2 | 非 system 部分总字符 ≤ `max(0, budget - system_chars)`；system 被摘要时每条 = `summarize_artifact(..., per)` 的输出（含 stats 头，允许略超 `per`） |
| J-3 | 预算允许时保留最后一条消息；丢弃时恰插入 1 条省略提示 |
| J-4 | `context_manager=None` 时 `build_stage_context` 与 `get_ai_response` 的行为与 P-175 前一致 |
| J-5 | 压缩不修改 `ChatSession.messages`，只影响当次 `llm_client.chat()` 的 payload |

## 4. 错误语义

| 场景 | 行为 |
|---|---|
| `messages` 为空 | 返回 `[]`，不抛异常 |
| `budget` 为 0 或负数 | 视为 0；system 摘要按 `per = max(1, ...)` 保底，历史返回空 |
| 单条消息本身超预算 | 该条被丢弃（历史）或摘要（system），不抛异常 |
| 产物文件读取失败 | 沿用既有 `[Error reading file]`，不影响其余产物 |
| `context_manager` 未接线 | 走旧路径，无压缩 |

## 5. 职责边界

- **职责外**：token 精确计数与 provider 侧窗口协商（U-1）；stage prompt 架构（U-2）；工具调用协议（裸 API 不发 `tools`，由 `ToolInvoker`/外部 agent 承担）。
- **能力边界**：抽取式摘要不能理解语义，只能按结构/关键词保行；对无标题、无关键词的长文本，摘要接近「首尾各半」。
