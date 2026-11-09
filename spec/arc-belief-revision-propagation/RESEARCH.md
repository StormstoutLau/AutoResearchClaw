---
id: arc-belief-revision-propagation-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-master-roadmap, arc-cli-agent-wiring-RESEARCH]
upstream: arc-master-roadmap
---

# 调研：想法被推翻的回写/回退，与外部信息注入的多步传播

> **Feature**: 研究结论被后续实验/调研证伪后的回写与回退；外部信息（如模拟评审）注入后对多个关联步骤的影响传播。
> **状态**: verified（代码事实 + 外部锚点；本批只调研与设计，不改代码）
> **Spec 步骤**: Step 1-2

## 1. 调研目标

1. 当前框架对“想法被推翻”提供了哪些回退/回写机制？边界与缺陷是什么？
2. 外部信息在某一阶段注入后，如何影响多个关联阶段？当前是否有传播机制？
3. 项目内是否已有同类调研？外部社区/学术有哪些高质量解法？
4. `F:\Spec_Workflow\spec\academic-writing-workflow` 的调研与规范能否复用？复用边界是什么？

## 2. 调研方法

| 工具 | 用途 | 查询 |
|---|---|---|
| SearchCodebase | 回退/决策/版本/指导/演化机制 | `PIVOT`、`DECISION_ROLLBACK`、`_version_rollback_stages`、`hitl_guidance`、`evolution` |
| Read | 关键函数与调用链 | `runner.py`、`stages.py`、`_analysis.py`、`_helpers.py`、`cli.py` |
| WebFetch | 官方工程模式 | Azure Saga、Temporal Event History |
| WebSearch | 学术与社区锚点 | HARKing、LATS/SWE-Search、living review、reference rot |
| 外部文档 | 同构调研与规范 | `F:\Spec_Workflow\spec\academic-writing-workflow`（RESEARCH §12/§13、ACADEMIC_FILE_SPEC） |

## 3. 当前框架机制审计

### 3.1 场景 A：想法被后续实验/调研推翻

#### 3.1.1 触发面

| 触发 | 代码路径 | 当前行为 |
|---|---|---|
| Stage 15 研究决策 | `_analysis.py:1272` 解析 `PROCEED/PIVOT/REFINE`；`:1330-1335` 返回 `decision` | `pivot`/`refine` 进入 runner 的回退处理 |
| HITL 门禁拒绝 | `executor.py:405-413` 返回 `StageStatus.REJECTED` + `decision="pivot"` | runner 只对 `Stage.RESEARCH_DECISION` 处理 pivot，其他门禁拒绝直接停管线 |
| 人工重跑 | `--from-stage` + `--output` | 手动指定起点，无自动影响集 |

#### 3.1.2 回退执行链

```text
Stage 15 decision=pivot/refine
  → DECISION_ROLLBACK（stages.py:129-134）
      pivot  → HYPOTHESIS_GEN (7)
      refine → ITERATIVE_REFINE (13)
      agent 模式 refine → EXPERIMENT_RUN (12)
  → _record_decision_history（runner.py:1515-1551）
  → _version_rollback_stages（runner.py:1236-1279）
      把 stage-07..15 改名为 stage-NN_v{attempt}
  → 递归 execute_pipeline(from_stage=target)（runner.py:731-742）
  → _promote_best_stage14（runner.py:744-746）
  → 超过 MAX_DECISION_PIVOTS=2 后强制 PROCEED + quality_warning（runner.py:748-782）
```

#### 3.1.3 已有的“留痕”能力

- **版本目录**：`stage-NN_v{attempt}` 保留被替换的产物，不物理删除。
- **决策历史**：`decision_history.json` 追加 `decision/rollback_target/attempt/timestamp`。
- **最佳实验提升**：`_promote_best_stage14` 在回退后选择最佳 Stage 14 数据。
- **演化经验**：管线结束时 `extract_lessons` 写入 `evolution/`（`runner.py:829-832`），后续 run 的 prompt overlay 可复用。

#### 3.1.4 关键缺陷

