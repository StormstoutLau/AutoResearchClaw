# 07 · HITL 与协作系统

本篇覆盖 `hitl/`、`copilot/`、`collaboration/`，以及 `calendar/`、`voice/`、`project/`、`trends/`。

---

## 1. HITL 干预模式

### 1.1 六种模式

`hitl/config.py:10-18` 的 `InterventionMode`：

| 模式 | 行为 |
|------|------|
| `full-auto` | 全部自动，不停顿 |
| `gate-only` | 只在 3 个 Gate（5/9/20）暂停审批 |
| `checkpoint` | 在每个 Phase 边界（2/6/8/11/13/15/19/23）暂停 |
| `step-by-step` | 每个阶段后都暂停，可编辑、可流式查看 |
| `co-pilot` | 在关键阶段深度协作，其余自动；结合 SmartPause |
| `custom` | 全部关闭，由 `stage_policies` 逐阶段配置 |

### 1.2 StagePolicy

`hitl/config.py:28-56` 定义单阶段策略：

| 分组 | 字段 |
|------|------|
| 基本控制 | `auto_execute`、`pause_before`、`pause_after`、`require_approval` |
| 观察 | `stream_output`、`show_llm_calls` |
| 干预 | `allow_edit_output`、`allow_inject_prompt`、`enable_collaboration` |
| 质量 | `min_quality_score`、`max_auto_retries` |
| 超时 | `human_timeout_sec`、`auto_proceed_on_timeout` |

`_default_policy_for_mode()`（`config.py:200-243`）按模式生成默认策略：

| 模式 | 规则 |
|------|------|
| gate-only | Stage 5/9/20：`require_approval=True`、`allow_edit_output=True` |
| checkpoint | Phase 边界：`pause_after=True`、`require_approval=True`、`allow_edit_output=True` |
| step-by-step | 所有阶段 `pause_after=True`、`allow_edit_output=True`、`stream_output=True` |
| co-pilot | 暂停集合 `{1,2,3,10,13,16,18,23}`、审批集合 `{5,8,9,15,20}`、协作集合 `{7,8,9,17}`、流式集合 `{12}` |
| full-auto / custom | 全部默认关闭 |

### 1.3 预设

`hitl/presets.py`：

| 预设 | 函数 | 说明 |
|------|------|------|
| `co-pilot` / `copilot` | `copilot_preset()` (`presets.py:12`) | 推荐模式 |
| `express` | `express_preset()` (`presets.py:37`) | 只审 8/9/20 三个关键点 |
| `thorough` | `thorough_preset()` (`presets.py:57`) | 每个 Phase 边界都审 |
| `learning` | `learning_preset()` (`presets.py:78`) | 每阶段暂停，教学用 |
| `autonomous` / `full-auto` | `autonomous_preset()` (`presets.py:89`) | HITL 关闭 |
| `gate-only` | `gate_only_preset()` (`presets.py:97`) | 仅 3 个门 |
| `step-by-step` | `step_by_step_preset()` (`presets.py:105`) | 每阶段暂停 |

`get_preset(name)`（`presets.py:130`）与 `list_presets()`（`presets.py:138`）供 CLI 使用。

---

## 2. 会话生命周期

### 2.1 核心对象

| 对象 | 位置 | 说明 |
|------|------|------|
| `HITLSession` | `hitl/session.py:37` | 一次 run 的全部人机交互状态；可持久化，供 `attach` 重连 |
| `SessionState` | `session.py:27` | active/paused/waiting_human/collaborating/completed/aborted |
| `Intervention` | `hitl/intervention.py:108` | 一次干预记录 |
| `WaitingState` | `intervention.py:179` | 「为什么暂停 + 可用动作」 |
| `HumanInput` | `intervention.py:65` | 人工输入（action、message、guidance、edited files） |
| `InterventionType` / `PauseReason` / `HumanAction` | `intervention.py:12/36/49` | 枚举 |

### 2.2 暂停—等待—恢复

```
session.pause(stage, name, reason, context_summary, output_files)   # session.py:140
    → state = WAITING_HUMAN，写 waiting 状态到磁盘
session.wait_for_human()                                             # session.py:169
    → 调用 input callback（CLI 阻塞 / WS 等待 / MCP / scripted）
    → 记录 intervention、更新状态、持久化
```

`set_input_callback()`（`session.py:88`）把具体交互通道注入会话；这使同一套 HITL 逻辑可以跑在终端、WebSocket、MCP 或脚本回放上。

