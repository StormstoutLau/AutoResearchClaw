---
id: arc-g7-concurrency-dual-plane-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-master-roadmap, arc-g7-soak-RESEARCH, arc-g7-orchestration-RESEARCH, arc-g7-drift-guard-RESEARCH, arc-g1-readiness-research]
upstream: arc-master-roadmap
---

# 调研：G7 并发/双平面段（P-172）

> **Feature**：G7 验收 A7-2（多 run 并发互不串扰）/ A7-3（双平面同 `ClaimStatus`）/ A7-5（Runbook 30 分钟恢复）/ A7-6（并发准入与预算前置拒绝）/ A7-7（worker slot 预留与 HITL 优先槽位），并补齐交付物「跨 run 事件归档策略」「Runbook + 观测看板」「并发准入（`max_concurrent_attempts` + `max_inflight_llm_calls`）」。
> **不在本批**：A7-1（72h field run）、A7-4（正式回放验收）——两者是 field run 验收，不因本批工具链就绪而虚报通过。
> **落点**：新增 `researchclaw/runtime/admission.py`、`researchclaw/llm/inflight.py`、`researchclaw/runtime/ops.py`；`config.py` / `runtime/supervisor.py` / `llm/client.py` / `cli.py` 接线；`docs/runbook-g7.md`。
> **先登记**：[observations-registry.md](../../docs/observations-registry.md) 的 high 项 O-165-3（wall/depth 溢出回归固化）/ O-165-6（`validate_task` 缺 `max_depth` 校验）**不在本批**：本批不触碰 `experiments/arc_bench/orchestration/`，按登记表 §2 承接规则留待下个 orchestration 批次。

## 1. 本仓现状（T1：源码/实测）