| # | 缺陷 | 证据 | 后果 |
|---|---|---|---|
| A-1 | 回退目标是**固定映射**，不是“被证伪的前提” | `stages.py:129-134` | 如果被推翻的是 Stage 2 的缺口判断，pivot 仍只回到 Stage 7；无法非时序回跳到因果源 |
| A-2 | 没有“影响集”记录 | `decision_history` 只有 decision/target/attempt | 不知道哪些阶段/产物被这次推翻波及，无法做最小回改 |
| A-3 | `checkpoint.json` 不随回退回滚 | `_version_rollback_stages` 只改名目录；`read_checkpoint` 仍读旧 `last_completed_stage`（`runner.py:138-163`） | 递归回退期间崩溃，resume 可能从错误阶段继续，读取被改名的旧目录 |
| A-4 | 递归调用漏传 `to_stage` | `runner.py:731-742` | `--to-stage` 在触发 REFINE 后可能被无视，跑到 Stage 23（既有 CODE_REVIEW 已记录） |
| A-5 | 门禁拒绝不执行 `GATE_ROLLBACK` | `stages.py:118-123` 的映射只在 `default_rollback_stage`/`advance(START)` 使用；`runner.py:805-812` 对所有 `REJECTED` 直接 break | Stage 20 模拟评审拒绝不会回到 `PAPER_OUTLINE`，只会停管线 |
| A-6 | 没有 prospective/retrospective 分离 | 计划文档与运行产物都在同一目录树；回退只改名 | 无法区分“计划改了”与“执行改了”，旧结论容易被新叙述覆盖（HARKing 风险） |
| A-7 | 没有收敛/ kill 判据 | 只有 `MAX_DECISION_PIVOTS=2` 数量上限 | 无法判断“再回退一轮是否有新证据”，可能 thrashing 或过早放弃 |

### 3.2 场景 B：外部信息注入（如模拟评审）影响多个关联步骤

#### 3.2.1 注入通道

| 通道 | 落点 | 传播范围 |
|---|---|---|
| `researchclaw hitl guide` | `hitl/guidance/stage_NN.md` + `stage-NN/hitl_guidance.md`（`cli.py:2358-2375`） | **单阶段**；只被该阶段 prompt / context 读取 |
| HITL 门禁编辑 | `executor.py:266-271` 写入 `stage-NN/hitl_guidance.md` | 单阶段 |
| 模拟评审（Stage 20 质量门） | `quality_report.json` + `REJECTED` | **停管线**，不自动回写上游 |
| 演化经验 | `evolution/`（管线结束写入，`runner.py:829-832`） | 下一次 run 的 prompt overlay，非本次多步 |
| 知识库 | `write_stage_to_kb`（DONE 阶段） | 供后续检索，不是回写/回退触发器 |

#### 3.2.2 传播缺口

- **B-1 无“意见 → 受影响产物 → 目标阶段”映射**：评审意见只作为该阶段文本，没有结构化 claim/章节/实验条件到上游阶段的依赖边。
- **B-2 Stage 20 拒绝不会触发多步返修**：`GATE_ROLLBACK[QUALITY_GATE] = PAPER_OUTLINE` 存在，但拒绝路径未消费该映射；`StageStatus.REJECTED` 直接 break。
- **B-3 多阶段指导需要人工逐个写**：`hitl guide` 一次只写一个 stage；没有批量/依赖闭包。
- **B-4 没有返修响应表**：没有“评审意见 → 改动文件/章节 → 验证证据”的点对点记录。
- **B-5 没有外部过期机制**：新文献、撤稿、数据源变化不会触发任何重检；当前只在 prompt overlay 里被动吸收经验。

### 3.3 项目内既有调研覆盖

| 文档 | 覆盖 | 与本题关系 |
|---|---|---|
| `docs/failure-guards-design.md` | 漂移、伪造执行、循环护栏（FA/FC） | 只覆盖“跑偏/假执行/循环”，不覆盖“因果回跳/多步传播” |
| `arc-master-roadmap.md` G1 | 事件链、回放、checkpoint 恢复 | 提供“append-only/可恢复”的底层，但未实现；不定义回退语义 |
| `arc-master-roadmap.md` G3 | 证据血缘、循环护栏 | 提供 claim→evidence 的血缘方向，可作为未来影响集的基础 |
| `arc-master-roadmap.md` G7 | 漂移护栏 | 监测目标漂移，不是回写/回退 |
| `docs/orchestration-benchmark-plan.md` | 可证伪假设与推翻条件 | 只用于评测假设，不是运行时机制 |

