# arc-longrun-progress-observability-20261126.md 异构复审报告（2026-11-26）

> **性质**：Layer-0 独立异构复审（T3，零代码/零门禁变更）。纪律同 P-020/P-023/P-030/P-062/P-160/P-161——**不采信**原文结论，全部以探针、读码、机检一手重验。
> **异构声明（RULE-5）**：本复审由 **GLM-5.3-Flash** 独立会话执行，调研文档由 DeepSeek-V4.1-Flash 产出——模型家族异构；reviewer 只标记问题、不改写实现（单向权限）。
> **对象**：[docs/arc-longrun-progress-observability-20261126.md](../docs/arc-longrun-progress-observability-20261126.md)（v0，329 行 / 24.6 KB）。工作树状态：干净（main @ `56b3dde` + P-192 未提交改动）。
> **探针**：`%TEMP%\p193_review_probe.py`、`%TEMP%\p193_review_probe2.py`（全部临时目录，零仓库变异；首轮探针在 `stage_events` 读取逻辑上预期算错一处，已用 v2 修正版复核）。

---

## 1. 一手复验（T 表）

| # | 项 | 探针/机检 | 结果 |
|---|---|---|---|
| T-1 | 心跳写入点：全仓仅 `_write_heartbeat` 一个定义，仅 `runner.py:1016` 处被调用，且在 `if result.status == StageStatus.DONE:` 分支内 | `Select-String -Path researchclaw\pipeline\runner.py -Pattern "_write_heartbeat"` | ✅ 原文 L65 断言准确 |
| T-2 | `heartbeat.json` 无「阶段开始」写入路径 | 同 T-1 + 读码 `runner.py` L1014-1016 | ✅ |
| T-3 | `llm.call` / `llm.result` 在 `EVENT_TYPES` 中声明但全仓零生产者 | `Get-ChildItem researchclaw -Recurse -Filter *.py | Select-String -Pattern '"llm\.call"|"llm\.result"'` | ✅ 零命中，原文 L77 断言准确 |
| T-4 | 日志配置 `basicConfig`/`dictConfig`/`setLevel` 全仓零命中 | 附录 A-2 命令执行 | ✅ 零命中，root logger 默认 WARNING 成立 |
| T-5 | `LeaseKeeper` 启动参数 `ttl=600`，续期间隔 `ttl/3=200s` | 读码 `runner.py` L271-280 + `lease.py` L301-320 | ✅ 原文 L87 与 §4.3 对齐 |
| T-6 | `stage_events.jsonl` 只在 Stage 4/5 DONE 后写，服务循环守卫，非进度上报 | 读码 `stage_events.py` `record_stage_progress` + `runner.py` L839-870 | ✅ 原文 L62-63 断言准确 |
| T-7 | `cost_log.jsonl` 每次 LLM 调用后追加、带 `stage`/`timestamp`、且 `flush()` | 读码 `cost_tracker.py` L227-237 + `runner.py` L807-809 | ✅ 原文 L43 与 §1.2 对齐 |
| T-8 | `agent_runs/attempt_NNN/` 由沙箱执行前创建，目录 mtime 对应执行尝试 | 读码 `code_agent.py` L1473-1487 + B 站现场 `ls -l` | ✅ 原文 L42-43 断言准确 |
| T-9 | `dashboard` 60s 硬编码、`read_run_state` 300s 判活跃 | 读码 `collector.py` L16-19 + `run_state.py` L25、L243-265 | ✅ 原文 L91-95、§2.5 表格准确 |
| T-10 | `Supervisor` 只看退出码/`restarts`/`max_wall_seconds`，不读 heartbeat/lease | 读码 `supervisor.py` L199 | ✅ 原文 L101 断言准确 |
| T-11 | 现场快照一致性：07:48Z `heartbeat.json` pid 181821、timestamp 11-25T14:14:37Z，与 P-191 旧进程一致 | B 站 `cat` 复核 | ✅ 17h34m 滞留成立 |
| T-12 | B 站 `agent_runs` 已有 attempt_001/002/003，main.py 3879→8823B | B 站 `ls -l` + `wc -c` | ✅ 实际进度已到第 3 次沙箱执行 |
| T-13 | `cost_log.jsonl` 本轮窗口 14 行，末条 07:56:15Z，`completion_tokens=16384` | B 站 `wc -l` + `tail -n 2` | ✅ 侧信道有效 |
| T-14 | §6.1 M1 `ProgressKeeper` 设计与现有 `_replace_with_retry` 原子写复用 | 读码 `runner.py` L172-189 | ✅ 复用路径存在，可行 |
| T-15 | §6.1 M1 `STALLED` 状态需增 `RunStatus` 枚举 | 读码 `run_state.py` `RunStatus` 定义 | ⚠️ 需改动枚举与 dashboard 契约，原文 L268 标记正确 |

