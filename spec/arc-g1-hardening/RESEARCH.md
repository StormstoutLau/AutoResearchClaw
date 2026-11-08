---
id: arc-g1-hardening-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-08
depends: [arc-g1-readiness-research-20261108, arc-master-roadmap]
upstream: arc-g1-readiness-research-20261108
---

# 调研：G-1 急救项落地依据

> **输入**：[G-1 开工前补充调研](../../docs/arc-g1-readiness-research-20261108.md)（H-1..H-8 复核 + Q18/Q19/Q20 七维对比）。
> **用户裁决（2026-11-08）**：Q18=A（L1 清单）、Q19=A（回环默认 + 强制 token）、Q20=A′（分层账本）；H-1..H-8 测试先行、同批实现。

## 1. 复核结论

| 项 | 事实 | 本批改动 |
|---|---|---|
| H-1 | Stage 12 主路径未写 `returncode`；agent 路径有 | 抽 `_build_run_payload` 统一两个 writer |
| H-2 | `contracts.max_retries` 无消费点 | `_call_with_retries` 包裹 stage 执行 |
| H-3 | `ClaimVerifier` 仅测试引用 | Stage 20/23 写 `claim_verification.json` |
| H-4 | `retrieval_degraded` 零命中 | Stage 4 写 `retrieval_status.json` |
| H-5 | 聚合层不过滤失败 run | `_collect_experiment_results` 过滤 + `excluded_runs` |
| H-6 | 3 处透传 `os.environ` | `build_subprocess_env` allowlist |
| H-7 | `safe_join` 不存在 | 新增 `safe_join` 并替换写入点 |
| H-8 | 默认 `*` + `allow_credentials=True` | 显式 origins + 启动校验 |

## 2. 裁决落地

- **Q18**：本批只裁决语义（L1 清单 + Croissant 四字段）；vendor/语料尚未入库，清单与校验脚本在 G2/G5 落地。
- **Q19**：本批实现——`host` 默认 `127.0.0.1`；非回环且无 token → `validate_server_security` 抛错；CORS 通配符直接拒绝。
- **Q20**：本批裁决语义（分层账本）；代码合并在 G6（run 账本属 G6 交付物），本批仅打卡版本与前置检查点。

## 3. 不在本批

- vendor/语料清单文件（G2/G5）。
- run 级预算账本与 `LLMClient.chat` 前置检查（G6）。
- A4-8 的全仓写入点替换（G4）；本批只覆盖 H-7 引用的 Stage 13 写入点。
