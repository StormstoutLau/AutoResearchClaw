# 10 · 模块参考与索引

本篇是查阅型参考：模块职责、关键类/函数索引、依赖矩阵、数据格式与术语表。

---

## 1. 顶层模块

| 模块 | 职责 | 关键入口 |
|------|------|----------|
| `researchclaw/__init__.py` | 版本号 | `__version__ = "0.5.0"` |
| `researchclaw/__main__.py` | `python -m researchclaw` | `main()` |
| `researchclaw/cli.py` | 22 个子命令、参数解析、dispatch | `main()` `cli.py:1511` |
| `researchclaw/run_state.py` | run 目录状态的唯一读取入口（兼容 v1/legacy checkpoint） | `RunState`、`read_run_state()`、`read_next_stage()` |
| `researchclaw/config.py` | 40+ 配置 dataclass、加载、校验、profile 叠加 | `RCConfig` `config.py:869`、`RCConfig.load` `:1050`、`validate_config` `:1104` |
| `researchclaw/adapters.py` | OpenClaw/MCP 能力协议与录制桩 | `AdapterBundle` `adapters.py:121` |
| `researchclaw/hardware.py` | GPU/MPS/CPU 检测、PyTorch 可用性、指标名过滤 | `detect_hardware` `hardware.py:44` |
| `researchclaw/health.py` | `doctor` 环境体检 | `DoctorReport` `health.py:34` |
| `researchclaw/quality.py` | 模板/占位内容（AI-slop）检测 | `assess_quality` `quality.py:146` |
| `researchclaw/report.py` | 从 run 目录生成 Markdown 报告 | `generate_report` `report.py:15` |
| `researchclaw/writing_guide.py` | 会议写作最佳实践知识库 | `format_writing_tips` `writing_guide.py:56` |
| `researchclaw/evolution.py` | 教训抽取、分类、时间衰减、存储 | `extract_lessons` `evolution.py:173`、`EvolutionStore` `:387` |
| `researchclaw/evolution_aevolve.py` | A-Evolve 观察/变异模型 | `Observation` `:39`、`Mutation` `:55` |

---

## 2. 子包总表

