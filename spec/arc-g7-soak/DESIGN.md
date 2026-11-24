---
id: arc-g7-soak-DESIGN
type: design
version: 1.2
status: verified
date: 2026-11-24
depends: [arc-g7-soak-RESEARCH, arc-g1-readiness-research]
upstream: arc-master-roadmap
---

# 设计：G7 第一段「soak 工具链」（P-160）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **变更面**：新增 `researchclaw/soak/`（driver/verifier/report）与 `soak` CLI；修复 `EventLog` 轮转边界恢复与 `runner` 的归档-only checkpoint 恢复；新增测试与报告模板。
> **本段定位**：A7-1 的**工具链 + 缩时演练**、A7-4 的**完整验收**；不包含 A7-2/A7-3/A7-5/A7-6/A7-7、FA、OB。
> **修订**：v1.1（2026-11-24，Step 6 反馈）D-4 收敛签名从“终态 + 完整阶段序列”改为**终态三字段**（状态/阶段/名称）；阶段序列保留为报告诊断。理由：runner 先写 checkpoint（`runner.py:950`）再发 `stage.completed`（`:951-953`），两者之间崩溃会永久缺失一条阶段事件，序列签名会把“同终态”误报为“不收敛”。A7-1 的原文是“收敛到同一终态”，终态三字段与判据一致。
> **修订**：v1.2（2026-11-24，Step 9 实施发现）新增 D-11（原子替换重试）与 J-10；D-7 扩展为 active 缺失/为空/**torn tail** 三种边界。依据：RESEARCH v1.1 F-1b/F-4 实测；fake worker 在 Windows 并发读下 `WinError 5` 崩溃，修复后通过。

---

## 1. 决策

| 编号 | 决策 | 被拒绝的替代方案 | 拒绝理由 / 代价 |
|---|---|---|---|
| D-1 | 本段只做 soak 工具链：driver + verifier + report + 轮转边界修复 | 把并发/双平面/漂移一起做 | 一个 PR 无法同时证明四类不变量；验收面混在一起会重演“一个批次多个 P 编号”的问题。代价：G7 仍需后续两段 |
| D-2 | 新建 `SoakDriver`，**不修改** `Supervisor` 的重启条件 | 在 `Supervisor` 上加“任何退出都重启” | 会改变生产退出码契约（75 才可重试），测试语义污染运行时。代价：driver 需要自己实现进程管理 |
| D-3 | 注入点用**阶段边界**（`inject_at_stages`），并要求“已观察到进度”才注入 | 纯 wall-clock 定时杀 | 墙钟在慢机器/LLM 抖动下不可复现，容易在 checkpoint 写入前杀，产生“假不收敛”。代价：需要真实运行至少经过这些阶段 |
| D-4 | 收敛签名 = `final_status + last_completed_stage + last_completed_name`（终态三字段） | 对 `pipeline_summary.json` 整体哈希 / 终态 + 完整阶段序列 | 整体哈希含 `generated` 时间戳；完整序列会因“checkpoint 已写、`stage.completed` 未写”的崩溃窗口永久缺一条事件，把同终态误报为不收敛。代价：签名不覆盖完整路径；路径作为报告诊断保留 |
| D-5 | 回放校验 = `verify_chain` + `seq` 覆盖 + `run_id` 一致 + `read_after` 游标 | 只调 `read_all()` 非空 | `read_all` 对归档段单条坏行会静默跳过（RESEARCH F-3）。代价：校验器需要组合多个检查 |
| D-6 | 报告同时产出 JSON（主格式）与 Markdown（人读） | 只产出 Markdown | 后续看板/CI 需要机读；Markdown 只做渲染。代价：两处字段需保持一致 |
| D-7 | F-1 修复：active 缺失/为空时，从**最后一个归档段最后一行**恢复 `last_seq/last_hash`；torn tail 在 `_refresh` 中截断到最后一个完整行 | 只从段名 `events.<first>-<last>` 取 `last` / 只标记 `truncated` 不截断 | 段名给不出 `last_hash`；不截断会让后续 append 被 `read_all` 永久遮蔽。代价：恢复时需读一个段的末行 + 一次截断写 |
| D-8 | F-2 修复：`runner` 的恢复前置从“active 存在”放宽为“active 或任一轮转段存在” | 新增 `EventLog.has_events()` 公共 API | 只需一处守卫，新增公共 API 是过度设计。代价：runner 里出现一次 glob |
| D-9 | `soak run` 写增量 `soak_session.jsonl` + 终态 `soak_report.json/.md`；`soak report` 可离线重渲染 | 只在内存里保留结果 | driver 自身被杀时，重启次数与恢复耗时不能丢。代价：多一个会话日志格式 |
| D-10 | 72h 现场运行**不纳入 CI**；报告用 `field_run.satisfied` 区分“工具链通过”与“现场未跑” | 在 CI 跑 72h | 仓库 CI 最大 `timeout-minutes: 30`；托管 runner 单 job 上限 360 分钟。代价：A7-1 现场证据需单独留证 |
| D-11 | checkpoint/heartbeat 的 `os.replace` 增加**有限重试**（5 次 × 50ms），只重试 `PermissionError`，最终仍失败则抛出 | 去掉 driver 的 checkpoint 轮询 / 吞掉错误 | 轮询是恢复耗时与注入门控所需；吞错会静默丢失 checkpoint。代价：Windows 上最坏多等 200ms |

## 2. 模块划分

| 模块 | 职责 | 不负责 |
|---|---|---|
| `researchclaw/soak/driver.py` | 启动 worker、按阶段注入硬杀、等待退出、回收死租约、记录重启/恢复耗时、写入会话日志 | 不写事件日志、不持租约、不判断业务阶段内容 |
| `researchclaw/soak/verifier.py` | 只读校验 run 目录：链、seq 覆盖、run_id、checkpoint/事件一致性、收敛签名、与基线对照 | 不修复、不写文件 |
| `researchclaw/soak/report.py` | 将会话记录 + 校验结果渲染为 JSON/Markdown，原子写入 | 不重新运行、不推断缺失读数 |
| `researchclaw/runtime/event_log.py` | F-1：轮转边界恢复 | 不改写入热路径 |
| `researchclaw/pipeline/runner.py` | F-2：归档-only checkpoint 恢复；D-11：checkpoint/heartbeat 原子替换重试 | 不改阶段逻辑 |
| `researchclaw/cli.py` | `soak run/verify/report` 子命令与退出码 | 不承载业务逻辑 |

## 3. 数据模型

```python
# researchclaw/soak/driver.py
@dataclass(frozen=True)
class SoakConfig:
    run_dir: Path
    worker_cmd: tuple[str, ...]
    duration_seconds: float = 72 * 3600
    max_restarts: int = 3
    inject_at_stages: tuple[int, ...] = ()      # 空 = 不主动注入
    poll_seconds: float = 5.0
    min_restart_interval_seconds: float = 10.0
    worker_exit_timeout_seconds: float = 30.0
    reference_run_dir: Path | None = None
    config_path: str | None = None

@dataclass(frozen=True)
class RestartRecord:
    reason: str                  # "injected" | "retryable_exit"
    at: str                      # ISO-8601 UTC
    exit_code: int | None
    stage_before: int
    stage_after: int | None
    recovery_seconds: float | None

@dataclass
class SoakResult:
    status: str                  # "passed" | "failed" | "timed_out" | "restarts_exhausted"
    restarts: list[RestartRecord]
    verification: RunVerification
    wall_seconds: float
    field_run_satisfied: bool    # wall >= 72h 且 restarts >= 3
```

```python
# researchclaw/soak/verifier.py
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
    event_checkpoint_skew: int          # checkpoint_stage - max_completed_stage（诊断）
    completed_stages: tuple[int, ...]
    terminal_status: str
    convergence_signature: dict
    reference_signature: dict | None
    converged: bool
    retention_limited: bool
```

## 4. API

```python
# verifier.py
def verify_run(run_dir, *, expected_run_id=None, reference_run_dir=None) -> RunVerification
def convergence_signature(run_dir) -> dict
def read_terminal_status(run_dir) -> str
def event_seq_coverage(events) -> tuple[tuple[int, ...], tuple[int, ...]]  # (gaps, duplicates)

# driver.py
class SoakDriver:
    def __init__(self, config: SoakConfig, *, spawn=None, clock=time.monotonic, sleep=time.sleep, kill=None): ...
    def run(self) -> SoakResult: ...

# report.py
def build_report(result: SoakResult, session: list[dict], config: SoakConfig) -> dict
def render_markdown(report: dict) -> str
def write_report(run_dir, report: dict) -> tuple[Path, Path]
```

### 4.1 Driver 循环

1. 校验 run 目录存在；空目录视为新 run，由 worker 初始化（不要求预先有 checkpoint）。
2. 记录 `driver_started`；循环直到终态/超时/预算耗尽：
   - spawn worker；记录 `worker_started`（pid、attempt）。
   - 轮询：读 `checkpoint.json`、`heartbeat.json`、`EventLog.last_seq`、`read_run_state`。
   - 若 `stage` 命中 `inject_at_stages`、尚未注入该阶段、且 `now - last_restart >= min_restart_interval`：
     - 记录 `restart_injected`（pre-kill stage）；
     - 硬杀进程树（Windows `taskkill /F /T /PID`，POSIX `proc.kill()`）；
     - 等进程退出；`_reclaim_stale_lease()`；
     - 记录 `worker_exited`，进入下一轮。
   - 若 worker 自行退出：
     - `rc == 0` → 记录 `worker_exited`，退出循环；
     - `rc == 75` 且预算未耗尽 → 按 full jitter 退避后重启（`reason="retryable_exit"`）；
     - 其他 `rc` → 终止，`status="failed"`。
   - 若 `wall >= duration` → 硬杀并终止，`status="timed_out"`。
3. 终态校验：`verify_run(...)`；`converged = verification.converged`。
4. 写 `soak_session.jsonl` 的 `driver_finished`；返回 `SoakResult`。

### 4.2 恢复耗时口径

- `recovery_seconds` = “第一次观察到 `checkpoint` 前进或 `heartbeat.timestamp` 晚于杀点” − “杀点”。
- 若重启后 worker 直接退出且没有进度，`recovery_seconds=None`，并计入 `recovery_missing`。
- 报告给出 `count/min/median/max/values`；不把 `None` 当 0。

### 4.3 收敛签名与对照

```python
signature = {
    "final_status": normalized_status,       # done/completed/failed/paused/unknown
    "last_completed_stage": int,             # checkpoint 终态阶段
    "last_completed_name": str,              # checkpoint 终态名称
}
# 诊断字段（不进签名）：completed_stages = stage.completed 的完整序列
```

- `normalized_status` 来自 `pipeline_summary.final_status`；缺失时回退 `checkpoint.status`；再缺失回退 `read_run_state().status.value`。
- 有 `reference_run_dir`：`converged = signature == reference_signature`；不等时 `problems` 列出逐字段差异。
- 无参考：`converged = chain_ok and not seq_gaps and not duplicate_seqs and terminal_status in {"done","completed"} and checkpoint_stage >= max_completed_stage`；`reference_signature=None`，报告标 `reference_missing=true`。
- 阶段序列 `completed_stages` 写入报告，用于解释 PIVOT/重入与失败分布；**不参与**终态等价判定。
- `event_checkpoint_skew = checkpoint_stage - max_completed_stage` 作为诊断字段；checkpoint 是权威（EventLog I-1），“checkpoint 领先事件”是已知崩溃窗口，不判失败；“checkpoint 落后事件”判 `checkpoint_behind_events`。

### 4.4 回放校验

| 检查 | 判据 | 失败输出 |
|---|---|---|
| 链 | `EventLog.verify_chain()` | `chain_message` |
| seq 覆盖 | `sorted(seqs) == list(range(1, last+1))`；`last_seq>=1` | `seq_gaps` / `duplicate_seqs` |
| run_id | 每条事件 `run_id == run_dir.name`（或 `expected_run_id`） | `run_id_mismatches` 的 seq 列表 |
| 游标回放 | `read_after(k)` 的 seq 严格递增且等于 `read_all()` 的后缀 | `cursor_mismatch` |
| 轮转可读 | `segments` 非空时，`read_all` 含 `first_seq..last_seq` | `archive_unreadable` |
| checkpoint 一致 | `checkpoint_stage >= max_completed_stage`；差值写入 `event_checkpoint_skew`（诊断） | `checkpoint_behind_events` |
| 保留删除 | `first_seq > 1` 且无 `events.1-*` 段 | `retention_limited=true`（72h 默认视为失败，除非显式 `allow_retention_gap=True`） |

## 5. F-1 / F-2 修复设计

### 5.1 F-1：`EventLog._refresh`

当前逻辑只在 active 存在时设置 `_last_seq/_last_hash`。新增回退：

```
if active exists and has >=1 valid line:
    use active last line
elif segments exist:
    last_seg = segments[-1].path
    last_line = last valid JSON line of last_seg
    if no valid line: raise EventDurabilityError(...)
    _last_seq = last_line["seq"]
    _last_hash = sha256(last_line_text)
    _seg_first = None
else:
    _last_seq = 0; _last_hash = ZERO_HASH
```

- 只读一个归档段，不扫描全部段；恢复成本有界（段上限 8 MiB）。
- 归档段可能是 `.gz`：用 `gzip.open(..., "rt")` 流式读到末行，内存 O(1)。
- 不改变 active 的 torn-tail 语义（仍丢弃并 `truncated=True`）。

### 5.2 F-2：`runner._recover_checkpoint_from_events`

```
if not events_path.exists() and not any(run_dir.glob("events.*.jsonl*")):
    return None
```

- 其余逻辑不变；`EventLog.read_all()` 已能读归档段。
- `rebuild_checkpoint` 仍要求至少一条 `stage.completed`；否则返回 `None`。

### 5.3 F-1b：torn tail 截断

- `_refresh` 检测到 active 中的第一条坏行后，保留其前的完整行，写 `events.jsonl.tmp`，`fsync`（受 `fsync` 开关控制），`os.replace`。
- 若没有完整行，写空文件；随后从归档段恢复 `last_seq/last_hash`。
- 截断失败抛 `EventDurabilityError`，不静默继续（否则后续 append 仍会写进坏文件）。

### 5.4 F-4 / D-11：原子替换重试

- `runner._replace_with_retry(tmp, target, attempts=5, delay=0.05)`：只捕获 `PermissionError`；成功即返回；用尽后重抛最后一次异常。
- 用于 `_write_checkpoint`、`_write_heartbeat`、`_write_recovered_checkpoint`。
- 不重试其他 `OSError`（磁盘满、权限永久拒绝等应快速失败）。

## 6. 报告格式

### 6.1 JSON（`arc-soak-report/1`）

```json
{
  "schema": "arc-soak-report/1",
  "run_id": "...",
  "started_at": "...",
  "ended_at": "...",
  "wall_seconds": 0,
  "config": {
    "duration_seconds": 259200,
    "max_restarts": 3,
    "inject_at_stages": [3, 7, 11],
    "poll_seconds": 5,
    "reference_run_dir": "..."
  },
  "restart_count": 0,
  "injected_restarts": 0,
  "unexpected_restarts": 0,
  "restarts": [
    {"reason": "injected", "at": "...", "exit_code": 1, "stage_before": 3,
     "stage_after": 4, "recovery_seconds": 2.5}
  ],
  "recovery_seconds": {"count": 0, "min": null, "median": null, "max": null, "values": []},
  "failure_stages": {"5": 2},
  "verification": {"ok": true, "chain_ok": true, "seq_gaps": [], "...": "..."},
  "reference": {"signature": {}, "match": true},
  "converged": true,
  "status": "passed",
  "field_run": {"required_wall_seconds": 259200, "required_restarts": 3, "satisfied": false}
}
```

### 6.2 Markdown 模板

固定七节：`Summary`、`Run`、`Restarts`、`Recovery`、`Failure stages`、`Event replay`、`Convergence & verdict`。每节表格字段来自 JSON；缺失值写 `n/a`，**不推断**。

## 7. 不变式

| 编号 | 不变式 |
|---|---|
| J-1 | soak driver 不获取 run 租约；worker 是唯一事件写者 |
| J-2 | `verify_run` 只读，不修改 run 目录 |
| J-3 | 任意重启后 `seq` 严格递增、无重复、链可校验 |
| J-4 | 收敛签名不含时间戳、run_id、重试次数等易变字段 |
| J-5 | 非注入的意外退出只在 `rc==75` 时重启；其他 `rc` 不重启 |
| J-6 | `max_restarts` 是硬上限，注入与可重试重启合并计数 |
| J-7 | 报告以 `tmp + os.replace` 原子写入，失败不留半文件 |
| J-8 | `field_run.satisfied` 只在 `wall>=259200` 且 `restarts>=3` 时为 true |
| J-9 | Windows 注入是硬杀；driver 等进程退出，只回收“可证明已死/已过期”的租约 |
| J-10 | checkpoint/heartbeat 的原子替换对**瞬时** `PermissionError` 有限重试；永久失败仍抛出，不静默丢状态 |

## 8. 验收映射

| ID | 落点 | 本段状态 |
|---|---|---|
| A7-1 | driver 注入 ≥3 次、缩时演练收敛；报告字段完整 | **工具链 + 缩时演练通过；72h 现场运行 pending（U-1）** |
| A7-4 | 轮转/压缩后 `read_all`、`read_after`、`verify_chain` 全量通过；轮转边界重启后可继续写 | **完整通过（测试）** |
| A7-2/A7-3/A7-5/A7-6/A7-7 | 不在本段 | 未开始 |
| FA-1..3 / OB-1..5 | 不在本段 | 未开始 |

## 9. 回退点

| 编号 | 回退动作 | 影响面 |
|---|---|---|
| R-1 | 删除 `researchclaw/soak/`、`soak` CLI 分支与测试 | 零运行时影响；回到 P-159 行为 |
| R-2 | 回退 `EventLog._refresh` 回退分支与对应测试 | 轮转边界恢复回到旧缺陷；其余不变 |
| R-3 | 回退 `runner._recover_checkpoint_from_events` 的 glob 守卫 | 归档-only 恢复回到旧缺陷 |
| R-4 | 回退报告模板/文档 | 只影响可读性，不影响运行 |

## 10. 非目标（职责边界）

- **职责外**：并发隔离（A7-2）、双平面（A7-3）、worker slot（A7-7）、漂移护栏（FA）、编排评测（OB）——各有独立验收面，不在本设计吞并。
- **能力边界**：本设计不能证明“任何 72h 现场运行都会收敛”；它只提供可重复的工具与机械判据。现场运行的证据必须由真实 `soak_report.json` 提供。

## 11. Review 记录（Step 4，自查·单视角）

> **RULE-4**：本节与正文同一会话，属自查（单视角）；未经异构基座复审。

| 检查项 | 结论 |
|---|---|
| 设计基于已验证调研 | D-2/D-3/D-6 对应 RESEARCH §4.2/§5.1；D-7/D-8 对应 §3.2 实测缺陷 |
| 无未经验证假设 | 72h 现场未跑 → U-1；基线来源 → U-2；均未写成已实现 |
| 无归因扭曲 | 未把 etcd/Chaos Mesh 的社区案例当作 ARC 正确性证据；只用于陷阱 |
| 替代方案 ≥2 并被否决 | D-2/D-3/D-4/D-6/D-7 均列出替代与代价 |
| 职责边界 | §10 区分“职责外”与“能力边界” |

## 12. 未决项（承接 RESEARCH U-1..U-4）

| 编号 | 判据 | 触发条件 | 当前倾向 | 证据 |
|---|---|---|---|---|
| U-1 | `soak_report.json` wall≥72h、restarts≥3、converged=true | 有独占主机时 | 本段只交付脚本；现场单独留证 | E5 |
| U-2 | 存在无注入 baseline 且签名相等 | 首次真实 soak 前 | baseline 先行 | E4 |
| U-3 | 注入以进度为前置，fixture 可复现 | Step 9 | 阶段边界 + 最小间隔 | E4 |
| U-4 | 生产 supervisor 契约不变 | Step 9 | 只复用 `full_jitter` | E3 |
