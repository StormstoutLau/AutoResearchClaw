---
id: arc-g7-orchestration-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-master-roadmap, orchestration-benchmark-plan, orchestration-capability-matrix, arc-g7-soak-RESEARCH]
upstream: arc-master-roadmap
---

# 调研：G7 第二段「编排评测」（P-162）

> **Feature**：P-162。G7 第二段，只做 **OB-1..OB-5 的 dry-run 评测工具链**：15 任务 × 适配器、plan/delegations/aggregate/trace/usage 五件套、确定性 judge + LLM 语义残差、预算/并行/散文消融三项负向验收。
> **本段不做**：真实科学实验重跑、外部框架（AIS v2 / AgentLab / AIDE）的编排能力排名、写作质量评分、G7 并发/双平面/漂移护栏；这些留给后续段或 field run。
> **与 P-160/P-161 的关系**：P-160 交付 soak 工具链；P-161 异构复审登记的 D-1..D-3（retention 逃生舱、POSIX 进程树、死代码）**不在本批**，由独立修复批承接；本批不重复报告、不以编排评测掩盖其未修状态。

---

## 1. 调研目标

1. 现有 `docs/orchestration-benchmark-plan.md` 的 15 任务 / 4 维度 / OB-1..OB-5，在**当前仓库实际**上哪些能直接复用，哪些只是纸面前提？
2. 学术与社区上，编排评测的**可证伪最小件**是什么：任务分解、委派、聚合、控制、成本、并行、judge 可靠性分别应如何机械化？
3. 第一段可交付的**边界**：dry-run 工具链能否在不引入真实框架依赖、不改现有 ARC-Bench 语义的前提下，产出可复现读数？

## 2. 调研方法

### 2.1 通道与降级链

| 通道 | 用途 | 实际结果 |
|---|---|---|
| `Read` / `Grep` / `Glob` | 本仓 `docs/orchestration-benchmark-plan.md`、`experiments/arc_bench/`、runner/judge/adapters | 已逐文件读取，行号见 §3 |
| `WebSearch` / `WebFetch` | 论文、官方文档、社区案例 | 命中多数；`raw.githubusercontent.com` 的 SwarmBench/OTel 部分文件抓取为空，改用 GitHub API / 官方页面 |
| `mcp_paper-search_search_arxiv` | arXiv 元数据核验 | SwarmBench 命中；MAST 查询未命中原文（返回无关综述），改用 arXiv abs 页 |
| GitHub Issues API | 社区反例（T3） | 命中 Inspect AI 的测试隔离 flake；其余检索为 0 条，已记录降级 |
| 本仓命令探针 | `run_baseline.py` 真实可运行性 | 实测 `FileNotFoundError: config/topics.yaml`（见 F-1） |

### 2.2 范围

- **时间**：2023（AutoGen/MT-Bench）至 2026-11（SwarmBench EMNLP 2026、仓库当前 main）。
- **领域**：多智能体编排评测、agent benchmark 方法学、LLM-as-judge、trace/可观测性。
- **排除**：真实 LLM 调用成本、外部框架安装、科学正确性 rubric（ARC-Bench 主榜）、G7 其他段。

## 3. 本仓事实（T1：源码/实测）

### 3.1 方案文档的纸面约定

| 事实 | 证据 |
|---|---|
| 15 任务分 D/L/A/C 四类；D4/L4/A4/C3 | `docs/orchestration-benchmark-plan.md` §2 |
| Rubric 四维各 0–3，合计 /12；聚合正确性=0 则总分 0 | 同上 `#L59-L71` |
| Adapter 接口 `start/collect/artifacts`，产出 plan/delegations/aggregate/trace/usage | 同上 `#L75-L97` |
| OB-1..OB-5 验收 | 同上 `#L117-L126` |
| “复用现有 runner/judge，不改现有脚本” | 同上 `#L15`、`#L93-L97` |

### 3.2 现有 ARC-Bench 资产

