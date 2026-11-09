---
id: arc-private-endpoint-hygiene-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-09
depends: [arc-private-endpoint-hygiene-RESEARCH]
upstream: arc-private-endpoint-hygiene-RESEARCH
---

# 设计：端点解析与泄漏门禁

## 1. 端点解析优先级

```
llm.base_url
  > RESEARCHCLAW_LLM_BASE_URL
  > preset.base_url（b-station 恒为 None）
```

- provider 以 `b-station` 开头且解析结果为空 → `ValueError`（`from_rc_config`）与配置校验 error（`validate_config`）双保险。
- `reviewer_from_rc_config` 同样接入 env 回退。
- 单测用 RFC 2606 保留域 `http://b-station.test`，永不指向真实主机。

## 2. 模板与 CLI

- `config.researchclaw.example.yaml`：地址、端口、用户名全部替换为 `<B_STATION_HOST>` / `<TUNNEL_PORT>` / `<API_PORT>` / `<user>`。
- `cmd_init` 选 b-station：`base_url: ""`，next-steps 只打印占位符命令。
- `_PROVIDER_URLS` 移除 b-station 条目（不再有本机端口默认值）。

## 3. 泄漏门禁

`scripts/private_config_check.py`：

| 规则 | 说明 |
|---|---|
| `rfc1918-ip` | 10/8、172.16/12、192.168/16 |
| `ssh-user@ip` | `user@<private-ip>` |
| `api-key-*` | `sk-` / `ghp_` / `AKIA` / `xox[baprs]-`；全 `x` 占位符放行 |

- 白名单：`tests/test_web_crawler.py`（SSRF 夹具）、脚本自身；
- 行内豁免：`private-config: allow`；
- pre-commit 新增 `private-config` 钩子；CI 增加同名步骤。

## 4. 本地配置隔离

`.gitignore` 新增：`/config.arc.yaml`、`/config.*.local.yaml`、`*.local.yaml`、`.env`、`.env.*`（`*.example*` 保留）。

## 5. 回滚

单提交 revert；preset 恢复需同时恢复测试与示例模板，否则 b-station 会重新指向本机端口。
