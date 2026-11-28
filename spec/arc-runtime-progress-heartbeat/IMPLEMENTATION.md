---
id: arc-runtime-progress-heartbeat-IMPLEMENTATION
type: design
version: 1.1
status: verified
date: 2026-11-27
depends: [arc-runtime-progress-heartbeat-DESIGN]
upstream: arc-runtime-progress-heartbeat-DESIGN
---

# 实施记录：阶段内步骤级进度与心跳（B-31b / B-33 L1 扩展）

> v1.1（2026-11-27，P-218）：部署后现场复验（运行 J）发现并修复 `read_run_state` 的重跑误报——旧 `pipeline_summary.failed` 会盖住新一轮的活跃心跳；补 §5 与 C-14。

## 1. 改动

| 文件 | 改动 |
|---|---|
| [`researchclaw/runtime/progress.py`](../../researchclaw/runtime/progress.py)（新增） | `ProgressKeeper`：30s 线程、启动即写、原子替换、投影 `steps.jsonl` 的 `last_step/phase/steps_done`；`read_last_step` / `count_steps` |
| [`researchclaw/pipeline/runner.py`](../../researchclaw/pipeline/runner.py) | 每阶段 `execute_stage` 前启动 keeper、`finally` 停止；`_write_heartbeat` 增 `status=done` / `updated_at` / `stage` 字段（保留 `timestamp`） |
| [`researchclaw/pipeline/code_agent.py`](../../researchclaw/pipeline/code_agent.py) | `_journal_progress_step` / `_files_digest`；模块成功写 `generate_file(done)`；专用入口写 `entrypoint`；每轮硬校验写 `hard_validation`；单发回退写 `generate_project` |
| [`researchclaw/pipeline/stage_impls/_code_generation.py`](../../researchclaw/pipeline/stage_impls/_code_generation.py) | 初始/每次 regen 的对齐判词写 `alignment`；阶段级入口重生成写 `entrypoint(stage)` |
| [`researchclaw/run_state.py`](../../researchclaw/run_state.py) | `RunStatus.STALLED`；`RunState.silence_sec`；按 `interval_sec` 推导有效阈值；仅 `in_progress_stage` 存在时判 `STALLED` |
| [`researchclaw/dashboard/collector.py`](../../researchclaw/dashboard/collector.py) | `RunSnapshot.silence_sec` 透传 |
| [`researchclaw/server/routes/projects.py`](../../researchclaw/server/routes/projects.py) | `/api/projects` 增 `silence_sec` |
| [`tests/test_progress_heartbeat.py`](../../tests/test_progress_heartbeat.py)（新增） | 13 例：心跳写入/刷新/投影/不可写不抛；STALLED/UNKNOWN/interval/silence；模块/入口/校验/对齐记账；进度行不可复用 |

## 2. 关键实现

```python
# runner.py —— 阶段内心跳
progress_keeper = ProgressKeeper(
    run_dir, run_id, stage, stage.name,
    stage_dir=run_dir / f"stage-{stage_num:02d}",
).start()
try:
    result = execute_stage(...)
finally:
    progress_keeper.stop()
```

```python
# code_agent.py —— 每模块 done 记账（摘要 only）
self._journal_progress_step(
    "generate_file", variant=file_name, status="done",
    inputs_digest=hash_text(file_spec_str + "\n---\n" + dep_code),
    outputs={file_name: hash_text(code)},
    model=..., elapsed_sec=..., prompt_version=...,
)
```

```python
# run_state.py —— STALLED 分支
elif (heartbeat_dt is not None and in_progress is not None
      and silence_sec > effective_stale):
    status = RunStatus.STALLED
```

## 3. 验证

```bash
python -m pytest tests/test_progress_heartbeat.py -q
# 13 passed

python -m pytest tests/test_progress_heartbeat.py tests/test_run_state.py \
  tests/test_generation_budget_contract.py tests/test_module_extraction_fallback.py \
  tests/test_repair_trace.py tests/test_blueprint_persistence.py \
  tests/test_entrypoint_contract.py tests/test_code_agent.py \
  tests/test_g1b_runtime.py tests/test_supervisor.py -q
# 181 passed

python -m pytest tests/test_web_platform.py tests/test_mcp_protocol.py -q
# 68 passed, 10 skipped

python -m pytest tests/test_rc_stages.py tests/test_rc_executor.py \
  tests/test_pipeline_summary_check.py tests/test_pipeline_skill.py -q
# 316 passed
```

环境性失败：`tests/test_rc_sentinel.py::TestSentinelScript::test_sentinel_script_is_valid_bash` 在 Windows 下把 `D:\...` 传给 Git Bash，路径反斜杠被吞（`No such file or directory`），与本批改动无关。

## 4. 边界

- 未部署 B 站；部署后心跳才会覆盖运行 I 这类「进行时」场景。
- 未做 `STALLED` 的告警/自动重启（B-31 M3）。
- 心跳的真实频率依赖线程调度，测试用 0.02s 间隔验证「会刷新」，生产默认 30s。
- `steps_done` 是账本行数，不是计划完成度。
- `ProgressKeeper.update()` 目前只供测试/未来阶段使用，主线依赖账本投影。

## 5. 现场复验（运行 J，P-218）

**部署**：工作树快照 42 848 489 B，两端 SHA-256 `f2be620a…c7bd` 一致；旧代码 `AutoResearchClaw-main.prev-p213`、旧 Stage 10 `stage-10.bak-p216`；`validate` 通过；导入自检 `IMPORT_OK` / `report_helper` / `decision_guard` / `progress_keeper` / `stalled` 全为 True，`code_version=0.5.0+b4c19b7a`。

**读数（15:51 启动，16:06 取样）**：

| 观测面 | 读数 | 判定 |
|---|---|---|
| `heartbeat.json` | `status=running`、`stage=10`、`phase=blueprint`、`last_step=blueprint:yaml_repair`、`steps_done=2`、`updated_at` 每 30s 刷新 | ✅ B-31b 生效（旧文件此前停在 11-25） |
| `stage-10/steps.jsonl` | 3 行：`blueprint:retry` → `blueprint:yaml_repair` → `generate_file:config.py`（29.12 s，`outputs` 带 sha256） | ✅ 成功模块首次进入账本 |
| 蓝图 | 首版 YAML 在第 832 行截断（`unexpected end of stream`）→ `Blueprint YAML invalid` → YAML-only 修复成功（5 files） | B-32 M1 路径现场复现 |

**新缺陷（本轮修复）**：`read_run_state` 在重跑时返回 `{'current_stage': 11, 'status': 'failed', 'is_active': False, 'silence_sec': 24.2}`——心跳明明是新的。根因两条：① `pipeline_summary.json` 只在整个 run 结束时写，失败后重跑会一直带着上一轮的 `final_status=failed`；② 阶段号只读 `last_completed_stage`，忽略 `in_progress_stage`（B-33 L0 的恢复语义没有同步到读取侧）。

**修法**：仅当心跳显式 `status="running"` 且新鲜（`live_running`）时，忽略陈旧 summary 并把阶段号切到 `in_progress_stage`；没有 `status` 字段的旧心跳保持原语义（已完成 run 的 `status=done` 也不会被误判为 running）。

**现场复核（部署 `run_state.py` 单文件后）**：同一 run 目录读出 `{'current_stage': 10, 'current_stage_name': 'CODE_GENERATION', 'status': 'running', 'is_active': True, 'silence_sec': 1.3}`。
