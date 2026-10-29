# 03 · 23 阶段逐条参考

本篇按阶段给出：目标、契约（输入/输出/DoD/错误码/重试）、实现位置、依赖模块、关键行为与回退。契约数据来自 `pipeline/contracts.py:29-207`，实现位置来自 `pipeline/stage_impls/`。

---

## 阶段总表

| # | Stage | 实现函数 | 文件:行 |
|---|-------|----------|---------|
| 1 | TOPIC_INIT | `_execute_topic_init` | `_topic.py:28` |
| 2 | PROBLEM_DECOMPOSE | `_execute_problem_decompose` | `_topic.py:126` |
| 3 | SEARCH_STRATEGY | `_execute_search_strategy` | `_literature.py:106` |
| 4 | LITERATURE_COLLECT | `_execute_literature_collect` | `_literature.py:382` |
| 5 | LITERATURE_SCREEN | `_execute_literature_screen` | `_literature.py:675` |
| 6 | KNOWLEDGE_EXTRACT | `_execute_knowledge_extract` | `_literature.py:861` |
| 7 | SYNTHESIS | `_execute_synthesis` | `_synthesis.py:31` |
| 8 | HYPOTHESIS_GEN | `_execute_hypothesis_gen` | `_synthesis.py:94` |
| 9 | EXPERIMENT_DESIGN | `_execute_experiment_design` | `_experiment_design.py:74` |
| 10 | CODE_GENERATION | `_execute_code_generation` / `_execute_collider_plan_generation` | `_code_generation.py:227/46` |
| 11 | RESOURCE_PLANNING | `_execute_resource_planning` | `_execution.py:44` |
| 12 | EXPERIMENT_RUN | `_execute_experiment_run` | `_execution.py:132` |
| 13 | ITERATIVE_REFINE | `_execute_iterative_refine` | `_execution.py:576` |
| 14 | RESULT_ANALYSIS | `_execute_result_analysis` | `_analysis.py:34` |
| 15 | RESEARCH_DECISION | `_execute_research_decision` | `_analysis.py:1139` |
| 16 | PAPER_OUTLINE | `_execute_paper_outline` | `_paper_writing.py:56` |
| 17 | PAPER_DRAFT | `_execute_paper_draft` | `_paper_writing.py:1330` |
| 18 | PEER_REVIEW | `_execute_peer_review` | `_review_publish.py:164` |
| 19 | PAPER_REVISION | `_execute_paper_revision` | `_review_publish.py:268` |
| 20 | QUALITY_GATE | `_execute_quality_gate` | `_review_publish.py:432` |
| 21 | KNOWLEDGE_ARCHIVE | `_execute_knowledge_archive` | `_review_publish.py:712` |
| 22 | EXPORT_PUBLISH | `_execute_export_publish` | `_review_publish.py:1493` |
| 23 | CITATION_VERIFY | `_execute_citation_verify` | `_review_publish.py:2723` |

---

## Phase A · Research Scoping

### Stage 1 · TOPIC_INIT

| 项 | 内容 |
|----|------|
| 目标 | 把用户主题固化为带范围、约束、成功标准的 SMART 研究目标，并检测硬件 |
| 输入 | 无 |
| 输出 | `goal.md`、`hardware_profile.json` |
| DoD / 错误码 | 含 topic/scope/constraints 的 SMART 目标 / `E01_INVALID_GOAL` / 重试 0 |
| 契约 | `contracts.py:31-38` |

实现要点（`_topic.py:28`）：

- 从 `PromptManager.for_stage("topic_init")` 渲染提示，可叠加历史演化教训（`_get_evolution_overlay`）；
- LLM 不可用时生成确定性的兜底目标文本；
- LLM 生成的 goal 前会插入「未验证草案」免责声明，避免下游把 SOTA 数字当事实；
- 调用 `hardware.detect_hardware()`，`ssh_remote` 模式下检测远端硬件；
- 若检测到 GPU 且处于 `sandbox` 模式，会尝试确保 PyTorch 可用（失败只 warning）。

### Stage 2 · PROBLEM_DECOMPOSE

| 项 | 内容 |
|----|------|
| 目标 | 把目标拆成 ≥3 个有优先级的研究子问题 |
| 输入 | `goal.md` |
| 输出 | `problem_tree.md`（以及 `topic_evaluation.json`） |
| DoD / 错误码 | ≥3 个优先子问题 / `E02_DECOMP_FAIL` / 重试 1 |
| 契约 | `contracts.py:39-45` |

