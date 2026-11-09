---
id: arc-private-endpoint-hygiene-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-09
depends: [arc-private-endpoint-hygiene-IMPLEMENTATION]
upstream: arc-private-endpoint-hygiene-IMPLEMENTATION
---

# 验收清单：私有端点卫生

## 1. 当前树

- [x] 无私网 IP（`private_config_check.py` 全仓 0 违规）
- [x] 无 `user@<private-ip>` SSH 目标
- [x] 示例模板只含 `<B_STATION_HOST>` / `<TUNNEL_PORT>` / `<API_PORT>` / `<user>` 占位符
- [x] CLI 生成模板的 `base_url` 为空，提示使用占位符

## 2. 端点解析

- [x] preset 不写死地址
- [x] `llm.base_url` > `RESEARCHCLAW_LLM_BASE_URL` > preset
- [x] 缺失端点 fail-closed（client 与 config 双保险）
- [x] live 测试未设 `ARC_BSTATION_BASE_URL` 即 skip

## 3. 防复发

- [x] `.gitignore` 覆盖 `config.arc.yaml` / `*.local.yaml` / `.env*`
- [x] pre-commit `private-config` 钩子
- [x] CI 同名步骤
- [x] SSRF 测试与占位符有明确白名单，不误伤

## 4. 实测

- [x] 扫描 0 违规
- [x] 离线 21 passed / 9 skipped
- [x] live 9 passed（显式端点）
- [x] 回归 55 passed / 9 skipped

## 5. 未纳入

- [x] 历史提交重写（保留，需单独授权）
