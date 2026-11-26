# ARC 长跑进度回传与停滞检测调研（2026-11-26）

> **性质**：Layer-0 调研（候选 T3），零代码 / 零 session / 零门禁变更。本文只做取证、对比与方案比较，不构成实施承诺。
> **触发**：P-192（B-30）重跑 Stage 10-12 期间，出现「磁盘已推进到第 3 次沙箱执行，但 `heartbeat.json` 停留在 17 小时前、重定向日志 208 字节、事件链 20 分钟无新增」的现象。
> **取证窗口**：2026-11-26 15:27–15:58（Asia/Shanghai，即 07:27–07:58 UTC），单次快照，非时序采样。
> **取证环境**：
> - 本地仓 `d:\AutoResearchClaw-main\AutoResearchClaw-main`（HEAD `56b3dde` + P-192 未提交改动）；
> - B 站 `scott-lau@scott-lau-GTR-Pro.local`，run 目录 `~/arc-runs/g7-baseline`，tmux `p192-stage12`。
> **方法**：E1 现场文件采样 / E2 读码锚点 / E3 外部一手文档（访问日期 2026-11-26）。外部资料仅作模式对照，未做行为复现实验。
> **边界**：① 未修改任何源码或运行配置；② `agent_runs` / `cost_log.jsonl` 作为「事实上的进度侧信道」属读码 + 采样推断，未被任何正式观测面消费；③ 快照值会随运行漂移，复现命令见附录 A。

---

## 0. 结论摘要

1. **不是「没有监控」，而是「监控写点绑定在阶段边界」**：`checkpoint.json`、`heartbeat.json`、`stage_health.json`、`code_agent_log.json` 全部在阶段结束后才落盘；阶段进行中，正式观测面是空白的。
2. **仓内确实存在秒级活体信号，但只用来自保**：`lease.json` 每 200 秒续期（`ttl=600` 的 1/3），是当前唯一能证明进程存活的数据，却不含任何业务进度，也没有对 `ops` / dashboard 暴露。
3. **存在两条未门面化的进度侧信道，但可用性不同**：`stage-10/agent_runs/attempt_NNN/`（每次沙箱执行的目录时间戳）能反映**当前进程内**的推进，但计数器随 Stage 10 重入从 001 重置，跨 PIVOT 不可比（§6.2 第 4 条）；`cost_log.jsonl`（每次 LLM 调用一行，带 `stage` 与 `timestamp`）**跨轮可比**，是本轮最可靠的旁证。
4. **日志通路是「双杀」**：仓库内没有任何 `basicConfig/setLevel`，root logger 默认 WARNING，所有 `logger.info` 的进度被丢弃；`print` 的阶段行在重定向到文件后按块缓冲，导致 `> log 2>&1` 阶段内几乎不增长。
5. **判定阈值与阶段时长结构性错配**：dashboard 以 60 秒判活跃、`read_run_state` 以 300 秒判活跃并降级 `UNKNOWN`；而 Stage 10 动辄 1–3 小时，于是 99% 的墙钟时间都被判为「不活跃」。
6. **社区共识可归纳为六条**（Temporal / Airflow / systemd / Lightning / LangGraph / K8s / W&B）：心跳与业务解耦并携带 details、用「心跳间隔的倍数」判停滞、按阶段/步低频采样、多源合成派生视图、状态机显式区分 RUNNING/STALLED/UNKNOWN、输出通道必须可观测。仓内已有 60% 的素材（`LeaseKeeper`、`EventLog`、`run_state`、`collector`、`notifications`），缺的是把它们接成一条链。

---

## 1. 现场事实（E1）

### 1.1 观测面快照（07:48:48Z）

| 观测面 | 实测 | 判读 |
|---|---|---|
| `heartbeat.json` | `pid=181821`、`last_stage=11`、`timestamp=2026-11-25T14:14:37Z` | 滞留 17h34m，pid 是上一轮进程 |
| `events.jsonl` 尾部 | `run.started` → `stage.started(CODE_GENERATION)`，`seq=7`、`fencing=1` | 20 分钟内零新增事件 |
| `/tmp/p192_stage12.log` | **208 字节**，mtime 15:27 | 启动后一行未增 |
| `lease.json` | `owner=...:747630`、`expires_at=07:57:49Z` | 每 200s 续期，唯一真实活体信号 |
| `checkpoint.json` | `last_completed_stage=11`（11-25T14:14Z） | 阶段级，不反映 Stage 10 进行中 |
| `stage-10/agent_runs/` | `attempt_001` 15:39、`attempt_002` 15:40、`attempt_003` 15:44 | 实际进度已到第 3 次沙箱执行 |
| `stage-10/agent_runs/*/main.py` | 3879 B → 3881 B → **8823 B** | 第 3 次产物明显变完整 |
| `cost_log.jsonl` | 238 行；本轮窗口 14 次调用；末条 07:56:15Z，`completion_tokens=16384` | 每次 LLM 调用一行，可反推调用节奏 |

### 1.2 侧信道为何「事实上有效」

