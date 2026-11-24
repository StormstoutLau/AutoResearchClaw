---
id: arc-g7-soak-RESEARCH
type: design
version: 1.1
status: verified
date: 2026-11-24
depends: [arc-master-roadmap, arc-g1-readiness-research, arc-g5-decisions]
upstream: arc-master-roadmap
---

# 调研：G7 第一段「soak 工具链」（P-160）

> **Feature**：P-160。G7 的第一段，只做**长时程运行 + 重启注入 + 收敛断言 + 回放校验 + 报告模板**；并发、双平面、漂移护栏、编排评测留给后续段。
> **Spec 步骤**：Step 1-2（调研）。
> **范围口径**：本段**不实际在 CI 跑 72h**；提供可在目标主机上跑 72h 的脚本，以及在 CI 可重复的**缩时演练**。
> **修订**：v1.1（2026-11-24，Step 9 实施发现）新增 F-1b（torn tail 未截断）与 F-4（Windows 并发读者使 `os.replace` 抛 `PermissionError`）；两者均由 soak 缩时演练/边界夹具实测暴露，已纳入本段修复面。

---

## 1. 调研目标

1. G7 的 A7-1（72h、≥3 次重启、收敛同一终态）与 A7-4（轮转后按 `run_id + seq` 完整回放）在**当前代码**上还缺什么？
2. 社区与学术上，长时程/崩溃恢复测试的**最小可信工具链**由哪些部件组成，哪些做法不应照搬？
3. 第一段的**可失败验收面**应如何切分，才能既不虚报 72h，也不把并发/双平面/漂移混进同一批？

## 2. 调研方法

### 2.1 通道与降级链

| 通道 | 用途 | 实际结果 |
|---|---|---|
| `Grep` / `Read` / `Glob` | 本仓事实（runtime、runner、tests） | 已逐文件读取，行号见 §3 |
| `mcp_paper-search`（Semantic Scholar） | 学术元数据 | **返回空列表**；降级到 WebSearch + 出版方/PDF 页 |
| `WebSearch` | 论文、官方文档、社区 issue | 命中；关键事实回溯到 T1 页面 |
| `WebFetch` | 官方文档/源码原文 | 命中多数；`sre.google` 章节页**抓取为空**，该来源只作 T2 线索，不承重 |
| `mcp_stackexchange` | 工程反例 | **两站均返回 0 条**；降级到 GitHub Issues API |
| GitHub Issues API | 社区案例（T3） | 命中 3 条，见 §4.3 |

### 2.2 范围

- **时间**：1994（software aging）至 2026-11（仓库当前状态）。
- **领域**：崩溃恢复测试、长时程性能/可靠性测试、事件日志回放、进程监督。
- **排除**：G7 的并发准入、双平面 ClaimStatus、漂移阈值（Q13）、OB-1..5；这些不在本段证据面内。

## 3. 本仓事实（T1：源码/测试）

### 3.1 已有可复用资产