| 子包 | 职责 | 关键模块/类 | 主要依赖 |
|------|------|-------------|----------|
| `pipeline/` | 23 阶段状态机、执行、门控、回滚、防伪 | `Stage`、`StageContract`、`execute_pipeline`、`execute_stage`、`stage_impls/*`、`VerifiedRegistry`、`PaperVerifier` | `config`、`llm`、`experiment`、`domains`、`prompts`、`templates`、`agents`、`literature`、`hitl`、`memory`、`knowledge`、`evolution` |
| `experiment/` | 9 种实验后端、指标、校验、可视化 | `SandboxProtocol`、`create_sandbox`、`ExperimentRunner`、`validate_code`、`UniversalMetricParser` | `config`、`hardware`、`prompts` |
| `domains/` | 领域画像、检测、Prompt 适配、profile 部署 | `DomainProfile`、`detect_domain`、`PromptAdapter`、`apply_profile_defaults` | `config`、`templates` |
| `agents/` | 代码检索、基准选择、图表生成 | `BaseAgent`、`CodeSearchAgent`、`BenchmarkOrchestrator`、`FigureOrchestrator` | `utils`、`domains` |
| `llm/` | OpenAI 兼容、Anthropic、ACP | `LLMClient`、`AnthropicAdapter`、`ACPClient`、`create_llm_client` | `config`、`utils` |
| `literature/` | 多源检索、缓存、新颖性、引用验证 | `Paper`、`search_papers`、`verify_citations` | `trends` |
| `web/` | Web 搜索/抓取/Scholar/PDF + SSRF | `WebSearchClient`、`WebCrawler`、`check_url_ssrf` | `literature` |
| `knowledge/` | Markdown/Obsidian 知识库、知识图谱 | `KBEntry`、`write_stage_to_kb`、`KnowledgeGraphBuilder` | 无（stdlib） |
| `memory/` | 三类记忆、检索、衰减 | `MemoryStore`、`MemoryRetriever`、`time_decay_weight` | 无（stdlib） |
| `hitl/` | 6 模式、会话、适配器、工坊、分支 | `HITLConfig`、`HITLSession`、`SmartPause`、`CostGuard` | `cost_tracker`（可选） |
| `copilot/` | 早期 Co-Pilot 控制器 | `CoPilotController`、`ResearchMode` | `config`、`pipeline` |
| `collaboration/` | 研究仓库、发布/订阅、去重 | `ResearchRepository`、`ArtifactPublisher`、`ArtifactSubscriber` | 无（stdlib） |
| `metaclaw_bridge/` | 技能注入、PRM、失败转技能 | `MetaClawSession`、`ResearchPRMGate`、`STAGE_SKILL_MAP` | `evolution`、`llm` |
| `prompts/` | 提示库与渲染 | `PromptManager`、`RenderedPrompt` | 无 |
| `skills/` | SKILL.md 加载/注册/匹配 | `SkillRegistry`、`Skill`、`match_skills` | 无 |
| `templates/` | 会议模板、Markdown→LaTeX、编译 | `ConferenceTemplate`、`markdown_to_latex`、`compile_latex` | `prompts`、`pipeline` |
| `overleaf/` | Overleaf Git 同步 | `OverleafSync`、`ConflictResolver` | 无 |
| `server/` | FastAPI、路由、WS、对话 | `create_app`、`TokenAuthMiddleware`、`ConnectionManager` | `config`、`pipeline`、`dashboard`、`adapters`、`voice`、`run_state` |
| `dashboard/` | 指标采集与广播 | `RunSnapshot`、`DashboardCollector`、`start_dashboard_loop` | `server`、`run_state` |
| `assessor/` | 5 维评分、历史对比、venue 推荐 | `PaperScorer`、`Rubric`、`VenueRecommender` | 无 |
| `project/` | 多项目、Idea 池、调度 | `ProjectManager`、`ProjectScheduler` | 无 |
| `trends/` | 趋势抓取、日报、自动选题 | `FeedManager`、`TrendAnalyzer`、`AutoTopicGenerator` | `literature` |
| `calendar/` | 会议 DDL 与提醒 | `ConferenceCalendar`、`SubmissionPlanner` | 无 |
| `voice/` | Whisper 转写 / TTS | `VoiceTranscriber` | 可选（httpx） |
| `wizard/` | 交互式配置向导 | `QuickStartWizard` | `config` |
| `mcp/` | MCP 服务端/客户端/传输 | `ResearchClawMCPServer`、`TOOL_DEFINITIONS`、`MCPClient` | `literature`、`run_state`、`pipeline.review_service` |
| `servers/` | 多机任务调度（SSH/Slurm/云） | `TaskDispatcher`、`ServerRegistry` | 无 |
| `utils/` | thinking 标签清理、文件名清洗 | `strip_thinking_tags`、`sanitize` | 无 |
| `data/` | 数据集/基准/预训练论文/framework 文档 | YAML + Markdown | 无 |
| `docker/` | 实验镜像与各领域 Dockerfile | Dockerfile / entrypoint | 无 |
| `feedback/` | 仅一份反馈分析提示词，无可执行代码 | `FEEDBACK_ANALYSIS_PROMPT.md` | 无 |

---

## 3. 关键类/函数总索引

### 3.1 流水线

