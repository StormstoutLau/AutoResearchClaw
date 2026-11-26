---
id: arc-stage10-intra-stage-checkpoint-DESIGN
type: design
version: 1.1
status: verified
date: 2026-11-26
depends: [arc-stage10-intra-stage-checkpoint-RESEARCH]
upstream: arc-stage10-intra-stage-checkpoint-RESEARCH
---

# 设计：Stage 10 内部断点（B-33 M1）

> v1.1（2026-11-26）：按 DeepScientist 对标裁决补 D-10（`continuation_anchor` 存 `step_id`）、
> D-11（`abandoned_attempt` 摘要）、D-12（不引入 `handoff.md`）。依据
> [对标分析](../../docs/arc-deepscientist-benchmark-20261126.md) + [异构复审](../../docs/arc-deepscientist-benchmark-review-20261126.md) D-2/D-5。

## 1. 决策

| ID | 决策 | 被拒替代 | 理由 |
|---|---|---|---|
| D-1 | `in_progress_stage` 优先于「下一阶段」 | 只在 `--resume` 时读事件流推断 | 事件推断无法区分「已完成」与「已开始未完成」，且需要额外解析 |
| D-2 | 阶段 DONE 时**整文件重写** checkpoint，隐式清除 `in_progress` | 单独 `del` 字段 | 现有 `_write_checkpoint` 已是全量重写，零额外改动 |
| D-3 | 蓝图在 `_phase1_blueprint` 返回前原子落盘 | 保持阶段末落盘 | Phase 1 后崩溃是最贵窗口（生成前），必须可恢复 |
| D-4 | 步骤身份为**复合键 `(step_id, variant)`**：`step_id` 取 `<phase>:<subject>`，`variant` 承载同类尝试/路径（`first`/`retry`、`sequential`/`single`、`prevalidate`/`gate`） | 把三段拼进单个 `step_id` 字符串 | 两字段分开存储可由 `last_done(step_id, variant)` 精确检索；`step_key()` 仅用于日志展示 |
| D-5 | 账本只存 `sha256` 摘要，不存正文 | 存代码副本 | 与事件日志 I-4 同纪律；正文已在 `experiment/` |
| D-6 | `outputs` 为空视为不可复用 | 空 outputs 直接命中 | 无产物即无证据，复用等于凭空跳过 |
| D-7 | 文件缺失/被改判 cache miss | 只比对摘要 | 手工修改产物后仍命中会引入未记录变更 |
| D-8 | `code_version` 单一算法（包版本 + 双文件 sha256 前 8 位），且**经 `importlib.resources` 读取**（zipimport 安全，`Path(__file__)` 兜底） | 并列「包版本或文件哈希」；只走 `Path(__file__)` | 两种口径会让跨阶段判定不一致；打包/安装后相对路径可能失效 |
| D-9 | 事件重建（`rebuild_checkpoint`）时**回填 `in_progress_stage`** | 只从 `stage.completed` 重建 | 否则 checkpoint 损坏会把 `--resume` 静默降级为「下一阶段」，跳过在飞阶段 |
| D-10 | `continuation_anchor` 存 **`step_id`（复合键）**，不存阶段名 | 存阶段名（DeepScientist 做法） | ARC 的阶段重入粒度是「步骤」；存阶段名无法表达 `blueprint:retry` 与 `gen:config.py` 的差别（复审 D-2） |
| D-11 | 阶段重试入口写 **`abandoned_attempt` 摘要**（放弃的 attempt、时间、产物清单、最后完成的 step_id） | 静默重建 attempt 目录 | 现场 09:45 重试时 `agent_runs/attempt_001` 被重建、旧日志被覆盖，**没有任何地方记录 80 分钟被丢弃**（复审 M2） |
| D-12 | **不引入 `handoff.md`** | 另写 Markdown 交接文档 | 与 `steps.jsonl` 职责重叠；人读摘要可由账本派生，不新增第二份可写记录（复审 D-5） |

## 2. 接口

```python
# researchclaw/pipeline/step_journal.py
STEP_JOURNAL_NAME = "steps.jsonl"
STEP_LOCK_NAME = ".steps.lock"

hash_text(text: str) -> str                      # "sha256:…"
code_version() -> str                            # "<pkg>+<8 hex>"
step_key(step_id: str, variant: str = "") -> str # 仅日志展示用
load_steps(stage_dir) -> list[dict]              # 末尾坏行容忍，中间抛 StepJournalError
append_step(stage_dir, *, step_id, variant="", status="done",
            inputs_digest="", outputs=None, model="", elapsed_sec=0.0,
            truncated=False, code_version_value=None, prompt_version="",
            ts=None, abandoned_attempt=None) -> dict   # D-11
last_done(steps, step_id, variant="") -> dict | None
should_skip(last, *, inputs_digest, files_on_disk,
            code_version_value=None, prompt_version="") -> bool
```

```json
// checkpoint.json 追加字段（D-10 / D-11）
{
  "in_progress_stage": 10,
  "continuation_anchor": "gen:main.py",          // step_id 复合键，非阶段名
  "abandoned_attempt": {
    "attempt": 1, "ended_at": "2026-11-26T09:45:00+00:00",
    "last_step_id": "gen:main.py",
    "artifacts": ["config.py", "utils.py", "main.py"]
  }
}
```

```python
# researchclaw/pipeline/runner.py
_write_stage_start(run_dir, stage, run_id) -> None   # 写 in_progress_stage
read_checkpoint(run_dir) -> Stage | None             # in_progress 优先
```

```python
# researchclaw/runtime/event_log.py
_last_unfinished_stage(events) -> dict | None         # 最新 started 且无后续 completed
rebuild_checkpoint(events) -> dict | None             # 回填 in_progress_*（D-9）
```

```python
# researchclaw/pipeline/code_agent.py
CodeAgent._persist_blueprint(arch_spec, *, variant, inputs_digest, prompt_version)
_blueprint_inputs_digest(topic, exp_plan, metric) -> str
```

## 3. `in_progress` 语义

| checkpoint 状态 | `read_checkpoint` 返回 |
|---|---|
| 无文件 | `None` |
| 仅 `last_completed_stage` | 下一阶段 |
| `in_progress_stage` 存在 | 该阶段（无论 `last_completed` 是什么） |
| 阶段 DONE 后（字段被清除） | 下一阶段 |

## 4. 非目标

- 不改 `checkpoint` 的「DONE 才推进」语义。
- 不接入生成路径的跳过逻辑（L2 留 M2）。
- 不做 LLM 响应缓存（L3 留 M3）。
- 不改 `--from-stage` 的归档行为。
- 不推广到 Stage 12/14。
- **不写 `handoff.md`**（D-12）：断点真值只有 `steps.jsonl`，人读摘要从账本派生。
- **不接 DeepScientist 的 11 态状态机**：`RunStatus` 状态扩展归 B-31，本批只动 `in_progress_stage`。

## 5. 边界

- checkpoint **损坏**时走 `_recover_checkpoint_from_events`：新增 D-9 后 `in_progress_stage` 可从事件回填，`--resume` 仍落在在飞阶段。**仍不可恢复的唯一情形**：事件链里没有任何 `stage.completed`（首个阶段就中断），此时 `rebuild_checkpoint` 返回 `None`，需人工用 `--from-stage` 指定。
- `append_step` 失败不回滚已写产物——账本是投影，产物是事实。
- `should_skip` 在 M1 只有单测覆盖，主线尚未调用（L2 留 M2）。
