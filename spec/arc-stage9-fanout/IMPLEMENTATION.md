---
id: arc-stage9-fanout-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-stage9-fanout-DESIGN, arc-stage9-fanout-RESEARCH]
upstream: arc-master-roadmap
---

# 实施：Stage 9 计划派生健壮化（P-177）

## 1. 交付锚点

| 交付 | 文件 | 符号/行 | 行为 |
|---|---|---|---|
| 子问题抽取（H1/H2 + `SQ<n>`） | [derive.py](../../researchclaw/plan/derive.py) | `_sub_questions` [L106-L128](../../researchclaw/plan/derive.py#L106-L128) | 任意级标题定位小节；优先 `SQ` 标题，其次列表 |
| goal 跳过提示块 | 同上 | `_goal_statement` [L131-L143](../../researchclaw/plan/derive.py#L131-L143) | 跳过 `>`/`---`/表格/标题 |
| 假设抽取（CJK 标记） | 同上 | `_hypothesis_statements` [L146-L184](../../researchclaw/plan/derive.py#L146-L184) | 支持 `H1` / `Hypothesis 1` / `最终假设 1`；空标记取下一标题 |
| 幂等替换 | 同上 | `_take_owned` [L203-L237](../../researchclaw/plan/derive.py#L203-L237) | 只删本 stage 的 proposed/active；外部依赖者受保护；返回 key→id |
| 横向 shard | 同上 | `_new_literature_shard` [L275-L286](../../researchclaw/plan/derive.py#L275-L286)、`_ensure_literature` [L288-L296](../../researchclaw/plan/derive.py#L288-L296) | 每 shard ≤ max_fanout |
| 有界分配 | 同上 | `_allocate` [L299-L318](../../researchclaw/plan/derive.py#L299-L318) | 优先未满父节点；全满新建 shard |
| Stage 7 派生 | 同上 | `add_synthesis_gaps` [L452-L486](../../researchclaw/plan/derive.py#L452-L486) | gaps → unknowns + question 节点 |
| Stage 8 派生 | 同上 | `add_hypothesis_nodes` [L489-L506](../../researchclaw/plan/derive.py#L489-L506) | 假设挂 literature shard |
| Stage 9 派生（语义边） | 同上 | `add_experiment_nodes` [L509-L566](../../researchclaw/plan/derive.py#L509-L566) | 实验优先挂 hypothesis，溢出挂 shard |
| 深度缺省 | [schema.py](../../researchclaw/plan/schema.py) | `DEFAULT_MAX_DEPTH = 4` [L30](../../researchclaw/plan/schema.py#L30) | 允许语义链 4 层 |
| exp_plan 契约修复 | [exp_plan.py](../../researchclaw/plan/exp_plan.py) | `ensure_methods` [L81-L127](../../researchclaw/plan/exp_plan.py#L81-L127) | 空 dict 不修复（交给守卫）；非空缺键 → 一次重生成 → 确定性回退 |
| 重建工具 | [rebuild.py](../../researchclaw/plan/rebuild.py) | `rebuild_plan` [L45-L117](../../researchclaw/plan/rebuild.py#L45-L117) | 按产物重建、保留受保护状态、违规不落盘 |
| CLI | [cli.py](../../researchclaw/cli.py) | `cmd_plan` [L541-L564](../../researchclaw/cli.py#L541-L564)、parser [L1962-L1970](../../researchclaw/cli.py#L1962-L1970) | `researchclaw plan rebuild --run-dir …` |
| 失败分类 | [exit_codes.py](../../researchclaw/runtime/exit_codes.py) | `CONFIG_HINTS` [L21-L25](../../researchclaw/runtime/exit_codes.py#L21-L25) | 计划/契约违规 → CONFIG(78)，不重启 |
| Stage 7/8 早校验 | [_synthesis.py](../../researchclaw/pipeline/stage_impls/_synthesis.py) | [L108](../../researchclaw/pipeline/stage_impls/_synthesis.py#L108)、[L283](../../researchclaw/pipeline/stage_impls/_synthesis.py#L283) | 写入后立即 `validate_plan` |
| Stage 9 契约修复接线 | [_experiment_design.py](../../researchclaw/pipeline/stage_impls/_experiment_design.py) | [L311-L321](../../researchclaw/pipeline/stage_impls/_experiment_design.py#L311-L321) | 解析成功后先补 `proposed_methods` |
| 验收用例 | [test_plan_robustness.py](../../tests/test_plan_robustness.py) | 15 用例 | 抽取/规模/幂等/fail-fast/契约/重建 |

## 2. TDD 红 → 绿

### 2.1 红（HEAD worktree，E1 可重放）

1. **收集失败**：新测试在 HEAD worktree 上 `ImportError: cannot import name '_sub_questions'`（1 error in 0.53s）。
2. **行为读数**（同一 worktree，脚本直调旧 builder）：

| 项 | 旧代码读数 | 期望 |
|---|---|---|
| `# Sub-questions` + `## SQ1..SQ4` | 生成 **1** 个 question | 4 |
| goal 首行 | `> **Note**` | 真实目标 |
| `add_synthesis_gaps` 跑两次 | 节点 4 → **7** | 不变 |
| 两次后校验 | `depth 4 exceeds 3` + `duplicate node statement` | 0 违规 |
| `add_hypothesis_nodes` 跑两次 | 节点 5 → **6** | 不变 |
| 假设语句 | 两条都是 `# 最终假设 1` | 两条真实陈述 |

### 2.2 绿

- `tests/test_plan_robustness.py`：**15 passed**。
- 计划相关回归（`test_research_plan` / `test_plan_stage_hooks` / `test_plan_replan` / `test_plan_decompose` + 新用例）：**54 passed**。
- 相关面（`-k "plan or synthesis or experiment_design or exit_code or stage_hooks or rebuild"`）：**126 passed**。
- 全量：见 §4 读数。

### 2.3 回归修复

首轮全量出现 1 处真实回归：`test_rc_executor.py::TestExperimentDesignGuard::test_empty_dict_response_pauses`
（`DONE` 而非 `PAUSED`）。原因：`ensure_methods` 把空 dict 也补成了方法，绕过了既有
schema-deficit 守卫。修复：空 dict 直接返回（DR-1），守卫保持 PAUSE。复跑该文件 **5 passed**。

## 3. 派生需求

| ID | 派生需求 | 来源 | 处置 |
|---|---|---|---|
| DR-1 | 空 dict 不触发契约修复 | 与既有 schema-deficit 守卫冲突 | `ensure_methods` 首行 `if not out: return out`；由守卫返回 PAUSED |
| DR-2 | 被外部依赖的节点不得删除 | 幂等替换可能制造悬空依赖 | `_take_owned` 计算 protected 集；只删无外部引用者 |
| DR-3 | 复用 id 保持依赖有效 | 重跑时不改变 id 才能让下游节点不悬空 | 返回 key→id，`_append_raw` 命中即复用 |
| DR-4 | shard 语句必须确定性 | 重跑需产生相同 key | `Literature evidence (group N) for: <goal>` |

## 4. 读数（本机 3.13.5）

| 测试面 | 读数 |
|---|---|
| 新用例 | 15 passed |
| 计划套件 | 54 passed |
| 相关面 | 126 passed |
| 全量 | 6 环境态失败（Windows shell hook / Keras 3 ×4 / bash 路径）+ 0 功能失败；108 skipped |

> 6 项环境态失败与 P-172/P-174/P-175 记录一致，与本批无关。

## 5. 边界

- 抽取仍是规则式：无法理解任意自由格式；失败时回退为「首行/主题」，计划质量下降但不静默失败。
- 实验→假设的分配是容量轮转，不是语义匹配；真正的 method→hypothesis 映射仍由 LLM 文本隐含。
- `rebuild` 保留 `done/failed/abandoned`，其余节点按新规则重建；人工新增的非派生节点会丢失（登记为 U-177-3）。
- 未改 `max_fanout` 缺省（仍 8），未改 23 stage 的执行顺序。
