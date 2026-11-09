---
id: arc-b-station-endpoint-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-09
depends: [arc-b-station-endpoint-RESEARCH]
upstream: arc-b-station-endpoint-RESEARCH
---

# 设计：B 站端点接入的最小改动面

## 1. 不变量

1. **默认行为零变化**：不设 b-station 为默认 provider；live 测试默认 skip。
2. **密钥纪律**：引擎不校验 key，框架侧用占位串（`local-halogen`），沿运维文档口径。
3. **env 注入通用化**：`env_extra` 不绑死 Anthropic 变量名，任何 CLI 子进程变量皆可注入。
4. **思考模型兼容**：`reasoning_content` 回退只发生在 content 为空时，正常响应零影响。

## 2. 改动面

| 文件 | 改动 |
|---|---|
| `researchclaw/llm/__init__.py` | preset +2：`b-station`（`…:18081/v1`）、`b-station-anthropic`（`…:18081` + adapter） |
| `researchclaw/cli.py` | choice "11"、`_PROVIDER_URLS`、`_PROVIDER_MODELS`（fallback 空）、b-station next-steps |
| `researchclaw/config.py` | `CliAgentConfig.env_extra: tuple[tuple[str,str],…]` + yaml mapping 解析 |
| `researchclaw/experiment/code_agent.py` | `_CliAgentBase` 注入 `env_extra`；`_run_subprocess` 合并 env；factory 两处透传 |
| `researchclaw/llm/client.py` | `_parse_chat_completions_response`：content 空 → 回退 `reasoning_content` |
| `config.researchclaw.example.yaml` | llm B 站 双 wire 注释段 + cli_agent env_extra 注释段 |
| `tests/test_b-station_provider.py`（新） | preset/wiring/URL/工厂/CLI 菜单/init 生成/思考回退/env 注入 + live（opt-in + 探测跳过） |

## 3. 测试策略

- **离线**：preset 断言、`from_rc_config`、`_raw_call` URL 捕获（双 wire）、`cmd_init` 生成并 `yaml.safe_load` 解析、env_extra 子进程注入（spawn `python -c` 读环境变量）、思考回退 3 用例（空 content 回退 / 正常不动 / 双空保持空）。
- **在线（opt-in）**：`ARC_BSTATION_LIVE=1` 且 18081 可达（socket 探测 1.5s，失败 skip）；双 wire 各 1 冒烟，`max_tokens=512`（给 thinking 留预算）。

## 4. 回滚

单提交 revert；preset 与配置均为增量，无迁移。