- `agent_runs/attempt_NNN/` 由沙箱执行前创建并写入文件（[code_agent.py L1473-1487](../researchclaw/pipeline/code_agent.py#L1473-L1487)），目录 mtime 精确对应每次执行尝试，是当前**最细的磁盘进度**。
- `cost_log.jsonl` 在每次 LLM 调用返回后追加一行，带 `timestamp` / `stage` / token 数，并 `flush()`（[cost_tracker.py L227-237](../researchclaw/cost_tracker.py#L227-L237)、[L37-54](../researchclaw/cost_tracker.py#L37-L54)）。`stage` 由 runner 在阶段开始时注入（[runner.py L807-809](../researchclaw/pipeline/runner.py#L807-L809)）。
- 但两者都不是「进度 API」：前者无 schema、无状态语义、会被下一轮覆盖；后者只有阶段粒度，且只记录「已完成」的调用，不覆盖单次长调用期间的静默。

### 1.3 事实小结

同一时刻，四类正式信号（heartbeat / events / log / checkpoint）一致地指向「不活跃」，而两类非正式信号（agent_runs / cost_log）一致地指向「快速推进」。**观测面与事实相反，且偏差方向是「误判为死」。**

---

## 2. 机制解剖（E2）

### 2.1 状态文件与写入时机

| 文件 | 写入函数 | 调用时机 | 粒度 |
|---|---|---|---|
| `checkpoint.json` | `_write_checkpoint`（[runner.py L192-221](../researchclaw/pipeline/runner.py#L192-L221)） | 阶段 DONE 后（[L971](../researchclaw/pipeline/runner.py#L971)） | 阶段 |
| `heartbeat.json` | `_write_heartbeat`（[L224-244](../researchclaw/pipeline/runner.py#L224-L244)） | **仅** `result.status == DONE`（[L1014-1016](../researchclaw/pipeline/runner.py#L1014-L1016)） | 阶段 |
| `stage_health.json` | 内联写（[executor.py L846-863](../researchclaw/pipeline/executor.py#L846-L863)） | 阶段末（`_write_checkpoint` 之前） | 阶段（事后） |
| `code_agent_log.json` | 内联写（[_code_generation.py L1159](../researchclaw/pipeline/stage_impls/_code_generation.py#L1159)） | Stage 10 结束时一次性写 | 阶段（事后） |
| `stage_events.jsonl` | `append_stage_event`（[stage_events.py](../researchclaw/runtime/stage_events.py)） | Stage 4/5 DONE 后，服务循环守卫 | 文献轮次 |
| `lease.json` | `LeaseKeeper`（[lease.py L291-320](../researchclaw/runtime/lease.py#L291-L320)） | 后台线程每 `ttl/3=200s` | 秒级存活 |

`_write_heartbeat` 全仓只有一个调用点，且被 `if result.status == StageStatus.DONE` 包住；`heartbeat.json` 没有任何「阶段开始」写入路径。这是第一层根因。

### 2.2 事件链：只有阶段边界

`EventLog` 是 append-only、逐行 `flush + fsync`、带 hash 链的可靠通道（[event_log.py L320-359](../researchclaw/runtime/event_log.py#L320-L359)）。但实际发射点只有：

- `run.started`（[runner.py L283](../researchclaw/pipeline/runner.py#L283)）
- `stage.started`（[L794-796](../researchclaw/pipeline/runner.py#L794-L796)）
- `stage.completed / stage.failed`（[L971-979](../researchclaw/pipeline/runner.py#L971-L979)）
- `budget_exhausted`（[llm/client.py L463-481](../researchclaw/llm/client.py#L463-L481)）
- `tool.call / tool.result`（`tools/invoker.py`）

`EVENT_TYPES` 里声明了 `llm.call` / `llm.result`（[event_log.py L37-45](../researchclaw/runtime/event_log.py#L37-L45)），但全仓没有任何生产者——最天然的「每次模型调用」进度点被声明后闲置。

### 2.3 日志通路：级别与缓冲双杀

1. **级别**：`researchclaw` 包内检索 `basicConfig` / `dictConfig` / `setLevel` **零命中**（见附录 A 命令 A-2），root logger 保持默认 WARNING。`CodeAgent._log_event` 走 `logger.info`（[code_agent.py L1551-1554](../researchclaw/pipeline/code_agent.py#L1551-L1554)），因此全部被丢弃；只有 `logger.warning/error`（如 P-191 的入口契约告警）才会出现在日志里。
2. **缓冲**：阶段起止用 `print`（[runner.py L794-795](../researchclaw/pipeline/runner.py#L794-L795)、[L921-937](../researchclaw/pipeline/runner.py#L921-L937)），stdout 在重定向到文件时是块缓冲。208 字节的日志文件是直接证据。
3. **入口无开关**：`run` 子命令没有 `--verbose` / `--log-level`（[cli.py L1764-1825](../researchclaw/cli.py#L1764-L1825)），运维无法在不改代码的前提下提高可见性。
4. **已有进度心跳被同一缺陷静默**：ACP 子进程路径实现了 30 秒一次的进度心跳日志（[acp_client.py L395-462](../researchclaw/llm/acp_client.py#L395-L462)，`"%s still running... %.0fs elapsed"`），但它走 `logger.info`——与第 1 条同一根因，因此**代码层面已有进度回传，只是在默认日志级别下不可见**。这意味着修复日志级别能立即拿到 30s 粒度的 ACP 进度，是 M1 中性价比最高的一项。

### 2.4 租约：唯一秒级活体信号

`_runtime_begin` 在启动 `LeaseKeeper` 时把 `ttl=600` 传入（[runner.py L271-280](../researchclaw/pipeline/runner.py#L271-L280)），keeper 以 `interval = max(1, ttl/3)` 续期（[lease.py L301-320](../researchclaw/runtime/lease.py#L301-L320)）。它解决的是「长 Stage 超过租约 TTL 被第二写者抢占」（R-3 / P-030），不是可观测性；其 payload 只有 `owner/pid/expires_at/fencing`。

### 2.5 判定阈值与状态机

| 消费者 | 活跃判据 | 超时后行为 |
|---|---|---|
| dashboard | `now - heartbeat.timestamp <= 60s`（[collector.py L16-19](../researchclaw/dashboard/collector.py#L16-L19)） | `is_active=False` |
| `read_run_state` | `<= 300s`（[run_state.py L25](../researchclaw/run_state.py#L25)、[L243-L265](../researchclaw/run_state.py#L243-L265)） | 状态降级 `UNKNOWN` |
| `last_update` | `heartbeat_ts or checkpoint_ts`（[L284](../researchclaw/run_state.py#L284)） | 停在上一阶段 |

`read_run_state` 的注释写得很清楚：「Nothing proves the process is alive: a checkpoint alone is not enough.」判定逻辑本身是对的——错的是上游没有在阶段内写心跳。

**两条补充（2026-11-26 复审核实）**

- **枚举面比阈值更严**：`DashboardCollector.collect_all` 与 `/api/projects` 都只枚举 `artifacts/rc-*`（[collector.py L89-91](../researchclaw/dashboard/collector.py#L89-L91)、[projects.py L20-22](../researchclaw/server/routes/projects.py#L20-L22)）。默认 `run` 生成的正是 `artifacts/rc-<ts>-<hash>`（[cli.py L152-155](../researchclaw/cli.py#L152-L155)、[L243-244](../researchclaw/cli.py#L243-L244)），但带 `--output` 的自定义 run（如本次 `g7-baseline`）**根本不会被枚举**——对这种 run，dashboard 的 60s 阈值连被触发的机会都没有。
- **`ops` 看得到但看不见进度**：`build_ops_view` 枚举全部子目录（[ops.py L158-172](../researchclaw/runtime/ops.py#L158-L172)），但每行的 `status`/`last_stage` 只取 `checkpoint.json`（[L144-155](../researchclaw/runtime/ops.py#L144-L155)），不读 `heartbeat.json` / `lease.json`。所以在长阶段内，`ops` 显示的仍是上一阶段的完成态。

### 2.6 监督器只监督「退出」

`Supervisor` 以子进程返回码、`restarts` 与 `max_wall_seconds` 作为控制量（[supervisor.py L199](../researchclaw/runtime/supervisor.py#L199)），不读取 heartbeat / lease，因此「进程活着但阶段停滞」这一最常见故障态不在其判定域内。

**且默认墙钟上限会先杀掉长阶段**：`DEFAULT_MAX_WALL_SECONDS = 1800`（[supervisor.py L31](../researchclaw/runtime/supervisor.py#L31)），CLI 亦以 `--max-wall-seconds default=1800` 暴露（[cli.py L1948](../researchclaw/cli.py#L1948)）。即使只把 supervisor 当作「重启器」启用，30 分钟也会撞上限，而 Stage 10 单阶段 1–3 小时——**当前默认参数下 supervisor 无法承载长阶段**，这项必须在 M3 一并处理（显式提高或改为按阶段 deadline）。

---

## 3. 失效链路

把上述机制串起来，得到一条完整的「看不见」因果链：

- **L1 写点绑定 DONE**：`heartbeat` 只在阶段完成后写 → 阶段内永远没有新鲜心跳。
- **L2 阈值与时长错配**：60s/300s 的活跃窗口 vs 1–3h 的阶段 → 阶段内 99% 时间被判「不活跃/UNKNOWN」。
- **L3 输出通道静默**：INFO 被默认级别吞掉；`print` 被块缓冲 → 日志不增长。
- **L4 事件类型闲置**：`llm.call/llm.result` 有声明无实现 → 事件链只有阶段边界。
- **L5 侧信道未门面化**：`agent_runs` 与 `cost_log` 有数据但无消费者 → ops/dashboard 看不到。
- **L6 监督器盲区**：只看退出码 → 停滞不触发任何告警或干预。

用户视角的时序（本轮实况）：15:27 启动 → 15:39/15:40/15:44 三次沙箱执行 → 15:48 查看时，`heartbeat` 显示昨天、日志 208 字节、`events` 停在 `stage.started`。**任何基于现有观测面的自动化都会在第 5 分钟就误判该 run 已死。**

---

## 4. 社区案例（E3）

### 4.1 Temporal：Heartbeat + Details + Heartbeat Timeout

- 长 Activity 在处理循环中周期性 `heartbeat(details)`；details 持久化，重试时可 `getHeartbeatDetails()` 从断点续跑。
- `heartbeatTimeout` 独立于 `startToCloseTimeout`，官方明确「短心跳超时 + 高频心跳」比「长执行超时」更快发现故障；「Without heartbeats … no visibility into whether an Activity is actually making progress or just a zombie that looks alive」。
- **可迁移**：心跳必须与阶段完成解耦、由业务循环主动上报、payload 携带可恢复的进度细节；判停滞用「心跳间隔的倍数」，不是总时长。

### 4.2 Airflow：Task Instance Heartbeat Timeout（原 zombie task）

- Task 进程周期性写心跳；scheduler 发现「状态 RUNNING 但心跳超时」即判 zombie，标记失败或重调度。
- 官方把「心跳停止」与 OOM、worker 重启、liveness probe 失败并列为「任务卡在 running」的常见成因。
- **可迁移**：`is_active` 不能只用于展示，必须进入状态机与重试/告警决策；心跳超时是一个**一等状态**。

### 4.3 systemd：`WatchdogSec=` + `sd_notify("WATCHDOG=1")`

- 服务必须周期性发送 keep-alive ping；超过 `WatchdogSec` 未收到即判 failed 并 `SIGABRT`。
- **可迁移**：外部看门狗只认「显式 keep-alive」，不认「进程存在」。ARC 的 `LeaseKeeper` 已经是这个形状，差的只是把「存活」升级为「存活 + 进度」。

### 4.4 PyTorch Lightning：低频采样而非逐步上报

- `log_every_n_steps` 默认 50；progress bar 用 `refresh_rate` 控制刷新批次；官方提示逐 batch 记录会拖慢训练。
- **可迁移**：进度上报要按 phase / attempt / N 步采样，不能逐 token；这直接决定事件量是否符合 ARC 的事件配额（A1-6）。

### 4.5 LangGraph / OpenAI Agents SDK：类型化流式事件

- LangGraph 提供 `updates` / `tasks` / `tools` / `custom` / `debug` 等流模式，按节点与工具生命周期发事件；Agents SDK 的 `run_streamed()` 暴露逐步事件。
- **可迁移**：阶段内应有显式的 `stage.progress`（phase 变更、attempt 变更、工具开始/结束），而不是靠猜日志。

### 4.6 Kubernetes Job：用 status 表达批任务进度

- Job 通过 `status`（active/succeeded/failed）、`completions`、`activeDeadlineSeconds` 表达进度与上限；官方与运维实践都建议**不要**给批任务加 liveness probe（会把「慢」误杀成「死」）。
- **可迁移**：停滞检测应「先告警、后策略干预」，默认不自动重启；对慢阶段要有显式的 deadline 而不是 liveness 式硬杀。

### 4.7 W&B / 实验追踪：实时同步 + 离线兜底 + 轮询心跳

- 默认实时同步，断网可 `WANDB_MODE=offline` 本地落盘后补传（[tracking FAQ](https://docs.wandb.ai/guides/track/tracking-faq)）；多数第三方 TUI 以固定间隔轮询活跃 run（具体间隔因实现而异，本仓不引用不可复核的数值）。
- **可迁移**：观测面要「多源合成 + 可离线」，不能依赖单文件是否新鲜；`last_update` 应取多源最大值。

### 4.8 Python 输出缓冲

- `-u` / `PYTHONUNBUFFERED=1` 强制 stdout/stderr 无缓冲；重定向场景下这是日志「看起来没动」的常见原因。
- **可迁移**：长跑入口应显式行缓冲，或在 CLI 启动时 `reconfigure(line_buffering=True)`；同时提供 `--log-level`。

### 4.9 共性六原则

| # | 原则 | 对应社区 | ARC 现状 |
|---|---|---|---|
| P-1 | 心跳与业务解耦，由后台节拍写，携带 details | Temporal / systemd | 有节拍（lease），无 details |
| P-2 | 用「心跳间隔 × k」判停滞，独立于总时长 | Temporal / Airflow | 无停滞概念 |
| P-3 | 进度按阶段/步低频采样，可合并 | Lightning / LangGraph | 只有阶段边界 |
| P-4 | 派生视图多源合成，文件为事实源 | W&B / K8s | 单源 heartbeat |
| P-5 | 状态机显式区分 RUNNING / STALLED / UNKNOWN，告警优先于重启 | Airflow / K8s | RUNNING / UNKNOWN 二态 |
| P-6 | 输出通道必须可见（级别 + 缓冲） | Python / 通用运维 | 双杀 |

---

## 5. 差距矩阵

| 能力 | ARC 现状 | 社区基线 | 差距 | 可复用资产 |
|---|---|---|---|---|
| 秒级活体心跳 | 有（lease，含 pid/expiry） | 有 | 低 | `LeaseKeeper` |
| 心跳携带进度 details | 无 | 有 | **高** | `_replace_with_retry` 原子写 |
| 阶段内进度事件 | 无（`llm.*` 声明未用） | 有 | **高** | `EventLog` / `_emit` |
| 停滞检测与告警 | 无 | 有 | **高** | `run_state` / `notifications` |
| 阶段内可恢复点 | 无（仅阶段级 checkpoint） | 有 | 中 | `checkpoint` 模式 |
| 日志可见性 | 差（INFO 丢弃 + 块缓冲） | 有 | **高** | 标准 logging |
| 派生视图 | dashboard 硬编码 60s、单源、仅 `rc-*`；`ops` 读全部但只看 checkpoint | 有 | 中 | `collector` / `ops` / `projects` |
| 监督器停滞感知 | 无（只看退出码；默认墙钟 1800s < 单阶段时长） | 有 | 中 | `supervisor` |

---

## 6. 建议方案

> 原则：先补“看得见”，再补“记得住”，最后补“自动干预”。三档均可独立上线，不改变 file-as-state 与事件摘要纪律（I-4）。

### 6.1 M1 / P0：最小可观测闭环（不改阶段实现）

**改动点**

1. 新增 `researchclaw/runtime/progress.py` 的 `ProgressKeeper`（或把 `LeaseKeeper` 升级为 `LeaseKeeper + ProgressKeeper` 双职责），与租约同一节拍（`ttl/3 = 200s`）：
   ```json
   {
     "pid": 747630, "run_id": "g7-baseline",
     "stage": 10, "stage_name": "CODE_GENERATION",
     "stage_started_at": "...", "attempt": 3, "phase": "sandbox",
     "last_event_seq": 7, "artifacts": ["agent_runs/attempt_003"],
     "updated_at": "...", "interval_sec": 200, "ttl_sec": 600
   }
   ```
   复用 `_replace_with_retry` 原子替换，避免 Windows 共享冲突（[runner.py L172-189](../researchclaw/pipeline/runner.py#L172-L189)）。
2. `read_run_state` 增加 `STALLED`：`silence = now - updated_at`；`stale_after = max(3*interval, 600)`。语义：
   - `silence <= stale_after` → `RUNNING`
   - `stale_after < silence <= stage_deadline` → `STALLED`（新状态，附 `silence_sec`）
   - 无心跳 → `UNKNOWN`（保持现有语义）

   **影响面（复审 D-1 补全，必须一次改齐）**：

   | 文件 | 改动 |
   |---|---|
   | [run_state.py L29-36](../researchclaw/run_state.py#L29-L36) | `RunStatus` 增 `STALLED = "stalled"`；`read_run_state` 的 elif 链插入 stall 分支（置于 `RUNNING` 之后、`UNKNOWN` 之前） |
   | [run_state.py L39-54](../researchclaw/run_state.py#L39-L54) | `RunState` 可选增 `silence_sec: float = 0.0`；`to_dict` 同步 |
   | [collector.py L105-116](../researchclaw/dashboard/collector.py#L105-L116) | `RunSnapshot` 增 `silence_sec`；`status` 直接透传 `state.status.value`（已天然兼容，无需额外映射） |
   | [projects.py L24-37](../researchclaw/server/routes/projects.py#L24-L37) | `/api/projects` 增 `silence_sec` 字段；前端需允许 `status="stalled"` |
   | 前端 | 若存在 `status` 白名单/染色映射，需登记 `stalled`（本仓无编译期约束，属运行时兜底） |

3. dashboard 的 60s 常量改为从 `heartbeat.interval_sec` 推导（[collector.py L16-19](../researchclaw/dashboard/collector.py#L16-L19)）；同时把 `collect_all` 的 `rc-*` 过滤放开或改为「有 `checkpoint.json` 即视为 run」，否则 `--output` 自定义 run 永远不可见。
4. `run` 增加 `--log-level`（默认 `INFO` 到 stderr）与 `--log-file`（可选）；启动时 `logging.basicConfig`，并对 stdout 做行缓冲（[cli.py L1764-1825](../researchclaw/cli.py#L1764-L1825)）。
5. 阶段开始改走 `logger.info`，与 `print` 并存，避免重定向后丢失（[runner.py L794-795](../researchclaw/pipeline/runner.py#L794-L795)）。

> **可独立成批（复审 O-2）**：第 4、5 项是 CLI / 日志的通用缺陷，与「长跑进度」耦合度低但收益最大——修复日志级别会立刻激活已存在的 ACP 30s 进度心跳（§2.3 第 4 条）与全部 `logger.info` 打点。建议拆为 B-31a（日志可见性，1 个文件 + 1 个测试）先行，B-31b 承载心跳 details 与 `STALLED`。

**验收口径（可机检）**

- 构造 90 秒假阶段：`heartbeat.updated_at` 至少刷新一次；`ops` 显示 `RUNNING`。
- `kill -STOP` 主进程：`>= stale_after` 后 `ops` 显示 `STALLED` 并给出 `silence_sec`。
- 重定向日志在阶段内 60 秒内增长（非 0 字节）。
- 每 200 秒最多 1 次心跳写，无额外 fsync 放大。

### 6.2 M2 / P1：阶段内进度

1. `EVENT_TYPES` 启用 `llm.call` / `llm.result`，**或**新增低频 `stage.progress`（二选一，避免双写）。选型矩阵（复审 D-2 补全）：

   | 维度 | `llm.call` / `llm.result` | `stage.progress`（推荐） |
   |---|---|---|
   | 粒度 | 逐次 LLM 调用 | phase 变更（≤6/阶段） |
   | 本轮实测量 | 07:27–07:58（31 分钟）14 次 ≈ 0.45 次/分钟；3h 阶段外推 ≈ 80–90 条 | Stage 10 全程 ≤6 条 |
   | 事件配额（A1-6） | 单阶段数十至上百条，叠加多阶段与 PIVOT 后持续累积 | 可忽略 |
   | fsync 成本 | 每调用 1 次 fsync（不满足 §4.4 低频原则） | 每 phase 1 次 |
   | 可恢复性 | 只能续「下一次调用」，无阶段语义 | 可直接对应可跳过 phase |
   | 调试价值 | 高（token/耗时/模型） | 中 |

   **默认取 `stage.progress`**；`llm.*` 仅在显式调试开关（如 `--trace-llm`）下启用，且必须带独立配额，不进入默认事件流。

2. Stage 10 显式 phase：`blueprint → generate → repair → validate → sandbox → entrypoint`，每次 phase 变更发一条事件并原子写 `stage-10/progress.json`（字段与 heartbeat details 同构）。
3. `ops` / dashboard 合成 `last_update = max(heartbeat.updated_at, lease.expires_at - ttl, 最新 artifact mtime, events 尾事件 ts)`，输出 `stage / phase / attempt / elapsed / silence_sec`。`ops` 现在只读 `checkpoint.json`（[ops.py L144-155](../researchclaw/runtime/ops.py#L144-L155)），需增读 `heartbeat.json`。
4. `agent_runs` **只作审计留存，不进入观测口径**（复审 D-3）：Stage 10 的 `agent_runs/attempt_NNN`（[code_agent.py L1477](../researchclaw/pipeline/code_agent.py#L1477)）与 `agent_sandbox/_project_N`（[L1457](../researchclaw/pipeline/code_agent.py#L1457)）由 `CodeAgent` 私有计数器 `self._runs` 驱动，每次 Stage 10 重入都从 001 重新计数，跨 PIVOT 不可比。单一事实源定为第 2 项的 `progress.json`；需要保留执行痕迹时，由 `progress.json` 写 `{attempt, artifact_dir}` 指向目录，而不是反过来由目录推断进度。

### 6.3 M3 / P2：恢复与告警

1. 按 phase 写可恢复标记（`stage-10/phase.json`），resume 时跳过已完成 phase；仅对幂等 phase 启用。
2. `Supervisor` 增加 stall 判定与通知，默认**只告警不重启**（对齐 K8s 对批任务的建议）。
   - **必须先解决墙钟上限（复审 O-3 补全）**：默认 `max_wall_seconds=1800`（[supervisor.py L31](../researchclaw/runtime/supervisor.py#L31)、[cli.py L1948](../researchclaw/cli.py#L1948)）小于单阶段时长，启用即误杀。方案二选一：① 改为按阶段 deadline（`stage_deadline` 与 M1 的 `stale_after` 同源）；② 显式要求 `--max-wall-seconds` 并由配置项给出下限校验（低于 3×`stale_after` 直接拒绝启动）。
   - **默认开启路径**：`supervisor` 是独立子命令（[cli.py L1943-1952](../researchclaw/cli.py#L1943-L1952)），`run` 不经过它。若希望「默认有 stall 告警」，应在 `run` 内直接启动 `ProgressKeeper`（M1 已有），把 stall 判定放在 `run` 的主循环，而不是依赖用户改用 `supervisor` 子命令——后者只能作为可选的崩溃重启层。
3. 告警复用现有 `notifications`（[executor.py L833-839](../researchclaw/pipeline/executor.py#L833-L839)），新增 `on_stalled` 开关。

### 6.4 明确不做（反例）

- **不逐 token 上报**：事件量会击穿配额（A1-6），且对齐不了 Lightning 的采样原则。
- **不在事件里放 prompt / 大 payload**：违反 I-4。
- **不把「慢」当「死」自动重启**：K8s 对批任务的明确经验。
- **不伪造进度**：与 B-30「取不到数值打印 `nan`、绝不填 0.0」同一纪律——宁可显示 `STALLED`，不显示假 `RUNNING`。
- **不在 `max_wall_seconds=1800` 的 supervisor 默认值下跑长阶段**：这是「把慢当死」的现成实例，M3 必须先改上限再谈启用。

---

## 7. 风险与成本

| 风险 | 说明 | 缓解 |
|---|---|---|
| GIL / C 扩展阻塞 | 心跳线程在极端阻塞下可能饿死 | 心跳失败本身即信号；租约续期同线程，二者一致性可交叉验证 |
| fsync 放大 | 事件链已逐行 fsync | 进度事件按 phase，200s 级；不新增逐调用 fsync |
| 时钟漂移 | 依赖 `now` 与文件时间戳 | 统一 UTC + 单调时钟算 elapsed；阈值留冗余 |
| 旧 run 兼容 | 旧 `heartbeat.json` 无 details | `details` 缺失时降级为阶段级语义，不报错 |
| Windows 共享冲突 | dashboard 并发读 | 复用 `_replace_with_retry` |
| 误报 | 合法长调用（单次 LLM 10+ 分钟） | `stale_after = max(3*interval, 600)`，且 STALLED 只告警 |
| supervisor 误杀长阶段 | 默认 `max_wall_seconds=1800` < Stage 10 时长 | M3 改为按阶段 deadline，或对 `--max-wall-seconds` 设下限校验 |

---

## 8. 结论与待决

**结论**：ARC 的持久化与恢复设计是完整的（checkpoint / events / lease / 原子写），缺的是「阶段内的可观测性」这一层。最小闭环（M1）只需一个后台心跳线程 + 一个 `STALLED` 状态 + 日志级别/缓冲修复，不动任何阶段实现，就能把「误判为死」变成「看得见在动，或明确看见停在哪」。

**待决**（2026-11-26 复审核实后更新）

1. ~~是否立 B-31~~ → **已决**：立 B-31（T1），已登记 `arc-master-roadmap.md` §3.2 与 §3.3 W0。
2. ~~M1 是否允许新增 `STALLED`~~ → **已决**：允许，影响面 5 处已在 §6.1 列全（`RunStatus` / `RunState` / `RunSnapshot` / `/api/projects` / 前端兜底）。
3. ~~进度事件选型~~ → **已决**：默认 `stage.progress`，`llm.*` 仅调试开关下启用（§6.2 矩阵）。
4. **仍待决**：「停滞告警」是否默认开启，以及通知渠道（现有 `notifications.channel`）；另需裁决 B-31 是否拆为 B-31a（日志可见性）与 B-31b（心跳 + STALLED）。

---

## 9. 修正记录（2026-11-26，针对异构复审 D-1..D-4 / O-1..O-4）

> 复审报告：[arc-longrun-progress-review-20261126.md](../docs/arc-longrun-progress-review-20261126.md)。本节记录每条意见的**核实结论**（属实 / 不属实 / 部分）与**落点**；核实全部基于读码 + 一手页面复检。

| 意见 | 核实结论 | 处理 |
|---|---|---|
| **D-1** `STALLED` 影响面未列全 | **属实**。`RunStatus` 5 值无 `STALLED`（[run_state.py L29-36](../researchclaw/run_state.py#L29-L36)）；`collector` 直接透传 `state.status.value` 故无需映射，但 `RunSnapshot`、`RunState.to_dict`、`/api/projects` 需同步 | §6.1 增 5 行影响面表；§8 待决 2 关闭 |
| **D-2** `llm.*` vs `stage.progress` 缺选型矩阵 | **属实**。原文仅「二选一」，无依据 | §6.2 增 6 维矩阵，**默认取 `stage.progress`**；§8 待决 3 关闭 |
| **D-3** `agent_runs` 纳入正式侧信道未细化 | **属实，且比复审描述更严重**：`agent_runs/attempt_NNN` 与 `agent_sandbox/_project_N` 均由 `CodeAgent._runs` 驱动（[code_agent.py L1457](../researchclaw/pipeline/code_agent.py#L1457)、[L1477](../researchclaw/pipeline/code_agent.py#L1477)），每次 Stage 10 重入从 001 重计，跨 PIVOT 不可比 | §6.2 第 4 条改为「只作审计留存」，单一事实源定为 `progress.json` |
| **D-4** 参考 12 存在失效/不可复核风险 | **属实**。页面仍可访问，但正文已无 `heartbeat` 字样，15s 数字无法复现 | 参考 12 换为 W&B tracking FAQ；§4.7 删除 15s 数值 |
| **O-1** `stage_health.json` 时机口径 | **属实**（写法差异），功能无影响 | §2.1 表格改为「阶段末（`_write_checkpoint` 之前）」 |
| **O-2** 日志项应拆独立批 | **采纳**。且核实到更强论据：ACP 已有 30s 进度心跳，仅被日志级别吞掉 | §6.1 增「可独立成批」说明（B-31a / B-31b）；§2.3 增第 4 条 |
| **O-3** supervisor 默认开启路径未说明 | **属实，且发现更硬的阻塞**：默认 `max_wall_seconds=1800`（[supervisor.py L31](../researchclaw/runtime/supervisor.py#L31)、[cli.py L1948](../researchclaw/cli.py#L1948)）小于单阶段时长，启用即误杀 | §2.6 / §6.3 / §6.4 / §7 四处同步；结论为「stall 判定放 `run` 主循环，supervisor 只作可选崩溃重启层」 |
| **O-4** 10 分钟长调用误报风险 | **属实且可控**。`stale_after = max(3×200, 600) = 600s` 正好覆盖 10 分钟 | 无需改动，§7 保留 |

**复核中新发现（原调研未写、复审未列）**

| # | 事实 | 落点 |
|---|---|---|
| N-1 | dashboard 与 `/api/projects` 只枚举 `artifacts/rc-*`；`--output` 自定义 run（如 `g7-baseline`）**完全不可见**，60s 阈值连触发的机会都没有 | §2.5 补充、§6.1 第 3 点 |
| N-2 | `ops` 枚举全部目录，但 `status/last_stage` 只取 `checkpoint.json`，不读 heartbeat/lease → 长阶段内恒显示上一阶段 | §2.5 补充、§6.2 第 3 点 |
| N-3 | `acp_client` 已实现 30s 进度心跳日志，但走 `logger.info`，被缺失的日志配置静默 | §2.3 第 4 条 |

---

## 附录 A 复现命令

A-1 现场快照（B 站）：

```bash
date -u
cat ~/arc-runs/g7-baseline/heartbeat.json
cat ~/arc-runs/g7-baseline/lease.json
tail -n 4 ~/arc-runs/g7-baseline/events.jsonl | cut -c1-260
wc -c /tmp/p192_stage12.log
ls -l ~/arc-runs/g7-baseline/stage-10/agent_runs/*/main.py
wc -l ~/arc-runs/g7-baseline/cost_log.jsonl
tail -n 2 ~/arc-runs/g7-baseline/cost_log.jsonl
```

A-2 读码取证（本地仓）：

```powershell
# 心跳写入点（应只有 1 处调用：L1016）
Select-String -Path researchclaw\pipeline\runner.py -Pattern "_write_heartbeat"

# 日志配置（应零命中）
Get-ChildItem researchclaw -Recurse -Filter *.py |
  Select-String -Pattern "basicConfig|dictConfig|setLevel\("

# 事件类型生产者（llm.call / llm.result 应零命中）
Get-ChildItem researchclaw -Recurse -Filter *.py |
  Select-String -Pattern '"llm\.call"|"llm\.result"'

# 阶段内进度落盘（应零命中）
Get-ChildItem researchclaw -Recurse -Filter *.py |
  Select-String -Pattern "stage\.progress|progress\.json"
```

## 附录 B 参考资料（访问日期 2026-11-26）

1. Temporal, *Long-Running Activity — Tracking Progress and Handling Cancellation with Heartbeats* — https://docs.temporal.io/design-patterns/long-running-activity
2. Temporal, *Detecting Activity failures* — https://docs.temporal.io/encyclopedia/detecting-activity-failures
3. Apache Airflow, *Troubleshooting*（Task stuck in running / heartbeat timeout） — https://airflow.apache.org/docs/apache-airflow/stable/troubleshooting.html
4. Apache Airflow, *Tasks*（zombie detection） — https://airflow.apache.org/docs/apache-airflow/2.10.4/core-concepts/tasks.html
5. systemd, *systemd.service — WatchdogSec=* — https://www.freedesktop.org/software/systemd/man/257/systemd.service.html
6. PyTorch Lightning, *Track and Visualize Experiments (advanced)* — https://lightning.ai/docs/pytorch/stable/visualize/logging_advanced.html
7. LangChain, *LangGraph Streaming* — https://docs.langchain.com/oss/python/langgraph/streaming
8. OpenAI, *Agents SDK — Streaming* — https://openai.github.io/openai-agents-python/streaming/
9. Kubernetes, *Jobs* — https://kubernetes.io/docs/concepts/workloads/controllers/job/
10. Buglyst, *Kubernetes Job Not Completing? Debug Stuck Pods* — https://buglyst.com/learn/guides/k8s-job-not-completing-debug
11. Weights & Biases, *Save metrics offline and sync later* — https://docs.wandb.ai/support/models/articles/is-it-possible-to-save-metrics-offline-a
12. Weights & Biases, *Frequently Asked Questions About Experiments*（offline 模式与 `WANDB_MODE`） — https://docs.wandb.ai/guides/track/tracking-faq
13. Python, *Command line and environment（-u / PYTHONUNBUFFERED）* — https://docs.python.org/pa/3/using/cmdline.html

> **参考 12 修正（复审 D-4 核实）**：原引 CoreWeave 托管的 LEET TUI 文档，并据此写「第三方 TUI 以 15s 心跳轮询活跃 run」。2026-11-26 复检该页（https://docs.coreweave.com/products/wandb/app/leet-tui）仍可访问，但**正文已无 `heartbeat` / `heartbeat_interval_seconds` 字样**，该 15s 数字无法从所引页面复现，属不可复核断言。已改为 W&B 官方 tracking FAQ（offline 语义），并删除正文中的 15s 具体数值（§4.7 改为「第三方 TUI 会以固定间隔轮询活跃 run」，不再给数字）。

## 附录 C 术语

- **Heartbeat details**：心跳携带的进度载荷，可在失败重试时用于断点续跑（Temporal）。
- **Stall / STALLED**：进程存活但超过 `k × 心跳间隔` 无进展的状态；与「进程不存在」区分。
- **Liveness vs readiness**：前者判「是否要重启」，后者判「是否能接活」；批处理任务不宜用 liveness 思路处理「慢」。
- **Side channel（侧信道）**：非为观测设计、但可反推进度的落盘痕迹，如 `agent_runs` 目录 mtime、`cost_log.jsonl`。