| 事实 | 证据 |
|---|---|
| 租约是**单 run 单写者**契约：`acquire` 冲突抛 `LeaseBusy`；同一 owner 幂等续约不增 fencing；不同 owner 接管 fencing+1 | [lease.py L1-L13](../../researchclaw/runtime/lease.py#L1-L13)、[L156-L190](../../researchclaw/runtime/lease.py#L156-L190) |
| fencing 只作**写者拒写**判据（`check_fencing`），不是全局序号 | [lease.py L246-L248](../../researchclaw/runtime/lease.py#L246-L248) |
| 跨进程租约锁用 `O_CREAT|O_EXCL` + 陈旧锁超时删除；PID 探活 Windows 用 `OpenProcess/GetExitCodeProcess`，POSIX 用 `os.kill(pid,0)` | [lease.py L116-L153](../../researchclaw/runtime/lease.py#L116-L153)、[L251-L288](../../researchclaw/runtime/lease.py#L251-L288) |
| 通用跨平台 advisory 锁已存在（Windows `msvcrt.LK_NBLCK` / POSIX `fcntl.flock` + 轮询 + 超时） | [filelock.py L1-L9](../../researchclaw/runtime/filelock.py#L1-L9)、[L59-L90](../../researchclaw/runtime/filelock.py#L59-L90) |
| supervisor **从不持有 run 租约**，只在 worker 可证死亡/过期时清理 stale lease；日志独立于 `events.jsonl`（无 lease/fencing） | [supervisor.py L1-L6](../../researchclaw/runtime/supervisor.py#L1-L6)、[L76-L99](../../researchclaw/runtime/supervisor.py#L76-L99) |
| supervisor 的 spawn 前无任何准入/配额检查；`_run_once` 直接 `Popen` + `wait` | [supervisor.py L101-L104](../../researchclaw/runtime/supervisor.py#L101-L104)、[L108-L136](../../researchclaw/runtime/supervisor.py#L108-L136) |
| `ProjectScheduler` 只是**进程内**优先队列：`_running: set`、`max_concurrent`，无跨进程持久化、无 HITL 保留槽、无 fencing | [scheduler.py L23-L89](../../researchclaw/project/scheduler.py#L23-L89) |
| 配置只有 `multi_project.max_concurrent=2`（项目级），无 `max_concurrent_attempts` / `max_inflight_llm_calls` / 优先槽 | [config.py L799-L806](../../researchclaw/config.py#L799-L806)、[L1695-L1699](../../researchclaw/config.py#L1695-L1699) |
| LLM 预算拒绝只在**运行中每次调用前**检查（`pre_call_budget_check`），没有 admission 边界的前置拒绝 | [client.py L322-L339](../../researchclaw/llm/client.py#L322-L339)、[model_policy.py L157-L164](../../researchclaw/llm/model_policy.py#L157-L164) |
| 已存在可复算的 `sum_cost_log(run_dir)`，可作 admission 前置拒绝的真值 | [cost_tracker.py L294-L325](../../researchclaw/cost_tracker.py#L294-L325) |
| 双平面生产/审计共用 `evaluate_claim`；Stage 23 与离线审计共用 `compare_claims`（唯一比对实现） | [claim_policy.py L154-L196](../../researchclaw/evidence/claim_policy.py#L154-L196)、[stage_hooks.py L198-L260](../../researchclaw/evidence/stage_hooks.py#L198-L260)、[offline_audit.py L54-L105](../../researchclaw/evidence/offline_audit.py#L54-L105) |
| Stage 23 会写 `claim_consistency.json`；离线审计**只读**（不写 run 目录） | [stage_hooks.py L275-L303](../../researchclaw/evidence/stage_hooks.py#L275-L303)、[offline_audit.py L108-L115](../../researchclaw/evidence/offline_audit.py#L108-L115) |
| 单 run 事件日志已有滚动 + 分段 + `apply_retention`（热 30 天 → gzip → 365 天删除），但**没有跨 run 归档/索引** | [event_log.py L474-L496](../../researchclaw/runtime/event_log.py#L474-L496) |
| soak 驱动已能注入重启并计算 `recovery_seconds`（`restart_injected` → 下次 `worker_started`） | [soak/driver.py L207-L367](../../researchclaw/soak/driver.py#L207-L367)、[soak/report.py L23](../../researchclaw/soak/report.py#L23) |
| 沙箱目录在 run 目录内（`stage-12/runs/.../sandbox`），结构上按 run 隔离，但无并发回归测试证明 | [_execution.py L266-L288](../../researchclaw/pipeline/stage_impls/_execution.py#L266-L288)、[L547](../../researchclaw/pipeline/stage_impls/_execution.py#L547) |
| HITL 等待靠 `waiting.json` + `response.json` 文件 IPC，轮询默认 2s；无「优先槽位」概念 | [hitl/file_wait.py L30-L31](../../researchclaw/hitl/file_wait.py#L30-L31)、[L70-L153](../../researchclaw/hitl/file_wait.py#L70-L153) |

**关键约束**：
1. 生产的无人值守入口是 `researchclaw supervisor`（[cli.py L479-L501](../../researchclaw/cli.py#L479-L501)），不是裸 `run`；准入放在 supervisor 才能在 spawn 前拦截。
2. 无新增外部依赖：跨进程协调只能用文件 + 现有 `exclusive_lock`（P-080），不得引入 Redis/DB。
3. 默认行为不得改变：新配置默认关闭/0，既有 4000+ 测试与单 run 路径零感知。
4. 预算前置拒绝必须用 run 目录真值（`cost_log.jsonl`），不能依赖进程内 tracker（resume 是新进程）。
5. 双平面不能自称「独立实现」：两平面共用同一判定内核，只能证明**同 oracle 重放一致 + 篡改可检**，不是 N-version。

## 2. 外部证据

### 2.1 工业官方 / 社区（T1，已回原文）

| # | 来源 | 关键结论 | 本批借用 | 不借用 |
|---|---|---|---|---|
| E1 | [Kubernetes — Resource Quotas](https://kubernetes.io/docs/concepts/policy/resource-quotas/) | 配额在**准入时**由 admission 控制器校验；超配额的新 Pod 被拒绝进入命名空间，而不是先创建再失败；支持按 `PriorityClass` 划分 scope | 预算/并发拒绝放在 **spawn 前**；准入失败必须显式记录，不创建半成品 | 不引入 K8s 依赖 |
| E2 | [Kubernetes — Pod Priority and Preemption](https://kubernetes.io/docs/concepts/scheduling-eviction/pod-priority-preemption/) | 优先级影响**调度顺序**；调度器可抢占低优先级 Pod；另有 **Non-preempting PriorityClass**（高优先级但不驱逐他人） | 用「非抢占式保留槽」保证 HITL 不被饿死：保留容量而不杀长任务 | 不做抢占（杀运行中 run 成本高且破坏检查点语义） |
| E3 | [Slurm — Quality of Service](https://slurm.schedmd.com/qos.html) | QOS 同时影响调度优先级、抢占与资源上限；可用 QOS 给一类作业保留/限制资源 | 「类别 + 上限」的双约束：normal 受 `max_attempts - reserved` 限制，HITL 受总上限限制 | 不实现多因子优先级计算 |
| E4 | [PostgreSQL — Explicit Locking / Advisory Locks](https://www.postgresql.org/docs/current/explicit-locking.html) | advisory lock 由应用定义语义，系统不强制；session 级锁在会话结束时自动清理 | 文件锁 + 租约的组合只在**使用该 helper 的写者**间生效（advisory 语义），必须在文档中声明边界 | 不使用数据库 |
| E5 | [SQLite — Write-Ahead Logging](https://www.sqlite.org/wal.html) | WAL 允许「多读者 + 单写者」；checkpoint 把 WAL 内容回写主库并**回收空间**，防止日志无界增长 | 跨 run 归档策略：单 run 内单写者 + 分段/checkpoint；跨 run 不合并真值，只做索引与逐 run 回收 | 不引入 SQLite |
| E6 | [Martin Kleppmann — How to do distributed locking](https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html) | 仅靠租约到期不安全（GC/暂停可在检查与写入之间发生）；写入端必须携带**单调 fencing token**，存储端拒绝旧 token | 复用既有 `lease.fencing`；slot 也带单调 `fencing`，便于审计「谁先谁后」 | 不实现 Redlock |
| E7 | [Borg, Omega, and Kubernetes（ACM Queue 2016）](https://dl.acm.org/doi/10.1145/2898442.2898444) | 十年三代容器管理系统的经验：声明式 API、优先级/配额、共享状态与乐观并发是规模化调度的核心 | 「准入 + 配额 + 优先级」是成熟形态；本仓用最小文件实现同语义子集 | 不构建集中式调度器 |
| E8 | [Google SRE — Incident Management Guide](https://sre.google/resources/practices-and-processes/incident-management-guide/) | 事件响应基于 ICS 的「3C」（coordinate/communicate/control），角色与流程预先是恢复速度的主因 | Runbook 必须显式写角色/判定/命令/验证/回退，而不是只列命令 | 不引入 IMAG 工具链 |

### 2.2 学术（T1，已回原文/摘要）

| # | 来源 | 关键结论 | 本批借用 |
|---|---|---|---|
| E9 | McKeeman, *Differential Testing for Software*, Digital Technical Journal 10(1):100-107, 1998（[PDF](https://www.zx.net.nz/mirror/digital/DTJ/www.hpl.hp.com/hpjournal/dtj/vol10num1/vol10num1art9.pdf)） | 对同一输入用两个实现/两条路径执行并比较结果，可发现单路径无法暴露的偏差 | 双平面「同一 claim 两路径重算 + 比对」的方法论来源 |
| E10 | [Borg/Omega/Kubernetes 论文](https://dl.acm.org/doi/pdf/10.1145/2898442.2898444) 的 admission/priority 章节 | 大规模系统把「准入」与「调度」分离：先决定能否进入，再决定放哪 | 本批把 admission（槽位/预算）与 supervisor（重启/退避）分层，互不耦合 |

### 2.3 与本仓既有裁决的关系

| 既有裁决 | 本批关系 |
|---|---|
| G1a/Q5：单 run 租约 + fencing + supervisor 不持租约 | **不改**；slot 是 supervisor 层的第二种资源，不替代 run 租约 |
| G3 P-080：advisory 文件锁 | **复用** `exclusive_lock` 作为 registry 唯一写入口 |
| G6：`pre_call_budget_check` + `budget_exhausted` | **复用**语义；新增 spawn 前拒绝，二者不重复计数 |
| G2 M5：`compare_claims` 唯一比对实现 | **不改**；A7-3 只加并发/跨 run 证据 |
| Q9：热 30 天 / 归档 365 天 / 摘要永久 | **沿用**为跨 run 归档参数默认值 |

### 2.4 降级记录

- `mcp_paper-search_search_arxiv` 两次返回空数组；改用 WebSearch 定位 McKeeman 1998 与 Borg 论文，再直接取 PDF/摘要页。
- `WebFetch` 对 `sre.google/sre-book/managing-incidents/`、ACM Queue 正文、Cornell SEDA PDF 返回空内容；保留可访问的 Google SRE incident guide 检索摘要与 ACM DOI 摘要页，不把论坛转述当承重证据。
- Argo Workflows 的 `concurrencyPolicy` 页面抓取为空；并发语义改用 K8s 配额/优先级 + Slurm QOS 两类官方文档承重。

## 3. 综合分析

1. **准入必须是 spawn 前的同步动作**（E1/E8）：仅靠 worker 内部预算检查会让 resume 先起进程再死，既浪费资源也污染事件。supervisor 是唯一合适边界。[★★★★★]
2. **HITL 不能靠抢占，只能靠保留**（E2/E3）：抢占会杀掉长跑 run 并制造半成品；保留 1 个槽位即可保证人工消息最多等一个 worker 退出。[★★★★★]
3. **跨进程协调用文件 + advisory 锁足够**（E4/E5）：本仓单机多 run 规模（N≤数十）不需要集中调度器；registry JSON + 锁 + 原子替换可崩溃恢复，且零新依赖。[★★★★☆]
4. **slot 也要 fencing**（E6）：文件锁只能防并发写坏 registry，不能证明「谁先拿到」；单调 `fencing` 让审计可排序，与 run 租约同构。[★★★★☆]
5. **双平面是 differential replay，不是 N-version**（E9）：两平面共用内核，正确断言只能是「同输入同状态 + 生产记录被篡改可检 + 审计只读」，不能宣称独立实现消除共模错误。[★★★★★]
6. **Runbook 的验收是时间，不是文档存在**（E8）：必须有一次计时演练；文档必须含症状→判定→命令→验证→回退，命令可直接复制执行。[★★★★☆]
7. **跨 run 归档不合并真值**（E5）：每个 run 目录仍是唯一真值；跨 run 只允许派生索引与逐 run 回收，索引丢了可从 run 目录重建。[★★★★☆]

## 4. 未决项（四元块）

- **U-1 队列等待语义**
  - 判据：槽位满时 supervisor 不 spawn；等待超过 `queue_timeout_sec` 后以非 retryable 的 CONFIG(78) 结束并留队列记录
  - 触发条件：Step 3 设计
  - 当前倾向：默认 `queue_timeout_sec=0`（立即返回 queued），由上层调度器重试；避免默认挂死
  - 证据等级：E1/E3

- **U-2 inflight 限流的归属**
  - 判据：`max_inflight_llm_calls>0` 时单 run 内并发 LLM 调用不超过上限；跨 run 公平由 slot 负责
  - 触发条件：Step 3 设计
  - 当前倾向：token 目录放 `run_dir/.inflight`，只在本 run 内计数
  - 证据等级：E5/E7

- **U-3 跨 run 归档的索引真相**
  - 判据：`RUN_INDEX.jsonl` 可由 run 目录重建；删除索引不影响任何 run 的可回放性
  - 触发条件：Step 3 设计
  - 当前倾向：索引 append-only + 锁；字段只取 `events_summary.json` 的派生值
  - 证据等级：E5

- **U-4 Runbook 演练的可重复性**
  - 判据：演练步骤只依赖仓库内命令与合成 run；不依赖真实 LLM/网络
  - 触发条件：Step 3 设计
  - 当前倾向：用 `soak` 注入硬杀 + `supervisor` 恢复 + `soak verify` 收敛的合成演练
  - 证据等级：E8

- **U-5 配置落位**
  - 判据：不新增顶层 section，字段进入既有 `multi_project`；默认值使既有行为不变
  - 触发条件：Step 3 设计
  - 当前倾向：`max_concurrent_attempts=2`、`hitl_priority_slots=1`、`max_inflight_llm_calls=0`、`slot_root=".researchclaw/slots"`、`queue_timeout_sec=0.0`
  - 证据等级：E3（config.py 源码）
