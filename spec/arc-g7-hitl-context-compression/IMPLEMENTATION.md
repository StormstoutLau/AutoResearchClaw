---
id: arc-g7-hitl-context-compression-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-g7-hitl-context-compression-DESIGN, arc-g7-hitl-context-compression-RESEARCH]
upstream: arc-master-roadmap
---

# 实施：HITL 上下文压缩接线（P-175）

## 1. 交付锚点

| 交付 | 文件 | 符号/行 | 行为 |
|---|---|---|---|
| 压缩入口 | [context_manager.py](../../researchclaw/hitl/context_manager.py) | `compress_messages` [L117-L150](../../researchclaw/hitl/context_manager.py#L117-L150) | 保留 system；历史按剩余预算滑动窗口；system 超预算均分摘要 |
| 摘要下界保护（DR-1） | 同上 | `summarize_artifact` [L187](../../researchclaw/hitl/context_manager.py#L187) | `half = max(1, max_chars // 2)`，避免 `max_chars < 2` 时 `summary[-0:]` 退化为全文 |
| ChatSession 字段 | [chat.py](../../researchclaw/hitl/chat.py) | `context_manager: Any = None` [L66](../../researchclaw/hitl/chat.py#L66) | 默认 `None`，既有构造零影响 |
| 请求前压缩 | 同上 | `get_ai_response` [L134-L136](../../researchclaw/hitl/chat.py#L134-L136) | `context_manager` 非空才压缩，压缩结果只进 payload |
| 产物摘要 | 同上 | `build_stage_context` [L189-L224](../../researchclaw/hitl/chat.py#L189-L224) | >3000 字符时优先 `summarize_artifact`，否则旧硬截断 |
| guidance 摘要 | 同上 | [L231-L237](../../researchclaw/hitl/chat.py#L231-L237) | 超 1000 字符用 `CONTEXT_BUDGETS["guidance"]` 摘要 |
| 自动接线 | [collaboration.py](../../researchclaw/hitl/collaboration.py) | `initialize` [L63-L69](../../researchclaw/hitl/collaboration.py#L63-L69) | 构造 `ContextManager(run_dir)` 并赋给 `chat.context_manager` |
| 验收用例 | [test_hitl_context_compression.py](../../tests/test_hitl_context_compression.py) | 5 用例 [L20-L97](../../tests/test_hitl_context_compression.py#L20-L97) | 摘要边界 / 压缩保序 / ChatSession 请求 / 阶段产物 / 接线 |

## 2. TDD 红 → 绿

1. **红**（E1，可重放）：在 `f8a00c8` 的临时 worktree 中放入新测试文件后运行，读数 **4 failed / 1 passed**：
   - `AttributeError: 'ContextManager' object has no attribute 'compress_messages'`
   - `TypeError: ChatSession.__init__() got an unexpected keyword argument 'context_manager'`
   - `TypeError: build_stage_context() got an unexpected keyword argument 'context_manager'`
   - `AttributeError: 'ChatSession' object has no attribute 'context_manager'`
   - 通过项 = `summarize_artifact` 既有行为（抽取式 + 有界），证明测试基线有效。
2. **绿**：实现后 `tests/test_hitl_context_compression.py + tests/test_hitl_collaboration.py` **52 passed**（5 新 + 47 既有）。
3. **回归**：`pytest tests -k hitl` → **253 passed / 1 failed / 57 skipped**；唯一失败为 `test_hitl_advanced.py::TestHookRegistry::test_shell_hooks`，读数 `[WinError 193] %1 不是有效的 Win32 应用程序`，属既有 Windows shell hook 环境态失败，与本批无关。

## 3. 派生需求

| ID | 派生需求 | 来源 | 处置 |
|---|---|---|---|
| DR-1 | `summarize_artifact` 在 `max_chars < 2` 时 `half` 取 0，`summary[-0:]` 会返回全文 | 实现 `compress_messages` 的 `per = max(1, ...)` 分支时发现 | 已改为 `max(1, max_chars // 2)`；Included in CHECKLIST F-2 |

## 4. 边界

- 不改 `researchclaw/llm/client.py`：请求体仍不含 `tools`，输入 token 仍不计数（U-1）。
- 不改 `_build_context_preamble`：管线 stage prompt 仍按字段字符硬截断（U-2）。
- 压缩只影响当次请求；`ChatSession.save()` 落盘的仍是全量消息。
- `ContextManager` 的 `build_context()`（面向未来重构的装配入口）本批未接线，仅复用其 `summarize_artifact` / `_trim_chat_history`。
