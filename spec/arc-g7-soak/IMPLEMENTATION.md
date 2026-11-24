---
id: arc-g7-soak-IMPLEMENTATION
type: design
version: 1.1
status: verified
date: 2026-11-24
depends: [arc-g7-soak-DESIGN, arc-g7-soak-RESEARCH]
upstream: arc-master-roadmap
---

# 实施：G7 第一段「soak 工具链」（P-160）

> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.2 / verified）。
> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.1 / verified）。
> **本批变更面**：新增 4 文件（soak 包 3 + `__init__`）+ 3 处缺陷修复（F-1/F-1b/F-2/F-4）+ CLI 3 子命令 + 4 个测试文件；无新依赖。

---

## 1. 文件清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `researchclaw/soak/__init__.py` | 新增 | 导出 `SoakConfig/SoakDriver/SoakResult/verify_run/...` |
| `researchclaw/soak/verifier.py` | 新增 | `RunVerification`、`verify_run`、`convergence_signature`、`event_seq_coverage`、`collect_failure_stages` |
| `researchclaw/soak/driver.py` | 新增 | `SoakConfig`、`RestartRecord`、`SoakResult`、`SoakDriver` |
| `researchclaw/soak/report.py` | 新增 | `build_report`、`render_markdown`、`write_report` |
| `researchclaw/runtime/event_log.py` | 修改 | F-1：active 缺失/为空时从最后归档段恢复 `last_seq/last_hash`；F-1b：torn tail 截断 |
| `researchclaw/pipeline/runner.py` | 修改 | F-2：`_recover_checkpoint_from_events` 接受归档-only；D-11：`_replace_with_retry` |
| `researchclaw/cli.py` | 修改 | `soak run/verify/report` 解析与处理 |
| `tests/test_soak_verifier.py` | 新增 | T01–T07 + checkpoint-ahead/failure-stage 边界 |
| `tests/test_event_log_roll_recovery.py` | 新增 | T08–T09 + torn-tail 回归 |
| `tests/test_checkpoint_atomic.py` | 新增 | T19 原子替换重试 |
| `tests/boundary_registry.yaml` | 修改 | S-061/S-062：soak spawn / taskkill 边界登记 |
| `tests/test_soak_driver.py` | 新增 | T10–T16 |

## 2. 接口签名（可实现）

```python
# researchclaw/soak/verifier.py
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class RunVerification:
    run_id: str
    ok: bool
    problems: tuple[str, ...]
    chain_ok: bool
    chain_message: str
    first_seq: int
    last_seq: int
    event_count: int
    seq_gaps: tuple[int, ...]
    duplicate_seqs: tuple[int, ...]
    run_id_mismatches: tuple[int, ...]
    segments: tuple[dict, ...]
    checkpoint_stage: int
    checkpoint_name: str
    checkpoint_status: str
    max_completed_stage: int
    event_checkpoint_skew: int
    completed_stages: tuple[int, ...]
    terminal_status: str
    convergence_signature: dict
    reference_signature: dict | None
    converged: bool
    retention_limited: bool
    failure_stages: tuple[tuple[int, int], ...]

def event_seq_coverage(events: list[dict]) -> tuple[tuple[int, ...], tuple[int, ...]]: ...
def convergence_signature(run_dir: str | Path) -> dict: ...
def read_terminal_status(run_dir: str | Path) -> str: ...
def collect_failure_stages(events: list[dict]) -> tuple[tuple[int, int], ...]: ...
def verify_run(
    run_dir: str | Path,
    *,
    expected_run_id: str | None = None,
    reference_run_dir: str | Path | None = None,
    allow_retention_gap: bool = False,
) -> RunVerification: ...
```

```python
# researchclaw/soak/driver.py
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

@dataclass(frozen=True)
class SoakConfig:
    run_dir: Path
    worker_cmd: tuple[str, ...]
    duration_seconds: float = 72 * 3600
    max_restarts: int = 3
    inject_at_stages: tuple[int, ...] = ()
    poll_seconds: float = 5.0
    min_restart_interval_seconds: float = 10.0
    worker_exit_timeout_seconds: float = 30.0
    worker_cwd: Path | None = None
    reference_run_dir: Path | None = None
    config_path: str | None = None

@dataclass(frozen=True)
class RestartRecord:
    reason: str
    at: str
    exit_code: int | None
    stage_before: int
    stage_after: int | None
    recovery_seconds: float | None

@dataclass
class SoakResult:
    status: str
    restarts: list[RestartRecord]
    verification: RunVerification
    wall_seconds: float
    field_run_satisfied: bool
    session: list[dict] = field(default_factory=list)

class SoakDriver:
    def __init__(
        self,
        config: SoakConfig,
        *,
        spawn: Callable | None = None,
        clock: Callable[[], float] = ...,
        sleep: Callable[[float], None] = ...,
        kill: Callable[[object], None] | None = None,
    ) -> None: ...
    session: list[dict]
    def run(self) -> SoakResult: ...
```