**结论**：ARC 内没有专门针对“信念修正/多步传播”的调研；只有零散的护栏与路线条目。

## 4. 外部锚点

### 4.1 回退的工程模式

**X-1 Saga：补偿式回滚与不可回退点**

- **来源**: https://learn.microsoft.com/azure/architecture/patterns/saga ；Garcia-Molina & Salem, SIGMOD 1987, DOI 10.1145/38713.38742
- **验证**: ✅ Azure 页面已抓取；原始论文 DOI 来自二手书目（⚠️ 未直读全文）
- **要点**: 长事务拆为本地事务 + 补偿事务；失败逆序补偿；存在 **pivot transaction**（过此不可补偿，只能重试）；补偿不是删除，而是语义相反的动作。
- **相关性**: ARC 的“回退”目前是改名旧目录 + 重跑，不是补偿；需要显式区分“可重做区间”和“已验收不可回退点”。

**X-2 Durable execution：追加日志 + 重放**

- **来源**: https://docs.temporal.io/workflow-execution/event
- **验证**: ✅ 官方文档已抓取
- **要点**: 事件历史 append-only；崩溃后重放恢复；非确定性副作用要移出可重放控制流。
- **相关性**: ARC 目前没有 `stage_events.jsonl`（全仓零命中）；G1 的目标正是此模式。回退不应删除历史，而应追加“回退事件”。

**X-3 非时序回溯（backjumping/CBJ）**

- **来源**: Lecoutre et al., *Artificial Intelligence* 173 (2009) 1592–1614（二手书目）；Russell & Norvig Ch.5
- **验证**: ⚠️ 未直读，引用外部调研书目
- **要点**: 失败时跳到“真正导致冲突的决策”，而非机械退一步；冲突子句/nogood 记录避免重复死胡同；反复探索无用子树 = thrashing。
- **相关性**: ARC 的 pivot 固定回 Stage 7、refine 固定回 Stage 13，属于“时序/层号回退”，不是因果回跳。

**X-4 内容寻址重算**

- **来源**: Snakemake/Nextflow provenance；OxyMake（arXiv 2606.20989）；DANTE（arXiv 2609.08695）（二手书目）
- **验证**: ⚠️ 未直读
- **要点**: 是否重跑由“输入/代码/参数/环境内容是否变化”决定，而非 mtime；mtime 会导致 phantom/missed re-run。
- **相关性**: ARC 当前没有显式依赖摘要；`stage-NN_vN` 只按次数命名，无法判断“这次回退该重算哪些阶段”。

### 4.2 留痕与学术规范

**X-5 Prospective vs retrospective provenance**

- **来源**: Freire & Chirigati, *IEEE Data Eng. Bull.* 2018；W3C PROV https://www.w3.org/TR/prov-overview/
- **验证**: ⚠️ 二手书目；W3C 标准页存在
- **要点**: “打算怎么做”（计划）与“实际做了什么”（执行）必须分别保全；回溯时计划变更改文档版本，执行变更追加事件。
- **相关性**: ARC 的计划（topic/exp_plan/decision）与执行（stage 产物/日志）没有显式二分。

**X-6 最小回改集**

- **来源**: 外部调研 A-44（闭环多轮规划：错误归因 + 定位补丁点 + 最小关键步骤恢复）
- **验证**: ⚠️ 二手书目
- **要点**: 回改范围应是因果必要集，不是“出错点之后全部重做”。
- **相关性**: ARC 的 `_version_rollback_stages` 会改名整个区间（7..15），范围由层号决定，而非因果必要集。

**X-7 返修语义与响应表**

- **来源**: 外部调研 A-45/A-46（major/minor revision、返原审、轮次上限、point-by-point response）
- **验证**: ⚠️ 二手书目
- **要点**: 大修需要补分析/补数据/重构论证，通常返原审；返修需逐条响应 + 变更高亮；轮次有上限。
- **相关性**: ARC 的 Stage 20 评审没有“意见→改动锚点”响应表，也没有返修轮次语义。