| 名称 | 位置 | 作用 |
|------|------|------|
| `Stage` | `pipeline/stages.py:22` | 23 阶段枚举 |
| `StageStatus` / `TransitionEvent` | `pipeline/stages.py:65/77` | 状态与事件 |
| `GATE_STAGES` / `GATE_ROLLBACK` / `DECISION_ROLLBACK` | `stages.py:109/118/129` | 门控与回滚 |
| `advance()` | `stages.py:252` | 状态迁移计算 |
| `gate_required()` | `stages.py:216` | 门控判定 |
| `StageContract` / `CONTRACTS` | `contracts.py:18/29` | 阶段 I/O 契约 |
| `execute_pipeline()` | `runner.py:431` | 全流水线执行 |
| `execute_iterative_pipeline()` | `runner.py:1629` | 写作质量迭代 |
| `read_checkpoint()` / `resume_from_checkpoint()` | `runner.py:126/146` | 断点恢复（返回下一阶段，供流水线内部使用） |
| `RunState` / `RunStatus` | `run_state.py:40/29` | 对外只读状态快照（阶段、状态、活跃、HITL、产物） |
| `read_run_state()` / `read_next_stage()` | `run_state.py:216/292` | 由 `checkpoint.json` + `heartbeat.json` + `pipeline_summary.json` 推导状态 |
| `_package_deliverables()` | `runner.py:915` | 交付物打包 |
| `execute_stage()` | `executor.py:594` | 单阶段执行 |
| `_STAGE_EXECUTORS` | `executor.py:567` | 阶段分发表 |
| `_run_hitl_pre_stage()` / `_run_hitl_post_stage()` | `executor.py:200/257` | HITL 钩子 |
| `StageResult` | `_helpers.py:34` | 阶段结果 |
| `VerifiedRegistry` | `verified_registry.py:64` | 真实数值登记 |
| `verify_paper()` | `paper_verifier.py:143` | 论文数字核验 |
| `run_debate()` | `debate.py:80` | 多模型辩论 |
| `run_tournament()` | `tournament.py:91` | Best-of-N |
| `CodeAgent` 五阶段 | `code_agent.py:1-20` | 蓝图/顺序生成/执行修复/树搜索/评审 |
| `OpenCodeBridge` | `opencode_bridge.py` | Beast Mode 外部编码 Agent |
| `diagnose_experiment()` / `assess_experiment_quality()` | `experiment_diagnosis.py` | 失败诊断 |
| `run_repair_loop()` | `experiment_repair.py:276` | 诊断—修复—重跑 |
| `judge_requirements()` | `requirements_judge.py:174` | Agent 模式需求审计 |
| `review_paper_text()` / `ReviewResult` | `pipeline/review_service.py` | Stage 18 与 MCP `review_paper` 共用的评审核心 |
| `collect_experiment_evidence()` | `pipeline/review_service.py` | 收集真实实验代码/指标/运行次数供评审 |
| `ResearchClawMCPServer` / `MCPClient` | `mcp/server.py` / `mcp/client.py` | 官方 SDK v2 `MCPServer` 与 `Client` 封装 |

### 3.2 实验与领域

| 名称 | 位置 | 作用 |
|------|------|------|
| `SandboxResult` / `SandboxProtocol` | `experiment/sandbox.py:282/291` | 统一执行接口 |
| `ExperimentSandbox` | `sandbox.py:307` | 本地 subprocess |
| `parse_metrics()` | `sandbox.py:89` | stdout 指标解析 |
| `validate_entry_point()` | `sandbox.py:21` | 入口点安全 |
| `DockerSandbox` | `docker_sandbox.py:93` | Docker 执行 |
| `SshRemoteSandbox` | `ssh_sandbox.py:31` | SSH 执行 |
| `ColabDriveSandbox` | `colab_sandbox.py:120` | Colab Drive |
| `ColliderAgentSandbox` / `BiologyAgentSandbox` / `StatAgentSandbox` | `collider_agent_sandbox.py:49`、`biology_agent_sandbox.py:58`、`stat_agent_sandbox.py:52` | 领域 Agent |
| `AgenticSandbox` | `agentic_sandbox.py:51` | Docker+Agent（未接线） |
| `create_sandbox()` / `create_agentic_sandbox()` | `factory.py:18/111` | 后端工厂 |
| `ExperimentRunner` | `runner.py:104` | 执行—评估—改进 |
| `ExperimentResults` / `UniversalMetricParser` | `metrics.py:38/103` | 统一结果 |
| `CodeValidation` / `validate_code()` | `validator.py:32` | AST 安全校验 |
| `HardwareProfile` / `detect_hardware()` | `hardware.py:30/44` | 硬件检测 |
| `DomainProfile` | `domains/detector.py:85` | 领域画像 |
| `detect_domain()` | `detector.py:490` | 三级检测 |
| `PromptAdapter` / `get_adapter()` | `domains/prompt_adapter.py:52/354` | 领域提示 |
| `apply_profile_defaults()` | `domains/deploy.py:281` | profile 配置叠加 |
| `UniversalExperimentPlan` | `domains/experiment_schema.py:63` | 通用实验计划 |
| `TaskDispatcher` | `servers/dispatcher.py:18` | 多机调度 |

### 3.3 LLM / Agent

