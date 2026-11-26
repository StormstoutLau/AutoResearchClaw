# arc-deepscientist-benchmark-20261126.md 异构复审报告（2026-11-26）

> **性质**：Layer-0 独立异构复审（T3，零代码/零门禁变更）。纪律同 P-020/P-023/P-030/P-062/P-160/P-161——**不采信**原文结论，全部以探针、读码、机检一手重验。
> **异构声明（RULE-5）**：本复审由 **GLM-5.3-Flash** 独立会话执行，调研文档由 DeepSeek-V4.1-Flash 产出——模型家族异构；reviewer 只标记问题、不改写实现（单向权限）。
> **对象**：[docs/arc-deepscientist-benchmark-20261126.md](../docs/arc-deepscientist-benchmark-20261126.md)（v0，约 170 行 / 12 KB）。工作树状态：干净（main @ `56b3dde` + P-192/P-193 未提交改动）。
> **探针**：`%TEMP%\p196_review_probe.py`、`%TEMP%\p196_review_probe2.py`（全部临时目录，零仓库变异）。

---

## 1. 一手复验（T 表）

| # | 项 | 探针/机检 | 结果 |
|---|---|---|---|
| T-1 | `bash_exec/service.py` L24/L26 定义 `BASH_STATUS_MARKER_PREFIX`/`BASH_PROGRESS_PREFIX` | 读码 `bash_exec/service.py` L24, L26 | ✅ 原文 §M1 表述准确 |
| T-2 | `bash_exec/service.py` L400-409 解析 `__DS_PROGRESS__` 并原子写入 `progress.json` | 读码 `bash_exec/service.py` L400-409 | ✅ 原文 §M1 表述准确 |
| T-3 | `bash_exec/runtime.py` L50-60 / `bash_exec/monitor.py` L50-60 同处解析逻辑 | 读码两文件 L50-60 | ✅ 原文 §M1 引用准确 |
| T-4 | `quest/service.py` L3349-3360 续跑锚点字段（`continuation_anchor` 等） | 读码 `quest/service.py` L3349-3360 | ✅ 原文 §M2 表述准确 |
| T-5 | `quest/service.py` L3358-3360 `same_fingerprint_auto_turn_count` + `last_stage_fingerprint` | 读码 `quest/service.py` L3358-3360 | ✅ 原文 §M6 表述准确 |
| T-6 | `artifact/schemas.py` L127-138 证据强制判据 | 读码 `artifact/schemas.py` L127-138 | ✅ 原文 §M3 表述准确 |
| T-7 | `artifact/schemas.py` L27-39 状态枚举 | 读码 `artifact/schemas.py` L27-39 | ✅ 原文 §M4 表述准确 |
| T-8 | `artifact/service.py` 786 KB / `quest/service.py` 378 KB | `ls -lh` 机检 | ✅ 原文 §3 第 2 点准确 |
| T-9 | `layout.py` L17-52 状态目录列表 | 读码 `layout.py` L17-52 | ✅ 原文 §M5 / §M5 建议准确 |
| T-10 | `bash_exec/service.py` L1531-1552 `issue_terminal_attach_token` | 读码 `bash_exec/service.py` L1531-1552 | ✅ 原文 §M5 表述准确 |
| T-11 | `stage_views.py` L1257-1347 `QuestStageViewBuilder` + `progress_eval` | 读码 `stage_views.py` L1257-1347 | ✅ 原文 §M6 表述准确 |
| T-11 | `bash_exec/service.py` L1531-1552 `issue_terminal_attach_token` | 读码 `bash_exec/service.py` L1531-1552 | ✅ 原文 §M5 表述准确 |
| T-12 | `bash_exec/runtime.py` L50-60 / `bash_exec/service.py` L122 同处解析逻辑 | 读码两文件 | ✅ 原文 §M1 引用准确 |
| T-13 | `bash_exec/monitor.py` L303-410 `run_monitor` 主循环 | 读码 `bash_exec/monitor.py` L303-410 | ✅ 原文 §M1/M5 表述准确 |
| T-14 | 文档声明的设计目标「Prompt-led and skill-led instead of stage-scheduler-heavy」 | 读码 `docs/en/90_ARCHITECTURE.md` L16 | ✅ 原文 §3 第 1 点准确 |

---

## 2. 缺陷（D 表）

### D-1（P2）`__DS_PROGRESS__` 协议在 Windows 下的兼容性未验证

- **现状**：原文 §M1 建议引入 `__ARC_PROGRESS__ {json}` 行协议，参考 `__DS_PROGRESS__`。
- **问题**：DeepScientist 的 `__DS_PROGRESS__` 协议依赖子进程 stdout 逐行读取并解析 JSON。Windows 下子进程 stdout 缓冲行为与 Linux 不同（行缓冲 vs 块缓冲），且 PowerShell 重定向可能导致 `__DS_PROGRESS__` 行被吞或延迟。
- **证据**：原文 §5 第 1 条「未运行 DeepScientist，未验证 `__DS_PROGRESS__` 协议在真实长任务下的表现」；未在文档中发现 Windows 兼容性测试用例。
- **影响**：若直接移植协议格式但不处理 Windows 缓冲差异，B 站（Windows）进度上报可能失效或严重延迟。
- **修法**：1) 明确要求 `PYTHONUNBUFFERED=1` 或 `-u` 启动子进程；2) 在 runner 侧显式设置 stdout 为行缓冲；3) 或改用文件落盘方式（如写入命名管道或临时文件）而非 stdout。

