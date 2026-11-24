---
id: arc-research-plan-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [research-plan-design, arc-master-roadmap]
upstream: null
---

# 调研：ResearchPlan v1 计划对象（P-152 / G8a）

> **Feature**：P-152。兑现总纲 G8a（P1，4 项）：把 Stage 2 的散文式分解升级为可校验、可存储、可追溯的任务图。
> **性质**：T1 实施批；单分支、单 PR；不替代 23 阶段。
> **结论先行**：① 不做自由 planner；② 计划由现有阶段产物**确定性派生**，不新增 LLM 调用；③ 12 条校验规则，非法即拒绝；④ 只在 Stage 2 与 Stage 9 失败关闭，Stage 7/8/14 的计划更新不阻塞阶段。

## 1. 问题

Stage 2 只写 `problem_tree.md`（Sub-questions / Priority / Risks 的自由文本），没有 schema、ID、依赖与验收。后果：

- 无法机械判断分解是否完整；
- Stage 7/8/9/14 与子问题无显式映射；
- 无法回答「哪个子问题被回答了」；
- 无法为 G8b 的版本化重规划提供稳定对象。

## 2. 设计源与外部锚点

设计源为 `docs/research-plan-design.md`（344 行，v1.0 draft；该文件在 `.gitignore` 中，故用行内引用）。其外部依据（PlanBench 的规划不可靠、Magentic-One 双账本、ADaPT 懒惰分解、LLMCompiler 依赖图）在本批不重新调研；本批只落地该设计的 P0+P1 切片。

## 3. 方案对比

| 方案 | 做法 | 问题 |
|---|---|---|
| A 自由 planner | 让 LLM 重新规划整个研究流程 | 与 23 阶段冲突，状态双真值；PlanBench 已证不可靠 |
| B Stage 2 追加一次结构化 LLM 调用 | 让 LLM 直接产出 plan JSON | 增加成本与失败面；离线/测试路径不可复现 |
| **C 从既有产物确定性派生（采用）** | 从 `problem_tree.md`、`synthesis.md`、`hypotheses.md`、`exp_plan.yaml` 解析节点 | 节点 statement 是「抽取」而非「生成」，计划丰富度有限 |

选择 C 的理由：G8a 的验收是**可校验、可存储、可追溯**，不是「计划文本有多聪明」。确定性派生让 Stage 2 在任何模式下（有/无 LLM）都产出合法计划，并可用纯函数测试。

## 4. 验收切片

| 总纲 ID | 本批落点 | 证据 |
|---|---|---|
| A8a-1 | Stage 2 写 `plan/plan.v1.json` + `plan_meta.json`；校验失败即 Stage 2 FAILED | `test_stage2_writes_valid_plan`、缺 acceptance/环/owner=99 用例 |
| A8a-2 | Stage 9 生成 `experiment` 节点（metric/dataset/baseline），与 `exp_plan.yaml` 双向检查 | `test_stage9_adds_experiments_and_consistency`、条件数不一致用例 |
| A8a-3 | 预算求和、深度 ≤3、扇出 ≤8、节点 ≤40、statement 不重复 | V10/V11 五条用例 |
| A8a-4 | `plan_digest` 规范化复算；篡改即拒绝 | `test_digest_tamper`、`test_roundtrip` |

## 5. 风险与边界

| 风险 | 处理 |
|---|---|
| LLM problem_tree 的子问题重复 | V11 拒重；Stage 2 FAILED，符合设计 §6 |
| 依赖链超过深度 3 | experiment 绑定 literature（而非 hypothesis），链路固定为 question→literature→experiment→analysis = 3 |
| Stage 9 首次一致性检查「自证」 | 生成后检查必然通过；另用 3 条件 vs 2 条件用例独立测检查器 |
| 旧 run 无 plan | Stage 7/8/9/14 钩子 `update_from_stage` 返回 None，不阻塞 |
| 计划与阶段双真值 | `plan/` 只描述意图；`stage-XX/` 仍是实际产物权威（设计 §8） |

## 6. Review 记录（Step 4）

- V7 原文为「hypothesis 依赖 literature 或 fact」；计划没有 `fact` 节点类型，本批收敛为 **literature**，并在 DESIGN 记录。
- 设计 §9 建议在 Stage 2 由 LLM 生成计划；本批改为确定性派生，属于**范围收敛**，已登记为诚实边界。
- G8b 的版本化、Progress Ledger、懒惰分解不在本批；`replan.max_versions=3` 只作为字段冻结。

## 7. 范围

- 做：schema、12 条校验、plan 存储与事件、Stage 2/7/8/9/14 钩子、21 条测试。
- 不做：重规划、版本 diff、Progress Ledger、ADaPT 懒惰分解、Stage 9 树搜索。

## 8. 诚实边界

- 节点 statement 是抽取式，不是生成式；计划质量受上游 `problem_tree.md` 质量约束。
- Stage 9 的一致性检查只能保证 plan ↔ `exp_plan.yaml` 的字段一致，不保证实验设计本身合理。
- 未在真实 LLM 全流程上验证计划生成率（指标 §11 留给后续批次）。