| 资产 | 事实 | 对本段的意义 |
|---|---|---|
| 55 个 topic（ML25/P10/Q10/B7/S3） | [README](../../experiments/arc_bench/README.md#L7-L12)；topic 注册表按域拆分 | 15 个任务可从既有 manifest 派生，不新增科学内容 |
| 5 个 baseline adapter | `AIScientistV2Adapter` / `AgentLabAdapter` / `AideAdapter` / `ResearchClawAdapter`（full/copilot） | 但它们只产出论文/指标，不产出编排五件套 |
| `FrameworkAdapter` / `StandardArtifacts` | [base.py](../../experiments/arc_bench/baseline/adapters/base.py#L31-L82) | 可作为桥接基类；`StandardArtifacts` 没有编排字段 |
| `run_baseline.py` | [入口](../../experiments/arc_bench/scripts/run_baseline.py#L201-L266)：adapter.run → build submission → `judge.py` | OB-2 声称复用它；实际有 F-1/F-2/F-3 三个阻断 |
| `judge.py` | LLM 第二轮把 **Writeup / README** 与 experiment summary 一起送审（[L576-L591](../../experiments/arc_bench/scripts/judge.py#L576-L591)）；`grade()` 读科学 rubric（[L1046-L1059](../../experiments/arc_bench/scripts/judge.py#L1046-L1059)） | 与 OB-5「删除散文分数不变」直接冲突 |
| `run_bench.py` | 已有正确的**多域 topic 聚合**（[L56-L84](../../experiments/arc_bench/scripts/run_bench.py#L56-L84)） | 可作为 F-1 的修复参照 |
| `evaluate.py` | 仍按 `ROOT/manifests` + `T*` 发现 topic（[L48-L49](../../experiments/arc_bench/scripts/evaluate.py#L48-L49)） | 与现域拆分布局不一致；不能直接复用 |
| `AgentStepResult` | 有 `llm_calls` / `token_usage`（[base.py](../../researchclaw/agents/base.py#L50-L57)） | 可用于 usage 反算的一个来源，但外部框架未必填 |

### 3.3 当前缺口（实测/读码）

| 编号 | 缺口 | 证据 | 影响 |
|---|---|---|---|
| **F-1** | `run_baseline._load_topics()` 读 `config/topics.yaml`，该文件已随域拆分移除 | 实测 `--dry-run` → `FileNotFoundError: experiments/arc_bench/config/topics.yaml`；`run_bench.py` 已改用五域聚合 | **OB-2 当前第一步即失败**；任何“复用 run_baseline”的验收都不成立 |
| **F-2** | `ADAPTERS` 是 3 项静态字典；无 dummy/orchestration 注册或插件入口 | [run_baseline.py L55-L59](../../experiments/arc_bench/scripts/run_baseline.py#L55-L59) | OB-2 的 dummy adapter 必须改现有 runner，或另写入口；与 plan §4“不改现有脚本”冲突 |
| **F-3** | `run_baseline.py` 硬编码调用 `scripts/judge.py`，无 `--judge` 分派 | [L253-L260](../../experiments/arc_bench/scripts/run_baseline.py#L253-L260) | 编排 rubric 无法经同一入口评分；若复用 `judge.py`，OB-5 必红 |
| **F-4** | 无 `Budget` 类、无 `budget_exceeded` 状态、无 plan/delegations/aggregate/trace/usage 五件套 | 全仓 grep 无实现；plan 仅接口草案 | OB-3/OB-4 无可执行载体 |
| **F-5** | `evaluate.py` topic 发现与现布局不一致 | 读码 `_topics_with_manifest` | 新评测不能直接复用聚合器；需新聚合器或修旧脚本 |
| **F-6** | 无编排 rubric；现有 `config/*/rubrics` 是科学 rubric（code/exec/results），不含分解/委派/聚合/控制 | 读 ML01 rubric | 需要独立 `orchestration` rubric 与 judge |
| **F-7** | 无 trace 契约/并发校验；`trace.jsonl` 仅 plan 提及 | 全仓 grep 无 `trace.jsonl` 生产者 | OB-3 无可验证对象 |
| **F-8** | 无“散文剥离”变体与判分隔离 | plan 只写 OB-5，未给实现 | OB-5 需要独立的 submission 变体与 judge 输入白名单 |

### 3.4 现有科学 manifest 是否足以派生 15 任务

| 任务类 | 可派生的现有 manifest | 可机械化的产物 | 风险 |
|---|---|---|---|
| D 分解 | ML01（5 条件 × 3 数据集 × 5 seed = 75 格）、ML05（PCA/t-SNE/UMAP × 数据集）、P01（11 能量点 × 条件）、Q03（shot 预算 × bond length） | 固定 schema 的 `metrics.json` + `rank.json`；可复算均值/方差 | 真跑成本高；dry-run 只能模拟 |
| L 委派 | P01（producer/verifier/literature 三角色）、ML02（bagging/boosting/stacking × 噪声）、S01（bootstrap 覆盖）、B01（FBA knockout） | `audit.json` / `delegations.json`（角色-工具-上下文） | P/B 依赖外部 agent；B01 需 iAF1260 数据 |
| A 聚合 | ML06（学习率 schedule 对比）、Q01（编码策略 × 数据集）、P03（排除 contour）、S02/S03 | `consensus.json` / `aggregate.json`（冲突、去重、裁决） | 需要隐藏真值；否则聚合正确性不可判 |
| C 控制 | ML04（特征缩放 × 分布）、Q02（CNOT 消融）、P02（Majorana 产生） | 过度拆分应降分；单 agent 可完成 | 必须构造“看似可拆、实际仅 2 个独立目标”的题面 |

> **结论**：15 个任务可以“从 manifest 派生题面与产物 schema”，但**不能**把真实科学运行当作 dry-run；第一段应使用**确定性 worker 模拟器**，把科学 manifest 只作为任务素材与隐藏真值来源。真实框架分数属于 field run，不在本段。

## 4. 外部证据

### 4.1 学术（T1，已核元数据）

| # | 来源 | 关键结论 | 本段借用 | 不借用 |
|---|---|---|---|---|
| E1 | **SwarmBench**，arXiv [2608.30661](https://arxiv.org/abs/2608.30661)，EMNLP 2026 Findings；代码 [ying1973/SwarmBench](https://github.com/ying1973/SwarmBench) | 评“任务分解 / 子智能体创建与委派 / 子任务结果聚合”三类能力；8 task types、400 samples；指标含 accuracy/efficiency/cost/process quality；主 agent 禁止调工具，子 agent 从带描述的模型池中选择；定义系统并行度 `ρ_t=|H_t|`，存在 `ρ_t>1` 的阶段才算 swarm 行为 | 三维度命名、`ρ_t` 并行定义、过程质量与成本并列、主/子 agent 分离 | 不抄 8 个任务；不使用其真实环境（Batch Download/OpenRCA 等） |
| E2 | **Why Do Multi-Agent LLM Systems Fail? (MAST)**，arXiv [2503.13657](https://arxiv.org/abs/2503.13657) | 1600+ 标注 trace，14 种失败模式，聚为 3 类：系统设计 / inter-agent misalignment / task verification；专家标注 Cohen's κ=0.88；LLM annotator 与人工高一致 | 用 3 类失败模式设计 D/L/A/C 的负向 fixture；把“验证/终止”作为聚合维的一部分 | 不把 MAST 当唯一评分标准；其任务域与 ARC 不同 |
| E3 | **MultiAgentBench / MARBLE**，arXiv [2503.01935](https://arxiv.org/abs/2503.01935) | 以 milestone-based KPI 同时测任务完成与协作/竞争质量；比较 star/chain/tree/graph 协调协议 | “里程碑 + 过程质量”双轨；把协调协议作为适配器元数据 | 不引入 MARBLE 运行时；不评竞争 |
| E4 | **AI Agents That Matter**，arXiv [2407.01502](https://arxiv.org/abs/2407.01502) | 现有 agent benchmark 过度关注 accuracy，忽略成本；缺少 holdout 与标准化评估导致不可复现；应联合优化 accuracy 与 cost | 成本效率维度、holdout 任务、预算前置、复现声明 | 不采用其具体 Pareto 优化器 |
| E5 | **BetterBench**，arXiv [2411.12990](https://arxiv.org/abs/2411.12990)，NeurIPS 2024 Spotlight | 46 条 benchmark 生命周期最佳实践；评估 24 个 benchmark，发现多数不报统计显著性、不易复现 | 任务版本化、配对比较、置信区间、复现清单、专家审查 | 不照搬 46 条全部；只取与本段相关的可机械项 |
| E6 | **Agentless**，arXiv [2407.01489](https://arxiv.org/abs/2407.01489) | 简单三段式 Agentless 在 SWE-bench Lite 达 32.00%（96 fixes）、成本 $0.70，胜过复杂开源 agent | OB-1 的“单发基线 ≤7/12”负向控制；提醒 gold 与单发差距过小则构念效度不足 | 不作为 ARC 任务基线；其任务域是代码修复 |
| E7 | **Judging LLM-as-a-Judge（MT-Bench）**，arXiv [2306.05685](https://arxiv.org/abs/2306.05685)，NeurIPS 2023 D&B | 强 LLM judge 与人类偏好 >80% 一致；存在 position / verbosity / self-enhancement 偏差与有限推理 | 确定性检查优先；LLM 只裁语义残差；随机化顺序、长度控制、人工校准子集 | 不以单一 judge 分数作为唯一真值 |
| E8 | **G-Eval**，arXiv [2303.16634](https://arxiv.org/abs/2303.16634) | CoT + 表单式 rubric 评分；GPT-4 在摘要任务与人类 Spearman 0.514；存在偏好 LLM 生成文本的偏差 | 把“分解/委派/聚合”拆成细粒度 rubric，先写评分步骤再打分 | 不把 0.514 当足够精度；仍需人工复核 |
| E9 | **Prometheus**，arXiv [2310.08491](https://arxiv.org/abs/2310.08491)，ICLR 2024 | 开源 13B evaluator 在 45 个自定义 rubric 上与人类 Pearson 0.897（GPT-4 0.882） | 若需本地 judge，可用“rubric + reference”形态；不绑定厂商模型 | 不引入 13B 依赖；本段默认仍用现有 LLM client |
| E10 | **Agent-as-a-Judge**，arXiv [2410.10934](https://arxiv.org/abs/2410.10934) | 用 agentic system 评 agentic system，能对中间过程给反馈；DevAI 55 任务 / 365 条层级需求，可靠性接近人工 | 过程级评分（trace/plan）而非只看终态；LLM judge 可读过程证据 | 不构建完整 DevAI；不采其 55 任务 |

### 4.2 工业官方文档（T1/T2）

| # | 来源 | 机制 | 本段借用 |
|---|---|---|---|
| E11 | [Anthropic：How we built our multi-agent research system](https://www.anthropic.com/research/multi-agent-research-system)（2025-06-13，T2 官方工程博客） | orchestrator-worker；lead 并行起 3–5 个子 agent，子 agent 并行用 3+ 工具；复杂查询研究时间最多降 90%；多 agent 比单 agent 在内部研究评测高 90.2%；多 agent 比 chat 多约 15× token；token 使用解释 BrowseComp 80% 方差；多 agent 适合 breadth-first，不适合强依赖/共享上下文任务；评估要“结果 + 合理过程”，小样本即可开始 | 任务分类以 breadth-first 为主；成本必须与准确率并列；评估同时看 outcome 与 process；D/L/A 任务应可并行 |
| E12 | [OpenTelemetry Traces](https://opentelemetry.io/docs/concepts/signals/traces/)（T1 官方文档） | trace = trace_id + span_id + parent_id + start/end + attributes + events；span 可嵌套 | `trace.jsonl` 的最小字段；并行区间 = 同 trace 下子 span 的时间重叠 |
| E13 | [Inspect AI](https://inspect.aisi.org.uk/)（UK AISI/Meridian，T1 官方文档） | 可组合 dataset/agent/tool/scorer；sandbox；多 agent primitives；可运行外部 agent（Claude Code/Codex/Gemini CLI）；Inspect View | 评测骨架：dataset + solver/adapter + scorer 分层；sandbox 隔离；结果可视化 |
| E14 | [OpenAI Cookbook：Orchestrating Agents — Routines and Handoffs](https://developers.openai.com/cookbook/examples/orchestrating_agents)（T2 官方 cookbook，已归档提示） | routines + handoffs；Swarm 是示例实现 | plan/delegations 的“交接”语义；只作模式参照，不作生产依赖 |
| E15 | [LangGraph Supervisor](https://reference.langchain.com/python/langgraph-supervisor) / [Handoffs](https://docs.langchain.com/oss/javascript/langchain/multi-agent/handoffs)（T2 官方文档） | supervisor 通过 handoff tool 转移控制；多 agent 子图；上下文需显式传递 | supervisor 式委派与“角色不重叠”评分；不当运行时依赖 |
| E16 | [CrewAI Crews](https://docs.crewai.com/en/concepts/crews)（T2 官方文档） | crew 有 sequential / hierarchical process；hierarchical 需要 manager LLM；可配置 delegation | 适配器元数据要声明 process 类型；顺序执行不得自报并行 |
| E17 | [AutoGen 论文](https://arxiv.org/abs/2308.08155)（T1 论文） | conversable agents；可组合 LLM/工具/人；对话式编排 | 作为“编排范式”背景；不引入 AutoGen 依赖 |

### 4.3 社区案例（T3，只用于陷阱）

| # | 来源 | 现象 | 对本段的约束 |
|---|---|---|---|
| C-1 | [OpenAI Swarm 现状](https://aidreamhub.com/en/tools/openai-swarm)（T3 转述称官方 README 已标 experimental/educational，并指向 Agents SDK） | Swarm 是教学/实验代码，不是生产推荐；已由 Agents SDK 取代 | 不把 Swarm 作为 baseline；只借 handoff 模式 |
| C-2 | [CrewAI Collaboration 文档](https://docs.crewai.com/en/concepts/collaboration)（T2 官方文档，但列的是故障模式） | 未开 `allow_delegation` 时 agent 不协作；开太多会 delegation loop | 委派分必须惩罚循环/空转；trace 要记录 handoff 次数与回边 |
| C-3 | [AutoGen Group Chat 文档](http://microsoft.github.io/autogen/0.4.7/user-guide/core-user-guide/design-patterns/group-chat.html)（T2 官方文档） | group chat 默认**顺序**，同一时刻只有一个 agent 工作 | 不能把“多 agent”自动当并行；OB-3 必须按 trace 判 |
| C-4 | [LangGraph 论坛：Command(goto) 导致 supervisor 与子节点并行](https://forum.langchain.com/t/tool-function-return-command-with-goto-variable-cause-parallel-running/2177)（T3） | 路由语义错误会让不应并行的节点并行 | 并行是“语义正确 + 时间重叠”双条件；不是只看 overlap |
| C-5 | [Inspect AI PR #4972](https://github.com/UKGovernmentBEIS/inspect_ai/pull/4972)（T3，2026-08） | 模块级全局 registry 被其它测试清空，xdist 下随机 flake；改为 per-test 隔离 fixture | 评测 harness 本身必须 per-task 隔离，禁止进程级全局状态；CI 要固定 seed/顺序 |

### 4.4 未验证/降级

| 来源 | 状态 | 处置 |
|---|---|---|
| `raw.githubusercontent.com` 的 SwarmBench `common_metrics.py` / `tracer.py` / OTel GenAI 页面 | 部分抓取为空 | 已用 GitHub API tree + 官方 OTel Traces 页替代；SwarmBench 具体代码仅作形态参照 |
| `mcp_paper-search_search_arxiv("Why Do Multi-Agent LLM Systems Fail")` | 未命中原文（返回无关综述） | 以 arXiv abs 页（2503.13657）为准，标 T1 |
| GitHub Issues 搜索 | 多条查询 0 条 | 保留 Inspect #4972 一条；其余社区证据用官方文档的“故障模式”章节，不冒充 issue |

## 5. 综合分析

### 5.1 关键发现

1. **计划的三维度有 T1 支撑，但 15 任务/3 框架是本地构念，不是 SwarmBench 的复制**：SwarmBench 是 8 task types / 400 samples；本仓 15 任务必须自己冻结题面与隐藏真值，不能声称与 SwarmBench 分数可比。[置信度 ★★★★★]
2. **OB-1 的“单发 ≤7/12”是构念效度闸门，不是装饰**：Agentless 表明简单基线可能胜过复杂 agent；若 gold 与单发差距不足，说明任务没有真正测到编排。必须把单发作为**负向控制**，并报告配对差值/区间，而非只报 gold 分数。[★★★★★]
3. **OB-5 要求新 judge，现有 `judge.py` 不可复用**：其第二轮 prompt 明确把 Writeup/README 送审（`judge.py:576-591`），删除散文必然改分。新 judge 必须只读 plan/delegations/aggregate/trace/usage，散文剥离是**输入白名单**问题，不是 prompt 提醒问题。[★★★★★，E3]
4. **OB-2 在当前仓库第一步就断**：`run_baseline.py` 读已不存在的 `config/topics.yaml`（实测 FileNotFoundError），且 adapter/judge 都是静态硬编码。要么做一次**通用入口扩展**（adapter module + judge 分派 + 多域 topic 加载），要么新增 orchestration 专用入口；plan 的“不改现有脚本”需要澄清为“不改评分语义/不改现有 adapter 契约”。[★★★★★，E1/E2]
5. **OB-3 只能按 trace 判，不能按自报判**：SwarmBench 用 `ρ_t=|H_t|` 定义并行；AutoGen group chat 默认顺序、LangGraph 路由 bug 会制造“假并行”。trace 至少要有 `span_id/parent_id/start/end/pid/thread_id`，并在评测侧计算最大并发与重叠；串行却声明并行 → 委派 0、总分 0。[★★★★☆]
6. **Judge 可靠性要分层**：MT-Bench 的 >80% 一致性与 position/verbosity 偏差、G-Eval 的 0.514 Spearman、Prometheus 的 0.897 Pearson 说明 LLM judge 可用但不可单独承重。正确形态是**确定性检查先行，LLM 只裁语义残差**，并做人校准子集 + 顺序随机化 + 长度控制。[★★★★★]
7. **成本/预算必须是一等公民**：AI Agents That Matter 与 Anthropic 都指出 accuracy-only 会误导；多 agent 约 15× token。OB-4 的 `budget_exceeded` 必须在**每次 LLM/工具调用前**检查，而不是事后截断。[★★★★☆]
8. **Harness 自身的隔离是评测可信度的一部分**：Inspect #4972 的全局 registry 污染会让结果随机翻转；本段必须 per-task 临时目录、无模块级可变全局、固定 seed/顺序。[★★★★☆，T3]

### 5.2 技术 landscape（可复用 vs 新建）

| 方案 | 形态 | 局限 | 结论 |
|---|---|---|---|
| 复用 `judge.py` + 科学 rubric | 现成 | 读散文、读科学 rubric，OB-5 必红；无编排维度 | 不采用 |
| 复用 `FrameworkAdapter` + 新 judge | 桥接五件套到 `StandardArtifacts`，新 `judge_orchestration.py` | 需要 runner 入口支持新 adapter/judge | **采用（桥接层）** |
| 全新独立 benchmark 包 | 不动 arc_bench | 重复 subset/aggregation/结果格式；与 OB-2 冲突 | 不采用 |
| 真实外部框架（AIS/AgentLab/AIDE） | 直接跑 | 不产编排五件套；需改每个 adapter；成本高 | 不作为第一段 |
| 确定性 worker 模拟器 + 3 适配器 | dry-run 可复现 | 构念效度有限，不能代表真实框架 | **采用（第一段）** |
| LLM 生成任务/评分 | 灵活 | 不可复现、易漂移 | 不采用；任务与真值冻结为文件 |

### 5.3 建议的第一段形态（供 DESIGN）

- **任务**：15 个冻结的 `task.json`（D4/L4/A4/C3），从 5 域 manifest 派生题面与隐藏真值；每个任务含 `subgoals`、`worker_capabilities`、`required_aggregate_schema`、`trap`、`budget`、`gold_plan`。
- **适配器**：3 个确定性 adapter：`gold_orchestrator`、`single_shot`、`dummy`；另设负向 fixture：`serial_claiming`（OB-3）、`over_budget`（OB-4）、`prose_only`（OB-5）。OB-1 的“3 框架”指前三个 adapter，不冒充真实框架。
- **五件套**：`plan.json`（子目标、依赖、输入/输出契约）、`delegations.json`（role/tool/context/父子/起止）、`aggregate.json`（结果、冲突、裁决）、`trace.jsonl`（OTel 风格 span）、`usage.json`（token/wall/tool latency/cost，按 trace 反算）。
- **评分**：确定性层（schema、MECE、依赖 DAG、角色-工具匹配、数值复算、冲突处理、预算、并行）占主导；LLM 只对“分解语义是否覆盖题面”给 residual，且输入不含散文。
- **OB 映射**：OB-1 用 15×3 dry-run + gold/单发阈值；OB-2 用 dummy 经基线入口产出 submission/judge_result；OB-3 用 serial_claiming fixture；OB-4 用 over_budget fixture；OB-5 用 prose-stripped 变体 + 输入白名单断言。

### 5.4 研究空白与本段定位

- 空白 1：仓库没有编排五件套/预算/trace 的任何实现（F-4/F-7）。
- 空白 2：现有 judge 与 runner 不适配 OB-2/OB-5（F-1/F-2/F-3）。
- 空白 3：没有“gold vs 单发”的构念效度闸门（OB-1 只写在文档）。
- 本段填补以上三项；**不**声称真实框架排名，也不声称 A7-2/A7-3 已解决。

## 6. 风险与边界

| 风险 | 处置 |
|---|---|
| **构念效度/同义反复**：gold 与任务共同设计，gold 必然高 | 单发负向控制；held-out 任务变体；隐藏真值；报告配对差值与区间；明确“本段测工具链，不测真实框架” |
| **LLM judge 偏差** | 确定性检查优先；LLM 只裁语义残差；顺序随机化、长度控制、人工校准子集；记录 judge 版本/prompt hash |
| **自报 trace/usage 不可信** | 要求 span 级 `pid/thread_id/start/end`；usage 从 trace + 工具记录反算；对无法验证的字段标 `self_reported=true`，不进承重分 |
| **15 任务成本** | dry-run 无 LLM；真实框架 field run 不在本段；单任务预算 120k token/900s 仅作为 fixture 上限 |
| **改 runner 影响 ARC-Bench** | 只做向后兼容的入口扩展；保留旧 topic/旧 judge 路径；用测试锁定旧行为 |
| **任务泄漏** | 15 任务与真值冻结为版本化文件；题面不泄露切分方式；评估集与示例集分离 |
| **统计功效不足** | 15 任务只报配对差值/自助置信区间，不宣称总体显著；BetterBench 的最小 QA 清单 |

## 7. 未决项登记（四元块）

- **U-1 15 任务的最终清单与冻结方式**
  - **判据**：15 个 `task.json` 有 `id/class/source_manifest/version/hidden_truth`，且 `git` 可追溯
  - **触发条件**：Step 3 设计时
  - **当前倾向**：D4=ML01/ML05/P01/Q03；L4=ML02/P01/S01/B01；A4=ML06/Q01/P03/S02；C3=ML04/Q02/P02 的控制变体
  - **证据等级**：E3（读 manifest）

- **U-2 OB-2 的入口形态**
  - **判据**：dummy adapter 经一个入口产出 `submission/` + `judge_result.json`，且旧 ARC-Bench topic/judge 行为不变
  - **触发条件**：Step 3 设计时
  - **当前倾向**：新增 `run_orchestration.py`（复用 `FrameworkAdapter`/submission 构建/新 judge），OB-2 措辞改为“baseline-compatible 入口”；若必须严格 `run_baseline.py`，则做一次通用 `--adapter-module` + `--judge` 扩展
  - **证据等级**：E1（F-1 实测）+ E3（F-2/F-3 读码）

- **U-3 LLM judge 的角色与校准**
  - **判据**：确定性层可单独产出总分；LLM residual 有 prompt hash、模型版本、人工校准 ≥30 条且报告一致性
  - **触发条件**：Step 3 设计时
  - **当前倾向**：默认 deterministic-only；LLM 作为可选 `--llm-residual`，不阻塞 CI
  - **证据等级**：E1（MT-Bench/G-Eval/Prometheus 摘要）

- **U-4 trace 信任边界**
  - **判据**：每个子 agent span 有独立 `pid/thread_id`；评测侧能计算 `max_concurrency`；串行 fixture 能判红
  - **触发条件**：Step 3 设计时
  - **当前倾向**：OTel 风格 span + 进程/线程 ID；无法证明的字段标 `self_reported`
  - **证据等级**：E1（OTel Traces）

- **U-5 “3 框架”的定义**
  - **判据**：OB-1 的 15×3 矩阵中 3 个 adapter 身份固定，且至少 1 个负向控制
  - **触发条件**：Step 3 设计时
  - **当前倾向**：gold / single_shot / dummy；真实框架留给 field run
  - **证据等级**：E3（plan §2/§6）

## 8. Review 记录（Step 2，自查·单视角）

> **RULE-4**：本节与正文同一会话，属自查（单视角）；未经异构基座复审。外部引用按“抽取 → 解析 → 字段比对 → 落状态”四步核验。

### 8.1 文献验证

| 引用 | ID | 验证方式 | 状态 |
|---|---|---|---|
| SwarmBench | arXiv 2608.30661；EMNLP 2026 Findings | arXiv abs + ACL PDF + 官方 repo README | 已验证（T1） |
| MAST | arXiv 2503.13657 | arXiv abs（v3） | 已验证（T1；venue 仅搜索索引，未回原文） |
| MultiAgentBench | arXiv 2503.01935 | arXiv abs | 已验证（T1） |
| AI Agents That Matter | arXiv 2407.01502 | arXiv abs | 已验证（T1） |
| BetterBench | arXiv 2411.12990；NeurIPS 2024 Spotlight | arXiv abs（comments） | 已验证（T1） |
| Agentless | arXiv 2407.01489 | arXiv abs | 已验证（T1） |
| MT-Bench | arXiv 2306.05685；NeurIPS 2023 D&B | arXiv abs | 已验证（T1） |
| G-Eval | arXiv 2303.16634 | arXiv abs | 已验证（T1） |
| Prometheus | arXiv 2310.08491；ICLR 2024 | arXiv abs | 已验证（T1） |
| Agent-as-a-Judge | arXiv 2410.10934 | arXiv abs | 已验证（T1） |
| AutoGen | arXiv 2308.08155 | arXiv abs | 已验证（T1） |
| Anthropic 多 agent 博客 | 官方 URL，2025-06-13 | WebFetch 全文 | 已验证（T2 官方工程博客） |
| OpenTelemetry Traces | 官方文档 | WebFetch 全文 | 已验证（T1） |
| Inspect AI | 官方文档 | WebFetch 全文 | 已验证（T1） |
| OpenAI Cookbook | 官方 URL（归档提示） | WebFetch 全文 | 已验证（T2） |
| LangGraph / CrewAI | 官方 docs | WebFetch（CrewAI 全文；LangGraph 搜索页） | 已验证（T2，LangGraph 为搜索级） |
| Inspect #4972 | GitHub PR | API 元数据+正文 | 已验证存在（T3） |

### 8.2 技术声明验证

| 声明 | 证据 | 状态 |
|---|---|---|
| `run_baseline.py` 当前读不存在的 `config/topics.yaml` | 实测 FileNotFoundError（§3.3 F-1） | ✅ E2 |
| `judge.py` 第二轮把 Writeup/README 送审 | 读码 `judge.py:576-591` | ✅ E3 |
| `ADAPTERS` 为 3 项静态字典 | 读码 `run_baseline.py:55-59` | ✅ E3 |
| 无编排五件套/Budget/trace | 全仓 grep 无实现 | ✅ E1 |
| SwarmBench 8 task types / 400 samples | ACL PDF 摘要 + repo README | ✅ T1 |
| MAST 14 modes / 3 categories / κ=0.88 | arXiv abs | ✅ T1 |
| Anthropic 90.2% / 15× token / 3–5 子 agent | 官方博客 | ✅ T2 |
| MT-Bench >80% agreement + biases | arXiv abs | ✅ T1 |

### 8.3 待修正项

- [x] 把“15 任务 × 3 框架”明确为**本地 dry-run 构念**，不冒充 SwarmBench 复现。
- [x] 把 OB-2 的“use run_baseline”冲突写成 U-2，不在调研阶段假装已解决。
- [x] 把“散文剥离”写成 judge 输入白名单问题，而非 prompt 提醒。
- [x] 把社区案例限制在陷阱用途，不作为最佳实践唯一依据。

### 8.4 Step 2 门禁

- [x] (a) 无 FALSIFIED 断言。
- [x] (b) 无 CONFLICT / STEP_GAP_OPEN；U-1..U-5 已登记。
- [x] (c) 承重断言均有 ≥1 T1 来源；T2/T3 处已标注。
- [x] (d) 假设已转 U-1..U-5，携带进 DESIGN。

## 9. 参考文献

1. Gao, J., Jin, Z., Men, T., Liu, K., Zhao, J. *SwarmBench: Can Large Language Models Act as Agent Swarm Orchestrators?* arXiv:2608.30661, EMNLP 2026 Findings. https://arxiv.org/abs/2608.30661
2. Cemri, M. et al. *Why Do Multi-Agent LLM Systems Fail?* arXiv:2503.13657. https://arxiv.org/abs/2503.13657
3. Zhu, K. et al. *MultiAgentBench: Evaluating the Collaboration and Competition of LLM agents.* arXiv:2503.01935. https://arxiv.org/abs/2503.01935
4. Kapoor, S. et al. *AI Agents That Matter.* arXiv:2407.01502. https://arxiv.org/abs/2407.01502
5. Reuel, A. et al. *BetterBench: Assessing AI Benchmarks, Uncovering Issues, and Establishing Best Practices.* arXiv:2411.12990, NeurIPS 2024 Spotlight. https://arxiv.org/abs/2411.12990
6. Xia, C. S. et al. *Agentless: Demystifying LLM-based Software Engineering Agents.* arXiv:2407.01489. https://arxiv.org/abs/2407.01489
7. Zheng, L. et al. *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena.* arXiv:2306.05685, NeurIPS 2023 D&B. https://arxiv.org/abs/2306.05685
8. Liu, Y. et al. *G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment.* arXiv:2303.16634. https://arxiv.org/abs/2303.16634
9. Kim, S. et al. *Prometheus: Inducing Fine-grained Evaluation Capability in Language Models.* arXiv:2310.08491, ICLR 2024. https://arxiv.org/abs/2310.08491
10. Zhuge, M. et al. *Agent-as-a-Judge: Evaluate Agents with Agents.* arXiv:2410.10934. https://arxiv.org/abs/2410.10934
11. Wu, Q. et al. *AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation.* arXiv:2308.08155. https://arxiv.org/abs/2308.08155
12. Anthropic. *How we built our multi-agent research system.* 2025-06-13. https://www.anthropic.com/research/multi-agent-research-system
13. OpenTelemetry. *Traces.* https://opentelemetry.io/docs/concepts/signals/traces/
14. UK AI Security Institute / Meridian Labs. *Inspect AI.* https://inspect.aisi.org.uk/
15. OpenAI. *Orchestrating Agents: Routines and Handoffs.* https://developers.openai.com/cookbook/examples/orchestrating_agents
16. LangChain. *langgraph_supervisor / Handoffs.* https://reference.langchain.com/python/langgraph-supervisor
17. CrewAI. *Crews.* https://docs.crewai.com/en/concepts/crews
18. Microsoft. *AutoGen Group Chat.* http://microsoft.github.io/autogen/0.4.7/user-guide/core-user-guide/design-patterns/group-chat.html
19. Inspect AI PR #4972. https://github.com/UKGovernmentBEIS/inspect_ai/pull/4972
