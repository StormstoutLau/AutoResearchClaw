---
id: arc-stage9-fanout-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-stage9-fanout-RESEARCH]
upstream: arc-master-roadmap
---

# 设计：Stage 9 计划派生健壮化（P-177）

> 依据：[RESEARCH.md](RESEARCH.md) 的 O-1..O-12 / R1..R6。
> 范围：抽取容错（C）、幂等（D）、早校验与 fail-fast（E）、重建工具（F）、结构修复（A/B）。
> 不在本批：替换 ResearchPlan schema；引入 LLM 规划器重写整图。

## 1. 决策表

| ID | 决策 | 被拒替代 | 理由与代价 |
|---|---|---|---|
| D-1 | `DEFAULT_MAX_DEPTH` 3 → **4** | 保持 3，把实验扁平挂到 literature | 扁平化正是 hub 的成因（R1/R2）；代价是图可深一层，但换来语义边 |
| D-2 | 实验节点在容量允许时依赖 **hypothesis**；否则依赖 literature shard | 全部依赖 literature（现状） | 恢复 `question→literature→hypothesis→experiment→analysis` 语义；代价是需 method→hypothesis 的容量分配 |
| D-3 | **横向 literature shard**：同一层建多个 literature 节点，每个 ≤ `max_fanout` | 新增 `group` 节点类型；纵向分组层 | 新类型会触碰 `NODE_TYPES` 与 V1；纵向分组多一层会超 depth。横向 shard 零 schema 变更 |
| D-4 | **幂等**：每个 stage 拥有自己的派生节点集；按 `(type, 归一化 statement)` 复用 id | 只做 statement 去重；整图重建 | 只去重无法处理产物变化；整图重建会丢 `done/failed`。按 stage 替换 + 外部引用保护命中两者 |
| D-5 | **抽取容错**：H1–H6、`SQ<n>` 标题、CJK `假设 N`；goal 跳过 blockquote/分隔线 | 只支持 `## ` 与 `H\d` | 现场 O-11/O-12 已证三种产物都不匹配；代价是解析器变复杂 |
| D-6 | Stage 7/8 写入后**立即校验** | 继续只在 Stage 2/9 校验 | 让坏结构在产生它的 stage 暴露（R5）；代价是早期失败更常见（正确的失败） |
| D-7 | 计划/契约违规 → **非可重试**（CONFIG=78） | 维持 75 | 确定性失败重试无意义（E5）；代价是需补 hints，误匹配风险有限 |
| D-8 | `exp_plan` 缺 `proposed_methods` → **一次有界重生成 + 确定性回退** | 直接 FAILED；无限重试 | 现场 O-4 显示 LLM 会漏键；一次修复 + 回退可让 stage 继续，且不掩盖 |
| D-9 | 新增 `researchclaw plan rebuild --run-dir` | 手改 `plan.v1.json` | 手改需重算 digest 且不可复现；工具化后可审计、可重放 |

## 2. 算法

### 2.1 抽取（C）

```
_section_block(text, keyword):
    找到第一个（任意级）含 keyword 的标题，记录级 L
    收集其后直到「标题级 ≤ L」的行

_sub_questions(tree):
    block ← section("sub-question") | section("sub question") | section("research question")
    若 block 内存在 SQ<n> 标题 → 取标题（≤8）
    否则取编号/项目列表（≤8）
    否则取 block 内任意更深标题（≤8）

_goal_statement(goal):
    跳过空行、标题、blockquote(>)、分隔线(---/***/|)、表格
    取第一个行；去掉成对 ** 强调

_hypothesis_statements(md):
    匹配 ^(#{1,6})?(最终|研究|核心|主要)?\s*(假设|hypothesis|h)\s*N
    若标记后无文本 → 向下 4 行找第一个非子标题（非「核心主张/为什么…/可测量预测」）作为语句
    回退：Hypotheses 小节的列表项 → 首个非标题行
```

### 2.2 有界派生（A/B）