实现要点（`_topic.py:126`）：LLM 生成子问题、优先级、风险；随后额外做一次「选题质量 1–10 评分」，低于 5 分时给出改写建议，但**不阻断**流程。

---

## Phase B · Literature Discovery

### Stage 3 · SEARCH_STRATEGY

| 项 | 内容 |
|----|------|
| 目标 | 定义检索策略、数据源与查询词 |
| 输入 | `problem_tree.md` |
| 输出 | `search_plan.yaml`、`sources.json`、`queries.json` |
| DoD / 错误码 | ≥2 条检索策略且数据源可用 / `E03_STRATEGY_BAD` / 重试 1 |
| 契约 | `contracts.py:47-53` |

实现要点（`_literature.py:106`）：

- LLM 以 JSON 返回 `search_plan_yaml` 与 `sources`；
- 解析失败时使用 `_build_fallback_queries()` 生成关键词查询与两条策略（keyword_core、backward_forward_citation）；
- `openclaw_bridge.use_web_fetch` 开启时，逐个请求数据源 URL 验证可达性并标记 `verified/unreachable`；
- 从计划中提取 `queries` 与 `year_min` 写入 `queries.json`，供 Stage 4 使用。

### Stage 4 · LITERATURE_COLLECT

| 项 | 内容 |
|----|------|
| 目标 | 用真实学术 API 收集候选论文 |
| 输入 | `search_plan.yaml` |
| 输出 | `candidates.jsonl`（可能附带 `web_context.md`、BibTeX） |
| DoD / 错误码 | ≥N 篇候选论文 / `E04_COLLECT_EMPTY` / 重试 2 |
| 契约 | `contracts.py:54-61` |

实现要点（`_literature.py:382`）：

- 优先 `literature.search.search_papers_multi_query()`，按 `config.literature_search.sources` 聚合 OpenAlex → Semantic Scholar → arXiv；
- 查询扩展（`_expand_search_queries`）+ 每源 limit + 查询间延迟；
- 注入 `researchclaw/data/seminal_papers.yaml` 中的奠基论文；
- `web.agent.WebSearchAgent` 可补充 web 检索上下文；
- API 全失败时回退到 LLM 生成候选（带明确的降级标记）；
- 输出 JSONL，每行含标题、作者、年份、摘要、引用数、DOI/arXiv ID、来源。

### Stage 5 · LITERATURE_SCREEN（GATE）

| 项 | 内容 |
|----|------|
| 目标 | 相关性 + 质量双筛，产出最终 shortlist |
| 输入 | `candidates.jsonl` |
| 输出 | `shortlist.jsonl` |
| DoD / 错误码 | 双筛完成并通过审批 / `E05_GATE_REJECT` / 重试 0 |
| 契约 | `contracts.py:62-69` |

实现要点（`_literature.py:675`）：

- 先做廉价关键词预过滤：标题+摘要与主题关键词至少 1 个重合；全被过滤时回退原候选（安全阀）；
- 按关键词重合度排序后再截断 token；
- LLM 逐篇给出相关性/质量判断；
- 若严格筛选把所有候选都拒绝，阶段返回 `PAUSED` + `decision="rejected_all"`，不写 `shortlist.jsonl`；
- 门控拒绝时回滚到 Stage 4。

### Stage 6 · KNOWLEDGE_EXTRACT

| 项 | 内容 |
|----|------|
| 目标 | 为每篇入选论文生成结构化知识卡片 |
| 输入 | `shortlist.jsonl` |
| 输出 | `cards/`（多份 Markdown） |
| DoD / 错误码 | 每篇 shortlist 论文一张卡 / `E06_EXTRACT_FAIL` / 重试 1 |
| 契约 | `contracts.py:70-76` |

实现要点（`_literature.py:861`）：

- 防御性门：`shortlist.jsonl` 为空时返回 `PAUSED` + `decision="upstream_blocked"`，并写 `knowledge_meta.json`，避免空输入生成垃圾卡片；
- 可拼接 Stage 4 的 `web_context.md`；
- LLM 输出卡片（问题、方法、数据、指标、结论、局限），写入 `cards/`。

---

## Phase C · Knowledge Synthesis

### Stage 7 · SYNTHESIS

| 项 | 内容 |
|----|------|
| 目标 | 聚类文献、识别 ≥2 个研究缺口 |
| 输入 | `cards/` |
| 输出 | `synthesis.md` |
| DoD / 错误码 | 主题聚类 + ≥2 缺口 / `E07_SYNTHESIS_WEAK` / 重试 1 |
| 契约 | `contracts.py:78-84` |

