---
id: arc-belief-revision-propagation-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-belief-revision-propagation-RESEARCH]
upstream: arc-belief-revision-propagation-RESEARCH
---

# 设计：回写/回退与外部信息传播的最小机制

> 输入：[RESEARCH.md](RESEARCH.md) §3 现状、§6 差距、§8 未决项。目标：先补语义与留痕，不引入重型引擎。

## 1. 设计不变量

1. **不删除历史**：旧阶段产物保留在 `stage-NN_vN`；新结论通过追加记录取代，不覆盖旧文本。
2. **因果回跳**：回退目标由“被证伪的前提”决定，不由层号机械决定。
3. **计划/执行二分**：计划变更改文档版本；执行变更追加 revision/decision 事件。
4. **最小回改集**：只重跑因果必要阶段，不做“出错点之后全部重做”。
5. **零新依赖**：不引入 Saga/Temporal/DAG/状态机库；只用现有文件与 JSON。
6. **收敛前置**：轮次上限、进展判据与 kill criteria 必须在回退开始前写定。

## 2. 决策表

| # | 决策 | 选择 | 被拒绝的替代 | 理由 |
|---|---|---|---|---|
| D-1 | 触发分类 | experiment-contradiction / research-contradiction / external-review / external-expiry / manual 五类 | 只保留 Stage 15 pivot/refine | 外部评审与外部过期当前无入口 |
| D-2 | 回退目标 | 由 `revision_targets` 按“前提类型”映射；保留 `DECISION_ROLLBACK` 作为 fallback | 固定 pivot→7、refine→13 | 无法回到 Stage 1/2/9/17/20 |
| D-3 | 影响集 | 先人工声明 + 产物/四文档弱依赖；不自动闭包 | 全量 DAG 自动闭包 | 依赖元数据不足，误报成本高 |
| D-4 | 留痕 | 新增 append-only `revision_log.json`，含 trigger/premise/impact_set/target/old/new/evidence/operator | 复用 `rework-graph.json` | 后者是 spec 流程层，不是 run 层 |
| D-5 | 外部评审 | 意见 → claim/章节/实验条件 → 影响集；输出 point-by-point 响应表 | 只写 `hitl_guidance.md` | 单阶段指导无法多步传播 |
| D-6 | Stage 20 拒绝 | 消费 `GATE_ROLLBACK[QUALITY_GATE]`，回到 `PAPER_OUTLINE`；不直接停管线 | 维持 REJECTED→break | 模拟评审的主要场景被卡死 |
| D-7 | 收敛 | `MAX_DECISION_PIVOTS` 保留；新增“每轮必须消解 ≥1 未消解项”与 kill criteria | 只靠轮次上限 | 数量上限不能防无进展回退 |
| D-8 | 外部过期 | 预注册重检触发 + 三分类（无变化/不改变结论/改变结论）；仅第三类触发回退 | 每次外部变化全量重跑 | 成本高，且多数不改变结论 |
| D-9 | 外部文档复用 | 只复用概念/矩阵/模板，不复制全文、不引入脚本 | 直接吸收 `academic-writing-workflow` 工具 | 项目语境不同，且 ARC 零依赖 |

## 3. 接口与数据形态

### 3.1 `revision_log.json`（append-only）

```json
{
  "revision_id": "rev-0001",
  "run_id": "rc-...",
  "trigger": "experiment-contradiction | research-contradiction | external-review | external-expiry | manual",
  "premise": {
    "statement": "被证伪的判断",
    "stage": "stage-02",
    "artifact": "gap_analysis.md"
  },
  "impact_set": ["stage-02", "stage-07", "stage-08"],
  "target_stage": "stage-02",
  "old_versions": ["stage-02_v1"],
  "new_versions": ["stage-02"],
  "evidence": ["stage-15/decision.md", "review.json#item-3"],
  "decision": "rollback | rework | accept-with-caveat",
  "operator": "human | agent",
  "convergence": {
    "round": 1,
    "max_rounds": 2,
    "resolved_item": "review-item-3",
    "kill_criteria": "no new evidence after 2 rounds"
  },
  "timestamp": "2026-11-10T..."
}
```