**X-8 HARKing 与预注册**

- **来源**: Kerr 1998, *Personality and Social Psychology Review* 2(3):196–217, DOI 10.1207/s15327957pspr0203_4；COS Registered Reports https://www.cos.io/initiatives/registered-reports
- **验证**: ✅ Kerr DOI 经 WebSearch 确认；COS 页面来自二手书目
- **要点**: 回溯合法，但把事后假设伪装成事先假设是 HARKing；预注册/Registered Reports 用时间戳区分确认性与探索性。
- **相关性**: ARC 回退后如果直接改写 hypothesis/decision 文本，没有“旧结论保留 + 新结论标注事后”的机制。

**X-9 负结果一等公民**

- **来源**: 外部调研 A-49（Kohavi 等工业数据；Emborg 2022）
- **验证**: ⚠️ 二手书目
- **要点**: 大量想法失败是常态；负结果应结构化记录，而非静默丢弃。
- **相关性**: ARC 的 `decision_history` 只记录回退，不记录“被证伪的假设/不可得的数据”本身。

### 4.3 外部过期、收敛与搜索

**X-10 外部过期与 living review**

- **来源**: Cochrane Handbook Ch.22；Klein et al., *PLoS ONE* 9(12):e115253 (2014)；Retraction Watch
- **验证**: ⚠️ 二手书目
- **要点**: 预设更新触发；三分类（无新证据 / 不改变结论 / 改变结论）；只有第三类触发全量更新；reference rot 有 link rot 与 content drift 两型。
- **相关性**: ARC 当前没有任何“外部过期”重检；回退只由内部 Stage 15 触发。

**X-11 Freeze / kill criteria**

- **来源**: 外部调研 A-57/A-58/A-59（scope freeze、escalation of commitment、kill criteria、renegotiation trap）
- **验证**: ⚠️ 二手书目
- **要点**: 全链冻结与单决策 pivot 是两个尺度；放弃条件必须预先写定，且不能因触发而顺势改判据。
- **相关性**: ARC 只有 `MAX_DECISION_PIVOTS=2` 数量上限，没有预注册的 kill 判据或 freeze 语义。

**X-12 树搜索与回溯式规划**

- **来源**: LATS, arXiv:2310.04406；SWE-Search, arXiv:2410.20285
- **验证**: ✅ 标题/摘要经 WebSearch 确认
- **要点**: 用 MCTS/树搜索替代线性执行，支持回溯与替代方案；混合价值函数可更早放弃无望分支。
- **相关性**: ARC 的 Stage 15 是单点 LLM 决策，不是树搜索；可作为未来“多候选回退方案”参考，但成本高。

**X-13 多代理失败分类**

- **来源**: MAST, arXiv:2503.13657（P-011 已验证）
- **验证**: ✅
- **要点**: 14 种失败模式，含“任务验证与终止”。
- **相关性**: 回退/传播缺少验证与终止判据，属于 MAST 的验证类失败。

## 5. `F:\Spec_Workflow\spec\academic-writing-workflow` 复用评估

### 5.1 可复用件

| 外部件 | 内容 | 复用方式 |
|---|---|---|
| RESEARCH §12.1-§12.4 | 四层模式：补偿 / 留痕 / 回跳 / 重算；最小回改集 | **概念复用**：作为 ARC 回退机制的骨架 |
| RESEARCH §12.5 | 模拟评审 → 多步调整；major/minor、响应表、轮次上限 | **模板复用**：评审意见 → 改动锚点响应表 |
| RESEARCH §12.6 | HARKing、预注册、负结果一等公民 | **纪律复用**：旧结论留痕、新结论标注事后 |
| RESEARCH §12.7 | 三类场景 × 本仓动作处置矩阵 | **结构复用**：改写为 ARC 的 stage/产物映射 |
| RESEARCH §13.2-§13.5 | 外部过期、freeze、kill criteria、escalation | **概念复用**：预注册重检触发与终止条件 |
| ACADEMIC_FILE_SPEC §0-§4 | 一份真值、名=身份/版本=元数据、声明=重数；RESULT_MAP/LINEAGE | **规范复用**：为 ARC 的 claim→artifact→stage 血缘提供模板 |

