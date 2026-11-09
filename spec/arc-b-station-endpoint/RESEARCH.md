---
id: arc-b-station-endpoint-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-09
depends: [arc-master-roadmap]
upstream: arc-master-roadmap
---

# 调研：B 站 LLM 端点与 Claude Code 接入

> **外部依据**：`D:\RPC\docs\2026-10-27_GLM1M_Qwen1M_启动与cc-switch接入.md`（2026-11-09 增补 §10）。
> **命名**：**B 站 = 三机推理集群（A/B/C）中的节点 B**（见 `D:\RPC\README.md` 拓扑图），与视频站无关；provider id 相应为 `b-station` / `b-station-anthropic`。
> **目标**：为 ARC/researchclaw 接入 B 站 LLM API 端点与 B 站 Claude Code，作为后续开发的测试基座。

## 1. 端点事实（引自运维文档，2026-11-09 口径）

| 项 | 值 |
|---|---|
| 服务 | B 站 halogen 0.18.18，无审查 Qwen3.8-Flash（`qwen38-flash-next-v2-abliterated.hgn`） |
| 上下文 | 1,048,576（YaRN 4x + int8 KV）；1M 档 `max_tok` 自适应 **16384** |
| 隧道 | 主控 `127.0.0.1:<TUNNEL_PORT>` → B 站 `127.0.0.1:8080`（cc-switch-tunnels.cmd 常驻）；`<ALT_TUNNEL_PORT>` 直连同目标 |
| API | OpenAI `/v1/chat/completions` + Anthropic `/v1/messages`（同一 base 双 wire） |
| 模型名 | `qwen3.8-flash-next`（引擎不校验）；key 占位串（`local-halogen`） |
| 注意 | ⚠ 18081 旧标签（GLM/DS4）已过期，当前实际 = 无审查 Qwen3.8 1M |

## 2. 框架接入面（静态读码）

| 层 | 现状 | 接入方式 |
|---|---|---|
| Provider preset | `PROVIDER_PRESETS`（`llm/__init__.py`） | 增 `b-station`（OpenAI wire，base 含 `/v1`）+ `b-station-anthropic`（adapter=anthropic，base 不含 `/v1`） |
| 校验 | `api_key_env`/`base_url` 必填（acp/ollama 豁免） | b-station 沿用必填 + 占位 key（executor L665 要求 base_url+api_key 非空） |
| CLI 菜单 | `_PROVIDER_CHOICES/URLS/MODELS` + `cmd_init` | 增 choice "11" 与 next-steps |
| Claude Code 子进程 | `_CliAgentBase._run_subprocess` 继承 `os.environ`；docstring 指明 `ANTHROPIC_BASE_URL`+`ANTHROPIC_AUTH_TOKEN` | 增 `CliAgentConfig.env_extra` 显式注入（不依赖 cc-switch 当前切换状态） |
| 响应解析 | **缺口：不提取 `reasoning_content`** | content 为空时回退 reasoning（Qwen3.8 为思考型模型，实测 `max_tokens=16` 全耗于思考 → 空 content） |

## 3. Live 探测发现（2026-11-09，隧道在线实测）

1. OpenAI wire：HTTP 200，`model=halogen-qwen3.8-flash-next`；`max_tokens=16` 时 **content 空、reasoning_content 有值**（思考耗尽预算）。
2. `max_tokens=64` 起正常返回答案（`1 + 1 = 2`）。
3. 结论：框架需 `reasoning_content` 回退 + 思考预算提示（live 测试用 512）。

## 4. 不在本批

- vendor/语料清单（Q18，G2/G5）；run 级预算账本（Q20，G6）。
- B 站端点不做 CI 常驻依赖（隧道非稳态），live 测试 opt-in（`ARC_BSTATION_LIVE=1`）+ 可达性探测跳过。