| 名称 | 位置 | 作用 |
|------|------|------|
| `PROVIDER_PRESETS` | `llm/__init__.py:13` | Provider 表 |
| `create_llm_client()` / `build_reviewer_llm()` / `build_panel_llms()` | `llm/__init__.py:60/88/105` | 客户端工厂 |
| `LLMResponse` / `LLMConfig` / `LLMClient` | `llm/client.py:56/70/93` | LLM 客户端 |
| `LLMClient.chat()` / `preflight()` | `llm/client.py:239/305` | 对话与预检 |
| `AnthropicAdapter` | `llm/anthropic_adapter.py:31` | Anthropic API |
| `ACPClient` | `llm/acp_client.py:62` | ACP CLI Agent |
| `BaseAgent` / `AgentOrchestrator` | `agents/base.py:65/189` | Agent 基类/编排 |
| `CodeSearchAgent` | `agents/code_searcher/agent.py:94` | GitHub 代码检索 |
| `BenchmarkOrchestrator` | `agents/benchmark_agent/orchestrator.py:163` | 数据集/基线选择 |
| `FigureOrchestrator` | `agents/figure_agent/orchestrator.py:126` | 图表生成 |

### 3.4 文献与出版

| 名称 | 位置 | 作用 |
|------|------|------|
| `Paper` / `Author` | `literature/models.py:33/16` | 论文模型 |
| `search_papers()` / `search_papers_multi_query()` | `literature/search.py:104/246` | 检索 |
| `papers_to_bibtex()` | `literature/search.py:378` | BibTeX |
| `check_novelty()` | `literature/novelty.py:185` | 新颖性 |
| `verify_citations()` | `literature/verify.py:681` | 引用验证 |
| `filter_verified_bibtex()` / `annotate_paper_hallucinations()` | `literature/verify.py:885/922` | 引用清理 |
| `check_url_ssrf()` | `web/_ssrf.py:21` | SSRF 防护 |
| `build_results_tables()` | `templates/results_table_builder.py:34` | 结果表 |
| `ConferenceTemplate` / `get_template()` | `templates/conference.py:21/551` | 会议模板 |
| `markdown_to_latex()` | `templates/converter.py:52` | Markdown→LaTeX |
| `compile_latex()` | `templates/compiler.py:54` | 编译 |
| `OverleafSync` | `overleaf/sync.py:17` | Overleaf 同步 |
| `format_writing_tips()` | `writing_guide.py:56` | 写作提示 |

### 3.5 知识/记忆/演化

| 名称 | 位置 | 作用 |
|------|------|------|
| `KBEntry` / `write_kb_entry()` | `knowledge/base.py:33/86` | 知识条目 |
| `write_stage_to_kb()` | `knowledge/base.py:146` | 阶段入库 |
| `KnowledgeGraphBuilder` / `KnowledgeGraphQuery` | `knowledge/graph/builder.py:16`、`query.py:16` | 图谱 |
| `MemoryEntry` / `MemoryStore` | `memory/store.py:22/58` | 记忆存储 |
| `MemoryRetriever` | `memory/retriever.py:43` | 记忆检索 |
| `time_decay_weight()` | `memory/decay.py:9` | 时间衰减 |
| `extract_lessons()` / `EvolutionStore` | `evolution.py:173/387` | 教训 |
| `ResearchPRMGate` | `metaclaw_bridge/prm_gate.py:111` | PRM |
| `STAGE_SKILL_MAP` | `metaclaw_bridge/stage_skill_map.py:13` | 阶段技能 |
| `assess_quality()` | `quality.py:146` | AI-slop 检测 |
| `PaperScorer` / `VenueRecommender` | `assessor/scorer.py:15`、`venue_recommender.py:8` | 评分/投稿 |

### 3.6 HITL / 接口

| 名称 | 位置 | 作用 |
|------|------|------|
| `InterventionMode` / `StagePolicy` / `HITLConfig` | `hitl/config.py:10/28/87` | HITL 配置 |
| `get_preset()` | `hitl/presets.py:130` | 预设 |
| `HITLSession` | `hitl/session.py:37` | 会话 |
| `HITLAdapter` | `hitl/adapters/__init__.py:10` | 适配协议 |
| `SmartPause` | `hitl/smart_pause.py:94` | 智能暂停 |
| `CostGuard` | `hitl/cost_guard.py:38` | 成本护栏 |
| `ClaimVerifier` | `hitl/claim_verifier.py:68` | 声明核验 |
| `BranchManager` | `hitl/branching.py:84` | 分支 |
| `IdeaWorkshop` / `BaselineNavigator` / `PaperCoWriter` | `hitl/workshops/*` | 工坊 |
| `CoPilotController` | `copilot/controller.py:18` | CoPilot |
| `main()` / `cmd_run()` | `cli.py:1511/156` | CLI |
| `RCConfig.load()` / `validate_config()` | `config.py:1050/1104` | 配置 |
| `create_app()` | `server/app.py:25` | FastAPI |
| `ResearchClawMCPServer` | `mcp/server.py:29` | MCP |
| `SkillRegistry` | `skills/registry.py:18` | 技能 |
| `QuickStartWizard` | `wizard/quickstart.py:11` | 向导 |

