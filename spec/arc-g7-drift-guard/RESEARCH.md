---
id: arc-g7-drift-guard-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [failure-guards-design, arc-master-roadmap, arc-g7-orchestration-RESEARCH, arc-g7-review-fixes-RESEARCH]
upstream: arc-master-roadmap
---

# 调研：G7 漂移护栏（P-167）

> **Feature**：G7 失败护栏 A（相关性漂移），验收 FA-1..FA-3；不包含护栏 B（伪造执行）与 C（循环不收敛）。
> **先登记**：[observations-registry.md](../../docs/observations-registry.md) 已把 P-161/P-163/P-165 的 O 表集中登记，本批不承接 O 项。
> **落点**：`researchclaw/guards/drift.py` + Stage 15 决策后置检查；不改 Stage 1/8/14 产物契约。

## 1. 本仓现状（T1：源码/实测）

| 事实 | 证据 |
|---|---|
| Stage 15 在 `_parse_decision` 后才拿到结构化决策 | [_analysis.py L1326](../../researchclaw/pipeline/stage_impls/_analysis.py#L1326) |
| 无法解析时已有 `StageStatus.PAUSED` 先例（不推进 checkpoint） | [_analysis.py L1352-L1359](../../researchclaw/pipeline/stage_impls/_analysis.py#L1352-L1359) |
| 正常 DONE 返回只带 `decision.md` / `decision_structured.json` | [_analysis.py L1399-L1404](../../researchclaw/pipeline/stage_impls/_analysis.py#L1399-L1404) |
| `StageStatus.PAUSED` 是合法状态；runner 在 PAUSED 时不推进 | [stages.py L65-L75](../../researchclaw/pipeline/stages.py#L65-L75)、[runner.py L833-L870](../../researchclaw/pipeline/runner.py#L833-L870) |
| 读取历史产物支持 `stage-XX[/_vN]` 排序 | [_helpers.py L399-L423](../../researchclaw/pipeline/_helpers.py#L399-L423) |
| `ClaimVerifier` 可对文本抽 claim 并按知识卡/短名单判 grounded；citation 无知识卡时 `grounded=False` | [claim_verifier.py L68-L109](../../researchclaw/hitl/claim_verifier.py#L68-L109)、[L210-L299](../../researchclaw/hitl/claim_verifier.py#L210-L299)、[L301-L337](../../researchclaw/hitl/claim_verifier.py#L301-L337) |
| 全仓无 `rq_cos` / `drift_report` / `scope_change_approval` 实现 | `Grep` 0 命中（`researchclaw/`） |
| 设计草案已给经验阈值 `rq_cos=0.35/0.45`、`unsupported=0.40`、`p_only=0.50` | `docs/failure-guards-design.md` §1（本地设计草案，`.gitignore` 未入库；阈值仅作初值） |
| 无 scope_change 机器可读批准产物 | `Grep scope_change` 仅命中设计文档与 prompts，无 writer |

**关键约束**：
1. Stage 15 已有"PAUSED 合法"先例，不需要改状态机；只需返回 `StageStatus.PAUSED`。
2. 默认离线运行不能依赖外部 embedding API；必须提供确定性后端。
3. `ClaimVerifier` 的 `unchecked` 不能计入分母（设计 §A.1 明确排除 `None`）。
4. 本批不新增 RCConfig 字段，阈值走模块默认 + 环境变量；避免配置 schema 变更扩散。

## 2. 外部证据

### 2.1 学术（T1，已回 arXiv abs 原文）

| # | 来源 | 关键结论 | 本批借用 | 不借用 |
|---|---|---|---|---|
| E1 | **Inherited Goal Drift**，arXiv [2603.03258](https://arxiv.org/abs/2603.03258)，ICLR 2026 Lifelong Agents Workshop | 现代 agent 仍会 goal drift；对 prefilled trajectory 的"继承漂移"很脆；drift 行为随 prompt 变化不一致，指令层级遵循不能可靠预测抗漂移 | 漂移必须在**运行轨迹的决策点**测，不能靠单次 prompt 约束；阈值/判定要允许多信号 | 不引入其股票交易/急诊环境 |
| E2 | **Why LLMs Aren't Scientists Yet**，arXiv [2601.03315](https://arxiv.org/abs/2601.03315) | 4 次端到端尝试中 3 次在实现/评估阶段失败；六类失败含 **implementation drift**、overexcitement（失败仍宣布成功）、长程记忆退化 | Stage 15 决策点做目标-结论一致性检查；WARN/PAUSE 而非自动重试 | 不照搬其 6 agent 管线 |
| E3 | **MLR-Bench**，arXiv [2505.19955](https://arxiv.org/abs/2505.19955)，NeurIPS 2025 D&B | 编码 agent 在 **80%** 案例产生 fabricated/invalid 实验结果；MLR-Judge 与专家高一致 | `unsupported_ratio` 作为漂移的第二信号；claim 级而非全文级 | 不采用其 201 任务 |
| E4 | **Kosmos**，arXiv [2511.02824](https://arxiv.org/abs/2511.02824) | 200 次 rollout 后仍会失去连贯性；用结构化 world model 维持目标；报告逐句引用代码/文献，独立科学家判定 79.4% 陈述准确 | 长跑需要显式目标锚；引用/证据可追溯是漂移的反向指标 | 不构建 world model |
| E5 | **FActScore**，arXiv [2305.14251](https://arxiv.org/abs/2305.14251)，EMNLP 2023 | 把长文拆成 atomic facts，计算"被可靠来源支持的比例"；自动估计误差 <2% | claim 级支持比例公式 | 不引入其检索/模型 |
| E6 | **RARR**，arXiv [2210.08726](https://arxiv.org/abs/2210.08726)，ACL 2023 | 为输出找 attribution 并后编辑不支持内容，尽量保留原文 | "证据不足 → 修正/暂停"的动作映射 | 不做自动后编辑 |
| E7 | **MAST**，arXiv [2503.13657](https://arxiv.org/abs/2503.13657) | 1600+ trace、14 失败模式、3 类；task verification 是独立失败类 | 把"验证/证据"与"目标一致性"分开计分 | 不照搬 14 模式 |
| E8 | **MT-Bench / LLM-as-judge**，arXiv [2306.05685](https://arxiv.org/abs/2306.05685) | 强 judge 与人类 >80% 一致，但有 position/verbosity/self-enhancement 偏差 | 本批**确定性规则优先**；LLM 残差留后续 | 不用 LLM 单独承重 |

### 2.2 工业官方 / 社区（T1/T2）

| # | 来源 | 机制 | 本批借用 |
|---|---|---|---|
| E9 | [OpenAI Agents SDK — Guardrails](https://openai.github.io/openai-agents-python/guardrails/) | input/output/tool guardrails；tripwire 可在检测到违规时立即中止；blocking 与 parallel 两种执行模式 | 输出护栏 + tripwire（PAUSE）；确定性检查优先 |
| E10 | [NVIDIA NeMo Guardrails](https://docs.nvidia.com/nemo/guardrails/) | input / retrieval / dialog / execution / output rails；可配置策略阻断或修改内容 | 本批是 **output rail**（Stage 15 决策后），不碰输入/工具 |
| E11 | [Ragas — Faithfulness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/) | `supported claims / total claims`；claim 拆分 + 逐条支持判断 | `unsupported_ratio` 的公式与"claim 级"口径 |
| E12 | [LangSmith Evaluation](https://docs.langchain.com/langsmith/evaluation) | 离线/在线 evaluator；code rules 与 LLM-as-judge 并用；在线采样监控 | 阈值/WARN 属在线监控面；PAUSE 属阻断面 |

### 2.3 降级记录

- `mcp_english-search` 连续返回 HTTP 522；按降级链改用 arXiv API + 官方文档直取（E1-E12 均回原文）。
- 社区 issue 搜索未命中与"goal drift 检测"直接相关的可复现 PR；不把论坛转述当承重证据。

## 3. 综合分析

1. **漂移是轨迹属性，不是单点文本属性**：E1 说明 prompt 级约束不足以抗漂移；护栏必须落在**决策点**，用目标-结论-证据三路信号联合判定。[★★★★☆]
2. **claim 支持率是可机械化的第二信号**：E3/E5/E11 给出同一口径——"被支持 claim / 有判定的 claim"。本仓已有 `ClaimVerifier`，可直接复用，避免新造 LLM judge。[★★★★★]
3. **默认必须离线确定性**：本仓无通用 embedding client；TF-IDF/词面余弦可复现、零依赖，但语义分辨力弱。正确形态是"词面极端低相似 + 高 unsupported → PAUSE；中等低相似 → WARN"；预留 `embed_fn` 注入给后续真实语义后端。[★★★★☆]
4. **PAUSE 优于自动 REFINE**：E2 的 implementation drift 与 overexcitement 表明自动重采样不改变目标函数；E9 的 tripwire 也是立即中止。首次触发即 PAUSED 待人，比"先强制 REFINE 再二次 PAUSE"更安全，也避免掩盖漂移。[★★★★★]
5. **合法 PIVOT 必须显式豁免**：E9/E10 的护栏都有 allow/exception 通道；本仓没有 scope_change 机器可读批准，需定义 `scope_change_approval.json` 契约，否则 FA-3 无法机械化。[★★★★☆]
6. **阈值是经验值**：E1/E2 未给可移植阈值；设计草案的 0.35/0.45/0.40/0.50 只能作为初值，必须可配置、可校准，并在报告中记录 backend/thresholds。[★★★★☆]

## 4. 未决项（四元块）

- **U-1 默认后端与 PAUSE 门槛**
  - 判据：离线词面后端在"完全无关 + 高 unsupported"时能 PAUSE；中等相似只 WARN；注入语义后端时走 0.35 门槛
  - 触发条件：Step 3 设计
  - 当前倾向：词面后端 `lexical_pause=0.20` 的极端门槛；注入后端走 `rq_pause=0.35`
  - 证据等级：E3（源码）/E1（外文）

- **U-2 scope_change 批准产物**
  - 判据：`stage-15/scope_change_approval.json` 有 `approved=true` 时 PIVOT 豁免；无文件/未批准不豁免
  - 触发条件：Step 3 设计
  - 当前倾向：本批定义契约 + `write_scope_change_approval` helper；HITL UI 接线留给后续
  - 证据等级：E3

- **U-3 claim 分母**
  - 判据：`unsupported_ratio = ungrounded/(grounded+ungrounded)`，`unchecked` 排除；分母 0 时不 PAUSE
  - 触发条件：Step 3 设计
  - 当前倾向：直接用 `ClaimVerifier.verify_text` 报告
  - 证据等级：E3（claim_verifier 源码）

- **U-4 结论段抽取**
  - 判据：优先取 `conclusion/discussion/results/结论/讨论/结果` 标题段；无标题取全文/末段
  - 触发条件：Step 3 设计
  - 当前倾向：标题匹配 + 末 40% 回退
  - 证据等级：E3

- **U-5 阈值校准**
  - 判据：≥30 条人工标注上报告 PAUSE/WARN 的精确率/召回率
  - 触发条件：首次接入真实运行前
  - 当前倾向：本批只给初值 + 可配置，不声称校准完成
  - 证据等级：E5

## 5. Review（Step 2，自查·单视角）

- [x] E1-E12 均回原文（arXiv abs / 官方文档），无"搜到了=事实"。
- [x] 承重断言（claim 支持率、PAUSE 优先、合法 PIVOT 豁免）均有 T1 来源。
- [x] 明确标注阈值是经验初值，未写成校准结论。
- [x] 降级链已记录（522 → arXiv/官方文档）。
- [x] 未把 P-161/P-163/P-165 的 O 项混入本批范围。

## 6. 参考文献

1. Menon, A. et al. *Inherited Goal Drift: Contextual Pressure Can Undermine Agentic Goals.* arXiv:2603.03258, ICLR 2026 Lifelong Agents Workshop.
2. Trehan, D., Chopra, P. *Why LLMs Aren't Scientists Yet: Lessons from Four Autonomous Research Attempts.* arXiv:2601.03315.
3. Chen, H. et al. *MLR-Bench: Evaluating AI Agents on Open-Ended Machine Learning Research.* arXiv:2505.19955, NeurIPS 2025 D&B.
4. Mitchener, L. et al. *Kosmos: An AI Scientist for Autonomous Discovery.* arXiv:2511.02824.
5. Min, S. et al. *FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation.* arXiv:2305.14251, EMNLP 2023.
6. Gao, L. et al. *RARR: Researching and Revising What Language Models Say, Using Language Models.* arXiv:2210.08726, ACL 2023.
7. Cemri, M. et al. *Why Do Multi-Agent LLM Systems Fail?* arXiv:2503.13657.
8. Zheng, L. et al. *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena.* arXiv:2306.05685, NeurIPS 2023 D&B.
9. OpenAI. *Agents SDK — Guardrails.* https://openai.github.io/openai-agents-python/guardrails/
10. NVIDIA. *NeMo Guardrails Library Developer Guide.* https://docs.nvidia.com/nemo/guardrails/
11. Ragas. *Faithfulness.* https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/
12. LangChain. *LangSmith Evaluation.* https://docs.langchain.com/langsmith/evaluation