实现要点（`_synthesis.py:31`）：读取最多 24 张卡片拼接上下文，LLM 生成聚类、缺口、优先级机会；失败时写确定性兜底模板。

### Stage 8 · HYPOTHESIS_GEN

| 项 | 内容 |
|----|------|
| 目标 | 生成 ≥2 个可证伪假设 |
| 输入 | `synthesis.md` |
| 输出 | `hypotheses.md`（可能附带 `perspectives/`、`tournament/`） |
| DoD / 错误码 | ≥2 个可证伪假设 / `E08_HYP_INVALID` / 重试 1 |
| 契约 | `contracts.py:85-91` |

实现要点（`_synthesis.py:94`），按配置选择三条路径：

1. **Tournament（Best-of-N）**：`llm.tournament_enabled` 且候选数 ≥2 时，用不同角色/模型生成 N 组假设，独立 judge 排序选优（`pipeline/tournament.py:91`）；
2. **多模型 Debate**：`build_panel_llms()` 非空时，多模型扮演角色、可选反驳轮、独立 judge 排名，再由 synthesizer 汇总（`pipeline/debate.py:80`）；
3. **Legacy 多视角**：单模型多角色生成，再综合（`_helpers._multi_perspective_generate` / `_synthesize_perspectives`）。

任一路径失败都会回退到 `_default_hypotheses()`，不阻断流水线。

---

## Phase D · Experiment Design

### Stage 9 · EXPERIMENT_DESIGN（GATE）

| 项 | 内容 |
|----|------|
| 目标 | 设计 baseline / proposed / ablation / 指标 / 统计检验 |
| 输入 | `hypotheses.md` |
| 输出 | `exp_plan.yaml`（以及 `domain_profile.json`、可选 `benchmark_plan.json`） |
| DoD / 错误码 | 含基线、消融、指标的实验计划并通过审批 / `E09_GATE_REJECT` / 重试 0 |
| 契约 | `contracts.py:93-100` |

实现要点（`_experiment_design.py:74`）：

- 先做领域检测，落盘 `domain_profile.json`，供 Stage 10/14/22 复用；
- 通过 `PromptAdapter.get_experiment_design_blocks()` 注入领域术语、标准基线、统计检验；
- 按主题注入 dataset / RL / 框架文档等提示块；
- 计划解析有多级兜底（字段规范化、从假设抽取方法名、默认计划）；缺少 `baselines/proposed_methods/ablations` 时直接失败；
- 若启用 BenchmarkAgent，则运行 Survey → Select → Acquire → Validate，生成 `benchmark_plan.json`；
- Co-Pilot 模式下可进入 Baseline Navigator 工坊（`hitl/workshops/baseline.py`）。

### Stage 10 · CODE_GENERATION（`hep_ph` 时 GATE）

| 项 | 内容 |
|----|------|
| 目标 | 生成多文件可运行实验工程 + 实验规格 |
| 输入 | `exp_plan.yaml` |
| 输出 | `experiment/`、`experiment_spec.md`；`collider_agent` 模式为 `collider_plan.md` |
| DoD / 错误码 | 多文件工程 + spec / `E10_CODEGEN_FAIL` / 重试 2 |
| 契约 | `contracts.py:101-109` |

实现要点（`_code_generation.py:227`）：

- `collider_agent` 模式走 `_execute_collider_plan_generation()`，生成物理分析计划和说明，而不是 Python 工程；
- 生成前注入：硬件/包提示、时间预算、数据集指导、多随机种子强制、BenchmarkAgent 选择、LLM/RL/框架文档；
- 代码生成按优先级：**OpenCode Beast Mode → CodeAgent → 传统单次生成**；
  - Beast Mode：`pipeline/opencode_bridge.py`，按复杂度评分决定是否调用外部 `opencode` CLI；
  - CodeAgent：蓝图 → 顺序生成 → 执行反馈修复 → 可选树搜索 → 多智能体评审（`pipeline/code_agent.py:1-20`）；
  - CodeSearcher 可为 CodeAgent 提供 GitHub 参考实现（`agents/code_searcher`）；
- 生成后 AST 校验（`experiment/validator.validate_code`），带最多 5 轮修复；
- 产出 `experiment_spec.md` 记录条件、指标、数据。

### Stage 11 · RESOURCE_PLANNING

