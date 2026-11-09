---
id: arc-private-endpoint-hygiene-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-09
depends: [arc-private-endpoint-hygiene-DESIGN]
upstream: arc-private-endpoint-hygiene-DESIGN
---

# 实施记录：私有端点卫生

## 1. 落点

| # | 改动 | 落点 |
|---|---|---|
| E-1 | P0 三处改占位符 | example yaml / cli next-steps / test docstring |
| E-2 | preset 去地址（`base_url: None`） | `researchclaw/llm/__init__.py` |
| E-3 | 端点解析优先级 + fail-closed | `researchclaw/llm/client.py`（main + reviewer） |
| E-4 | 配置校验 fail-closed | `researchclaw/config.py::validate_config` |
| E-5 | CLI 模板与提示去地址 | `researchclaw/cli.py` |
| E-6 | live 测试改 `ARC_BSTATION_BASE_URL`、未设即 skip | `tests/test_b_station_provider.py` |
| E-7 | `.gitignore` 本地配置/凭据 | `.gitignore` |
| E-8 | 泄漏门禁脚本 + pre-commit + CI | `scripts/private_config_check.py`、`.pre-commit-config.yaml`、`.github/workflows/ci.yml` |

## 2. 验证

```bash
# V1 全仓泄漏扫描
python scripts/private_config_check.py

# V2 离线测试（含 endpoint 解析与 fail-closed）
python -m pytest tests/test_b_station_provider.py -q

# V3 live（显式端点）
$env:ARC_BSTATION_LIVE='1'; $env:ARC_BSTATION_BASE_URL='<tunnel-endpoint>'
python -m pytest tests/test_b_station_provider.py -q -k Live

# V4 受影响回归
python -m pytest tests/test_rc_config.py tests/test_cli.py tests/test_rc_llm.py tests/test_anthropic.py -q
```

## 3. 结果（2026-11-09）

- V1：**0 violation**（3 处历史文档中的 `sk-xxxx` 占位符按规则放行）。
- V2：**21 passed, 9 skipped**。
- V3：**9 passed**（显式端点；未设时全部 skip）。
- V4：**55 passed, 9 skipped**（含 b-station 离线用例）。
- 历史提交 `98518fd`/`2aa6a78`/`31adf8f` 未重写；当前树与新提交不再含私网地址。

## 4. 未执行

- `git filter-repo` 历史重写（需单独授权）。
- 真实 `config.arc.yaml` 的迁移（用户本地文件，不在仓库）。
