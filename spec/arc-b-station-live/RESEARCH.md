---
id: arc-b-station-live-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-09
depends: [arc-b-station-endpoint-IMPLEMENTATION]
upstream: arc-b-station-endpoint-IMPLEMENTATION
---

# 调研：B 站端点 live 覆盖扩展

> **前序**：P-007 只覆盖双 wire 的"能通"冒烟（2 用例）。本批补充能力级 live 用例，并用真实响应校准断言。

## 1. 端点实测（2026-11-09，隧道 18081）

| 探测 | 结果 |
|---|---|
| `GET /health` | `status=ok`、`model=halogen-qwen3.8-flash-next`、`context=1048576`、`capability_probe=ok`、`endpoints` 含 `/v1/chat/completions` 与 `/v1/messages` |
| JSON 模式（`response_format=json_object`） | HTTP 200，content 为 `{"status":"ok"}` |
| 多轮（user/assistant/user） | 正确回忆 `42` |
| 系统提示 | 生效 |
| Token 用量（OpenAI wire） | `prompt/completion/total` 均 > 0，`model` 回显 `halogen-qwen3.8-flash-next` |
| Token 用量（Anthropic wire） | **`input_tokens=0`，实际输入记在 `cache_read_input_tokens=56`** |

## 2. 由此确认的缺口

`anthropic_adapter` 只读 `input_tokens`，忽略 `cache_read_input_tokens` 与 `cache_creation_input_tokens`。halogen 在缓存命中时把整段输入计入 cache_read，导致：

- `LLMResponse.prompt_tokens` 为 0；
- 成本记账漏计输入侧（`cost_tracker` 按 prompt_tokens 计价）。

按 Anthropic usage 语义，可计费输入 = `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`。

## 3. 本批范围

- 新增 7 个 live 用例：`/health` 1M 声明、JSON 模式、系统提示、多轮回忆、OpenAI 用量、Anthropic 用量、preflight。
- 新增 1 个离线用例：cache 输入计入 prompt usage。
- 修 `anthropic_adapter` 的 usage 汇总。

## 4. 不在本批

- 1M 长上下文 needle（实测 prefill 成本高，改由 `/health` 声明 `context=1048576` 断言）。
- `/v1/responses` wire（框架当前只走 chat_completions / messages）。