| 项 | 内容 |
|----|------|
| 目标 | 生成带依赖、GPU 数、时间估算的任务计划 |
| 输入 | `exp_plan.yaml` |
| 输出 | `schedule.json` |
| DoD / 错误码 | 资源计划含 GPU/时间估算 / `E11_SCHED_CONFLICT` / 重试 1 |
| 契约 | `contracts.py:110-116` |

实现要点（`_execution.py:44`）：LLM 返回 `tasks` 列表；若缺失则使用 baseline/proposed 两任务模板，并标记 `_meta.source = template|model`。

---

## Phase E · Experiment Execution

### Stage 12 · EXPERIMENT_RUN

| 项 | 内容 |
|----|------|
| 目标 | 按模式真实执行实验并采集指标 |
| 输入 | `schedule.json`、`experiment/` |
| 输出 | `runs/`（`run-*.json`、可选 `results.json`） |
| DoD / 错误码 | 所有计划运行完成且有产物 / `E12_RUN_FAIL` / 重试 2 |
| 契约 | `contracts.py:118-125` |

实现要点（`_execution.py:132`）按 `experiment.mode` 分支：

| 模式 | 行为 |
|------|------|
| `collider_agent` | 读 `collider_plan.md`，调用 `ColliderAgentSandbox`；支持 `incremental` 快照与结果合并 |
| `sandbox` / `docker` | `create_sandbox()`；多文件用 `run_project()`，单文件用 `run()`；自动依赖安装（sandbox） |
| `simulated` | 不执行代码，按 schedule 生成 `status="simulated"` 的占位结果 |
| 其他（`ssh_remote`、`colab_drive`、`biology_agent`、`stat_agent`） | 通过 `ExperimentRunner` + `create_sandbox()` 分发到对应后端 |
| `agentic` | `create_sandbox()` 不处理该模式，会抛 `RuntimeError`（当前未接线，见 [05](05-experiment-and-domains.md) §9） |

执行后：

- 优先读取沙箱产出的 `results.json`；否则从 stdout 解析指标并自动生成 `results.json`；
- 运行状态分为 `completed` / `partial`（超时但有指标）/ `failed`；
- 即使退出码为 0，若 stdout 含 `FAIL:`、`NaN/divergence`、`Traceback` 且无指标，也判失败；
- 记录 `time_budget_warning.json`（预算用尽）、种子数不足警告、<5 秒完成的可疑警告。

### Stage 13 · ITERATIVE_REFINE

| 项 | 内容 |
|----|------|
| 目标 | 编辑—运行—评估循环，保留最佳版本 |
| 输入 | `runs/` |
| 输出 | `refinement_log.json`、`experiment_final/` |
| DoD / 错误码 | 循环收敛或达到最大迭代 / `E13_REFINE_FAIL` / 重试 2 |
| 契约 | `contracts.py:126-133` |

实现要点（`_execution.py:576`）：

- agent 模式（`collider_agent` / `biology_agent` / `stat_agent`）**跳过**：把 Stage 12 结果复制到 `experiment_final/`，写 `refinement_log.json` 标记 `skipped`；
- `simulated` 模式同样跳过，把生成代码复制为最终代码；
- 其余模式进入真实精炼循环：读取 `runs/`、比较指标方向、执行改进、记录 iterations 与 `best_version`。

---

## Phase F · Analysis & Decision

### Stage 14 · RESULT_ANALYSIS

| 项 | 内容 |
|----|------|
| 目标 | 汇总指标、统计检验、生成分析结论与图表 |
| 输入 | `runs/` |
| 输出 | `analysis.md`（以及 `experiment_summary.json`、`charts/` 等） |
| DoD / 错误码 | 指标分析 + 统计检验 + 结论 / `E14_ANALYSIS_ERR` / 重试 1 |
| 契约 | `contracts.py:135-141` |

实现要点（`_analysis.py:34`）：

- `_collect_experiment_results()` 汇总 `runs/`；
- 合并 Stage 13 `refinement_log.json` 中更丰富的结果，并按指标方向判断哪份更优（避免“更全但更差”的数据覆盖最佳结果）；
- 生成 `experiment_summary.json`，包含 `metrics_summary`、`condition_summaries`、`paired_comparisons`、`best_run`；
- 可调用 FigureAgent 生成数据图（`agents/figure_agent`）；
- 统计检验与结论写入 `analysis.md`。

### Stage 15 · RESEARCH_DECISION