### 2.3 策略查询

`HITLSession` 提供：

- `should_pause_before()` / `should_pause_after()`（`session.py:108/113`）
- `should_stream()` / `should_collaborate()`（`session.py:123/128`）
- `quality_threshold()`（`session.py:133`）
- `get_policy()`（`session.py:105`）

`should_pause_after()` 在 `pause_after`、`require_approval`、`enable_collaboration` 任一为真时返回 True。

---

## 3. 与 Pipeline 的接线

`pipeline/executor.py` 在两个位置接入 HITL：

### 3.1 前置钩子 `_run_hitl_pre_stage()`（`executor.py:200-254`）

- 若策略要求 `pause_before` → `session.pause(PRE_STAGE)`；
- `SKIP` → 返回 DONE（跳过本阶段）；
- `ABORT` → 返回 FAILED + `decision="abort"`；
- 有 `guidance` → 写入 `stage-XX/hitl_guidance.md`；
- 否则返回 None，正常执行。

### 3.2 后置钩子 `_run_hitl_post_stage()`（`executor.py:257-437`）

1. **CostGuard**：超预算时暂停，可 ABORT；
2. **SmartPause**：策略不要求暂停时，用置信度模型判断是否值得人工介入；
3. 决定暂停原因（GATE_APPROVAL / POST_STAGE / CONFIDENCE_LOW / QUALITY_BELOW_THRESHOLD）；
4. 汇总上下文（状态、产物、前 500 字符）；
5. `session.pause()` + `wait_for_human()`；
6. 根据 `HumanAction` 返回不同 `StageResult`：
   - `APPROVE` → 原结果
   - `REJECT` → `REJECTED`，`decision="pivot"`
   - `EDIT` → 原结果（文件已被适配器修改）
   - `SKIP` → DONE
   - `ABORT` → FAILED，`decision="abort"`
   - `COLLABORATE` → 进入协作循环 `_run_collaboration_loop()`
   - `INJECT` → 保存 `hitl_guidance.md`

---

## 4. 适配器（Adapter）

`hitl/adapters/__init__.py:10-35` 定义 `HITLAdapter` 协议：

```python
collect_input(waiting) -> HumanInput
show_stage_output(...)
show_message(...)
show_error(...)
show_progress(...)
```

| 适配器 | 位置 | 用途 |
|--------|------|------|
| `CLIAdapter` | `adapters/cli_adapter.py:99` | 终端暂停面板、动作选择、编辑、聊天 |
| `WebSocketHITLAdapter` | `adapters/ws_adapter.py:41` | Web 仪表盘实时交互 |
| `MCPHITLAdapter` | `adapters/mcp_adapter.py:90` | 向外部 Agent 暴露 `hitl_get_status/approve/reject/inject/view_output` |
| `ScriptedHITLAdapter` | `adapters/scripted_adapter.py:50` | 读取预写干预 JSON，匹配阶段返回输入，否则自动 approve；用于可复现实验 |

CLI 在 `cmd_run` 中根据 `--interventions` 或 `HITL_INTERVENTIONS_FILE` 选择 Scripted，否则用 CLIAdapter（`cli.py:377-395`）。

---

## 5. 智能暂停与守护

| 组件 | 位置 | 作用 |
|------|------|------|
| `ConfidenceSignal` | `hitl/smart_pause.py:23` | 各信号（质量、置信度、新颖性风险、历史拒绝、阶段关键性） |
| `SmartPause` | `hitl/smart_pause.py:94` | 加权求 `overall_confidence`，低于阈值（默认 0.7）建议暂停 |
| `QualityPrediction` / `QualityPredictor` | `hitl/quality_predictor.py:19/42` | 按阶段评估文献、假设、实验、结果、草稿、引用，预测最终质量 |
| `CostStatus` / `CostGuard` | `hitl/cost_guard.py:19/38` | 跟踪成本与预算，50%/80%/100% 阈值，`should_pause()` |
| `EscalationLevel` / `EscalationPolicy` / `EscalationTracker` | `hitl/escalation.py:25/35/68` | 分层通知（terminal → Slack → email → 自动停止） |
| `InterventionStats` / `InterventionLearner` | `hitl/learning.py:22/64` | ALHF：从历史干预学习暂停策略 |
| `Claim` / `VerificationReport` / `ClaimVerifier` | `hitl/claim_verifier.py:25/47/68` | 从生成文本抽取 claim，对照文献/实验结果标记 grounded/ungrounded |
| `compute_sha256()` / `generate_manifest()` / `verify_manifest()` | `hitl/checksums.py:20/29/67` | 阶段产物哈希与完整性校验 |
| `Notification` / `NotificationManager` | `hitl/notify.py:17/44` | 暂停/质量下降/错误通知 |
| `StageEditor` / `StageReviewer` | `hitl/editor.py:14/204` | 阶段产物编辑与复核 |
| `HookRegistry` | `hitl/hooks.py:42` | 扩展钩子 |