```python
# researchclaw/soak/report.py
def build_report(result, session, config, *, reference_signature=None) -> dict: ...
def render_markdown(report: dict) -> str: ...
def write_report(run_dir, report: dict) -> tuple[Path, Path]: ...
```

```python
# researchclaw/cli.py
def parse_duration(text: str) -> float: ...
def cmd_soak(args: argparse.Namespace) -> int: ...
def cmd_soak_run(args) -> int: ...
def cmd_soak_verify(args) -> int: ...
def cmd_soak_report(args) -> int: ...
```

## 3. 关键算法

### 3.1 `event_seq_coverage`

```
seqs = [int(e["seq"]) for e in events if int-able]
duplicates = sorted({s for s in seqs if count(s) > 1})
first = min(seqs) if seqs else 0
last = max(seqs) if seqs else 0
gaps = [s for s in range(first, last + 1) if s not in set(seqs)]
return tuple(gaps), tuple(duplicates)
```

- 内部缺口才是失败；`first > 1` 单独由 `retention_limited` 表达，避免把 30 天保留策略误报成“几千个缺口”。

### 3.2 `verify_run` 判定顺序

1. `run_dir` 不存在 → `problems=("run_dir_missing",)`，直接返回（不构造 `EventLog`，避免 mkdir 写）。
2. 读 checkpoint/summary；构造 `EventLog`；`read_all()`；`verify_chain()`。
3. `event_seq_coverage`；`run_id` 检查；`read_after(probe)` 游标检查。
4. `max_completed_stage`、`checkpoint_stage` 一致性：只判 `checkpoint_stage < max_completed_stage`（落后）；领先差值写入 `event_checkpoint_skew`（checkpoint 权威）。
5. `terminal_status` 与 `convergence_signature`。
6. 有参考 → 签名相等；无参考 → 终态完成 + 链/seq/checkpoint 全过。
7. `ok = not problems`；`converged` 见 DESIGN §4.3。

### 3.3 `SoakDriver.run`

> 收敛签名按 DESIGN v1.1 D-4 使用**终态三字段**；`completed_stages` 只作为报告诊断，不参与 `converged` 判定。

```
result.status = "failed"
while True:
    spawn worker
    while worker alive:
        if wall >= duration: kill; status=timed_out; break
        state = read checkpoint/heartbeat/event last_seq
        if progress changed: last_progress = wall
        target = smallest unconsumed inject_at_stages <= checkpoint_stage
        if target and wall - last_restart >= min_interval:
            kill; wait; reclaim lease; record; continue outer
        sleep(poll_seconds)
    if worker exited:
        rc = proc.returncode
        if rc == 0: break
        if rc == 75 and restarts < max_restarts: backoff; continue
        if rc != 0 and last_exit_was_injected: continue
        status = "failed"; break
verify = verify_run(...)
converged = verify.converged
status = "passed" if converged else "failed"
```

- 注入后的退出不按 `rc` 判定失败：注入是主动杀，`rc` 可能是 1/负值；记录 `reason="injected"`。
- 注入预算与可重试重启合并计数；达到 `max_restarts` 后不再注入，但允许 worker 跑完（`capped=True` 写入报告）。
- 若没有观察到任何进度就到达 `duration` → `timed_out`，不把“没启动”误判为“不收敛”。

### 3.4 恢复耗时

```
killed_at = clock()
...
first_progress_at = first time (checkpoint_stage > stage_before) or (heartbeat_ts > killed_heartbeat_ts)
recovery_seconds = first_progress_at - killed_at
```

- 重启后进程直接退出且无进度 → `None`；报告单独计 `missing`。
- `statistics.median` 只在非空列表上调用。

## 4. 源码锚点（实施前 HEAD `284e105`）

