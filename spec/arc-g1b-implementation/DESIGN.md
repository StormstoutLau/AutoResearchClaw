---
id: arc-g1b-implementation-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1b-implementation-RESEARCH]
upstream: arc-g1b-implementation-RESEARCH
---

# 设计：G1b 实施（supervisor / exit codes / attempt / outbox）

## 1. 决策

| ID | 决策 |
|---|---|
| D-1 | 退出码：`0/65/75/77/78/85` 六类；`85` = 正常暂停（R-1） |
| D-2 | supervisor **不持租约**，只管理进程（R-2） |
| D-3 | 租约由 worker 持有，`LeaseKeeper` 线程每 TTL/3 续期（R-3） |
| D-4 | attempt 记录写 `<run>/attempts/stage-NN/attempt-<k>.json`，Stage 状态只由 executor 迁移 |
| D-5 | outbox = 事件日志投影；`effect.queued` − `effect.done`，key=`sha256(kind+payload)` |
| D-6 | 本批不含 SSE/WS（P-031） |

## 2. 退出码分类

```python
class ExitClass(str, Enum):
    OK = "ok"                 # 0
    DATA = "data"             # 65
    RETRYABLE = "retryable"   # 75
    REVOKED = "revoked"       # 77
    CONFIG = "config"         # 78
    PAUSED = "paused"         # 85
```

`classify_results(results) -> int`：

1. 任一 `FAILED` → 按错误文本匹配：401/403/revoked → 77；config/version/invalid → 78；否则 75。
2. 无 FAILED、有 `PAUSED/BLOCKED_APPROVAL/REJECTED` → 85。
3. 否则 → 0。
4. 空结果 → 65（无可执行阶段属数据/输入问题）。

`is_retryable(code) -> bool`：仅 75。

## 3. attempt 记录

```jsonc
// <run>/attempts/stage-12/attempt-2.json
{
  "stage": 12, "stage_name": "EXPERIMENT_RUN", "attempt": 2,
  "started_at": "...", "ended_at": "...",
  "exit_class": "retryable", "exit_code": 75,
  "session_id": null, "context_replayed": true,
  "resume_note": "..."
}
```

- 写入时机：stage 结束时（DONE/FAILED 均写）；`attempt` 编号按同目录已有文件 +1。
- `build_resume_note(stage, attempt, last_error, artifacts)`：≤500 字，含失败阶段、错误摘要、产物清单、恢复要求。
- **不迁移 Stage 状态**：attempt 只记录，`StageStatus` 仍由 `execute_stage`/runner 决定。

## 4. outbox

```python
class EffectQueue:
    def __init__(event_log)
    def pending() -> list[Effect]      # queued − done（同 key 去重，保留首个）
    def run(handler, *, kinds=None) -> dict   # 执行 + 写 effect.done
```

- `Effect = {kind, key, payload}`；`key = sha256(kind + canonical(payload))`。
- 执行前写 `effect.started`，成功后 `effect.done{key,result:"ok"}`，失败 `effect.done{key,result:"error:<摘要>"}`（失败也落 done，避免无限重试；重试由调用方显式重新入队）。
- 幂等：同一 key 已 done 则跳过。

## 5. supervisor

```python
class Supervisor:
    def __init__(run_id, run_dir, worker_cmd, max_restarts=5, max_wall=1800, ...)
    def run() -> int            # 返回最终退出码
```

- 循环：spawn → wait → 分类；`75` 且预算未尽 → full jitter（base2 cap300）后重试；`85` → 停止并写 `run.paused`；其余非 0 → 停止。
- 每次重启前写 `stage.retried` 事件（若事件日志可写；失败不阻断）。
- **不 acquire/release 租约**；重启前仅做残留清理（见 RESEARCH R-2）。
- worker 命令默认 `[sys.executable, "-m", "researchclaw", "run", "--resume", ...]`，由 CLI 组装。

## 6. 验收映射

| 验收 | 落点 |
|---|---|
| A1-3 | §5 supervisor 循环；kill 后 `--resume` |
| A1-7 | §2 分类表 + `is_retryable` |
| A1-9 | §3 `session_id` + `context_replayed` |
| A1-10 | §4 EffectQueue |
| A1-11 | §3 attempt 不迁移 Stage |
| A1-12 | §3 `build_resume_note` |

## 7. 回滚

- 新增模块独立，CLI 仅改 `cmd_run` 返回值与新增 `supervisor` 子命令；回退 = 恢复 `return 0 if failed == 0 else 1` 并删子命令。
- `ARC_EVENTS_DISABLED=1` 时 outbox/attempt 仍可用（attempt 不依赖事件；resume_note 降级为无产物清单）。
