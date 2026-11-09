---
id: arc-b-station-live-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-09
depends: [arc-b-station-live-IMPLEMENTATION]
upstream: arc-b-station-live-IMPLEMENTATION
---

# 验收清单：B 站 live 覆盖扩展

## 1. 用例完整性

- [x] `/health` 断言 1M 上下文 + 双 wire + capability_probe
- [x] JSON 模式返回可解析 JSON
- [x] 系统提示生效
- [x] 多轮上下文回忆
- [x] OpenAI wire 用量字段 > 0
- [x] Anthropic wire 用量字段 > 0（cache 计入）
- [x] `preflight()` 返回成功
- [x] cache 计费离线用例（input=0 / cache_read=56 → prompt=56）

## 2. 边界

- [x] live 双闸：`ARC_BSTATION_LIVE=1` + socket 探测；CI 不依赖隧道
- [x] 断言结构化，不依赖精确文本
- [x] 统一 `max_tokens=512`，避免 thinking 吃光预算

## 3. 实测

- [x] 离线 19 passed / 9 skipped
- [x] live 9 passed
- [x] Anthropic/LLM 回归 43 passed / 1 skipped
- [x] 首跑暴露的 Anthropic cache 计费缺口已修复