### 5.2 不可直接复用件

| 外部件 | 原因 |
|---|---|
| `vN` session / M7 证据账本 | 属于 Spec_Workflow 的 spec 流程，不是 ARC 的 23 阶段 run |
| 400KB RESEARCH 全文 | 上下文过重；按节引用即可 |
| 外部脚本/工具 | ARC 定位零新依赖；不引入 Saga/DAG/状态机库 |
| `D:\Article` 仓规范 | 论文仓文件规范，不是运行时回退机制 |

### 5.3 复用结论

**可以复用，但只复用“概念、处置矩阵与模板”，不搬实现、不加依赖。** 建议在 ARC 的 DESIGN 中把外部 §12.7 的三类场景矩阵改写为“Stage 15 决策 / 门禁拒绝 / 外部评审 / 外部过期”四类触发，并保留其“旧口径留痕 + 最小回改集 + 收敛判据”三条纪律。

## 6. 综合分析

### 6.1 差距矩阵

| 能力 | 当前 | 缺口 |
|---|---|---|
| 回退触发 | Stage 15 pivot/refine；门禁拒绝停管线 | 门禁/外部评审不触发回退；无外部过期 |
| 回退目标 | 固定映射（7/13/12） | 非因果回跳；无法回到 Stage 1/2/9/17/20 |
| 影响集 | 无 | 不知道哪些阶段/产物需重做 |
| 留痕 | `_vN` + `decision_history` | 无 revision record；无 prospective/retrospective 分离 |
| 恢复 | checkpoint | 回退不回滚 checkpoint；递归漏传 `to_stage` |
| 多步传播 | 单阶段 hitl guidance | 无依赖闭包/批量注入/响应表 |
| 收敛 | `MAX_DECISION_PIVOTS=2` | 无 kill criteria、无进展判据、无 freeze |
| 外部过期 | 无 | 无重检触发、无三分类分流 |

### 6.2 可选路线

| # | 路线 | 成本 | 收益 | 风险 |
|---|---|---|---|---|
| R-1 | 最小修复：checkpoint 回滚 + `to_stage` 透传 + `revision_log.json` + 触发→目标映射 | 低 | 立刻消除恢复错误与“固定回 7/13”的硬编码 | 影响集仍靠人工 |
| R-2 | 标准：R-1 + 评审响应表 + Stage 20 拒绝回退 + 影响集声明 | 中 | 覆盖外部评审多步返修 | 需要 claim→artifact 依赖元数据 |
| R-3 | 重型：Saga/Temporal/DAG 引擎 + 自动影响闭包 | 高 | 全自动补偿/重算 | 违零依赖定位，过度工程 |

**建议**：先 R-1，再按真实案例升级到 R-2；R-3 不做。依据：X-1/X-2 提供模式但不要求引擎；X-6 强调最小回改集；X-11 强调先写判据；外部 RESEARCH C-8 也裁定“不引入重型本体”。

## 7. 幻觉抑制审查

| 声明 | 验证方式 | 状态 |
|---|---|---|
| Stage 15 pivot→7、refine→13 | 读 `stages.py:129-134` | ✅ |
| 回退不改 checkpoint | 读 `_version_rollback_stages` 与 `read_checkpoint` | ✅ |
| 递归漏传 `to_stage` | 读 `runner.py:731-742` | ✅ |
| Stage 20 拒绝停管线 | 读 `runner.py:805-812` | ✅ |
| 无 `stage_events.jsonl` | 全仓 grep 零命中 | ✅ |
| 外部 §12/§13 的引用 | 外部 RESEARCH 书目 + 关键页 WebFetch/WebSearch | ✅/⚠️ 已标注 |

## 8. 对设计的输入

### 8.1 约束

1. 不引入 Saga/Temporal/DAG 引擎；保持零新依赖。
2. 回退必须保留旧产物（append-only / `_vN`），不得删除历史。
3. 计划变更与执行变更分别留痕；不得就地改写旧结论。
4. 外部评审必须能落到“意见 → 产物/阶段”的显式映射。
5. 收敛判据必须预先写定，且不得在触发时顺势修改。