---

## 6. 分支探索

`hitl/branching.py`：

| 类 | 位置 | 说明 |
|----|------|------|
| `Branch` | `branching.py:30` | 分支元数据 |
| `BranchComparison` | `branching.py:69` | 多分支对比结果 |
| `BranchManager` | `branching.py:84` | `create_branch()`（复制 pipeline 状态）、`compare_branches()`、`merge_branch()` |

`create_branch()`（`branching.py:84`）在任意阶段复制 run 目录到分支目录，用于并行探索多个假设；`merge_branch()`（`branching.py:158`）把选定分支从某阶段起覆盖回主线。
`copilot/branching.py:15` 提供一套更面向 Co-Pilot 的 `BranchManager`（create/list/switch/delete/compare）。

---

## 7. 三个协作工坊

| 工坊 | 类 | 位置 | 用于阶段 |
|------|----|------|----------|
| Idea Workshop | `IdeaCandidate` / `IdeaEvaluation` / `IdeaWorkshop` | `hitl/workshops/idea.py:22/64/89` | Stage 7–8：头脑风暴、评分、精炼、查新 |
| Baseline Navigator | `BaselineCandidate` / `BenchmarkCandidate` / `BaselineNavigator` | `hitl/workshops/baseline.py:21/52/80` | Stage 9：AI 建议基线 + 人工增删 + 复现检查 |
| Paper Co-Writer | `SectionDraft` / `PaperCoWriter` | `hitl/workshops/paper.py:22/41` | Stage 16–19：逐节共同撰写、人工编辑、AI 润色 |

### 协作会话对象

| 类 | 位置 | 说明 |
|----|------|------|
| `ChatMessage` / `ChatSession` | `hitl/chat.py:17/48` | 人机聊天记录与会话 |
| `CollaborationSession` | `hitl/collaboration.py:23` | 共享产物、人工编辑、AI 响应、修订历史 |

`_run_collaboration_loop()`（`executor.py:440-564`）提供终端命令：`done`、`abort`、`show <file>`、`edit <file>`、`files`，其余输入作为聊天。

---

## 8. CoPilot（独立于 HITL 的一套控制器）

`copilot/` 是早期/并行的 Co-Pilot 实现：

| 类 | 位置 | 说明 |
|----|------|------|
| `ResearchMode` | `copilot/modes.py:8` | `co-pilot` / `auto-pilot` / `zero-touch` |
| `CoPilotController` | `copilot/controller.py:18` | `should_pause(stage, is_gate)`、展示结果、请求反馈、处理反馈、从配置构造 |
| `Feedback` / `FeedbackHandler` | `copilot/feedback.py:27/39` | 反馈模型与持久化 |
| `BranchManager` | `copilot/branching.py:15` | 分支管理 |

关系说明：**运行时主路径使用 `hitl/`**（CLI `--mode` 解析到 `hitl.presets`）；`copilot/` 是较早的控制器，配置项 `copilot.mode` 仍存在，但未成为 CLI 主路径。二次开发时以 `hitl/` 为准，除非明确要复用 `copilot` 的分支/反馈实现。

---

## 9. 研究协作仓库

`collaboration/` 用于多 Agent/多人共享研究产物：

| 类 | 位置 | 说明 |
|----|------|------|
| `ResearchRepository` | `collaboration/repository.py:21` | 研究仓库（产物集合） |
| `ArtifactPublisher` | `collaboration/publisher.py:15` | 发布产物 |
| `ArtifactSubscriber` | `collaboration/subscriber.py:13` | 订阅产物变更 |
| `content_hash()` / `deduplicate_artifacts()` | `collaboration/dedup.py:12/30` | 内容去重 |

---

## 10. 辅助服务

### 10.1 会议日历 `calendar/`