---

## 4. 依赖矩阵

按 `researchclaw/**` 内部 import 次数聚合（仅列主要边）：

| 源 | 目标 | 次数 |
|----|------|------|
| pipeline | llm | 18 |
| pipeline | experiment | 17 |
| pipeline | domains | 14 |
| pipeline | prompts | 14 |
| cli | hitl | 13 |
| pipeline | config | 12 |
| experiment | config | 11 |
| pipeline | adapters | 11 |
| pipeline | hitl | 10 |
| pipeline | templates | 8 |
| pipeline | agents | 6 |
| pipeline | literature | 6 |
| pipeline | metaclaw_bridge | 5 |
| pipeline | data | 4 |
| pipeline | hardware | 3 |
| pipeline | memory / skills / evolution / knowledge / web | 1–2 |
| server | dashboard / pipeline / config / adapters / voice | 2–3 |
| trends | literature | 3 |
| literature | trends | 2 |
| agents | utils / domains | 1–5 |
| domains | config / templates | 1–2 |
| metaclaw_bridge | evolution / llm | 1 |
| llm | config / utils | 1–2 |

**判断**：

- 修改 `llm` / `config` / `adapters` / `prompts` 的公开接口会波及大量模块；
- `pipeline` 对 `knowledge/memory/skills/web/experiment_spec/pitfall_detector` 的引用多为 `try/except`，属于可选依赖；
- `experiment` 与 `pipeline` 存在少量双向引用，通过函数内延迟导入化解循环依赖。

---

## 5. 数据格式速查

| 文件 | 格式 | 写入方 | 主要字段 |
|------|------|--------|----------|
| `checkpoint.json` | JSON | `_write_checkpoint` | `last_completed_stage`、`last_completed_name`、`run_id`、`timestamp`、`hitl`（`read_run_state` 兼容可选 `schema`、`stage`） |
| `heartbeat.json` | JSON | `_write_heartbeat` | `pid`、`last_stage`、`last_stage_name`、`run_id`、`timestamp` |
| `pipeline_summary.json` | JSON | `_build_pipeline_summary` | 阶段计数、degraded、final_stage/status、content_metrics |
| `decision_history.json` | JSON list | `_record_decision_history` | decision、rollback_target、attempt、timestamp |
| `stage-XX/decision.json` | JSON | `_write_stage_meta` | stage_id、status、decision、artifacts、error、next_stage |
| `stage-XX/stage_health.json` | JSON | `execute_stage` | duration、status、artifacts_count、error、timestamp |
| `stage-XX/prm_score.json` | JSON | PRM 门 | stage、prm_score、model、votes |
| `experiment_diagnosis.json` | JSON | `_run_experiment_diagnosis` | deficiencies、repairable、quality_assessment |
| `experiment_summary.json` | JSON | Stage 14 | metrics_summary、condition_summaries、paired_comparisons、best_run |
| `results.json` | JSON | 沙箱/Stage 12 | source、metrics、conditions、structured |
| `verification_report.json` | JSON | Stage 23 | summary、results、integrity_score |
| `references_verified.bib` | BibTeX | Stage 23 | 清理后的条目 |
| `candidates.jsonl` / `shortlist.jsonl` | JSONL | Stage 4/5 | 论文元数据 |
| `refinement_log.json` | JSON | Stage 13 | iterations、best_version、mode |
| `experiment_memory/*.jsonl` | JSONL | ExperimentMemory | 条件、指标、失败模式 |
| `evolution/*.jsonl` | JSONL | EvolutionStore | LessonEntry |
| KB `docs/kb/<category>/*.md` | Markdown + YAML frontmatter | `write_kb_entry` | id/title/stage/run_id/tags/evidence |
| `deliverables/` | 混合 | `_package_deliverables` | 论文/参考文献/代码/图表/报告 |

---

## 6. 术语表

