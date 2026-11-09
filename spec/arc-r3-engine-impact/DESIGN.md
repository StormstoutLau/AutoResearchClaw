---
id: arc-r3-engine-impact-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-r3-engine-impact-RESEARCH]
upstream: arc-r3-engine-impact-RESEARCH
---

# 设计：R-3 分层接受与引擎条件引入

> 输入：[RESEARCH.md](RESEARCH.md) §7-§9。目标：把“是否引入引擎”从二元拒绝改为可验证的分层决策。

## 1. 设计不变量

1. 先 R-3a/R-3b，后 R-3c；引擎不是第一选择。
2. 引擎必须藏在 `WorkflowRuntime` 接口后，stage 代码不得 import Temporal/Saga 类型。
3. 自动影响闭包必须保守过近似 + 人工确认；禁止全自动静默重跑。
4. 每次引擎化必须有预写 kill criteria 与成本预算。
5. 不改变 `provider=llm` 的默认路径与现有阶段契约。

## 2. 决策表

| # | 决策 | 选择 | 被拒绝的替代 | 理由 |
|---|---|---|---|---|
| D-1 | R-3 定位 | 分层接受：R-3a/b 可做，R-3c 条件引入 | 永久拒绝 / 立即全量引入 | 影响面差异大，需按能力拆分 |
| D-2 | 依赖元数据 | `dependencies.yaml` + `artifact_manifest.json`（digest） | 从 LLM 输出自动抽取 | 自动抽取不可靠 |
| D-3 | 影响闭包 | 反向可达 + 保守过近似 + 人工确认 | 全自动最小闭包 | 漏算比多算更危险；先保守 |
| D-4 | 补偿 | 只覆盖本地文件/目录/进程；外部副作用人工标记 | 分布式补偿事务 | 外部适配器无统一幂等契约 |
| D-5 | pivot 标记 | 新增 `pivot: true`（提交/投稿/外部副作用后） | 只靠轮次计数 | 需要显式不可回退点 |
| D-6 | 引擎边界 | `WorkflowRuntime` 适配器（local/none、Temporal、Saga） | 直接在 `runner.py` 调 Temporal SDK | 防锁死、可回退 |
| D-7 | 引擎触发 | 并发≥3 / 分钟级恢复 SLA / 外部补偿>10 次周 / checkpoint 损坏 / 有运维预算 | 按“感觉需要”引入 | 触发必须可机械判定 |
| D-8 | kill criteria | 引擎引入后 2 个迭代无净收益 → 回退 local runtime | 无限期维持 | 防 zombie infrastructure |
| D-9 | 本批范围 | 只写分析，不写代码 | 立即实现 R-3a | 需先裁决触发阈值 |

## 3. 接口

### 3.1 依赖清单

```yaml
# dependencies.yaml（每个 stage 声明）
stage: 10
inputs:
  - artifact: stage-09/exp_plan.yaml
    digest: sha256:...
  - artifact: stage-08/hypotheses.md
    digest: sha256:...
outputs:
  - artifact: stage-10/experiment/main.py
    digest: sha256:...
```

### 3.2 影响计划

```json
{
  "trigger": "external-review",
  "changed_nodes": ["claim-3"],
  "impact_set": ["stage-17", "stage-20"],
  "conservative": true,
  "requires_human_confirm": true,
  "estimated_cost_usd": 0.42
}
```

### 3.3 补偿注册表

```yaml
compensations:
  - action: "restore_stage_version"
    scope: "stage-10"
    kind: "local"
  - action: "mark_external_side_effect"
    scope: "ssh_remote"
    kind: "manual"
```

### 3.4 运行时适配器

```python
class WorkflowRuntime(Protocol):
    def run(self, plan: RunPlan) -> RunResult: ...
    def signal(self, run_id: str, event: str, payload: dict) -> None: ...
    def query(self, run_id: str, key: str) -> Any: ...
```

本地实现 = 现有 `execute_pipeline`；Temporal/Saga 实现只在 R-3c 评估。

## 4. 采用门槛（R-3c）

| 条件 | 机械判定 | 当前值 |
|---|---|---|
| 并发 run | `active_runs >= 3` | 1 |
| 恢复 SLA | 崩溃到续跑 < 5 min | 未测 |
| 外部补偿频率 | >10 次/周 | 未统计 |
| checkpoint 损坏 | 压测出现不可恢复损坏 | 未测 |
| 运维预算 | 有 owner + 预算 | 无 |

**结论**：当前五项均未满足，R-3c 不启动；R-3a/b 可先做。

## 5. 被拒绝的方案

| 方案 | 拒绝理由 |
|---|---|
| 立即引入 Temporal | 运维/CI/本地开发影响面大，触发条件未满足 |
| 立即做全量 DAG 自动闭包 | 依赖元数据不足，漏算风险高 |
| 永久拒绝引擎 | 与用户要求不符；保留条件引入 |
| 把引擎类型泄漏到 stage | 锁死实现，违 D-6 |

## 6. 影响与回滚

- R-3a/b 新增文件：`dependencies.yaml`、`artifact_manifest.json`、`impact_plan.json`、`compensation_registry.yaml`、`pivot` 标记。
- 默认路径：不启用时行为不变。
- 回滚：删除新增文件/标记；不改旧 stage 产物。
- R-3c：适配器可切回 local；Temporal 侧数据可丢弃，不影响文件型 run。

## 7. 测试策略（未来实施）

1. 依赖清单：每个 stage 的输入/输出 digest 可重算。
2. 影响闭包：变更一个 artifact → impact set 包含所有下游；无漏算。
3. 保守性：图不完整时默认扩大到相邻 stage，并标 `requires_human_confirm`。
4. 补偿：本地产物可恢复；外部副作用有 manual 标记。
5. pivot：标记后拒绝自动回退，要求人工确认。
6. 适配器：local runtime 与 Temporal runtime 通过同一 contract test。

## 8. 未决项

沿用 [RESEARCH.md](RESEARCH.md) §10 的 U-1..U-6。
