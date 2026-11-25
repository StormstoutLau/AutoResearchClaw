---
id: arc-stage9-fanout-RESEARCH
type: design
version: 1.1
status: verified
date: 2026-11-25
depends: [arc-g7-run-id-stability-RESEARCH]
upstream: arc-master-roadmap
---

# 调研：Stage 9 阻塞（fanout / 抽取 / 幂等 / exp_plan 契约）

> **症状**：B 站基线 run（`g7-baseline`）在 Stage 9 `EXPERIMENT_DESIGN` 失败；supervisor 记为 `rc=75`，重启 5 次后 `supervisor_exhausted`。
> **取证方式**：2026-11-25 经 SSH 在 B 站只读采集（`plan.v1.json`、`plan_events.jsonl`、`events.jsonl`、`stage-07/08/09` 产物），并在站上用仓内真实 builder 复算。**零写入、零代码改动**。

## 1. 现场读数（E1，B 站实测）

| # | 读数 | 证据 |
|---|---|---|
| O-1 | `checkpoint.json`：`last_completed_stage=8`，`run_id=g7-baseline` | 站上 `~/arc-runs/g7-baseline/checkpoint.json` |
| O-2 | `supervisor.jsonl`：`restart_scheduled` 5 次（attempt 1..5），末条 `supervisor_exhausted rc=75 restarts=6`，最后一次 worker `elapsed=930.1s` | 同上 `supervisor.jsonl` |
| O-3 | 前 4 次失败文本一致：`invalid research plan after Stage 9: fanout 12 exceeds 8`（seq 29/34/39/44，fencing 4–7） | `events.jsonl` |
| O-4 | **末次失败文本不同**：`research plan / exp_plan mismatch: exp_plan has no proposed_methods`（12:25:18Z） | `stage-09/decision.json`、`stage-09/stage_health.json` |
| O-5 | 存储计划 10 节点：1 question（根）+ 1 literature + 6 gap question + 2 hypothesis；depth=2，**fanout=8**（恰在上限），`validate_plan` 0 违规 | 站上 `plan.v1.json` + 真实 `_depth_and_fanout` |
| O-6 | 图结构：`n2(literature)` 的 children = `n3..n10` 共 **8**（6 个 gap 问题 + 2 个假设）；唯一根 `n1` 只连 `n2` | 站上图 dump |
| O-7 | 在存储计划上再加 1 个 experiment 节点 → **fanout=9**，`V11 fanout 9 exceeds 8`；再加 4 个 → 12（与 O-3 吻合） | 站上 `add_experiment_nodes` 复算 |
| O-8 | 再跑一次 Stage 8 builder → fanout=9 且触发 `duplicate node statement` | 站上 `add_hypothesis_nodes` 复算 |
| O-9 | `stage-09/exp_plan.yaml` 顶层键只有 `baselines/datasets/objectives/topic`，**没有** `proposed_methods` / `ablations` | 站上 YAML 解析 |
| O-10 | `plan_events.jsonl` 中 `plan.updated` 在 **stage 8** 出现两次（11:51:58Z、12:14:29Z） | 站上 `plan/plan_events.jsonl` |
| O-11 | `stage-02/problem_tree.md` 用 `# Sub-questions`（H1）+ `## SQ1 —` 小节；`stage-08/hypotheses.md` 用 `# 最终假设 1` / `## ...`，无 `H1:` / `### H1` 形式 | 站上产物 |
| O-12 | `stage-01/goal.md` 首个非标题行是 `> **Note (Stage 01 — unverified draft):** ...` | 站上产物 |

## 2. 代码路径（T1，回原文）