| 类 | 位置 | 说明 |
|----|------|------|
| `Conference` | `deadlines.py:19` | 会议元数据与 DDL |
| `ConferenceCalendar` | `deadlines.py:76` | 会议日历查询 |
| `SubmissionPlanner` | `planner.py:11` | 生成投稿时间线 |
| `Reminder` / `ReminderCalculator` | `reminder.py:13/23` | 提醒计算 |

CLI：`researchclaw calendar --upcoming`、`--plan <venue>`、`--domains`。

### 10.2 语音 `voice/`

| 模块 | 作用 |
|------|------|
| `voice/transcriber.py` | Whisper 转写（服务路由 `/api/voice/transcribe`） |
| `voice/synthesizer.py` | TTS |
| `voice/commands.py` | 语音指令解析 |

### 10.3 多项目 `project/`

| 类 | 位置 | 说明 |
|----|------|------|
| `Project` | `models.py:11` | 项目元数据 |
| `Idea` | `models.py:57` | 项目创意 |
| `ProjectManager` | `manager.py:18` | 项目 CRUD、状态、切换 |
| `IdeaPool` | `idea_pool.py:16` | 创意池 |
| `ProjectScheduler` | `scheduler.py:23` | 项目级任务队列与并发控制 |

CLI：`researchclaw project list/status/create/switch/compare`。

### 10.4 趋势 `trends/`

| 类 | 位置 | 说明 |
|----|------|------|
| `FeedManager` | `feeds.py:35` | 抓取 arXiv/S2 等源 |
| `TrendAnalyzer` | `trend_analyzer.py:30` | 趋势分析 |
| `AutoTopicGenerator` | `auto_topic.py:14` | 自动生成研究主题 |
| `DailyDigest` | `daily_digest.py:15` | 每日摘要 |
| `OpportunityFinder` | `opportunity_finder.py:11` | 机会识别 |

CLI：`researchclaw trends --digest / --analyze / --suggest-topics`。

---

## 11. CLI 侧 HITL 命令

| 命令 | 实现 | 作用 |
|------|------|------|
| `run --mode <mode>` | `cmd_run`（`cli.py:156`） | 选择 HITL 模式/预设 |
| `attach <run_dir>` | `cmd_attach`（`cli.py:2186`） | 附加到暂停中的流水线 |
| `status <run_dir>` | `cmd_status`（`cli.py:2234`） | 查看流水线与 HITL 状态 |
| `approve <run_dir> --message` | `cmd_hitl_approve`（`cli.py:2270`） | 批准当前门 |
| `reject <run_dir> --reason` | `cmd_hitl_reject`（`cli.py:2287`） | 拒绝当前门 |
| `guide <run_dir> --stage N --message` | `cmd_hitl_guide`（`cli.py:2304`） | 向指定阶段注入指导 |

---

## 12. 关键类/函数索引

| 名称 | 位置 | 作用 |
|------|------|------|
| `InterventionMode` | `hitl/config.py:10` | 6 种模式 |
| `StagePolicy` | `hitl/config.py:28` | 阶段策略 |
| `HITLConfig` | `hitl/config.py:87` | HITL 总配置 |
| `_default_policy_for_mode()` | `hitl/config.py:200` | 模式默认策略 |
| `get_preset()` | `hitl/presets.py:130` | 预设查找 |
| `HITLSession` | `hitl/session.py:37` | 会话 |
| `HITLSession.pause()` / `wait_for_human()` | `hitl/session.py:140/169` | 暂停/等待 |
| `HITLAdapter` | `hitl/adapters/__init__.py:10` | 交互适配协议 |
| `CLIAdapter` / `WebSocketHITLAdapter` / `MCPHITLAdapter` / `ScriptedHITLAdapter` | `hitl/adapters/*` | 四种通道 |
| `SmartPause` | `hitl/smart_pause.py:94` | 置信度驱动暂停 |
| `CostGuard` | `hitl/cost_guard.py:38` | 成本护栏 |
| `ClaimVerifier` | `hitl/claim_verifier.py:68` | 声明核验 |
| `BranchManager` | `hitl/branching.py:84` | 分支探索 |
| `IdeaWorkshop` / `BaselineNavigator` / `PaperCoWriter` | `hitl/workshops/*` | 三个工坊 |
| `_run_hitl_pre_stage()` / `_run_hitl_post_stage()` | `pipeline/executor.py:200/257` | 流水线接线 |
| `CoPilotController` | `copilot/controller.py:18` | CoPilot 控制器 |
| `ResearchRepository` / `ArtifactPublisher` / `ArtifactSubscriber` | `collaboration/*` | 协作仓库 |