| 锚点 | 用途 |
|---|---|
| `researchclaw/runtime/event_log.py:170-201` | `_refresh` 需增加归档段回退 |
| `researchclaw/runtime/event_log.py:223-235` | `_roll_if_needed` 的 `os.replace` 边界 |
| `researchclaw/runtime/event_log.py:306-320` | `read_all` 的坏行容忍（F-3） |
| `researchclaw/runtime/event_log.py:326-355` | `verify_chain` 复用 |
| `researchclaw/runtime/event_log.py:446-466` | `rebuild_checkpoint` 复用 |
| `researchclaw/pipeline/runner.py:378-393` | `_recover_checkpoint_from_events` 守卫（F-2） |
| `researchclaw/pipeline/runner.py:172-201` | 新增 `_replace_with_retry`（D-11） |
| `researchclaw/runtime/supervisor.py:33-37` | `full_jitter` 复用 |
| `researchclaw/runtime/lease.py:78-108,251-288` | `read_lease/release/is_pid_alive` 复用 |
| `researchclaw/cli.py:1710-1716,1931-1934` | CLI 子命令与 dispatch 插入点 |

## 5. 测试用例（TDD：先红后绿）

| ID | 文件 | 用例 | 期望（绿） | 负向 |
|---|---|---|---|---|
| T01 | `test_soak_verifier.py` | 有效 run（事件+checkpoint+summary） | `ok=True, chain_ok=True, converged=True` | — |
| T02 | 同上 | 篡改 active 中间行 | `chain_ok=False`，含 `payload_sha256` | 误判 ok |
| T03 | 同上 | seq 缺口（删中间行） | `seq_gaps` 非空，`ok=False` | 缺口被忽略 |
| T04 | 同上 | 篡改 `run_id` | `run_id_mismatches` 非空 | 跨 run 事件被接受 |
| T05 | 同上 | checkpoint 落后事件 | `problems` 含 `checkpoint_behind_events` | 静默通过 |
| T06 | 同上 | 轮转 3 段 + `read_after` | `read_all`/游标一致，`seq_gaps=()` | 归档漏读 |
| T07 | 同上 | 参考签名不同 | `converged=False`，含字段差异 | 误判收敛 |
| T08 | `test_event_log_roll_recovery.py` | F-1：轮转后删 active，重开再 append | `last_seq=2`，append 得 3，`verify_chain` ok | 重开 seq=0 / 断链 |
| T09 | 同上 | F-2：归档-only + checkpoint 缺失 | `read_checkpoint` 返回下一阶段，写 `recovered=true` | 返回 None |
| T10 | `test_soak_driver.py` | 基线 vs 3 次注入的 fake worker | 签名相等，`restarts=3`，`converged=True` | 任一次不收敛 |
| T11 | 同上 | 注入 4 个阶段、`max_restarts=2` | 只注入 2 次，`capped=True`，仍收敛 | 超预算重启 |
| T12 | 同上 | worker 以 65 退出 | 不重启，`status=failed` | 对数据错误重启 |
| T13 | 同上 | 杀进程后残留租约 | driver 只回收死/过期租约，下一次可启动 | 双写/LeaseBusy |
| T14 | 同上 | 报告字段 | 含 restart/recovery/failure/verification/requirements | 缺字段 |
| T15 | 同上 | `parse_duration("72h"/"90m"/"5s"/"7")` | 259200/5400/5/7 | 解析错误 |
| T16 | 同上 | `soak verify` CLI 退出码 | 0 通过 / 1 失败 / 2 输入错误 | 退出码错 |
| T17 | `test_event_log_roll_recovery.py` | F-1b：append 后写坏尾行，重开再 append | 坏尾被截断，`read_all` 见 [1,2]，链 ok | 新事件被坏行遮蔽 |
| T18 | `test_soak_verifier.py` | F-4 崩溃窗口：checkpoint 领先 1 条事件 | `event_checkpoint_skew=1`，`ok=True`，`converged=True` | 误判不收敛 |
| T19 | `test_checkpoint_atomic.py` | `Path.replace` 前两次抛 `PermissionError` | 第 3 次成功，checkpoint 落盘，无 `.tmp` | 首次失败即崩 |
| T20 | `test_soak_driver.py` | run 目录不存在 | `status=failed` + `run_dir_missing`，不创建目录 | 静默新建 |
| T21 | 同上 | `duration=0.06s` + 8 阶段 worker | `status=timed_out`，不判收敛 | 超时后伪造收敛 |
| T22 | 同上 | 活 PID 租约 + `lease_timeout=0.05` | `lease_held`，不启动 worker | 抢活租约 |
| T23 | 同上 | 已有 `soak_report.json`，删 Markdown | `soak report` 重渲染，不重跑 worker | 依赖 worker 重跑 |

