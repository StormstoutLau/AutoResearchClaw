---
id: arc-private-endpoint-hygiene-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-09
depends: [arc-b-station-live-IMPLEMENTATION]
upstream: arc-b-station-live-IMPLEMENTATION
---

# 调研：私有端点信息入库卫生

> **触发**：B 站接入把 `<B_STATION_HOST>` / `<user>` / `127.0.0.1:<TUNNEL_PORT>` 写进了提交。
> **目标**：私有基础设施地址不进仓库；端点由配置/环境变量提供；新增泄漏可被门禁拦截。

## 1. 泄漏面盘点

| 级别 | 内容 | 位置 |
|---|---|---|
| P0 | `<user>@<B_STATION_HOST>`（私网 IP + 用户名） | `config.researchclaw.example.yaml`、`researchclaw/cli.py`、`tests/test_b_station_provider.py` |
| P1 | `127.0.0.1:<TUNNEL_PORT>` 硬编码 | `PROVIDER_PRESETS`、`_PROVIDER_URLS`、测试常量、4 份 spec |
| P2 | 以上内容已进入历史提交 | `98518fd` / `2aa6a78` / `31adf8f` |
| 非问题 | SSRF 测试中的 `172.16/192.168`；容器内 `/home/researcher` | `tests/test_web_crawler.py`、`docker_sandbox.py` |

## 2. 裁决

- **A0**：清当前树的 P0（3 处改占位符）。
- **A1**：preset 不写死地址；端点来源 `llm.base_url` > `RESEARCHCLAW_LLM_BASE_URL`；缺失 fail-closed。live 测试改读 `ARC_BSTATION_BASE_URL`，未设即 skip。
- **A2**：`.gitignore` 覆盖本地配置/凭据；新增 `private_config_check.py` 作为 pre-commit + CI 门禁。
- **A3（未采纳）**：不重写历史（破坏性，需单独授权）；历史中的地址保留，当前树与新提交不再新增。

## 3. 兼容性

- 依赖 preset 默认 URL 的 b-station 配置需显式写 `llm.base_url`；这是私有端点的正确默认。
- 其余 provider 的 preset 行为不变。
- live 测试不再默认探测本机端口，必须显式给端点。