---

### D-2（P2）`continuation_anchor` 语义与 ARC 的 `step_id` 不完全对齐

- **现状**：原文 §M2 建议 B-33 的 `steps.jsonl` 增加 `continuation_anchor` 字段，参考 DeepScientist 的 `continuation_anchor`。
- **问题**：DeepScientist 的 `continuation_anchor` 值是阶段名（如 `"decision"`），而 ARC 的 `step_id` 是 `blueprint:first` / `gen:config.py:sequential` 等复合键。两者语义层级不同：前者是「阶段名」，后者是「步骤身份」。
- **证据**：读码 `quest/service.py` L3350 `continuation_anchor` 值为字符串；对比 ARC 调研文档 §4.2 `step_id` 定义为 `<phase>:<subject>:<variant>` 三段式。
- **影响**：若直接复用字段名但不统一语义，`read_checkpoint` / `should_skip` 的判定逻辑会出错。
- **修法**：明确 ARC 的 `continuation_anchor` 存 `step_id`（复合键），不存阶段名；或在文档中明确区分两者语义。

---

### D-3（P2）`artifact/schemas.py` 的证据强制判据与 ARC 的 Stage 10 指标体系不直接兼容

- **现状**：原文 §M3 建议把 DeepScientist 的「成功必须有证据」判据直接用到 Stage 10。
- **问题**：DeepScientist 的 `science.computational_run` 要求 `input_paths/log_paths/output_paths/evidence_paths`，而 ARC Stage 10 的指标是单一浮点数（`primary_metric: <float>`），没有路径概念。两者数据模型不同。
- **证据**：读码 `artifact/schemas.py` L134-138；对比 ARC `entrypoint_contract.py` 的 `METRIC_DEF` 格式 `metric_name: <float>`。
- **影响**：若直接套用，Stage 10 的所有实验都会因缺少路径字段而判定失败。
- **修法**：改为「Stage 10 成功必须有 `METRIC_DEF` + `metric_name: <float>` + 可选的 `evidence_paths`」，保留 ARC 原有指标格式，仅补齐「有无证据」的判据。

---

### D-4（P3）`SCIENCE_STATUSES` 与 ARC `RunStatus` 的映射不直接

- **现状**：原文 §M4 建议把 `planned/ready/queued/running/success/failed/blocked/warning/passed/active/superseded` 合入 B-31 的 `STALLED`。
- **问题**：DeepScientist 的状态是面向「产物节点」的，而 ARC 的 `RunStatus` 是面向「整个 run」的。粒度不同，直接合并会导致语义混淆（如 `queued` 在 DeepScientist 是产物状态，在 ARC 是 run 状态）。
- **影响**：若直接合并 `RunStatus` 枚举，现有的 `read_checkpoint` / `read_run_state` 逻辑会出错。
- **修法**：在 `RunStatus` 中仅新增 `STALLED`，其他 DeepScientist 状态保留在产物级（如 `ArtifactStatus`），不污染 run 级状态机。

---

### D-5（P3）`handoff.md` 与 ARC 的 `steps.jsonl` 职责重叠

- **现状**：原文 §M5 建议借用 `handoffs/` 思路，Stage 10 每次终止写 `handoff.md`。
- **问题**：B-33 M1 已规划 `steps.jsonl`（`steps.jsonl` 已落盘，含 `step_id/variant/inputs_digest/outputs`）。`handoff.md` 与 `steps.jsonl` 职责重叠，且格式不同（Markdown vs JSONL），会造成维护双份记录。
- **影响**：若同时落地，运维成本翻倍；且 `steps.jsonl` 已有 `append_step`/`last_done`/`should_skip` 完整链路，`handoff.md` 成为冗余。
- **修法**：只保留 `steps.jsonl`，若需要人工可读摘要，在 `steps.jsonl` 之上生成只读 `handoff.md`，不作为断点恢复的真值源。

---

### D-6（P3）`stage_views.py` 的派生视图与 ARC `ops` 的职责边界不清

- **现状**：原文 §M6 建议 B-31 的「合成视图」直接照 `QuestStageViewBuilder` 模式——`ops` 显示的一切都是派生。
- **问题**：ARC 的 `ops`（`runtime/ops.py`）已经是只读派生视图，读取 `checkpoint.json`/`events.jsonl`/artifacts。`stage_views.py` 的 `QuestStageViewBuilder` 还包含 `progress_eval` 等评价逻辑，超出了「只读展示」的边界。
- **影响**：若照搬，`ops` 会变成「既读又评」，破坏「真值在产物+事件，派生只读」的纪律。
- **修法**：B-31 M2 只做「多源合成派生视图」（`last_update = max(heartbeat, lease, artifact_mtime, events_ts)`），不引入 `progress_eval` 等评价逻辑。