### 5.1 测试 fixture（fake worker）

`tests/test_soak_driver.py` 在 `tmp_path` 写 `fake_worker.py`，由 `sys.executable` 运行：

```python
# 伪代码（测试内字符串）
run_dir = Path(sys.argv[1]); total = int(sys.argv[2])
lease = acquire(run_dir, owner="fake:%d" % os.getpid(), ttl=60)
log = EventLog(run_dir, run_dir.name, fencing=lease.fencing)
log.append("run.started", {"fake": True})
start = 1
cp = run_dir / "checkpoint.json"
if cp.exists(): start = json.loads(cp.read_text())["last_completed_stage"] + 1
for stage in range(start, total + 1):
    time.sleep(0.04)
    # 与真实 runner 同序：先写 checkpoint，再发 stage.completed（runner.py:950-953）
    atomic_write(cp, {"last_completed_stage": stage, "last_completed_name": "S%d" % stage,
                      "run_id": run_dir.name, "timestamp": now()})
    log.append("stage.completed", {"name": "S%d" % stage, "stage": stage}, stage=stage)
    atomic_write(run_dir / "heartbeat.json", {"pid": os.getpid(), "last_stage": stage,
                  "last_stage_name": "S%d" % stage, "run_id": run_dir.name, "timestamp": now()})
write pipeline_summary.json {"run_id": ..., "final_status": "done", "final_stage": total, ...}
release(run_dir, lease); sys.exit(0)
```

- 每次重启都会追加 `run.started`，与真实 runner 一致。
- 被硬杀时不执行 `release`，由 driver 的 `_reclaim_stale_lease` 回收，覆盖 J-9。

## 6. 低效排除表

| 低效操作 | 排除理由 | 替代 |
|---|---|---|
| 在 CI 跑 72h | 仓库 CI `timeout-minutes` 最大 30；托管 runner 上限 360 分钟 | 缩时演练 + 现场报告 |
| 每轮 poll 全量 `read_all()` | O(事件数) × 72h | 只读 `checkpoint`/`heartbeat`/`last_seq`；终态才 `read_all` |
| 对 `pipeline_summary.json` 整体哈希 | 含 `generated` 时间戳，重启必变 | 四字段签名 |
| 为 soak 新建第二套事件日志 | 双写、假绿 | 复用 `EventLog` |
| 用 `Popen.terminate()` 当“优雅停止” | Windows 上是 `TerminateProcess`，不跑清理 | 明确标为硬杀；等待退出 + 回收死租约 |
| 纯 wall-clock 注入 | 慢机器上在 checkpoint 前杀，产生假失败 | 阶段边界 + 进度前置 |
| 在 `verify_run` 里 `mkdir` | 违反只读 | 先判断 `run_dir` 存在 |
| 失败后自动无限重试 | 隐藏失败（RESEARCH §4.1 E2） | `max_restarts` 硬上限 + 报告 `capped` |
| 吞掉 `PermissionError` 或直接放弃 checkpoint 写 | 静默丢状态，比崩溃更难查 | 5×50ms 重试；用尽后重抛 |
| 只标记 torn tail 不截断 | 后续事件永久不可见 | 截断到最后完整行再 append |

## 7. 版本与兼容性核验（Step 6）

| 项 | 核验 |
|---|---|
| Python 下限 | `pyproject.toml` `requires-python = ">=3.11"`；本批只用 3.11 可用的 stdlib |
| 新增三方依赖 | 无 |
| `dataclasses`/`statistics`/`subprocess`/`gzip`/`hashlib`/`os.replace` | 均为 stdlib，3.11 可用 |
| `subprocess.run(capture_output=True)` | 3.7+ |
| Windows `taskkill` | 系统自带；`evidence/sidecar.py:110` 与 `experiment/code_agent.py:428` 已有同用法 |
| 既有 `EventLog` API | `append/read_all/read_after/verify_chain/rebuild_checkpoint` 签名不变 |
| 既有 `Supervisor` API | 不变；soak 只 import `full_jitter` |
| CLI 兼容性 | 只新增 `soak` 子命令；既有命令不变 |

