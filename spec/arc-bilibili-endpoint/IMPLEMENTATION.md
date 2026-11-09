---
id: arc-bilibili-endpoint-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-09
depends: [arc-bilibili-endpoint-DESIGN]
upstream: arc-bilibili-endpoint-DESIGN
---

# 实施记录：B站端点接入

## 1. 落点

| # | 改动 | 落点 |
|---|---|---|
| E-1 | preset `bilibili` / `bilibili-anthropic` | `researchclaw/llm/__init__.py` |
| E-2 | CLI choice "11" / URL / models / next-steps | `researchclaw/cli.py` |
| E-3 | `CliAgentConfig.env_extra` + 解析 | `researchclaw/config.py` |
| E-4 | CLI 子进程 env 注入（claude_code + codex） | `researchclaw/experiment/code_agent.py` |
| E-5 | `reasoning_content` 回退 | `researchclaw/llm/client.py::_parse_chat_completions_response` |
| E-6 | 示例配置（双 wire + cli_agent env_extra 注释段） | `config.researchclaw.example.yaml` |
| E-7 | 测试 20 用例（18 离线 + 2 live） | `tests/test_bilibili_provider.py` |

## 2. 验证

```bash
# V1 离线全套（18 用例）
python -m pytest tests/test_bilibili_provider.py -q

# V2 live 冒烟（隧道 18081 在线时）
$env:ARC_BILI_LIVE='1'; python -m pytest tests/test_bilibili_provider.py -q -k Live

# V3 LLM 回归
python -m pytest tests/test_rc_llm.py tests/test_anthropic.py tests/test_minimax_provider.py \
  tests/test_atlascloud_provider.py tests/test_cost_tracker.py tests/test_cli.py -q
```

## 3. 结果（2026-11-09 实测）

- V1：**18 passed, 2 skipped**（live 默认关）。
- V2：**隧道在线，2 passed**——OpenAI wire 与 Anthropic wire 均真实命中 B站 1M（`model=halogen-qwen3.8-flash-next`，答案非空）。
- V3：**105 passed, 4 skipped**——`reasoning_content` 回退零回归。
- Live 首跑曾失败：`max_tokens=16` 全耗于 thinking → content 空；由此发现并修复 E-5，并把 live 预算提至 512。

## 4. 未执行 / 边界

- B站端点不是 CI 依赖（隧道非稳态）；live 测试需 `ARC_BILI_LIVE=1` 且隧道在线。
- 18081 旧标签（GLM/DS4）已过期——如需 GLM/DS4 需先按运维文档 §7 重载并在 cc-switch 恢复标签。
- `codex` 路径同样获得 env 注入能力，但未做 B站专项验证（codex 走 OpenAI 协议，端点本身兼容，留待需要时验证）。
