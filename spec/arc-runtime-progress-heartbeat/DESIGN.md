---
id: arc-runtime-progress-heartbeat-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-27
depends: [arc-runtime-progress-heartbeat-RESEARCH]
upstream: arc-runtime-progress-heartbeat-RESEARCH
---

# 设计：阶段内步骤级进度与心跳（B-31b / B-33 L1 扩展）

## 1. 决策

| ID | 决策 | 被拒替代 | 理由 |
|---|---|---|---|
| D-1 | 新增独立 `runtime/progress.py` 的 `ProgressKeeper` | 扩展 `LeaseKeeper` | 租约是「谁可以写」的跨进程所有权；进度是「写到哪」的阶段投影。混在一个线程会让租约失败与进度失败互相掩盖 |
| D-2 | 心跳间隔 **30s**，`stale_after = max(3×interval, 300)` | 沿用调研的 200s / 600s | 30s 才能让 dashboard 的分钟级视图有意义；载荷约 0.5 KB，120 次/小时，fsync 放大量可忽略。300s 下限与 `read_run_state` 既有默认一致 |
| D-3 | 原子写（temp + `os.replace` 重试），全部异常吞掉 | 直接 `write_text` | Windows 共享冲突会撕裂 JSON；心跳绝不能让阶段失败 |
| D-4 | 心跳**投影** `steps.jsonl` 的末行，不复制步骤状态 | 在 ProgressKeeper 里维护第二份进度 | 单一事实源；`append_step` 已带锁与 fsync |
| D-5 | `STALLED` 仅在 `in_progress_stage` 存在且 `silence > stale_after` 时判定 | 所有陈旧心跳都判 `STALLED` | 已完成/未知 run 的陈旧心跳仍是 `UNKNOWN`（保持既有测试契约） |
| D-6 | 步骤账本补 `generate_file(done)` 与 `entrypoint`；`hard_validation`/`alignment`/`generate_project` 记进度行但 `outputs` 为空 | 所有步骤都写 outputs | `should_skip` 要求非空 outputs；进度行带 outputs 会被误当可复用工作 |
| D-7 | 保留 `timestamp` 字段并新增 `updated_at` | 只改新字段 | sentinel/dashboard 的旧读者仍能工作 |
| D-8 | 不引入 `__ARC_PROGRESS__` stdout 协议 | 按调研原稿加 stdout 行 | stdout 在重定向时块缓冲；文件账本零缓冲风险（复审 D-1） |
| D-9 | dashboard 的活跃阈值由心跳 `interval_sec` 推导（`max(param, 3×interval)`） | 固定 60s | 30s 心跳下固定 60s 会在调度抖动时误报 inactive |

## 2. 接口

```python
# researchclaw/runtime/progress.py
HEARTBEAT_NAME = "heartbeat.json"
DEFAULT_INTERVAL_SEC = 30.0
MIN_STALE_AFTER_SEC = 300.0

class ProgressKeeper:
    def __init__(self, run_dir, run_id, stage, stage_name, *,
                 stage_dir=None, interval=30.0, stale_after=None): ...
    def start(self) -> "ProgressKeeper": ...   # 先同步写一次，再启动线程
    def update(self, **fields) -> None: ...    # phase/status 等覆盖项
    def stop(self) -> None: ...
```

```json
// heartbeat.json（运行中）
{
  "pid": 1045926, "run_id": "g7-baseline",
  "stage": 10, "stage_name": "CODE_GENERATION",
  "status": "running", "stage_started_at": "2026-11-27T01:39:27+00:00",
  "phase": "generate", "last_step": "generate_file:data.py",
  "last_step_status": "done", "last_step_ts": "2026-11-27T01:53:00+00:00",
  "steps_done": 4,
  "updated_at": "…", "timestamp": "…",
  "interval_sec": 30.0, "stale_after_sec": 300.0,
  "last_stage": 10, "last_stage_name": "CODE_GENERATION"
}
```

```python
# researchclaw/run_state.py
class RunStatus(str, Enum):
    RUNNING = "running"
    STALLED = "stalled"   # 新增
    ...

RunState.silence_sec: float   # to_dict 同步
```

## 3. `STALLED` 判定

| 条件 | 结果 |
|---|---|
| `pipeline_summary.final_status` ∈ {done, failed} | 保持 COMPLETED / FAILED |
| 心跳静默 ≤ `max(stale_after_sec, 3×interval)` | RUNNING，`is_active=True` |
| HITL waiting | PAUSED |
| 心跳静默 > 阈值 且 `in_progress_stage` 存在 | **STALLED**，`is_active=False`，`silence_sec` |
| 心跳静默 > 阈值 但无 `in_progress_stage` | UNKNOWN（旧 run 语义） |
| 无心跳 | UNKNOWN（不伪造） |

## 4. 步骤账本扩展

| step_id | 写入时机 | status | outputs |
|---|---|---|---|
| `generate_file` | 每模块代码成功抽取后 | `done` | `{file: sha256}` |
| `entrypoint` | 专用入口生成成功（CodeAgent）或阶段级重生成成功 | `done` | `{main.py: sha256}` |
| `hard_validation` | 每轮硬校验结束 | `done` / `failed` | 空 |
| `alignment` | 初始/每次 regen 的判词 | `done` / `misaligned` | 空 |
| `generate_project` | 单发回退产出文件 | `done` | `{file: sha256}` |

## 5. 非目标与边界

- 心跳不参与断点复用；`should_skip` 只读 `steps.jsonl`。
- 心跳写失败只记 DEBUG，不影响阶段。
- 阶段级 `entrypoint` 记录写在 `exp_dir.parent`（即 `stage-10`），与 CodeAgent 记录同一账本。
- 不改 `_write_stage_start` / `_write_checkpoint` 的语义。
- 不改 supervisor；`max_wall_seconds=1800` 的问题留 B-31 M3。
- `steps_done` 是账本行数，不是「计划总数」；不伪造百分比。