| 资产 | 事实 | 对本段的意义 |
|---|---|---|
| [`EventLog`](../../researchclaw/runtime/event_log.py#L122-L443) | 追加写、逐行 `prev_sha256` 链、`payload_sha256`、`seq` 单调；段上限 8 MiB / 10,000 事件；单 run 上限 256 MiB / 200,000 事件 | A7-4 的存储底座已存在；本段补**轮转后回放验证** |
| [`EventLog.read_all/read_after`](../../researchclaw/runtime/event_log.py#L306-L324) | 按段名排序读取 active + `events.<first>-<last>.jsonl[.gz]`；`read_after(seq)` 供游标回放 | 回放不需要新存储格式 |
| [`EventLog.verify_chain`](../../researchclaw/runtime/event_log.py#L326-L355) | 校验 seq 连续、`prev_sha256`、`payload_sha256`；summary 最新时校验 `chain_tail` | A7-4 的机械判据 |
| [`rebuild_checkpoint`](../../researchclaw/runtime/event_log.py#L446-L466) | 从 `stage.completed` 事件重建 checkpoint 载荷 | A7-1 收敛/恢复的已有路径 |
| [`Supervisor`](../../researchclaw/runtime/supervisor.py#L49-L136) | 只在退出码 **75** 时重启；full jitter；`max_restarts`/`max_wall_seconds`；supervisor 自己不持租约 | 可复用退避与停止语义；但**不覆盖硬杀重启** |
| [`lease.py`](../../researchclaw/runtime/lease.py#L156-L243) | 单写者、fencing 单调、TTL 300s、`LeaseKeeper` 后台续约 | 重启注入时必须避免双写 |
| [`runner.read_checkpoint`](../../researchclaw/pipeline/runner.py#L345-L375) | checkpoint 缺失/损坏时从事件日志恢复，写 `recovered: true` | A7-1 的恢复入口 |
| [`tests/test_event_log.py`](../../tests/test_event_log.py#L117-L147) | 已有段轮转、gz 归档/删除测试 | 缺口：**轮转边界崩溃**未覆盖 |

### 3.2 当前缺陷（实测复现，E2）

| 编号 | 缺陷 | 复现与读数 | 影响 |
|---|---|---|---|
| **F-1** | `EventLog._refresh` 在 active `events.jsonl` 不存在时，只从 active 读 `last_seq/last_hash`；若崩溃发生在 `os.replace` 之后、新 active 写入之前，重新打开后 `last_seq=0`、`last_hash=ZERO_HASH` | 脚本：2 条事件触发轮转 → 删除 active → 重开 `last_seq=0`；再 append 得到 `seq=1`，`verify_chain` 返回 `(False, 'seq gap at 1 (expected 2)')` | A7-1/A7-4 直接失败：崩溃点恰好落在轮转边界时产生**重复 seq 与断链** |
| **F-2** | [`_recover_checkpoint_from_events`](../../researchclaw/pipeline/runner.py#L378-L393) 以 `events.jsonl` 存在为前置；轮转后 active 为空/不存在时，即使归档段里有完整 `stage.completed`，也不会恢复 | 脚本：2 条 `stage.completed`，轮转后删除 active；`rebuild_checkpoint(read_all())` 能返回 stage 2，但 runner 的恢复入口因 `events.jsonl` 不存在直接返回 `None` | A7-1 的 checkpoint 恢复在轮转边界失效 |
| **F-3** | [`read_all`](../../researchclaw/runtime/event_log.py#L306-L320) 对归档段允许**静默跳过 1 条坏行** | 读码：`tolerance > 1` 才抛；单条坏行只跳过 | 回放校验不能只依赖 `read_all`，必须叠加 `verify_chain` 与 seq 覆盖检查 |
| **F-1b** | `_refresh` 发现 torn tail 后只设置 `truncated=True`，**不截断** active；下一次 `append` 写在坏行之后，`read_all` 遇到坏行即停，后续事件永久不可见 | 夹具：append 1 条 → 追加 `{"seq":2,"broken"` → 重开 → append seq2 → 修复前 `read_all` 只见 seq1；修复后截断坏尾，`read_all` 见 [1,2]，链通过 | A7-1/A7-4：崩溃在写一半的行上会“看似恢复、实际丢事件” |
| **F-4** | `_write_checkpoint` / `_write_heartbeat` 的 `Path.replace` 无重试；Windows 上并发读者（soak driver 每 10ms 读 checkpoint）持有目标句柄时，`os.replace` 抛 `WinError 5`，worker 直接崩溃 | 缩时演练：fake worker 在第 7 阶段退出码 1，stderr `PermissionError: [WinError 5] ... checkpoint.json.tmp -> checkpoint.json`；修复为 5×50ms 重试后通过 | 72h 长跑中任何看板/校验读者都可能触发；不能靠“不要读”规避 |

> 说明：F-1/F-2 属于**本段必须修复**的缺陷，因为不修就无法让 A7-1/A7-4 的验收变红后转绿；它们不是无关重构。

### 3.3 现状边界

- `Supervisor` 把非 75 退出视为终止；硬杀（Windows `TerminateProcess`、POSIX `SIGKILL`）不会被它重启。G7 需要的是**测试工具主动注入重启**，不是改变生产 supervisor 的退出码契约。
- `EventLog` 的保留策略会在 30 天后压缩、365 天后删除；72h soak 不会触发删除，但 A7-4 的“轮转后回放”必须在压缩后仍可读（gz 路径已有）。
- `pipeline_summary.json` 每次 `run --resume` 都会被重写，字段含 `generated` 时间戳与仅本次调用的 `stages_*` 计数；收敛签名**不能**直接对整个 summary 求哈希。

## 4. 外部证据

### 4.1 学术（T1，已核元数据）

| # | 来源 | 关键结论 | 本段借用 | 不借用 |
|---|---|---|---|---|
| E1 | Candea & Fox, *Crash-Only Software*, HotOS IX, 2003（[USENIX PDF](https://www.usenix.org/legacy/events/hotos03/tech/full_papers/candea/candea.pdf)） | 崩溃安全、恢复快速；停止只有崩溃、启动只有恢复；组件级透明重试 | “重启即恢复”作为 soak 的基本假设；恢复路径必须与正常启动同构 | 微重启（microreboot）工程体系 |
| E2 | Yuan et al., *Simple Testing Can Prevent Most Critical Failures*, OSDI 2014（[USENIX 登录文章](https://www.usenix.org/system/files/login/articles/login_feb15_05_yuan.pdf)） | 198 个生产故障中 **92%** 的灾难性失败来自对**非致命错误**的错误处理；对错误处理路径做简单测试即可预防多数 | 重启注入要覆盖**错误路径/边界**，不能只测 happy path | 其静态检查器 Aspirator |
| E3 | Parnas, *Software Aging*, ICSE 1994；Cotroneo et al., *A Survey of Software Aging and Rejuvenation Studies*, ACM JETCS 10(1), 2014, DOI [10.1145/2539117](https://doi.org/10.1145/2539117) | 长运行系统会因资源/状态累积而退化；soak/aging 测试的目标是**慢燃缺陷** | 72h 时长的动机；报告需保留时间序列而非只看终态 | 具体 rejuvenation 策略与预测模型 |
| E4 | *Principles of Chaos Engineering*（[principlesofchaos.org](https://principlesofchaos.org/)，2019-03 版） | 先定义可测的 steady state；假设其在实验组与对照组都成立；注入真实故障；用差异推翻假设；最小化爆炸半径；自动化持续运行 | 收敛签名 = steady state；基线与 soak 对照；重启预算与 blast radius | “在生产跑”这一条不适用于本仓 CI |

> 诚实边界：E3 只读了出版方摘要与 ACM 元数据，**未逐节读原文**；其“长运行退化”结论作为动机使用，不作为本段算法的唯一依据。

### 4.2 工业官方文档（T1）

| # | 来源 | 机制 | 本段借用 |
|---|---|---|---|
| E5 | [Kubernetes Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/) | 首次崩溃立即重启；后续指数退避；成功运行约 10 分钟后重置退避；`CrashLoopBackOff` 是退避状态 | 重启预算 + 退避 + “稳定运行后重置”的语义参照 |
| E6 | [Chaos Mesh：Simulate Pod Faults](https://chaos-mesh.org/docs/simulate-pod-chaos-on-kubernetes/) | `pod-kill` 杀死 Pod；需 ReplicaSet 等机制保证重启；独立 Pod 不保证恢复 | 故障注入必须与“谁负责重启”解耦；本段由 soak driver 负责重启 |
| E7 | [etcd Robustness Testing](https://github.com/etcd-io/etcd/blob/main/tests/robustness/README.md) | 用简化模型校验真实行为；记录客户端操作历史；失败时生成包含操作历史与数据目录的报告；维护“历史 bug 可复现”表 | “模型/基线 + 操作历史 + 失败报告”的形态；验证器与被测进程分离 |
| E8 | [Temporal Workflow 文档](https://docs.temporal.io/workflows) | Event History 是唯一事实源；恢复时从事件历史重放；决策必须可重放；Activity 结果记录后不重复执行 | A7-4 的“按事件历史回放”判据；不要把 `pipeline_summary` 当唯一事实源 |
| E9 | [Python `subprocess` 文档](https://docs.python.org/3/library/subprocess.html)；[Microsoft `TerminateProcess`](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-terminateprocess) | Windows 上 `terminate()` 走 `TerminateProcess`；无条件终止，DLL 全局状态可能受损；`atexit` 在未处理信号/`os._exit()` 下不执行 | 重启注入在 Windows 上是**硬杀**，不能依赖清理钩子；必须验证崩溃后的磁盘状态 |
| E10 | [AWS：Exponential Backoff and Jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/) | full jitter 相比无 jitter 显著降低调用量并缩短完成时间 | 复用现有 supervisor 的 full jitter，不在 soak driver 里另造退避 |

### 4.3 社区案例（T3，只用于陷阱，不作为最佳实践）

| # | 来源 | 现象 | 对本段的约束 |
|---|---|---|---|
| C-1 | [etcd #19884 “Investigate robustness test flake”](https://github.com/etcd-io/etcd/issues/19884)（2025-05 创建，2025-12 关闭） | 失败原因是 **“Broken validation assumptions”**，不是产品缺陷 | 验证器必须能区分“产品不收敛”与“验证假设错误”；报告要保留原始读数 |
| C-2 | [Chaos Mesh #4539](https://github.com/chaos-mesh/chaos-mesh/issues/4539) | 串行 workflow 在 pod-kill 后卡住不继续 | 注入器自身要有超时/看门狗；不能把“注入后卡住”误判为“被测系统不收敛” |
| C-3 | [x0x PR #223](https://github.com/saorsa-labs/x0x/pull/223) | 同一 PR 同时修 “restart persistence / convergence-test gaps / soak harness” | “soak harness + 重启持久化 + 收敛测试”是社区常见组合；可作为形态参照，不可作为正确性证据 |

### 4.4 未采用/未验证来源

| 来源 | 状态 | 处置 |
|---|---|---|
| Google SRE Book, *Testing for Reliability* | `WebFetch` 返回空；仅有搜索摘要 | 标 T2 线索；不用于承重断言 |
| `mcp_paper-search`（Semantic Scholar） | 三次查询均空 | 降级链已记录；学术元数据改用出版方页面 |
| `mcp_stackexchange` | 两次查询均 0 条 | 降级到 GitHub Issues API |
| 各类“soak test 8–72 小时”营销博客 | T4 | 只作线索；时长结论回溯到 E3/E4 |

## 5. 综合分析

### 5.1 关键发现

1. **A7-1 的难点不是“重启”，而是“重启点落在持久化边界”**：现有 EventLog 在轮转边界会重置 `seq`（F-1），torn tail 未截断会让后续事件不可见（F-1b），checkpoint 恢复又要求 active 文件存在（F-2），Windows 并发读者还会让 checkpoint 替换失败（F-4）。这些缺陷必须先修，否则 72h soak 的失败会被误读为“模型不稳定”。[置信度：★★★★★，E2 实测]
2. **A7-4 可以完全机械化**：`verify_chain` + seq 覆盖 + `read_after` 已足够；需要新增的是“轮转后重开、继续写、再全量回放”的测试与报告字段。[置信度：★★★★★，源码 + E7/E8]
3. **收敛签名必须排除易变字段**：`pipeline_summary.generated`、`run_id`、时间戳、重试次数都会变；应使用“最终状态 + 已完成阶段序列 + checkpoint 终态”作为签名，并与基线对照。[置信度：★★★★☆，源码 + E4 steady state]
4. **重启注入必须与退避/预算解耦**：生产 `Supervisor` 只重启退出码 75，不应为测试改成“任何退出都重启”；soak driver 应是独立测试工具，复用 full jitter，但自己决定注入与重启。[置信度：★★★★☆，源码 + E5/E6/E10]
5. **报告是工具链的一等公民**：etcd 的实践表明失败报告必须保留操作历史与原始数据；本段报告至少包含重启次数、恢复耗时、失败阶段分布、链校验/回放读数、收敛对照。[置信度：★★★★★，E7]
6. **72h 本身不能由 CI 证明**：CI 的 job 上限与成本都不允许；本段只能证明“缩时演练 + 工具可用”，72h 现场运行作为 operator 步骤单独留证。[置信度：★★★★★，仓库 CI 事实]

### 5.2 技术 landscape

| 方案 | 形态 | 局限 | 结论 |
|---|---|---|---|
| 直接扩 `Supervisor` | 在现有 supervisor 里加“硬杀后重启” | 会改变生产退出码契约；测试语义污染运行时 | 不采用 |
| 新 `SoakDriver` + 复用 `EventLog/lease` | 测试工具独立，注入/时钟/进程可替换 | 需要新增模块与测试 | **采用** |
| 外部框架（Chaos Mesh/Temporal/Jepsen） | 完整故障注入/重放平台 | 引入第二套状态模型、部署成本高；与 file-as-state 冲突 | 不采用（只借形态） |
| 只写文档不写工具 | Runbook + 手工 kill | 不可重复、不可 CI 化 | 不采用 |

### 5.3 研究空白与本段定位

- 空白 1：仓库没有“进程被杀后继续跑”的可重复工具；现有 `Supervisor` 只覆盖可重试退出。
- 空白 2：事件日志轮转后的回放只有存储层单测，没有“重启后继续写 + 全量回放”的端到端用例。
- 空白 3：没有统一的 soak 报告格式，重启次数/恢复耗时/失败阶段分布无法横向比较。
- 本段填补以上三项；**不**声称填补并发隔离、双平面一致性或漂移护栏。

## 6. 第一段范围建议（供 Step 3 决策）

### 6.1 纳入

| 能力 | 说明 | 对应验收 |
|---|---|---|
| `SoakDriver` | 启停 worker、按计划注入硬杀、记录重启与恢复耗时、限制重启预算 | A7-1（工具面） |
| `verify_run` | 只读校验：链、seq 覆盖、run_id 一致、checkpoint/事件一致性、收敛签名 | A7-1/A7-4 |
| 收敛签名 | `final_status + last_completed_stage + stage.completed 序列`（排除时间戳） | A7-1 |
| 报告 | JSON + Markdown：重启次数、恢复耗时、失败阶段分布、链/回放读数、收敛对照 | A7-1/A7-4 + G7 观测面 |
| 轮转边界修复 | F-1/F-1b/F-2/F-4 + 回归测试 | A7-4 |
| CLI | `researchclaw soak run/verify/report` | 工具可用性 |
| 缩时演练 | 测试内 3 次硬杀 + 收敛对照，不跑 72h | A7-1（可失败） |

### 6.2 明确不做

- 不跑真实 72h（留给目标主机 operator 运行；报告模板提供字段）。
- 不做多 run 并发、`max_concurrent_attempts`、worker slot（A7-2/A7-6/A7-7）。
- 不做双平面 ClaimStatus（A7-3）。
- 不做 Runbook 人工演练（A7-5；本段只产出恢复所需的机械读数）。
- 不做漂移护栏（FA-1..3）与编排评测（OB-1..5）。

## 7. 未决项登记（四元块）

- **U-1 72h 现场运行的主机与窗口**
  - **判据**：产出 `soak_report.json`，`wall_seconds ≥ 259200`、`restarts ≥ 3`、`converged=true`、`chain_ok=true`
  - **触发条件**：有可独占 ≥72h 的主机时
  - **当前倾向**：本段只交付脚本与模板；现场运行单独留证，不并入 CI
  - **证据等级**：E5（未执行）

- **U-2 收敛对照的基线来源**
  - **判据**：存在一个无注入的 baseline run 目录，且 `convergence_signature` 与 soak run 相等
  - **触发条件**：首次真实 soak 前
  - **当前倾向**：先跑 baseline，再跑注入；`soak verify --reference` 读取基线签名
  - **证据等级**：E4（设计判断）

- **U-3 注入点的确定性**
  - **判据**：注入计划以“已观察到 checkpoint 前进/心跳更新”为前置；同一 fixture 下注入次数与阶段可复现
  - **触发条件**：Step 3 设计时
  - **当前倾向**：按“进度事件 + 最小间隔”注入，不以纯 wall-clock 作为唯一条件
  - **证据等级**：E4

- **U-4 是否复用 `Supervisor` 的退避**
  - **判据**：soak driver 不改变生产 supervisor 的退出码契约；两者退避参数可独立配置
  - **触发条件**：Step 3 设计时
  - **当前倾向**：复用 `full_jitter`，不复用 `Supervisor.run()` 的重启条件
  - **证据等级**：E3（源码）

## 8. 对设计的输入（约束）

1. **单一事实源**：事件日志是回放真值源；`checkpoint.json` 是恢复真值源；报告不得另造状态。
2. **不双写**：soak driver 不获取 run 租约；worker 持租约；硬杀后等租约过期/失效再重启。
3. **Windows 优先**：注入用 `Popen.kill()` 或 `taskkill /F /T /PID`；不依赖 `atexit`。
4. **可测试性**：driver 接受注入的 `spawn`/`clock`/`sleep`，测试不需要真实 LLM。
5. **报告可机读**：JSON 是主格式，Markdown 是渲染；字段名稳定，供后续看板消费。
6. **不伪绿**：72h 未跑就标 `pending_field_run`；A7-1 只能标“工具链 + 缩时演练通过”。

## 9. Review 记录（Step 2，自查·单视角）

> **RULE-4 声明**：本节由实现同一会话完成，属**自查（单视角）**；未经异构基座复审。外部引用按“抽取 → 解析 → 字段比对 → 落状态”四步核验，结果见下表。

### 9.1 文献验证

| 引用 | ID | 验证方式 | 状态 |
|---|---|---|---|
| Crash-Only Software | HotOS IX, 2003, USENIX PDF | WebSearch 命中 + PDF 摘要读取 | 已验证（T1） |
| Simple Testing Can Prevent Most Critical Failures | OSDI 2014, USENIX | WebSearch 命中 + ACM/登录文章摘要 | 已验证（T1，摘要级） |
| Software Aging | ICSE 1994, pp. 279-287 | WebSearch 命中 + 多份 PDF 引用 | 已验证（T1，元数据） |
| Software Aging and Rejuvenation Survey | DOI 10.1145/2539117 | ACM 页面命中（JETCS 10(1), 2014） | 已验证（T1，元数据） |
| Kubernetes Pod Lifecycle | kubernetes.io 官方 | WebFetch 全文命中 | 已验证（T1） |
| Chaos Mesh PodChaos | chaos-mesh.org 官方 v2.8.7 | WebFetch 全文命中 | 已验证（T1） |
| etcd Robustness README | github.com/etcd-io/etcd | WebFetch raw 全文命中 | 已验证（T1 源码） |
| Temporal Workflows | docs.temporal.io | WebFetch 全文命中 | 已验证（T1） |
| Python subprocess / MS TerminateProcess | docs.python.org / learn.microsoft.com | WebFetch 命中（TerminateProcess 全文；subprocess 目录页） | 已验证（T1） |
| AWS Backoff and Jitter | aws.amazon.com 官方博客 | WebFetch 全文命中 | 已验证（T2 官方博客） |
| Principles of Chaos | principlesofchaos.org | WebFetch 全文命中 | 已验证（T1 社区标准） |
| etcd #19884 / Chaos Mesh #4539 / x0x #223 | GitHub | API 元数据与正文命中 | 已验证存在（T3，仅陷阱） |
| Google SRE Book | sre.google | WebFetch 空 | **未验证（T2 线索，不承重）** |

### 9.2 技术声明验证

| 声明 | 证据 | 状态 |
|---|---|---|
| 轮转边界重开会重置 seq | §3.2 实测脚本输出 | ✅ 已验证（E2） |
| torn tail 未截断导致后续事件不可见 | §3.2 F-1b 夹具 | ✅ 已验证（E2） |
| Windows 并发读者使 checkpoint 替换失败 | §3.2 F-4 缩时演练 stderr | ✅ 已验证（E2） |
| runner 恢复要求 active 文件存在 | 源码 `runner.py:378-393` + 实测 | ✅ 已验证（E1/E2） |
| Windows `terminate()` 是硬杀 | MS TerminateProcess 文档 + Python 文档 | ✅ 已验证（T1） |
| 92% 灾难性失败来自非致命错误处理 | USENIX 登录文章摘要 | ✅ 摘要级已验证；未逐页读 OSDI 原文 |
| 72h 不能在 GitHub 托管 runner 完成 | 仓库 CI 五 job 均 `ubuntu-latest`，显式 `timeout-minutes` 最大 30（`.github/workflows/ci.yml`）；GitHub 托管 runner 单 job 上限 360 分钟 | ✅ 已验证（仓库事实 + 平台常识） |

### 9.3 待修正项

- [x] 将“Google SRE soak”从承重证据降为 T2 线索（抓取为空）。
- [x] 将 `mcp_stackexchange`/`mcp_paper-search` 的空结果写入降级链，不静默跳过。
- [x] 明确“未跑 72h”为 U-1，不在本段标 A7-1 全绿。

### 9.4 Step 2 门禁

- [x] (a) 无 FALSIFIED 断言。
- [x] (b) 无 CONFLICT / STEP_GAP_OPEN。
- [x] (c) 承重断言均有 ≥1 T1 来源；单源处已标“摘要级/元数据级”。
- [x] (d) 假设已转 U-1..U-4 四元块，携带进 DESIGN。

## 10. 参考文献

1. Candea, G., Fox, A. *Crash-Only Software*. HotOS IX, 2003. https://www.usenix.org/legacy/events/hotos03/tech/full_papers/candea/candea.pdf
2. Cotroneo, D., Natella, R., Pietrantuono, R., Russo, S. *A Survey of Software Aging and Rejuvenation Studies*. ACM JETCS 10(1), 2014. DOI 10.1145/2539117.
3. Parnas, D. L. *Software Aging*. ICSE 1994, pp. 279-287.
4. Yuan, D. et al. *Simple Testing Can Prevent Most Critical Failures*. OSDI 2014. https://www.usenix.org/system/files/login/articles/login_feb15_05_yuan.pdf
5. Kubernetes. *Pod Lifecycle*. https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
6. Chaos Mesh. *Simulate Pod Faults* (v2.8.7). https://chaos-mesh.org/docs/simulate-pod-chaos-on-kubernetes/
7. etcd. *Robustness Testing* README. https://github.com/etcd-io/etcd/blob/main/tests/robustness/README.md
8. Temporal. *Workflows / Event History replay*. https://docs.temporal.io/workflows
9. Python Software Foundation. *subprocess — Subprocess management*. https://docs.python.org/3/library/subprocess.html
10. Microsoft. *TerminateProcess function*. https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-terminateprocess
11. AWS Architecture Blog. *Exponential Backoff and Jitter*. 2015-03-04. https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
12. *Principles of Chaos Engineering*. 2019-03. https://principlesofchaos.org/
13. etcd issue #19884. https://github.com/etcd-io/etcd/issues/19884
14. Chaos Mesh issue #4539. https://github.com/chaos-mesh/chaos-mesh/issues/4539
15. x0x PR #223. https://github.com/saorsa-labs/x0x/pull/223