| 术语 | 含义 |
|------|------|
| **Stage / Phase** | Stage 是 23 个执行单元；Phase 是 8 个逻辑分组 |
| **Gate** | 需要人工审批的阶段（5/9/20；hep_ph 下 10） |
| **Contract / DoD** | 阶段输入输出契约与完成定义 |
| **PIVOT / REFINE** | Stage 15 的两种回滚决策 |
| **HITL** | Human-in-the-Loop，人在回路 |
| **Co-Pilot** | 深度协作模式；`hitl/` 为主实现，`copilot/` 为早期控制器 |
| **SmartPause** | 基于置信度的动态暂停 |
| **PRM** | Process Reward Model 式质量门，LLM-as-judge 多票打分 |
| **MetaClaw** | 跨运行技能进化/PRM 桥 |
| **ACP** | Agent Client Protocol，用外部 CLI Agent 充当 LLM |
| **Domain Profile** | 描述领域实验约定与部署默认值的 YAML |
| **Sandbox** | 实验执行后端（本地/Docker/SSH/Colab/Agent） |
| **VerifiedRegistry** | 论文中允许出现的实验数值登记表 |
| **AI-slop** | 模板化/占位内容，由 `quality.py` 检测 |
| **ARC-Bench** | 55 主题开放研究基准（`experiments/arc_bench/`） |
| **Beast Mode** | 用 OpenCode 处理复杂代码生成的模式 |
| **Tournament** | Best-of-N 候选生成 + 独立 judge 选优 |
| **Debate** | 多模型多角色 + 反驳 + 裁判 + 合成 |

---

## 7. 已知缺口汇总

> 逐项复现、社区案例与修复方案见 [11-gap-remediation-research.md](11-gap-remediation-research.md)；验收状态见 [12-remediation-acceptance-checklist.md](12-remediation-acceptance-checklist.md)。

| 问题 | 说明 | 相关文档 | 状态 |
|------|------|----------|------|
| 缺失可选模块 | `cost_tracker`、`pipeline.event_log`、`pipeline.experiment_spec`、`pipeline.pitfall_detector` 被引用但文件不存在，均 `try/except` 降级 | 09 §10.1 | PR-5 待处理 |
| 打包目标不存在 | `pyproject.toml` 声明 `sibyl`、`arc`，仓库无此目录 | 09 §10.2 | 已修复（PR-1：`packages = ["researchclaw"]`） |
| Web 依赖未声明 | FastAPI/uvicorn 不在依赖或 extras 中 | 09 §10.2 | 已修复（PR-1：新增 `server` / `mcp` / `voice` extras） |
| 前端路径不匹配 | 代码找 `frontend/`，实际是 `frontend-legacy/` | 09 §10.2 | 已修复（PR-2：`_resolve_frontend_dir()` + `RESEARCHCLAW_FRONTEND_DIR`） |
| 状态推导分散 | Dashboard/Projects 各自解析 checkpoint，legacy/v1 字段不一致，`current_stage` 常为 0 | 09 §10.2 | 已修复（PR-2：统一走 `run_state.read_run_state()`） |
| README Python API 不存在 | `from researchclaw.pipeline import Runner` 无效，应使用 `execute_pipeline` | 09 §10.2 | PR-6 待处理 |
| `agentic` 未接线 | 工厂/配置已声明，但主流程无调用 | 05 §9 | 已修复（PR-4：Stage 10/12 显式分派） |
| biology/stat Stage 12 分支缺失 | 走通用 `ExperimentRunner`，代码文本被当作 prompt | 05 §9 | 已修复（PR-4：`_execute_agent_experiment()`） |
| 默认 `simulated` | 不显式设 `experiment.mode` 会产出假数据 | README §7、05 §9 | 已修复（PR-4：默认 `sandbox` + warning + Stage 20 阻断） |
| MCP 部分 stub | `search_literature`、`review_paper` 未实现 | 09 §4 | 已修复（PR-3：官方 SDK `MCPServer` + 6 工具真实实现） |

---

## 8. 版本与维护建议

- 当前版本 `0.5.0`；阶段数、配置键、模板注册表是高频变更点，改动时同步更新本 Wiki 的 `02/03/09`。
- 行号会随重构漂移；定位时优先用「类名/函数名 + 文件」，行号仅作近似。
- 若新增 Stage，请同步：`stages.py`、`contracts.py`、`executor._STAGE_EXECUTORS`、`stage_impls/`、`PHASE_MAP`、KB 映射（`knowledge/base.py:120`）、报告/前端阶段列表。
