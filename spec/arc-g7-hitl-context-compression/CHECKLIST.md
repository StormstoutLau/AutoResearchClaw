---
id: arc-g7-hitl-context-compression-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-25
depends: [arc-g7-hitl-context-compression-IMPLEMENTATION, arc-g7-hitl-context-compression-DESIGN]
upstream: arc-master-roadmap
---

# 审查验收 Checklist：HITL 上下文压缩接线（P-175）

> **计数**：**26 项 = 文档 4 + 功能 6 + 接口 3 + 不变式 5 + 错误 3 + 测试与门禁 5**。
> **状态**：24 通过 + 2 待回填（C-1 两轮 CI / C-2 门禁读数在 §9 逐项回填）。

## 1. 文档一致性

| 检查项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| D-1 RESEARCH 回原文 | RESEARCH v1.0 | 本仓事实 ≥8 条带文件/行锚点；外部来源标 T2/T3 | ✅ | RESEARCH §1 表 10 行、§2 表 3 行 |
| D-2 DESIGN 覆盖实现 | 四文档 | D-1..D-6 均有落点 | ✅ | D-1↔collaboration/chat；D-3/D-4↔`compress_messages`；D-5↔`summarize_artifact`；D-6↔默认参数 |
| D-3 IMPLEMENTATION 源码锚点 | 四文档 | ≥5 锚点且行号可达 | ✅ | IMPLEMENTATION §1 表 8 行 |
| D-4 术语一致 | 四文档 | 压缩/摘要/预算/滑动窗口同义 | ✅ | 四文档一致；「摘要」始终指抽取式 `summarize_artifact` |

## 2. 功能验收

