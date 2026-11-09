---
id: arc-b-station-live-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-09
depends: [arc-b-station-live-RESEARCH]
upstream: arc-b-station-live-RESEARCH
---

# 设计：live 用例矩阵与断言策略

## 1. 断言策略

1. **结构性断言优先**：思考型模型输出可变，不断言精确文本；断言"非空 / 含关键数字 / JSON 可解析 / 用量 > 0"。
2. **1M 用声明验证**：`/health` 的 `context` 字段是端点自述，避免烧 15 分钟 prefill 换一个弱结论。
3. **opt-in 与可达性双闸**：`ARC_BSTATION_LIVE=1` 且 socket 探测 18081 成功才运行；CI 不依赖隧道。
4. **思考预算**：live 调用统一 `max_tokens=512`（1M 档上限 16384），避免 thinking 吃光预算。

## 2. 用例矩阵

| 用例 | wire | 断言 |
|---|---|---|
| `test_health_reports_1m_context_and_both_wires` | HTTP | `context=1048576`、双 wire 在 `endpoints`、`capability_probe=ok` |
| `test_json_mode_returns_parseable_json` | OpenAI | `json_mode=True` 返回可解析 JSON 且 `status=ok` |
| `test_system_prompt_is_respected` | OpenAI | system 指令生效（2+2 → 含 4） |
| `test_multi_turn_context_recall` | OpenAI | 三轮对话后仍记得 42 |
| `test_token_usage_is_reported` | OpenAI | prompt/completion/total > 0；model 回显 qwen |
| `test_anthropic_wire_reports_usage` | Anthropic | content 非空；prompt/completion > 0（含 cache） |
| `test_preflight_reports_ok` | OpenAI | `preflight() == True` |

## 3. 计费修复

`anthropic_adapter` 的 usage 汇总改为：

```
prompt_tokens = input_tokens + cache_read_input_tokens + cache_creation_input_tokens
total_tokens  = prompt_tokens + output_tokens
```

离线用例固定 `input=0 / cache_read=56 / output=29`，断言 `prompt=56 / total=85`。

## 4. 影响面

- 仅 `researchclaw/llm/anthropic_adapter.py` 与测试文件。
- 对非缓存命中的 Anthropic 响应：cache 字段缺省 0，行为不变。
- `cost_tracker` 自动受益，无需改动。