| 项 | 内容 |
|----|------|
| 目标 | 基于证据决定 PROCEED / REFINE / PIVOT / ABORT |
| 输入 | `analysis.md` |
| 输出 | `decision.md`（`StageResult.decision` 同步设置） |
| DoD / 错误码 | 带证据的 PROCEED/PIVOT 决策 / `E15_DECISION_FAIL` / 重试 1 |
| 契约 | `contracts.py:142-148` |

实现要点（`_analysis.py:1139`）：

- agent 模式先走「requirements 审计」：LLM judge 判断计划要求是否满足，决定 REFINE 或 PROCEED（`pipeline/requirements_judge.py:174`）；
- 检测退化 REFINE 循环：多轮指标完全相同或饱和时，注入「应 PROCEED」提示；
- 注入实验诊断结果（`experiment_diagnosis.json`）与消融有效性评估；
- LLM 输出决策；`refine` → 回滚 Stage 13（agent 模式回 Stage 12），`pivot` → 回滚 Stage 8，最多 2 次；
- 达到上限强制 PROCEED，并可能写 `quality_warning.txt`。

---

## Phase G · Paper Writing

### Stage 16 · PAPER_OUTLINE

| 项 | 内容 |
|----|------|
| 目标 | 生成章节级论文大纲 |
| 输入 | `analysis.md`、`decision.md` |
| 输出 | `outline.md` |
| DoD / 错误码 | 完整章节大纲 / `E16_OUTLINE_FAIL` / 重试 1 |
| 契约 | `contracts.py:150-156` |

实现要点（`_paper_writing.py:56`）：读取最佳分析（`_read_best_analysis`）、决策、实验数据 preamble；支持多轮迭代反馈（`iteration_context.json`）；LLM 空输出时会提高 `max_tokens` 重试。

### Stage 17 · PAPER_DRAFT

| 项 | 内容 |
|----|------|
| 目标 | 按大纲逐节写出完整论文 |
| 输入 | `outline.md` |
| 输出 | `paper_draft.md`（以及 `draft_quality.json`） |
| DoD / 错误码 | 全章节草稿 / `E17_DRAFT_FAIL` / 重试 1 |
| 契约 | `contracts.py:157-163` |

实现要点（`_paper_writing.py:1330`）：

- 优先使用 `experiment_summary_best.json`（跨 REFINE 轮次的最佳数据），否则选择“最富”的 `stage-14*` 摘要；
- 构建实验数据、验证注册表、结果表（`templates/results_table_builder.py`）的上下文；
- 逐节生成，控制篇幅（提示库要求约 5,000–6,500 词）；
- 生成 `draft_quality.json`，记录自动质量警告，供 Stage 18 评审参考。

### Stage 18 · PEER_REVIEW

| 项 | 内容 |
|----|------|
| 目标 | 多视角同行评审，并检查方法—证据一致性 |
| 输入 | `paper_draft.md` |
| 输出 | `reviews.md` |
| DoD / 错误码 | ≥2 个可执行评审视角 / `E18_REVIEW_FAIL` / 重试 1 |
| 契约 | `contracts.py:164-170` |

实现要点（`_review_publish.py:164`）：

- 优先使用独立 reviewer 模型（`build_reviewer_llm` / `_build_reviewer_or_generator`），避免「作者即评审」的自偏好；
- 评审提示由当前提示库提供（ML：NeurIPS/ICML 审稿人；HEP：理论/现象学/实验审稿人）；
- 注入 `draft_quality.json` 的自动质量问题；
- 收集实验证据（`_collect_experiment_evidence`）供评审交叉核对。

### Stage 19 · PAPER_REVISION

| 项 | 内容 |
|----|------|
| 目标 | 逐条回应评审意见并修订论文 |
| 输入 | `paper_draft.md`、`reviews.md` |
| 输出 | `paper_revised.md` |
| DoD / 错误码 | 所有评审意见被处理 / `E19_REVISION_FAIL` / 重试 1 |
| 契约 | `contracts.py:171-177` |

实现要点（`_review_publish.py:268`）：合并评审意见与原稿，要求逐条回应；带长度守卫，避免修订后大幅缩短或膨胀；保留修改说明。

---

## Phase H · Finalization

### Stage 20 · QUALITY_GATE（GATE）

| 项 | 内容 |
|----|------|
| 目标 | 综合质量评分 + 反伪造硬门 |
| 输入 | `paper_revised.md` |
| 输出 | `quality_report.json` |
| DoD / 错误码 | 质量分达标且通过审批 / `E20_GATE_REJECT` / 重试 0 |
| 契约 | `contracts.py:179-186` |

实现要点（`_review_publish.py:432`）：