---

## 2. 缺陷（D 表）

### D-1（P2）`STALLED` 状态落地路径未完全对齐

- **现状**：原文 §6.1 第 2 点建议 `read_run_state` 增加 `STALLED`，§6.1 第 3 点建议 dashboard 从 `heartbeat.interval_sec` 推导阈值。但 `RunStatus` 定义在 `run_state.py`，dashboard 读取的是 `RunState.is_active`（布尔），而非 `RunStatus` 枚举。引入 `STALLED` 至少需改：
  1. `run_state.py`：`RunStatus` 增 `STALLED`，`read_run_state` 逻辑分支
  2. `collector.py`：`RunSnapshot` 增 `status: "stalled"` 字段或复用 `is_active=False` + 新增 `stall_sec`
  3. 前端（如有）对 `"stalled"` 的显示
- **原文缺口**：§6.1 第 2 点只写了 `read_run_state`，未提 `RunStatus` 枚举与 `collector.py` 的同步改动。建议补全影响面说明。

### D-2（P2）`llm.call/llm.result` 启用与 `stage.progress` 二选一的决策依据偏薄

- **现状**：§6.2 第 1 点列为「二选一，避免双写」，但未给出选型矩阵。关键差异：
  - `llm.call/result`：粒度细（逐次调用），量大（本轮 14 次/4 分钟 ≈ 3.5/min），事件配额（A1-6）压力大
  - `stage.progress`：粒度粗（phase 变更），量可控（Stage 10 全程 ≤6 条），符合 §4.4 Lightning 低频采样原则
- **建议**：补一个 2×2 决策表（粒度/量/配额/可恢复性），明确选 `stage.progress` 作为 M2 默认，`llm.*` 仅在显式开启调试模式时启用。

### D-3（P3）`agent_runs` 纳入「正式侧信道」的具体做法未细化

- **现状**：§6.2 第 4 点「只读计数，不改其写盘逻辑」。但 `agent_runs` 目录名是 `attempt_001/002/...`，跨 Stage 复用时会重置计数（Stage 10 是 CodeAgent 私有）。若要在 `ops`/dashboard 统一展示，需约定：
  - 只读 `stage-10/agent_runs` 下最新目录 mtime 作为「当前 attempt」？
  - 还是让 CodeAgent 每次写 `stage-10/progress.json`（§6.2 第 2 点已含），以此为准，`agent_runs` 仅作归档？
- **建议**：明确以 `progress.json` 为单一事实源，`agent_runs` 仅作审计留存，避免双源不一致。

### D-4（P3）外部参考资料引用存在 1 处失效风险

- **条目 12**：CoreWeave LEET TUI（https://docs.coreweave.com/products/wandb/app/leet-tui）为商业托管文档，可能随产品版本变更或下线。建议改引 W&B 官方 `wandb.sdk.lib.sync_manager.SyncThread._heartbeat_interval` 源码（GitHub 永久链接）或删除该条。

---

## 3. 观察项（O 表）