### 8.2 未决项登记（四元块）

- **U-1 影响集如何确定**
  - **判据**：能机械列出“被证伪前提 → 受影响阶段/产物”的集合，且与实际重跑集合一致。
  - **触发条件**：出现一次回退波及 ≥3 个阶段或两次回退互相覆盖的真实 run。
  - **当前倾向**：先人工声明 + 复用四文档/产物链接的弱依赖；暂不建全量 DAG。
  - **证据等级**：E1（外部类比，无本仓实测）。

- **U-2 外部评审的分类与映射**
  - **判据**：评审意见能映射到 minor/major 两类，并给出目标阶段集合与验证证据。
  - **触发条件**：Stage 20 收到首次真实外部模拟评审并拒绝。
  - **当前倾向**：minor → 论文层；major → 论文 + 实验/分析层；用响应表记录。
  - **证据等级**：E1。

- **U-3 收敛与 kill 判据**
  - **判据**：每轮回退能指出“消解了哪条未消解项”；无进展即升级人工，而非自动续轮。
  - **触发条件**：出现一次连续两轮回退无新增证据的 run。
  - **当前倾向**：保留 `MAX_DECISION_PIVOTS=2`，增加“无进展”检查；阈值待实测。
  - **证据等级**：E1。

- **U-4 外部过期重检**
  - **判据**：预设触发（新文献/撤稿/数据源变更）能输出“无变化 / 不改变结论 / 改变结论”三分类。
  - **触发条件**：出现一次引用撤稿或数据源失效的真实案例。
  - **当前倾向**：先登记触发，不建自动监听。
  - **证据等级**：E1。

- **U-5 revision record 形态**
  - **判据**：能记录 trigger/premise/impact_set/target/old_version/new_version/evidence/operator，且 append-only。
  - **触发条件**：R-1 进入实现批次。
  - **当前倾向**：新增 `revision_log.json`，不复用 `rework-graph.json`（后者是 spec 层）。
  - **证据等级**：E1。

- **U-6 外部文档复用边界**
  - **判据**：只引用概念/矩阵/模板，不复制 400KB 文档、不引入外部脚本/依赖。
  - **触发条件**：P-014 进入设计评审。
  - **当前倾向**：按 §5.3 执行。
  - **证据等级**：E2（已完成结构对照）。

## 9. 参考文献

1. Microsoft Azure Architecture Center. *Saga distributed transactions pattern*. https://learn.microsoft.com/azure/architecture/patterns/saga
2. Garcia-Molina, H., Salem, K. *Sagas*. ACM SIGMOD 1987. DOI 10.1145/38713.38742.
3. Temporal. *Events and Event History*. https://docs.temporal.io/workflow-execution/event
4. Lecoutre, C. et al. *Last-conflict based backtracking*. Artificial Intelligence 173 (2009) 1592–1614.
5. Freire, J., Chirigati, F. *Provenance and the Different Flavors of Computational Reproducibility*. IEEE DEBULL 2018.
6. W3C. *PROV-Overview*. https://www.w3.org/TR/prov-overview/
7. Kerr, N. L. *HARKing: Hypothesizing After the Results are Known*. Pers Soc Psychol Rev 2(3):196–217, 1998. DOI 10.1207/s15327957pspr0203_4.
8. COS. *Registered Reports*. https://www.cos.io/initiatives/registered-reports
9. Cochrane. *Handbook Ch.22: Prospective approaches to accumulating evidence*. https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-22
10. Klein, M. et al. *Scholarly Context Not Found: One in Five Articles Suffers from Reference Rot*. PLoS ONE 9(12):e115253, 2014.
11. LATS. arXiv:2310.04406.
12. SWE-Search. arXiv:2410.20285.
13. MAST. arXiv:2503.13657.
14. `F:\Spec_Workflow\spec\academic-writing-workflow\RESEARCH.md` §12-§13（同构调研，二手来源）。
15. `F:\Spec_Workflow\spec\academic-writing-workflow\ACADEMIC_FILE_SPEC.md` §0-§4（规范模板）。

---

**Review 签字**: 待复核 日期: 2026-11-10
