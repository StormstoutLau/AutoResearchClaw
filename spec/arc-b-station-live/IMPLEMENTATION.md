---
id: arc-b-station-live-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-09
depends: [arc-b-station-live-DESIGN]
upstream: arc-b-station-live-DESIGN
---

# 实施记录：live 覆盖扩展

## 1. 落点

| # | 改动 | 落点 |
|---|---|---|
| E-1 | 7 个 live 用例（health/JSON/system/multi-turn/usage×2/preflight） | `tests/test_b_station_provider.py::TestBStationLiveAPI` |
| E-2 | 1 个离线 cache 计费用例 | 同文件 `TestAnthropicCacheUsage` |
| E-3 | Anthropic usage 汇总含 cache 字段 | `researchclaw/llm/anthropic_adapter.py` |

## 2. 验证

```bash
# V1 离线（live 默认 skip）
python -m pytest tests/test_b_station_provider.py -q

# V2 live（隧道在线）
$env:ARC_BSTATION_LIVE='1'; python -m pytest tests/test_b_station_provider.py -q -k Live

# V3 Anthropic / LLM 回归
python -m pytest tests/test_anthropic.py tests/test_rc_llm.py -q
```

## 3. 结果（2026-11-09 实测）

- V1：**19 passed, 9 skipped**。
- V2：**9 passed**（全部 live 用例，7.9s）。
- V3：**43 passed, 1 skipped**。
- 首跑发现：Anthropic wire `prompt_tokens=0`（实为 `cache_read_input_tokens=56`）→ E-3 修复后转绿。

## 4. 未执行

- 1M needle 长上下文压测（由 `/health` 声明替代）。
- `/v1/responses` wire 与 vision（端点声明支持，框架未接）。
