---
id: arc-bilibili-endpoint-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-09
depends: [arc-bilibili-endpoint-IMPLEMENTATION]
upstream: arc-bilibili-endpoint-IMPLEMENTATION
---

# 验收清单：B站端点接入

## 1. 接入完整性

- [x] `bilibili` preset（OpenAI wire，`…:18081/v1/chat/completions`）
- [x] `bilibili-anthropic` preset（`…:18081/v1/messages`，halogen 原生）
- [x] CLI 菜单 choice "11" + `cmd_init` 生成合法配置（yaml.safe_load 复验）
- [x] `CliAgentConfig.env_extra` 注入 claude_code/codex 子进程（spawn 实测）
- [x] 示例配置双 wire 注释段 + cli_agent env_extra 注释段

## 2. 思考模型兼容

- [x] content 空 → `reasoning_content` 回退（3 用例：回退/不动/双空）
- [x] live 首跑暴露的空 content 缺口已修复并复验

## 3. 实测（2026-11-09，隧道在线）

- [x] 离线 18 passed / 2 skipped
- [x] live 2 passed（双 wire 真实命中 B站 1M，`model=halogen-qwen3.8-flash-next`）
- [x] LLM 回归 105 passed / 4 skipped

## 4. 边界

- [x] live 测试 opt-in（`ARC_BILI_LIVE=1`）+ 可达性探测，CI 不依赖隧道
- [x] 未设 bilibili 为默认 provider；`researchclaw/` 其余行为零变化