### 3.2 `revision_targets`（前提类型 → 目标阶段）

| 前提类型 | 目标阶段 | 说明 |
|---|---|---|
| 研究问题/缺口 | `PROBLEM_DECOMPOSE` / `TOPIC_INIT` | 需要回到研究问题层 |
| 假设 | `HYPOTHESIS_GEN` | 保留现有 pivot 语义 |
| 实验设计 | `EXPERIMENT_DESIGN` | 条件/变量/数据设计被证伪 |
| 执行/实现 | `EXPERIMENT_RUN` / `ITERATIVE_REFINE` | 代码或运行失败 |
| 分析/结论 | `RESULT_ANALYSIS` / `RESEARCH_DECISION` | 指标解释或决策被证伪 |
| 论文 claim | `PAPER_OUTLINE` / `PAPER_WRITING` / `QUALITY_GATE` | 评审意见落在写作层 |

### 3.3 评审响应表（point-by-point）

| 评审意见 | 类型 | 受影响 claim/产物 | 改动锚点 | 验证证据 | 状态 |
|---|---|---|---|---|---|
| R-1 | minor/major | `paper_draft.md#L...` | `stage-17/...` | `tests/...` | open/closed |

## 4. 执行流程（建议）

```text
触发（Stage 15 / 门禁拒绝 / 外部评审 / 外部过期）
  → 归类 trigger + 定位 premise + 声明 impact_set
  → 写 revision_log.json（append-only）
  → 选择 target_stage（revision_targets，fallback DECISION_ROLLBACK）
  → 版本化受影响阶段（stage-NN_vN，保留旧产物）
  → 递归 execute_pipeline(from_stage=target, to_stage=原 to_stage)
  → 每轮检查：是否消解 ≥1 未消解项；无进展 → 人工升级
  → 完成后写响应表与 revision 结果
```

## 5. 被拒绝的方案

| 方案 | 拒绝理由 |
|---|---|
| 引入 Saga/Temporal/DAG 引擎 | 零依赖定位；现有文件 + JSON 足够表达 |
| 全量依赖图自动闭包 | 当前无可靠依赖元数据；误报/漏报成本高 |
| 回退时删除/重写旧阶段 | 破坏可追溯与可复现；违 I-1/I-2 |
| 直接把 `academic-writing-workflow` 全文复制进 ARC | 语境不同、体量过大；只复用概念与模板 |
| 只靠 `hitl guide` 单阶段注入 | 无法覆盖“评审意见影响多步”的主场景 |

## 6. 影响面与回滚

- 代码（未来批次）：`runner.py`（checkpoint/to_stage/revision log）、`stages.py`（targets）、`_analysis.py`（Stage 15 触发）、`executor.py`（门禁拒绝）、`cli.py`（review 命令）。
- 产物：新增 `revision_log.json`、`review_response.md`；`stage-NN_vN` 语义不变。
- 默认路径：无回退触发时行为不变。
- 回滚：删除 revision log/response 文件即可；不改旧阶段产物。

## 7. 测试策略（供后续实施）

1. checkpoint 回滚：回退后 `checkpoint.json` 指向 target 前一个阶段；崩溃恢复不跳过。
2. `to_stage` 透传：`--to-stage 17` + REFINE 不会跑到 18+。
3. revision log：每次回退追加一条，字段齐全且 append-only。
4. Stage 20 拒绝：`REJECTED` 触发 `PAPER_OUTLINE` 回退，而非 break。
5. 评审响应表：每条意见有 claim/产物锚点与验证证据。
6. 收敛：两轮无进展触发人工升级，不自动续轮。

## 8. 未决项

沿用 [RESEARCH.md](RESEARCH.md) §8.2 的 U-1..U-6，不重复定义。