```
max_fanout ← plan.constraints.max_fanout (默认 8)

stage7:
    移除 stage7 拥有的 proposed/active question 节点（外部引用者受保护）
    shards ← ensure_literature(needed = #gaps)
    分配 gaps：逐个挂到第一个未满的 shard；全满则新建 shard

stage8:
    shards ← ensure_literature()
    移除 stage8 hypotheses，按 statement 复用 id
    分配 hyps：同上（与 gaps 共享 shard 容量）

stage9:
    parents ← 全部 hypothesis；为空则 literature shards
    移除 stage9 proposed/active experiments
    分配 experiments：优先 hypothesis，全部满员时新建 literature shard 承接
```

`ensure_literature(needed)` 的目标 shard 数 = `ceil(needed / max_fanout)`；shard 语句为
`Literature evidence (group N) for: <goal>`，保证重跑可复现。

### 2.3 幂等（D）

`_take_owned(plan, stage, types)`：
1. 候选 = 该 stage 拥有、类型命中、状态 `proposed|active` 的节点；
2. **保护**：被候选集之外节点依赖的候选（例如已存在的 experiment 依赖某 hypothesis）不删；
3. 返回 `(type, 归一化 statement) → id`，供新节点复用 id。

复用 id 让重跑不产生新 id，也让依赖者保持有效。

### 2.4 早校验与 fail-fast（E）

```
Stage 7/8: update_from_stage(...) → load_plan → validate_plan
           violations 非空 ⇒ StageResult(FAILED, "invalid research plan after Stage 7/8: …")
exit_codes: CONFIG_HINTS += {"invalid research plan", "research plan / exp_plan mismatch",
                             "replanned plan is invalid"}
```

`exp_plan` 契约（D-8）在 Stage 9 解析成功后立即执行，先于一致性检查。

### 2.5 重建（F）

```
rebuild_plan(run_dir):
    读 stage-01 goal / stage-02 problem_tree / stage-07 synthesis /
       stage-08 hypotheses / stage-09 exp_plan
    按新 builder 从头派生
    保留 done/failed/abandoned 状态（按 statement key 匹配）
    constraints.max_depth/max_fanout 归位到缺省
    version ← old.version + 1；parent_version ← old.version
    validate；无违规才 update_plan（有违规只报告，不落盘）
```

## 3. 不变式

| ID | 不变式 |
|---|---|
| J-1 | 同一产物上重复执行任一 builder，节点集合与 id 不变 |
| J-2 | 任意节点的直接子节点数 ≤ `constraints.max_fanout` |
| J-3 | 图深度 ≤ `constraints.max_depth`（新计划为 4） |
| J-4 | 实验节点优先依赖 hypothesis；仅容量不足时依赖 literature shard |
| J-5 | 有外部依赖者的节点不被替换删除 |
| J-6 | 替换后不存在悬空依赖（V3 恒过） |
| J-7 | `invalid research plan` / `exp_plan mismatch` 不会触发 supervisor 重启 |

## 4. 错误语义

| 场景 | 行为 |
|---|---|
| 产物缺失（如无 synthesis） | 跳过对应 builder；rebuild 用 topic 兜底 |
| `exp_plan` 缺 `proposed_methods` | 一次重生成；仍缺失则确定性回退并告警 |
| Stage 7/8 校验失败 | `FAILED` + `invalid research plan after Stage N`；退出码 78，不重启 |
| rebuild 后仍有违规 | 打印违规并返回 65，**不写盘**（旧计划保留） |
| 旧计划不存在 | `version=1`，正常写入 |
| 受保护节点与新派生冲突 | 保留受保护节点；新节点复用其 id（若 key 相同） |

## 5. 职责边界

- **职责外**：图语义的进一步细化（如 method→hypothesis 的显式映射由 LLM 提供）；`max_fanout` 的全局调参；阶段执行调度。
- **能力边界**：抽取仍是规则式，无法理解任意自由格式；无法解析时回退为「首行/主题」，并在 plan 中体现为低质量节点（不静默丢弃）。

## 6. 拒绝方案汇总

| 方案 | 拒绝理由 |
|---|---|
| 仅调大 `max_fanout` | 掩盖 R1；Stage 14 仍会写出超限图 |
| 保持 depth=3 + 扁平化 | 现状即此，已证必然失败 |
| 新增 `group` 节点类型 | 触碰 `NODE_TYPES`/V1/DC，收益与横向 shard 相同 |
| 用 LLM 重写整图 | 引入不确定性与额外调用；本批目标是确定性 |
| 手改 `plan.v1.json` | digest 需重算、不可复现、无审计事件 |
