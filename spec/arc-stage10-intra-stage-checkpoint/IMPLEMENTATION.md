---
id: arc-stage10-intra-stage-checkpoint-IMPLEMENTATION
type: design
version: 1.1
status: verified
date: 2026-11-26
depends: [arc-stage10-intra-stage-checkpoint-DESIGN]
upstream: arc-stage10-intra-stage-checkpoint-DESIGN
---

# 实施记录：B-33 M1（L0 + N-1 + L1）

> v1.1（2026-11-26）：按异构复审 D-1..D-5 修正——澄清复合键口径、订正归因笔误、
> 事件重建回填 `in_progress_stage`（D-4）、`code_version` 改走 `importlib.resources`（D-5）、
> 测试改名并补 8 例。

## 1. 改动

| 文件 | 改动 |
|---|---|
| `researchclaw/pipeline/step_journal.py`（新增） | `STEP_JOURNAL_NAME` / `STEP_LOCK_NAME`；`hash_text`、`code_version`、`step_key`、`load_steps`、`append_step`、`last_done`、`should_skip`；append 经 `safe_join` 打开 + `exclusive_lock` + `flush` + `fsync`，并在 `tests/boundary_registry.yaml` 登记写点 W-032（policy=safe_join，owner=P-193）；坏行末尾容忍、中间抛 `StepJournalError`；**`_read_package_bytes` 经 `importlib.resources` 读取生成器源码，`Path(__file__)` 兜底**（D-5） |
| `researchclaw/pipeline/runner.py` | 新增 `_write_stage_start`（保留 `last_completed_stage`，写 `in_progress_stage/name/at`，`tmp + _replace_with_retry`）；`read_checkpoint` 在解析后优先返回 `in_progress_stage`；阶段循环 `stage.started` 后调用 `_write_stage_start`（异常不中断） |
| `researchclaw/runtime/event_log.py` | 新增 `_last_unfinished_stage`；`rebuild_checkpoint` 在重建时回填 `in_progress_stage/name/at`（D-9 / 复审 D-4），使 checkpoint 损坏后 `--resume` 仍落在在飞阶段 |
| `researchclaw/pipeline/code_agent.py` | 新增模块级 `_blueprint_inputs_digest`；新增 `CodeAgent._persist_blueprint`（原子写 `architecture_spec.yaml` + `append_step`）；`_phase1_blueprint` 标记 `variant = first/retry`，拿到 `arch_spec` 后立即落盘；重建 `RenderedPrompt` 时补 `version=`（即 `prompt_version` 字段） |
| `tests/test_step_journal.py`（新增） | 22 例：seq 单调、正文不入账本、坏行末尾/中间、`last_done` 变体与 truncated、`should_skip` 命中/摘要/版本/篡改/删除/空 outputs、`code_version` 形状/包读取/字节变化/文件缺失兜底 |
| `tests/test_checkpoint_in_progress.py`（新增） | 9 例：无 checkpoint、完成返回下一阶段、`in_progress` 优先、更早完成不掩盖在飞、完成清除、`_write_stage_start` 保留 last_completed、无 checkpoint 可用、无临时文件 |
| `tests/test_blueprint_persistence.py`（新增） | 6 例：成功落盘、YAML 失败仍落盘、账本 variant=first、截断重试 variant=retry（2 次调用）、无 `.tmp` 残留、账本不含蓝图正文 |
| `tests/test_event_log.py`（修改） | 新增 5 例：重建回填在飞阶段、完成后不标记、重试以最后一次 started 为准、无完成事件返回 None、端到端「checkpoint 损坏 + 在飞阶段 → 该阶段」 |

## 2. 行为对照

| 场景 | 之前 | 现在 |
|---|---|---|
| Stage 10 中途 kill 后 `--resume` | 落在 Stage 12，跳过未完成阶段 | 落在 Stage 10（`in_progress_stage` 优先） |
| Stage 10 中途 kill + `checkpoint.json` 损坏 | 退回阶段级，落在 Stage 12 | 事件重建回填 `in_progress_stage`，仍落在 Stage 10（D-9） |
| Phase 1 后崩溃 | 磁盘无蓝图，无账本 | `architecture_spec.yaml` 已存在，账本有 `blueprint:first/retry` |
| 蓝图截断重试 | 无区分 | `variant=retry`，与 `first` 分开记账 |
| 产物被手工改 | — | `should_skip` 校验 `outputs` 摘要，不符即 miss |
| 代码/提示变更 | — | `code_version`/`prompt_version` 变化使步骤失效 |
| 打包/zip 安装后取版本 | 相对路径可能失效 | `importlib.resources` 读取，`Path(__file__)` 兜底 |

## 3. 验证

```bash
python -m pytest tests/test_step_journal.py tests/test_checkpoint_in_progress.py \
  tests/test_blueprint_persistence.py tests/test_event_log.py -q
# 55 passed

python -m pytest tests/test_code_agent.py tests/test_entrypoint_contract.py \
  tests/test_codegen_truncation.py -q
# 63 passed

python -m pytest tests/test_rc_runner.py tests/test_runner_events.py \
  tests/test_checkpoint_atomic.py tests/test_rc_checkpoint.py -q
# 72 passed
```

## 4. 边界

- **D-10 / D-11 / D-12 未实施**（DESIGN v1.1 新增，DeepScientist 对标裁决）：`continuation_anchor`（存 `step_id`）、`abandoned_attempt` 摘要、明确不引入 `handoff.md`。本批只交付 L0 + N-1 + L1 的三件套，上述三项为设计裁决，留 M1 后续补丁。
- **L2 未接入**：`should_skip` 已就绪并有 8 条单测，但生成路径尚未调用它（M2）。- **L3 未做**：无 LLM 响应缓存。
- checkpoint 损坏且**事件链中无任何 `stage.completed`**（首个阶段即中断）时，`rebuild_checkpoint` 返回 `None`，需人工 `--from-stage` 指定；这是 D-9 之后仅剩的恢复盲区。
- `--from-stage` 手动重跑仍不归档旧产物（沿用既有行为）。
- B 站未部署验证；本轮只做本地实现与回归。