| # | 内容 | 定级 |
|---|---|---|
| O-1 | §2.1 表格中 `stage_health.json` 标注「阶段（事后）」——实际上它在 `executor.py` 阶段返回前写（L846-863），此时 `result.status` 已定但 `_write_checkpoint` 尚未调用，严格说是「阶段末、checkpoint 前」。不影响结论，仅口径微差。 | 实现注记 |
| O-2 | §6.1 第 4/5 点（日志 `--log-level`、行缓冲、阶段始用 `logger.info`）属于 CLI/运行时通用改动，不应挂在「长跑可观测」单项下。若后续并入 B-31，建议拆为独立 P 行（如 B-31a）或登记在 G7 运维项。 | 实施建议 |
| O-3 | §6.3 第 2 点 `Supervisor` 增 stall 告警「默认只告警不重启」——但 `Supervisor` 目前是 `researchclaw run` 的包装器（`cli.py` `supervisor` 子命令），默认不启用。若要「默认告警」，需在 `supervisor` 子命令默认参数里开启，或由 `run --supervised` 隐式开启。原文未说明触发路径。 | 实施建议 |
| O-4 | §7 风险表「误报：合法长调用（单次 LLM 10+ 分钟）」——本轮观测到 `completion_tokens=16384` 单次调用约 4 分钟，尚未触及 10 分钟。若模型输出更长，`stale_after = max(3*200, 600) = 600s` 已覆盖 10 分钟，风险可控。原文阈值设计合理。 | 确认 |

---

## 4. 结论与待办

### 通过项（✅）

1. **取证完整**：E1 现场快照、E2 读码锚点（含行号）、E3 外部文档一一对应，无幻觉引用。
2. **因果链清晰**：L1–L6 六层失效链路完整解释了「磁盘推进、监控静默」的矛盾。
3. **社区对标到位**：六原则（P-1..P-6）覆盖 Temporal/Airflow/systemd/Lightning/LangGraph/K8s/W&B，映射表 §4.9 可直接作为设计依据。
4. **方案分层合理**：M1/P0（只补心跳 details + STALLED + 日志）、M2/P1（阶段内事件）、M3/P2（恢复 + 告警）可独立上线，不破坏 file-as-state 与事件摘要纪律（I-4）。
5. **验收口径可机检**：M1 4 条验收均可写成 pytest/探针，符合 ARC「机检优先」纪律。

### 待办（需原作者或后续立项处理）

| # | 项 | 责任 | 备注 |
|---|---|---|---|
| 1 | 补全 `STALLED` 影响面：`RunStatus` 枚举、`collector.py`、`dashboard` 前端 | 立项时 | D-1 |
| 2 | `llm.*` vs `stage.progress` 选型矩阵，建议默认 `stage.progress` | 设计冻结时 | D-2 |
| 3 | `agent_runs` 与 `progress.json` 单一事实源约定 | 实施时 | D-3 |
| 4 | 修正/删除参考文献 12（CoreWeave LEET） | 文档定稿前 | D-4 |
| 5 | §6.1 第 4/5 点（日志开关/行缓冲）是否拆为独立 P 行 | 立项规划时 | O-2 |
| 6 | `Supervisor` stall 告警默认开启路径（`run --supervised` 还是 `supervisor` 子命令） | 实施时 | O-3 |
| 7 | 立 B-31（T1）承载 M1，并在总纲 §3.2/§3.3 登记 | 本批后续 | §8 待决 1 |

---

## 5. 复审纪律确认

- ✅ 全程**不改写**原文档（零变异）
- ✅ 所有「✅」结论均来自探针/读码/机检，非采信原文
- ✅ 缺陷定级遵循 P1=阻塞、P2=需修、P3=可观
- ✅ 异构模型：GLM-5.3-Flash（本会话） vs DeepSeek-V4.1-Flash（原文产出会话）

---

**复审结果**：文档**通过**，可作为 B-31 立项依据。上述 7 项待办中，D-1/D-2/D-3 属设计冻结前必须闭合，D-4/O-2/O-3 属实施细节，建议在 B-31 spec 四文档阶段解决。

---

## 6. 核实与修正结果（2026-11-26 第二轮，实施方执行）

> 本节由**实施方**回填，记录对 §2–§3 每条意见的核实动作与落点。核实方式：读码 + 一手页面复检，不采信本报告原文。修正已写入 [调研文档 §9 修正记录](arc-longrun-progress-observability-20261126.md)。