| 验收项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| F-1 `compress_messages` 保序 | DESIGN §2 | 首条 system、末条最近轮、含省略提示 | ✅ | `test_compress_messages_keeps_system_and_recent_turns` |
| F-2 预算约束与 DR-1 下界 | DESIGN §3 J-2 | 总长 ≤ 预算 + 提示开销；`max_chars=1` 不返回全文 | ✅ | 同用例 `sum ≤ 700`；`half = max(1, ...)` [L187](../../researchclaw/hitl/context_manager.py#L187) |
| F-3 ChatSession 请求前压缩 | DESIGN D-2 | 传入 LLM 的 messages 已压缩 | ✅ | `test_chat_session_compresses_before_llm_call` |
| F-4 大产物抽取摘要 | DESIGN D-5 | 含标题与 `key lines` 统计头，长度受限 | ✅ | `test_build_stage_context_summarizes_large_artifact`；`test_summarize_artifact_is_extractive_and_bounded` |
| F-5 guidance 超预算摘要 | DESIGN §2 | >1000 字符走摘要 | ✅ | [chat.py L231-L237](../../researchclaw/hitl/chat.py#L231-L237)；`CONTEXT_BUDGETS["guidance"]=1000` |
| F-6 默认零行为变化 | DESIGN D-6 | `context_manager=None` 走旧分支 | ✅ | 47 条既有 HITL 用例全绿（52−5） |

## 3. 接口验收

| 验收项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| I-1 新参数可选 | DESIGN D-6 | `build_stage_context(..., *, context_manager=None)` | ✅ | [chat.py L189-L190](../../researchclaw/hitl/chat.py#L189-L190) |
| I-2 `budget` 关键字可选 | DESIGN §2 | `compress_messages(messages, *, budget=None)` | ✅ | [context_manager.py L117-L121](../../researchclaw/hitl/context_manager.py#L117-L121) |
| I-3 返回形态 | DESIGN §2 | `list[dict[str, str]]`，role 保持 system/user/assistant | ✅ | `test_chat_session_compresses_before_llm_call` 断言 `messages[0]["role"]=="system"` |

## 4. 不变式

| 不变式 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| J-1 system 在首位 | DESIGN §3 | 压缩后首条 system | ✅ | F-1/F-3 用例断言 |
| J-2 非 system ≤ 剩余预算 | DESIGN §3 | `sum ≤ budget - system_chars` | ✅ | F-1/F-2 读数 |
| J-3 保留最后一条 + 单条提示 | DESIGN §3 | 末条 `a19`；`omitted` 恰 1 条 | ✅ | F-1 用例 |
| J-4 `None` 时行为不变 | DESIGN §3 | 既有 47 用例全绿 | ✅ | 52 passed 全量 |
| J-5 不改 `self.messages` | DESIGN §3 | 压缩仅作用于 payload | ✅ | `get_ai_response` 只在局部变量上压缩 [L134-L136](../../researchclaw/hitl/chat.py#L134-L136) |

## 5. 错误处理

| 场景 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| E-1 空列表 | DESIGN §4 | 返回 `[]` 不抛 | ✅ | `compress_messages` [L129-L130](../../researchclaw/hitl/context_manager.py#L129-L130) |
| E-2 budget ≤ 0 | DESIGN §4 | 视为 0，system 有下限、历史为空 | ✅ | `max(0, int(budget))` + `per = max(1, ...)` |
| E-3 文件读取失败 | DESIGN §4 | 既有 `[Error reading file]` 不变 | ✅ | 既有分支保留 [L223-L224](../../researchclaw/hitl/chat.py#L223-L224) |

## 6. 测试与门禁

| 项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| T-1 新用例 | CHECKLIST §2-§5 | 5/5 通过 | ✅ | `tests/test_hitl_context_compression.py` 5 passed |
| T-2 定向回归 | 新用例 + `test_hitl_collaboration.py` | 52 passed | ✅ | 读数 52 passed |
| T-3 HITL 全量 | `pytest tests -k hitl` | 除既有环境态外全绿 | ✅ | 253 passed / 1 failed（`test_shell_hooks`，`WinError 193`，既有环境态）/ 57 skipped |
| C-1 两轮 CI | 3.11–3.14 矩阵 | 两轮全 success | ⏳ 待回填 | 待 PR 创建后回填 |
| C-2 门禁链 | 6+4 道 | 全通过 | ⏳ 待回填 | §9 |

## 7. 诚实边界

1. 字符预算不是 token 预算：与 provider tokenizer 存在偏差（U-1）。
2. 抽取式摘要不理解语义，只按标题/关键词/首行保行；无结构长文本退化为首尾各半。
3. 管线 23 个 stage 的 prompt 未接入压缩器，仍用 `_build_context_preamble` 硬截断（U-2）。
4. `ContextManager.build_context()` 仍未接线，本批只用其摘要与滑动窗口两个方法。
5. 未做真实模型的长对话 A/B（上下文压缩质量需人工评阅，登记为后续）。

## 8. 批次自审（ADD）

| 项 | 级别 | 内容 | 处置 |
|---|---|---|---|
| P3-1 | low | `summarize_artifact` 的 stats 头使单条 system 摘要可能略超均分额 | 已在 J-2 显式记录；不额外裁剪 stats（否则失去「压缩了多少」的可观测性） |
| P3-2 | medium | `compress_messages` 只在 ChatSession 调用点生效；其它直接调用 `llm_client.chat` 的路径（如 web dialog）不受约束 | 本批不改 web dialog；登记为后续统一入口候选 |
| P3-3 | low | 被丢弃的早期轮次在请求中不可见，模型可能重复提问 | 省略提示已显式说明；全量历史可从 `hitl/chat_stage_NN.jsonl` 恢复 |

## 9. 门禁读数

| 门禁 | 读数 |
|---|---|
| `dc_validator` | 4 文件 / **0 违规** |
| `step-gate` | **5/5 pass**（research → design → implement → verify → finalize） |
| `verify-anchor` | **10 真实 / 0 硬性 / 0 软性** |
| `step_enforce` | `mode=batch pid=P-175 digest_bound=1` |
| `pre-commit` | **10/10 Passed** |
| 两轮 CI | 待跑 |