- **硬门 1**：若 `VerifiedRegistry` 中没有任何真实实验数值，直接 BLOCKED（防止在无实验数据时导出论文）；
- 用独立 judge 模型评估全文（最多 40,000 字符），并与实验摘要交叉核对（实验失败/空指标时，论文中的数值视为伪造）；
- 评分维度与阈值来自提示库与配置；
- 拒绝后回滚 Stage 16（重写论文）。

### Stage 21 · KNOWLEDGE_ARCHIVE

| 项 | 内容 |
|----|------|
| 目标 | 归档复盘与可复现性包 |
| 输入 | 无（扫描 run 目录） |
| 输出 | `archive.md`、`bundle_index.json` |
| DoD / 错误码 | 复盘 + 可复现包索引 / `E21_ARCHIVE_FAIL` / 重试 1 |
| 契约 | `contracts.py:187-193` |

实现要点（`_review_publish.py:712`）：LLM 生成复盘；扫描阶段产物并写入 `bundle_index.json`（文件/哈希/大小等），用于复现与审计。该阶段是唯一非关键阶段。

### Stage 22 · EXPORT_PUBLISH

| 项 | 内容 |
|----|------|
| 目标 | 组装最终论文、参考文献、图表、LaTeX 并编译 |
| 输入 | `paper_revised.md` |
| 输出 | `paper_final.md`、`code/`，以及 `paper.tex`、`references.bib`、`charts/`、`sanitization_report.json` |
| DoD / 错误码 | 目标格式导出成功 / `E22_EXPORT_FAIL` / 重试 1 |
| 契约 | `contracts.py:194-200` |

实现要点（`_review_publish.py:1493`）：

1. **图表注入**：从 `stage-14*/charts` 与 `stage-22/charts` 收集图片，按章节分布插入 `![Figure ...]` 引用；
2. **伪造数据清洗**：`_sanitize_fabricated_data()` 扫描 Markdown/LaTeX 表格中的数值，未在 `VerifiedRegistry` 中登记的替换为 `---`，并写 `sanitization_report.json`；
3. **引用补齐**：扫描 `\cite{}` 中缺失于 `references.bib` 的 key，尝试检索并补全；
4. **LaTeX 转换**：`templates.markdown_to_latex()` + `get_template(target_conference)`；
5. **编译与质量检查**：`templates.compile_latex()`，复制图表、修复路径、移除缺失图片，检查摘要/章节结构；
6. 领域适配器可覆盖默认会议模板（如 HEP 用 `jhep`/`prd`）。

### Stage 23 · CITATION_VERIFY

| 项 | 内容 |
|----|------|
| 目标 | 验证每条引用真实存在，剔除/标注幻觉引用 |
| 输入 | `paper_final.md`（`references.bib` 可选） |
| 输出 | `verification_report.json`、`references_verified.bib`、`paper_final_verified.md` |
| DoD / 错误码 | 所有引用经真实 API 验证 / `E23_VERIFY_FAIL` / 重试 1 |
| 契约 | `contracts.py:201-207` |

实现要点（`_review_publish.py:2723`）：

- 无 BibTeX 时生成空报告，直接复制论文为 verified 版本；
- 有 BibTeX 时调用 `literature.verify.verify_citations()`（`literature/verify.py:681`）：
  - L1：arXiv ID 查询 + 标题相似度；
  - L2：DOI / CrossRef（以及 DataCite/OpenAlex）；
  - L3：标题搜索（Semantic Scholar/OpenAlex）；
  - L4：LLM 相关性判断（区分“真实但无关”的引用）；
- 用 `filter_verified_bibtex()` 移除 `HALLUCINATED` 条目，用 `annotate_paper_hallucinations()` 在正文标注可疑引用；
- 该阶段为关键阶段，幻觉引用必须阻断或清理后才能导出。

---

## 附：阶段间数据依赖速查

```
goal.md ──► problem_tree.md ──► search_plan.yaml ──► candidates.jsonl
   ──► shortlist.jsonl ──► cards/ ──► synthesis.md ──► hypotheses.md
   ──► exp_plan.yaml ──► experiment/ + experiment_spec.md ──► schedule.json
   ──► runs/ ──► refinement_log.json + experiment_final/ ──► analysis.md
   ──► decision.md ──► outline.md ──► paper_draft.md ──► reviews.md
   ──► paper_revised.md ──► quality_report.json ──► archive.md
   ──► paper_final.md + paper.tex + references.bib + charts/
   ──► verification_report.json + references_verified.bib
```