## 8. 红 → 绿计划

| 轮次 | 动作 | 预期读数 |
|---|---|---|
| R1 | 先写 T01–T23（不写实现） | `ModuleNotFoundError: researchclaw.soak`；F-1/F-1b/F-2 用例失败 |
| R2 | 实现 F-1/F-1b/F-2/F-4 | T08/T09/T17/T19/T20/T22 green；既有 `test_event_log.py` green |
| R3 | 实现 verifier | T01–T07/T18 green |
| R4 | 实现 driver/report/CLI | T10–T16/T21/T23 green |
| R5 | 回归 | `test_event_log/test_supervisor/test_lease/test_rc_executor/test_cli_*` green |
| R6 | 门禁 | dc / grandfather / step-gate / verify-anchor / step_enforce / pre-commit 全绿；CI 两轮 |

> 红相读数必须写进 §10；禁止“测试全过但无失败记录”。

## 9. 回退点（与 DESIGN §9 对齐）

| 编号 | 回退动作 |
|---|---|
| R-1 | 删除 `researchclaw/soak/`、CLI `soak` 分支、3 个测试文件 |
| R-2 | 回退 `EventLog._refresh` 的归档段回退分支 |
| R-3 | 回退 `runner` 的 glob 守卫 |
| R-4 | 删除 `soak_report.*` 与文档 |

## 10. 实施读数（Step 9 后回填）

| 项 | 读数 |
|---|---|
| 红相 | 2 个收集错误：`ModuleNotFoundError: researchclaw.soak`、`ImportError: parse_duration`；2 个行为失败：F-1 `last_seq=0`（期望 2）、F-2 `read_checkpoint=None`（期望 stage 3） |
| 绿相 | 新增 27 passed in 5.87s；T08/T09/T17/T19 边界全绿；T10 3 次硬杀后与 baseline 终态签名相等 |
| 回归 | `test_rc_executor` 207 passed（249.96s）；`test_event_log` 16 passed；runtime/CLI 56 passed；`test_rc_runner/checkpoint/sentinel/hitl` 92 passed + 1 环境失败（`bash -n` 的 Windows 路径转换，非本批）；`test_boundary_coverage` 17 passed（首轮 2 failed → 登记 S-061/S-062 后绿） |
| 全量（本机 3.13） | 3866 passed / 108 skipped / 8 failed；8 项中 2 项为本批边界登记缺失（已修），余 6 项为环境：memory Keras3×4、hitl `.sh` WinError 193×1、sentinel bash 路径×1；CI Linux 需复核 |
| 门禁 | dc_validator 四文档 0 违规；grandfather 0/0/0；repo_stats/console_gen 一致；blackbox module ok；step-gate 5/5；step_enforce digest_bound=1；pre-commit/CI 待跑 |
| CI | 待两轮 |

## 11. Review 记录（Step 6，自查·单视角）

> **RULE-4**：本节与正文同一会话，属自查（单视角）；未经异构基座复审。

| 检查项 | 结论 |
|---|---|
| 依赖版本真实存在 | 无新增依赖；stdlib 3.11 可用 |
| 签名可实现 | 所有 dataclass/函数均为 stdlib 组合；无虚构库 |
| 与 DESIGN 对齐 | D-1..D-10 均有落点；F-1/F-2 锚点与 DESIGN §5 一致 |
| 低效排除 | §6 非空，8 项 |
| 回退点 | §9 四项，均有可执行动作 |

## 12. 派生需求登记（Step 8）

| 编号 | 派生需求 | 来源 | 验收 |
|---|---|---|---|
| DR-1 | `lease_clear_timeout_seconds=10.0`：杀进程后最多等 10s 让死租约可回收；超时则报告 `lease_held`，不再盲目重启 | J-9；DESIGN §4.1 未给常量 | T13 |
| DR-2 | worker stdout/stderr 落 `soak_worker.out.log`/`soak_worker.err.log`（追加写） | 现场排障需要；DESIGN 未给文件名 | T10 后检查文件存在 |
| DR-3 | 注入预算耗尽且仍有未消费目标时，记录 `restart_capped` 会话事件 + 报告 `capped=true` | D-6 硬上限的可见性 | T11 |
| DR-4 | 游标探测点取 `max(1, last_seq//2)`，只做一次 `read_after` 对比 | P-1 成本约束；DESIGN §4.4 未给探测点 | T06 |

