---
id: arc-g7-run-id-stability-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-g7-run-id-stability-DESIGN, arc-g7-run-id-stability-RESEARCH]
upstream: arc-master-roadmap
---

# 实施：run_id 稳定性与 A7-1 现场适配（P-174）

## 1. 交付锚点

| 交付 | 文件 | 符号/行 | 行为 |
|---|---|---|---|
| run_id 取目录名 | [cli.py](../../researchclaw/cli.py) | `cmd_run` [L243-L251](../../researchclaw/cli.py#L243-L251) | 显式 `--output` → `run_id = run_dir.name` |
| 回归用例 | [test_rc_cli.py](../../tests/test_rc_cli.py) | `test_output_dir_name_is_the_stable_run_id` [L364](../../tests/test_rc_cli.py#L364) | 断言 `run_id=g7-baseline`、`run_dir=out` |
| 现场决策 | [arc-g7-field-run-decision-20261125.md](../../docs/arc-g7-field-run-decision-20261125.md) | §3/§5/§7 | B 站拓扑、两阶段、验收 |
| 现场配置模板 | [config.g7-field.example.yaml](../../config.g7-field.example.yaml) | 全文 | 裸 API + loopback + 小规模真实实验 |

## 2. TDD 红 → 绿

1. **红**：新用例期望 `captured["run_id"] == "g7-baseline"`；未修复前 `cmd_run` 返回 `rc-*`，测试失败。
2. **绿**：`if output: run_id = run_dir.name`；用例通过。
3. **回归**：`tests/test_rc_cli.py + test_admission.py + test_supervisor.py + test_event_replay_rotation.py` **61 passed**；全量 **3953 passed / 6 环境态失败 / 108 skipped**。

## 3. B 站现场部署（2026-11-25）

| 项 | 读数 |
|---|---|
| 主机 | `scott-lau@<B_HOST>`（B 站，模型同机；实际地址见 RPC `inventory/ports.yaml`）；Python 3.12.3；423G 可用 |
| 模型 | `halogen-qwen3.8-flash-next`；1,048,576 ctx；`json_schema/json_object`；`/health` 200 |
| 传输 | 51.87MB tgz → `~/AutoResearchClaw-main`；`~/arc-venv`（`pip install -e .[all]` + torch 2.15.0+cpu + sklearn + pandas） |
| 体检 | `researchclaw doctor` **PASS**（api_key/sandbox_python 已修） |
| 冒烟 | Stage 1 `TOPIC_INIT` **67.9s**，退出 0 |
| 基线 | `~/arc-runs/g7-baseline`，`run_id=g7-baseline`，当前已过 Stage 7（运行中） |
| 网络 | B 站 DuckDuckGo 不可达、OpenAlex 429 → `web_search=false`、`sources=[arxiv, semantic_scholar]` |
| 现场干预 | Stage 3 后 seed 英文 `queries.json`；`research.domains` 补英文词，避免 Stage 5 全拒 |

## 4. 边界

- **72h field run 未启动**：基线仍在运行；等基线收敛后再启动 soak，避免双跑争模型与 CPU。
- **两次人工干预**：seed queries 与英文 domains 记录在 field decision；A7-1 的「无人值守」声明需在后续不干预 run 中复核。
- 不改默认 `artifacts/<rc-*>` 行为，不新增配置字段。