| # | 事实 | 证据 |
|---|---|---|
| F-1 | Stage 9 写 `exp_plan.yaml` → `add_experiment_nodes` → `check_experiment_plan_consistency` → `validate_plan`；任一不通过即 `FAILED`，**不写 plan** | [_experiment_design.py L648-L689](../../researchclaw/pipeline/stage_impls/_experiment_design.py#L648-L689) |
| F-2 | 计划校验只在 Stage 2 与 Stage 9 执行；Stage 7/8/14 只写不校验 | [_topic.py L227-L240](../../researchclaw/pipeline/stage_impls/_topic.py#L227-L240)、[_synthesis.py L88-L95](../../researchclaw/pipeline/stage_impls/_synthesis.py#L88-L95)、[L245-L253](../../researchclaw/pipeline/stage_impls/_synthesis.py#L245-L253) |
| F-3 | `_section_lines` 只识别 `## ` 级标题；H1（`# Sub-questions`）不生效 → 子问题列表为空 → 回退为「topic 一条」 | [derive.py L36-L46](../../researchclaw/plan/derive.py#L36-L46)、[L120-L131](../../researchclaw/plan/derive.py#L120-L131) |
| F-4 | goal 取「第一个非标题行」→ 结果是 `> **Note ...**` 提示行，污染 literature 节点语句 | [derive.py L133-L146](../../researchclaw/plan/derive.py#L133-L146) |
| F-5 | `_HYPOTHESIS` 只匹配 `H\d+` 前缀；不命中则回退为「首行」 | [derive.py L23-L24](../../researchclaw/plan/derive.py#L23-L24)、[L253-L262](../../researchclaw/plan/derive.py#L253-L262) |
| F-6 | 所有 gap 问题、所有 hypothesis、所有 experiment 都直接挂到同一个 literature 节点（`depends_on` 指向 literature） | [derive.py L228-L249](../../researchclaw/plan/derive.py#L228-L249)、[L282-L290](../../researchclaw/plan/derive.py#L282-L290)、[L312-L345](../../researchclaw/plan/derive.py#L312-L345) |
| F-7 | `_append_node` 只做 `_next_id`，**无去重/无 upsert**；重复执行同一 stage 钩子会重复追加同类节点 | [derive.py L60-L72](../../researchclaw/plan/derive.py#L60-L72) |
| F-8 | `fanout` = 任一节点子节点数的最大值；`max_fanout` 缺省 8；节点上限 40 | [schema.py L119-L140](../../researchclaw/plan/schema.py#L119-L140)、[L27-L29](../../researchclaw/plan/schema.py#L27-L29)、[L282-L290](../../researchclaw/plan/schema.py#L282-L290) |
| F-9 | 失败文本不含 revoked/config 关键词 → `classify_error` 归为 **RETRYABLE(75)** | [exit_codes.py L50-L56](../../researchclaw/runtime/exit_codes.py#L50-L56) |
| F-10 | supervisor 仅对可重试码重启；缺省上限 5 次 | [supervisor.py L193-L207](../../researchclaw/runtime/supervisor.py#L193-L207) |
| F-11 | 测试夹具规模 2 gap / 2 hypothesis / 2 method（fanout 6），从未覆盖真实规模 | [test_research_plan.py L42-L60](../../tests/test_research_plan.py#L42-L60)、[L230-L258](../../tests/test_research_plan.py#L230-L258) |
| F-12 | 深度上限 3 是硬约束；实验节点因此被强行挂到 literature（而非 hypothesis）以维持在 3 层内 | [schema.py L28](../../researchclaw/plan/schema.py#L28)、[derive.py L309-L311](../../researchclaw/plan/derive.py#L309-L311) |

## 3. 根因（六层，按影响排序）

1. **结构：单 hub**（F-6）。`literature` 同时是 6 个 gap 问题、2 个假设、N 个实验的父节点；扇出等于「下游总量」而非「语义分支宽度」。现场已到 8（上限），**任何实验都会越界**（O-5/O-7）。
2. **深度与扇出的设计冲突**（F-12）。语义正确应是 `question → literature → hypothesis → experiment → analysis`（depth 4），但上限是 3；实现用「把实验挂到 literature」来压深度，代价正是 hub 与扇出膨胀。
3. **抽取脆弱**（F-3/F-4/F-5，O-11/O-12）。三个产物解析器都只认一种格式：
   - `# Sub-questions`（H1）→ 0 条子问题 → 计划退化为「1 条 topic 问题」；
   - `## SQ1` 式问题无法进入节点；
   - `# 最终假设 1` 不匹配 `H\d` → 假设退化为「首行标题」；
   - goal 首个非标题行是提示块 → literature 语句被写成 `> **Note ...**`。
4. **非幂等追加**（F-7，O-10/O-8）。Stage 8 被执行两次，计划里出现 2 个假设节点（当前产物只解析出 1 个）；任何 `--resume` 重跑都会继续累加，`duplicate node statement` 也可能被触发。
5. **校验时机 + 重试语义**（F-2/F-9/F-10，O-2/O-3）。坏结构在 Stage 7/8 写入、Stage 9 才暴露；确定性违规被归为可重试，5 次重启全部无效。
6. **`exp_plan` 契约漂移**（O-4/O-9）。末次尝试的 LLM 输出只有 `baselines/datasets/objectives/topic`，缺 `proposed_methods`，于是失败文本从「fanout」变成「mismatch」。**同一 stage 的错误会随 LLM 重新生成而变形**，进一步说明「按错误文本分类重试」不可靠。

> 结论：`fanout 12` 只是最外层症状。即使把阈值调到 12，Stage 9 仍会因 `exp_plan` 契约缺失而失败；即使补齐 `exp_plan`，计划本身也因抽取脆弱而语义贫瘠（1 条问题 + 2 条标题式假设）。

## 4. 社区与学术解法

| # | 来源 | 关键做法 | 对本仓的启示 | 层 |
|---|---|---|---|---|
| E1 | [Anthropic — Multi-agent research system](https://www.anthropic.com/engineering/built-multi-agent-research-system) | orchestrator 并发 3–5 个 subagent，按复杂度调节投入；子代理上下文隔离，只回传摘要 | fan-out 是**运行时并发**参数，不应被当成「图里必须有这么多兄弟节点」 | T2（摘要级） |
| E2 | [LangChain — Deep research agent](https://docs.langchain.com/oss/javascript/deepagents/deep-research.md) | `maxConcurrentResearchUnits = 3`；「每轮最多 3 个并行子智能体」，多轮迭代 | 超出单轮上限时**分批 + 聚合**，而非一次性铺开 | T1 |
| E3 | [LLMCompiler (arXiv:2312.04511)](https://arxiv.org/abs/2312.04511) | Planner 产 DAG，Task Fetching Unit 派发；失败交给 replanner 修正计划 | 图校验失败的语义是「重新规划」，不是原样重跑 | T1 |
| E4 | [ADaPT (arXiv:2311.05772)](https://arxiv.org/pdf/2311.05772) | 按需分解；实测 `d_max ∈ {1,2,3}`，性能随深度上限提升 | 深度上限是**可调参数**，不是必须用扁平化去换的硬约束 | T1 |
| E5 | [Temporal — Non-Retryable Errors](https://docs.temporal.io/design-patterns/non-retryable-errors) | 永久性失败（非法输入等）必须立即失败；重试只会浪费分钟到小时 | 图结构违规 / 契约违规应映射为非可重试 | T1 |
| E6 | [LangGraph — Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api) | 用「超级步上限」兜底失控循环，且运行时可配 | 护栏保留但可配，不应硬编码且无出口 | T1 |
| E7 | [OpenAI — Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) | 以 JSON Schema 约束输出；仍要求应用处理 refusal/不完整响应 | `exp_plan` 应有显式 schema，而不是靠后置一致性检查才发现缺字段 | T1 |
| E8 | [Instructor — Retry Mechanisms](https://python.useinstructor.com/learning/validation/retry_mechanisms/) | 校验失败 → 把错误格式化为反馈 → 让 LLM 重生成（有界重试） | 契约违规应在**生成侧有界重试**，而不是上升到 supervisor 重启整个 stage | T2 |
| E9 | [Map-Reduce Agents 实践](https://www.callsphere.ai/blog/vw7g-map-reduce-multi-agent-pattern-2026) | 反模式：无界 fan-out；建议并发 5–10；分层 reduce | 用「分组节点 + 分层聚合」承载超量工作 | T3（仅方向） |

## 5. 方案对比

| 方案 | 做法 | 解决哪层根因 | 代价 |
|---|---|---|---|
| **A 分层分组（结构）** | 引入 `workstream`/`batch` 节点：gap 问题、假设、实验各自按 ≤`max_fanout` 分组，组节点汇入 literature/analysis | R1/R2 | 图形态变化；需同步一致性检查与 Stage 14 |
| **B 恢复语义边 + 放宽深度** | 实验依赖 hypothesis（而非 literature）；`max_depth` 3→4；超量实验再分批 | R1/R2 | 需 method→hypothesis 映射；改设计文档口径 |
| **C 抽取容错** | 三个解析器支持 H1/H2/H3、编号列表、`SQ`/`假设` 前缀；goal 跳过 blockquote 提示行；无法解析时**告警并降级**而非静默产出垃圾节点 | R3 | 纯确定性改动，风险低 |
| **D 幂等 upsert** | 每个 stage 只拥有自己类型的节点：先按 `(type, 归一化 statement)` 去重，或整组替换该 stage 的派生节点 | R4 | 需定义「哪些节点可被人工改」 |
| **E 早校验 + fail-fast** | Stage 7/8 写入后立即校验；确定性违规映射 65；`exp_plan` 契约违规走生成侧有界重试（E7/E8） | R5/R6 | 需区分「可重试」与「需重生成」 |
| **F 重建工具** | `researchclaw plan rebuild --run <dir>`：按产物确定性重建并重 seal | 解卡存量 run | 需保留人工字段 |
| **G 调阈值（应急）** | `max_fanout` 提到 12/16/32 | 只掩盖 R1 | 护栏失效；Stage 14 仍会写出超限图 |

**建议**：**C + D + E 先做**（低风险、直接消除「垃圾节点 + 重复节点 + 无效重启」），**A 或 B 随后做**（解决 hub/深度冲突，需设计裁决），**F 用于解卡当前 run**，G 仅作带审计的应急。

## 6. 对当前 run 的判读

- 现状：计划 fanout 恰为 8，**再加 1 个实验即 9**；即使 `exp_plan` 恢复正常，Stage 9 仍会失败。
- 末次失败原因已是另一条（缺 `proposed_methods`），说明**重试会让错误文本漂移**；靠重试不会收敛。
- 结论：该 run 在不改代码的前提下**无法越过 Stage 9**；需要 F（重建 + 分组）或 G（放宽阈值，且仍需补齐 `exp_plan`）才能继续。

## 7. 未决项（四元块）

| ID | 判据 | 触发条件 | 当前倾向 | 证据等级 |
|---|---|---|---|---|
| U-177-1 现场计数与图形态 | ✅ 已完成：10 节点 / fanout 8 / hub=n2 / 6 gap + 2 hyp | — | 关闭 | E1 |
| U-177-2 深度上限是否放宽到 4 | 设计裁决：语义边 vs 深度护栏 | A/B 方案设计阶段 | 倾向 B（实验依赖假设）+ 分组，depth 4 | E3 |
| U-177-3 重建与人工编辑边界 | 重建后 `abandoned` 节点与已批准 goal 是否保留 | F 实施前 | 只重建 `proposed/active` 派生节点 | E3 |
| U-177-4 `exp_plan` 最小 schema | 是否强制 `proposed_methods` 非空；缺失时重生成几次 | E 实施前 | 强制非空 + 生成侧最多 2 次反馈重试 | E1 |
| U-177-5 幂等键口径 | 按 `(type, statement)` 去重 vs 按 `owner_stage` 整组替换 | D 实施前 | 整组替换（stage 拥有自己的派生节点集） | E3 |

## 8. Review（Step 2 自查）

> **[自查·单视角]（RULE-4）**；未引入异构第二会话（RULE-5）。

| 检查 | 结果 |
|---|---|
| 现场读数可复核 | O-1..O-12 均可由站上只读命令重放；未写入任何文件 |
| 根因有代码锚点 | F-1..F-12 全部带文件/行号 |
| 复算可重放 | O-7/O-8 用仓内真实 builder 在站上复算 |
| 外部结论多源 | 结构：E1/E2/E9；校验-修复：E3/E5/E8；契约：E7 |
| 归因扭曲检查 | 未把「Anthropic 3–5 个子代理」直接换算成本仓阈值；E1 是并发参数，文中明确区分 |
| 未把 T3 当判据 | E9 标 T3，仅作方向 |

## 9. 诚实边界

1. 前 4 次失败的 `exp_plan` 内容未留存（每次覆盖写），只能由 `fanout 12` 反推「6 gap + 2 hyp + 4 method」；末次内容已留存（O-9）。
2. 未在 B 站执行任何修复或写入；本文件与站上状态一一对应，但修复后需重新取证。
3. E1 原文抓取失败，仅依据检索摘要。
4. 本文件不主张「放宽阈值能提升研究质量」；只主张「当前实现把总量误当扇出，且抽取/幂等/契约三处缺陷叠加，导致确定性阻塞」。