| 意见 | 核实 | 关键证据 | 落点 |
|---|---|---|---|
| D-1 | **成立** | `RunStatus` 仅 5 值（[run_state.py L29-36](../researchclaw/run_state.py#L29-L36)）；`collector` 透传 `status.value`，`RunSnapshot` / `RunState.to_dict` / `/api/projects` 需同步 | 调研 §6.1 影响面表（5 处） |
| D-2 | **成立** | 原文仅「二选一」，无选型依据 | 调研 §6.2 六维矩阵，默认取 `stage.progress` |
| D-3 | **成立，且本报告低估了严重性** | `agent_runs` 与 `agent_sandbox` 均由 `CodeAgent._runs` 计数（[code_agent.py L1457](../researchclaw/pipeline/code_agent.py#L1457)、[L1477](../researchclaw/pipeline/code_agent.py#L1477)），Stage 10 每次重入从 `attempt_001` 重计 → **跨 PIVOT 不可比**，不是「约定不清晰」而是「数据本身不可用于跨轮比较」 | 调研 §6.2 第 4 条（单一事实源改为 `progress.json`） |
| D-4 | **成立** | 2026-11-26 复检 `https://docs.coreweave.com/products/wandb/app/leet-tui` 可访问，但正文**已无 `heartbeat` 字样**，15s 数字无法复现 | 参考文献 12 换为 W&B tracking FAQ；§4.7 删数值 |
| O-1 | **成立（口径）** | `stage_health.json` 在 `executor.py` 阶段返回前写，早于 runner 的 `_write_checkpoint` | 调研 §2.1 表格措辞 |
| O-2 | **采纳，并找到更强论据** | `acp_client._run_acp_with_heartbeat` 已实现 30s 进度日志（[acp_client.py L395-462](../researchclaw/llm/acp_client.py#L395-L462)），仅因缺失日志配置不可见 | 调研 §2.3 第 4 条、§6.1「可独立成批」（B-31a/B-31b） |
| O-3 | **成立，并发现更硬的阻塞** | `DEFAULT_MAX_WALL_SECONDS = 1800`（[supervisor.py L31](../researchclaw/runtime/supervisor.py#L31)）、CLI 默认同值（[cli.py L1948](../researchclaw/cli.py#L1948)）< Stage 10 单阶段时长 → 启用即误杀 | 调研 §2.6、§6.3 第 2 点、§6.4、§7 风险表 |
| O-4 | **成立且可控** | `stale_after = max(3×200, 600) = 600s` 覆盖 10 分钟长调用 | 无需改动 |

### 6.1 复核中新发现（本报告未列，实施方补充）

| # | 事实 | 证据 | 定级 |
|---|---|---|---|
| N-1 | dashboard 与 `/api/projects` 只枚举 `artifacts/rc-*`；`--output` 自定义 run（本次 `g7-baseline`）完全不可见，60s 阈值无从触发 | [collector.py L89-91](../researchclaw/dashboard/collector.py#L89-L91)、[projects.py L20-22](../researchclaw/server/routes/projects.py#L20-L22)；默认 run 名 `rc-<ts>-<hash>`（[cli.py L152-155](../researchclaw/cli.py#L152-L155)） | **P2（比 D-1 更贴近本次现场）** |
| N-2 | `ops` 枚举全部目录但 `status/last_stage` 只取 `checkpoint.json`，不读 heartbeat/lease → 长阶段恒显示上一阶段 | [ops.py L144-155](../researchclaw/runtime/ops.py#L144-L155) | P2 |
| N-3 | `acp_client` 已有 30s 进度心跳日志，但被 `logger.info` + 缺失日志配置静默 | [acp_client.py L459-462](../researchclaw/llm/acp_client.py#L459-L462) | P1（修复成本最低、收益最大） |

### 6.2 修正后的待办状态

| 原待办 | 状态 |
|---|---|
| 1 补全 `STALLED` 影响面 | **已闭合**（调研 §6.1 表） |
| 2 `llm.*` vs `stage.progress` 选型 | **已闭合**（默认 `stage.progress`） |
| 3 `agent_runs` 单一事实源 | **已闭合**（`progress.json` 为唯一事实源） |
| 4 修正参考文献 12 | **已闭合**（换 W&B FAQ，删 15s 数值） |
| 5 §6.1 第 4/5 点是否拆批 | **建议采纳**：拆 B-31a（日志可见性）/ B-31b（心跳 + STALLED），待用户裁决 |
| 6 supervisor 默认开启路径 | **已闭合**：stall 判定放 `run` 主循环；supervisor 仅作可选崩溃重启层，且须先改 `max_wall_seconds` |
| 7 立 B-31 并登记总纲 | **已完成**（roadmap §3.2 B-31 行 + §3.3 W0） |
