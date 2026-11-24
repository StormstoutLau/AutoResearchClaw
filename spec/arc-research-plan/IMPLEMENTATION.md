---
id: arc-research-plan-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-research-plan-DESIGN]
upstream: null
---

# 实施：ResearchPlan v1 计划对象（P-152 / G8a）

> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **变更面**：4 个新模块 + 4 个阶段实现接入 + 1 个测试文件。

---

## 1. 变更清单

| 文件 | 动作 | 内容 |
|---|---|---|
| `researchclaw/plan/__init__.py` | 新增 | 公开 API 导出 |
| `researchclaw/plan/schema.py` | 新增 | schema 常量、`Violation`、`plan_digest`、`seal_plan`、`validate_plan`（V1–V12） |
| `researchclaw/plan/store.py` | 新增 | 原子写 `plan.v1.json`/`index.json`/`plan_events.jsonl`，`update_from_stage` |
| `researchclaw/plan/derive.py` | 新增 | Stage 2/7/8/9/14 的确定性派生与一致性检查 |
| `researchclaw/pipeline/stage_impls/_topic.py` | 修改 | Stage 2 派生计划、校验、写 `plan_meta.json`，非法即 FAILED |
| `researchclaw/pipeline/stage_impls/_synthesis.py` | 修改 | Stage 7 gaps/unknowns、Stage 8 hypothesis 节点（均告警不阻塞） |
| `researchclaw/pipeline/stage_impls/_experiment_design.py` | 修改 | Stage 9 experiment 节点 + `exp_plan.yaml` 双向检查，不一致即 FAILED |
| `researchclaw/pipeline/stage_impls/_analysis.py` | 修改 | Stage 14 标记 analysis/experiment 状态 |
| `tests/test_research_plan.py` | 新增 | 21 条用例（20 单元 + 1 Stage 2 集成） |

## 2. 读数

```text
$ python -m pytest tests/test_research_plan.py -q
.....................                                                    [100%]
21 passed in 0.30s

$ python -m pytest tests/test_research_plan.py tests/test_rc_stages.py \
    tests/test_stage12_returncode.py tests/test_stage_claim_hooks.py \
    tests/test_stage_events.py tests/test_stage_retries.py \
    tests/test_pipeline_summary_check.py tests/test_rc_novelty.py -q
207 passed in 2.22s

$ python -m pytest tests/test_rc_executor.py tests/test_rc_novelty.py -q
244 passed in 98.52s
```

诚实记录：本批**不是严格 TDD**。先实现纯函数模块（schema/store/derive）并跑通，再补 21 条用例；首轮 20 passed；新增 Stage 2 集成用例首轮失败，原因是测试配置缺 `notifications.channel` 与 `knowledge_base.root`（测试夹具缺陷），补齐后 21 passed。未修改实现迁就测试。

## 3. 实现要点

### 3.1 计划派生

- Stage 2：解析 `problem_tree.md` 的 `## Sub-questions`（编号/项目符号），最多 8 个 question 节点；无解析结果时以 topic 建一个节点。
- Stage 7：解析 `## Gap` 标题与下一行，写入 `unknowns`，新增 1 个 literature 节点 + 每个 gap 一个 question 节点。
- Stage 8：解析 `H1/H2` 或 `## Hypotheses` 列表，最多 5 个 hypothesis 节点，依赖 literature。
- Stage 9：每个 `proposed_methods` 一个 experiment 节点，带 metric/dataset/baseline/method；与 `exp_plan.yaml` 双向检查。
- Stage 14：analysis 节点置 done/failed；有指标时 experiment 节点一并置 done。

### 3.2 存储与摘要

- 每次写入重算 `plan_digest`，写 `plan.v1.json` 与 `index.json`，追加 `plan_events.jsonl`（`plan.created` / `plan.updated`）。
- 原子写（临时文件 + fsync + replace），失败不留下半文件。

### 3.3 失败策略

- Stage 2 校验失败 → `StageStatus.FAILED`，不进入 Stage 3。
- Stage 9 不一致或校验失败 → `StageStatus.FAILED`。
- Stage 7/8/14 的计划更新异常只告警，不影响阶段结果。

## 4. 门禁读数

| 门禁 | 读数 |
|---|---|
| dc_validator（本批 feature） | 0 违规（全仓 148 条存量） |
| grandfather_gate | 0/0/0 |
| step-gate | 5/5 pass |
| verify-anchor | 10 真实 / 0 硬性 / 0 软性 |
| step_enforce | `mode=batch pid=P-152 digest_bound=1` |
| pre-commit | 适用钩子全绿 |
| PR CI | 待推送后核对 |

## 5. 未做与边界

- 未实现重规划、版本 diff、Progress Ledger、ADaPT 懒惰分解、Stage 9 树搜索（G8b）。
- 计划节点是抽取式，不是生成式；质量受上游产物约束。
- Stage 9 的首次一致性检查由构造保证；检查器用独立负向用例验证。
- 未在真实 LLM 全流程上统计计划生成率与分解覆盖率。