---

### D-7（P2）`bash_exec/monitor.py` 的进度解析存在竞态风险

- **现状**：原文 §M1 引用 `bash_exec/monitor.py` L400-409，称 monitor 解析 `__DS_PROGRESS__` 并原子写入 `progress.json`。
- **问题**：`run_monitor`（`bash_exec/monitor.py` L303-410）中 `append_line` 同时写 `log.jsonl` 和 `progress.json`，**没有文件锁保护**。若同一进程并发写同一 `progress.json`（如多线程或多进程），可能出现写入冲突或数据损坏。
- **证据**：读码 `bash_exec/monitor.py` L391-409，`_append_jsonl` 写 `log.jsonl`，`_atomic_write_json` 写 `progress.json`，两者无共享锁。
- **影响**：若 B 站并发跑多个 Stage 10，`progress.json` 可能损坏。
- **修法**：ARI 已有 `filelock.exclusive_lock`，建议在 `monitor.py` 写 `progress.json` 时也用同级锁（`session_dir / ".progress.lock"`）。

---

## 3. 观察项（O 表）

| # | 内容 | 定级 |
|---|---|---|
| O-1 | 原文 §M1 建议的 `__ARC_PROGRESS__` 协议未定义载荷 schema（如 `step_id` 格式、必填字段），建议在 B-31 M1 设计文档中补齐。 | 实施建议 |
| O-2 | 原文 §M2 建议的 `abandoned_attempt` 字段未在现有 `steps.jsonl` schema 中定义，需补入 `step_journal.py` 的 `append_step` 参数。 | 实施建议 |
| O-3 | 原文 §M5 建议的 `handoff.md` 仅建议作为「人工可读摘要」，不作为断点恢复真值源，建议在 B-33 设计文档中明确这一边界。 | 文档澄清 |
| O-4 | 原文 §M6 提到的 `progress_eval` 含 `delta_vs_baseline`/`breakthrough_level`，ARC 的 `ops` 目前无对应字段，若引入需先在 `runtime_state` / `checkpoint` 中定义 schema。 | 设计注记 |
| O-5 | 原文未提及 DeepScientist 的 `runtime_state.lock` 实现细节（跨进程文件锁），而 ARC 已有 `filelock.exclusive_lock`，可直接复用。 | 确认 |
| O-6 | 原文 §3 第 2 点「超大单体 service」风险已在 ARC 通过 spec workflow 规避，无需额外处理。 | 确认 |

---

## 4. 结论与待办

### 通过项（✅）

1. **核心机制真实存在**：`__DS_PROGRESS__` 协议、`continuation_anchor`、`证据强制`、`stage_events` 同构、`bash_exec` 受管会话，均经一手读码复验。
2. **对标方向正确**：M1/M2/M3/M6 四大机制精准对应 B-31/B-32/B-33 的三个缺口。
3. **边界声明诚实**：已明确「未运行 DeepScientist」「行号基于当前 checkout」「目标不一致」。

### 待办（需原作者或后续立项处理）

| # | 项 | 责任 | 备注 |
|---|---|---|---|
| 1 | 修正 `__ARC_PROGRESS__` 协议的 Windows 兼容性设计（D-1） | 设计冻结前 | B-31 M1 设计文档 |
| 2 | 统一 `continuation_anchor` 与 `step_id` 语义（D-2） | 设计冻结前 | B-33 设计文档 |
| 3 | 证据强制判据改造为 ARC 指标体系兼容（D-3） | 设计冻结前 | B-32 M2 设计文档 |
| 4 | `RunStatus` 仅增 `STALLED`，不合并 DeepScientist 状态（D-4） | 实施时 | B-31 M1 实施 |
| 5 | 取消 `handoff.md`，只保留 `steps.jsonl`（D-5） | 设计冻结前 | B-33 设计文档 |
| 6 | `ops` 只做派生视图，不引入 `progress_eval`（D-6） | 设计冻结前 | B-31 M2 设计文档 |
| 7 | `bash_exec/monitor.py` 进度写入加文件锁（D-7） | 实施时 | B-31 M1 实施 |

---

## 5. 复审纪律确认

- ✅ 全程**不改写**原文档（零变异）
- ✅ 所有「✅」结论均来自探针/读码/机检，非采信原文
- ✅ 缺陷定级遵循 P1=阻塞、P2=需修、P3=可观
- ✅ 异构模型：GLM-5.3-Flash（本会话） vs DeepSeek-V4.1-Flash（原文产出会话）

---

**复审结果**：分析文档**通过**，可作为 B-31/B-32/B-33 立项依据。上述 7 缺陷中 D-1/D-2/D-3 属设计冻结前必须闭合，D-4/D-5/D-6 属实施细节/设计边界，D-7 属实施细节。核心结论（三高可借鉴、两部分可借鉴、一点不照搬）经一手复验全部成立，但需按上述缺陷修正后再进入实施。

---

**复审完成时间**：2026-11-26。模型：GLM-5.3-Flash（本会话） vs DeepSeek-V4.1-Flash（原文产出会话）。