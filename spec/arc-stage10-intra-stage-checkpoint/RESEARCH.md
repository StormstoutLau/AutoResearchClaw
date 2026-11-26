---
id: arc-stage10-intra-stage-checkpoint-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-26
depends: [arc-stage10-blueprint-fallback]
upstream: arc-master-roadmap
---

# 调研：Stage 10 内部断点（B-33 M1）

> **背景**：B 站 Stage 10（P-192 重跑）单阶段耗 3471 s / 17 次 LLM 调用。排查期间每次终止都要整体重跑，单次试错成本约 1 小时。上一轮调研（[arc-stage10-intra-stage-checkpoint-20261126.md](../../docs/arc-stage10-intra-stage-checkpoint-20261126.md)）已完成社区对标与方案分层，并经异构复审（[review](../../docs/arc-stage10-checkpoint-review-20261126.md)）修正。本批只做 **M1 = L0 + N-1 + L1**。

## 1. 现场证据

| 事实 | 证据 |
|---|---|
| `checkpoint.json` 只有 `last_completed_stage / name / timestamp / hitl` | 读码 `runner.py` L192-221 |
| `_write_checkpoint` 仅在 `status == DONE` 后调用 | `runner.py` L971 |
| `read_checkpoint` 返回 checkpoint 的**下一阶段** | `runner.py` L365-395 |
| `--resume` 直接采用该返回值 | `cli.py` L349-353 |
| 本轮 checkpoint 停在 `11`，Stage 10 未完成 | B 站 `checkpoint.json` |
| `architecture_spec.yaml` 只在 `CodeAgent.generate()` 返回后写 | `_code_generation.py` L1173-1176 |
| `steps.jsonl` 不存在 | B 站 `ls stage-10/steps.jsonl` |

## 2. 缺陷

| ID | 缺陷 | 后果 |
|---|---|---|
| D-1 | `--resume` 跳过未完成阶段 | 拿退化产物跑 Stage 12，且无从察觉 |
| D-2 | 蓝图仅在阶段末落盘 | Phase 1 后崩溃 → 磁盘无蓝图，断点无 `outputs` 可校验 |
| D-3 | 无步骤级账本 | 已完成步骤全部重跑 |
| D-4 | 重建 `RenderedPrompt` 时丢 `version` | prompt 版本无法进入摘要，缓存判据失效 |

## 3. 约束

- 不破坏 file-as-state 与事件日志 I-4（账本只存摘要，不存 prompt/代码正文）。
- 阶段仍是事务边界（`checkpoint` 只在 DONE 推进）。
- 只动 Stage 10；`steps.jsonl` 不推广到 Stage 12/14（用户裁决）。
- 断点复用必须能因代码/提示变更而失效，不能固化旧产物。

## 4. 结论

M1 三项：
1. **L0**：`checkpoint.json` 增 `in_progress_stage`，`read_checkpoint` 让其优先；
2. **N-1**：`_phase1_blueprint` 拿到蓝图即原子落盘并记账；
3. **L1**：新增 `pipeline/step_journal.py`（append-only、摘要、`should_skip` 纯函数）。

L2 的接入（生成路径实际跳过）与 L3（LLM 响应缓存）留 M2/M3。
