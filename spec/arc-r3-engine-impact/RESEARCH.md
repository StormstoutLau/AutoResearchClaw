---
id: arc-r3-engine-impact-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-belief-revision-propagation-RESEARCH, arc-master-roadmap]
upstream: arc-belief-revision-propagation-RESEARCH
---

# 调研：R-3 重型方案的影响面与可控性（Saga / Temporal / DAG / 自动影响闭包）

> **定位**：本批不把 R-3 视为“拒绝项”，而是拆成 R-3a/R-3b/R-3c，分别评估影响面是否可控。
> **输入**：P-014 的现状审计与外部锚点；本批补充引擎级影响面分析。
> **状态**：verified（概念与影响面分析；未做引擎实测）

## 1. 调研目标

1. Saga、Temporal、DAG 引擎、自动影响闭包各自要改什么？改哪里？
2. 影响面（代码/数据/运行/运维/安全/成本/兼容/失败模式）是否可控？
3. 哪些能力可以“不引入引擎”先落地？哪些必须引擎？
4. 若未来引入引擎，触发条件与 kill criteria 是什么？

## 2. 方法

| 工具 | 用途 | 查询/来源 |
|---|---|---|
| Read | 当前管线结构、回退、checkpoint、stage 契约 | `runner.py`、`stages.py`、`contracts.py` |
| WebFetch | 官方工程模式 | Azure Saga、Temporal Event History |
| WebSearch | 学术/社区锚点 | Differential Dataflow、AGM、LATS/SWE-Search |
| 外部文档 | 同构分析 | `F:\Spec_Workflow\spec\academic-writing-workflow` §12-§13 |

## 3. R-3 的四个组件

| 组件 | 要解决的问题 | 最小形态 | 重型形态 |
|---|---|---|---|
| C-1 Saga/补偿 | 回退时撤销已完成的副作用 | 本地产物版本化 + 显式 pivot 标记 | 分布式补偿事务、补偿日志、重试/幂等 |
| C-2 Durable execution | 崩溃后从事件历史恢复，不重做副作用 | append-only 事件文件 + 重放 | Temporal Server + Worker + Event History |
| C-3 DAG 调度 | 按依赖图选择性重算/并行 | 声明式依赖清单 + 拓扑排序 | Airflow/Dagster/Prefect 等调度器 |
| C-4 自动影响闭包 | 从被证伪前提推导需重跑的阶段 | 显式依赖 + 反向可达 + 保守过近似 | 自动依赖抽取 + 动态图 + 最小补丁集 |

## 4. 当前前置条件

| 前置 | 现状 | 证据 |
|---|---|---|
| 事件链/重放 | **没有** `stage_events.jsonl`；G1 未实现 | 全仓 grep 零命中 |
| 依赖元数据 | 只有 stage 输入/输出契约（`contracts.py`）与 markdown 链接 | `pipeline/contracts.py` |
| 副作用清单 | 无补偿注册表；外部副作用（SSH/Colab/Docker/MCP/通知）无统一接口 | `experiment/`、`adapters.py` |
| 内容哈希 | 无 artifact digest/inputs_digest | 全仓零命中 |
| pivot 标记 | 只有 `MAX_DECISION_PIVOTS` 计数，无“不可回退点”标记 | `stages.py:134` |

## 5. 影响面矩阵

### 5.1 代码与数据

| 组件 | 代码触点 | 数据/产物 | 兼容性 |
|---|---|---|---|
| C-1 Saga | `runner.py`、`stages.py`、各 stage 的副作用点、`adapters.py`、`experiment/*` | 补偿日志、pivot 标记、旧版本目录 | 中：需要每个 stage 声明补偿动作 |
| C-2 Temporal | 整个 `execute_pipeline`/`execute_stage` 重构为 workflow/activity；worker、server、SDK | Event History、持久化 DB、任务队列 | 低：本地/CI/CLI 都要改 |
| C-3 DAG | `STAGE_SEQUENCE` 改为图；调度器、并发、取消、HITL gate | 依赖图、拓扑序、运行计划 | 中高：动态 PIVOT 会改变图 |
| C-4 闭包 | 依赖清单、artifact digest、反向可达、影响计划 | `impact_plan.json`、`dependencies.yaml` | 中：先声明式，可渐进 |

### 5.2 运行与运维

| 维度 | C-1 | C-2 | C-3 | C-4 |
|---|---|---|---|---|
| 新增服务 | 无 | **Temporal Server + DB + Worker** | 可选调度器/队列 | 无 |
| 本地开发 | 低影响 | 高：需本地 server/dev worker | 中 | 低 |
| CI | 中：补偿测试 | 高：workflow 测试环境 | 中 | 低 |
| 可观测性 | 补偿日志 | Event History + UI | DAG 视图 | impact plan |
| 升级/迁移 | 低 | 高：SDK/协议版本、确定性约束 | 中 | 低 |
| 故障恢复 | 依赖现有 checkpoint | 强（重放） | 中 | 无 |

### 5.3 安全、成本与失败模式

| 维度 | 风险 | 可控性 |
|---|---|---|
| 安全 | 补偿动作可能调用外部 API/SSH/云资源，需凭据与审计 | 中：必须 allowlist + 人工确认 |
| 成本 | 自动闭包可能过度重跑（token/算力） | 中：保守过近似 + 预算上限 |
| 失败模式 | 部分补偿、非幂等副作用、补偿顺序错误 | 低-中：需幂等键与补偿契约 |
| 失败模式 | Temporal 非确定性代码/版本不兼容 | 低：workflow 版本化纪律 |
| 失败模式 | 依赖图不完整导致漏算（陈旧结果） | 高：保守过近似可缓解 |
| 失败模式 | 动态图/LLM 输出导致图漂移 | 低：先声明式静态图 |

## 6. 外部锚点

| # | 锚点 | 结论 | 验证 |
|---|---|---|---|
| X-1 | Azure Saga | 本地事务 + 补偿；pivot 后不可补偿；补偿是语义相反动作 | ✅ 已抓取 |
| X-2 | Temporal Event History | append-only 事件历史 + 重放；非确定性副作用移出可重放控制流 | ✅ 已抓取 |
| X-3 | Differential Dataflow (CIDR 2013) | 增量计算/Z-set，适合“输入变化 → 输出增量更新” | ✅ 标题/摘要命中 |
| X-4 | OxyMake/DANTE（外部调研书目） | 内容寻址缓存键替代 mtime；避免 phantom/missed re-run | ⚠️ 二手 |
| X-5 | W3C PROV | Entity/Activity/Agent 血缘标准 | ⚠️ 标准页存在，未抓正文 |
| X-6 | AGM belief revision (1985) | 信念修正的公理框架；收缩/修正而非删除历史 | ✅ 综述命中 |
| X-7 | Doyle TMS (1979) | 真值维护系统：依赖网络 + 理由记录 | ⚠️ 二手 |
| X-8 | LATS / SWE-Search | MCTS/树搜索支持回溯与替代方案 | ✅ 标题/摘要命中 |
| X-9 | MAST | 验证/终止类失败是主要类别 | ✅ P-011 已验证 |
| X-10 | 外部 academic-writing-workflow §12-§13 | 四层回退模式、最小回改集、外部过期、freeze/kill | ⚠️ 二手（同构调研） |

## 7. 可控性判定

| 方案 | 影响面 | 可控性 | 结论 |
|---|---|---|---|
| 完整 Temporal | 运行时/运维/CI/本地开发/所有 stage | **低** | 不在当前约束内直接引入 |
| 完整 Saga | 所有副作用点 + 外部适配器 | **中低** | 仅限本地产物可做；外部副作用需人工 |
| 完整 DAG 引擎 | 调度器/并发/动态图 | **低** | 依赖元数据不足，先不做 |
| 自动影响闭包（全自动） | 依赖抽取 + 动态图 | **低** | 易漏算/误算 |
| R-3a：依赖清单 + 内容哈希 + 保守闭包 | stage 契约 + artifact digest | **高** | 可先做，零引擎 |
| R-3b：补偿注册表 + pivot 标记（本地） | 各 stage 的本地产物 | **中高** | 可做，外部副作用除外 |
| R-3c：引擎化（Temporal/Saga） | 全链路 + 运维 | **条件可控** | 仅当 R-3a/b 不足且触发条件满足 |

## 8. 分解建议

- **R-3a（先做）**：声明式 `dependencies.yaml` + `artifact_manifest.json`（digest）+ `impact_plan.json`（反向可达、保守过近似、人工确认）。不引入引擎。
- **R-3b（按需）**：`compensation_registry` + pivot 标记；只覆盖本地文件/目录/进程，外部 SSH/Colab/MCP 副作用标为“人工补偿”。
- **R-3c（条件引入）**：把 `execute_pipeline` 包在 `WorkflowRuntime` 适配器后；Temporal/Saga 只是适配器实现。触发条件（任一）：
  1. 并发 run ≥ 3 或需要多 worker；
  2. 崩溃恢复 SLA 要求分钟级自动续跑；
  3. 外部副作用补偿成为常态（>10 次/周）；
  4. 现有文件型 checkpoint 在压测中出现不可恢复损坏；
  5. 有明确运维预算与 owner。

## 9. 结论

**R-3 不再“显式拒绝”，改为“分层接受 + 引擎条件引入”。** 完整 Saga/Temporal/DAG 在当前零依赖、单机文件型管线的约束下影响面不可控；但 R-3a/R-3b 可控且能覆盖大部分回退/传播需求。R-3c 保留为有触发条件的候选，而不是永久否决。

## 10. 未决项

- **U-1 依赖清单的完整性**：判据=impact plan 与实际重跑集合一致；触发=首次自动闭包漏算/多算；倾向=声明式 + 人工确认；E1。
- **U-2 补偿边界**：判据=本地产物可自动补偿、外部副作用有明确人工标记；触发=R-3b 实施；倾向=只做本地；E1。
- **U-3 引擎触发阈值**：判据=并发/SLA/外部副作用/运维预算四项可机械判定；触发=R-3c 评审；倾向=按 §8 阈值；E1。
- **U-4 引擎适配器边界**：判据=`WorkflowRuntime` 接口可替换、不泄漏 Temporal 类型到 stage；触发=R-3c 设计；倾向=窄接口；E1。
- **U-5 成本模型**：判据=闭包重跑的 token/算力/存储可预估；触发=首次 R-3a 实测；倾向=预算上限 + 人工确认；E1。
- **U-6 kill criteria**：判据=引擎引入后 2 个迭代无净收益即回退；触发=R-3c 实施；倾向=预先写定；E1。

## 11. 参考文献

1. Microsoft Azure. *Saga distributed transactions pattern*. https://learn.microsoft.com/azure/architecture/patterns/saga
2. Temporal. *Events and Event History*. https://docs.temporal.io/workflow-execution/event
3. McSherry, F. et al. *Differential Dataflow*. CIDR 2013.
4. Alchourrón, C., Gärdenfors, P., Makinson, D. *On the Logic of Theory Change*. Journal of Symbolic Logic, 1985.
5. Doyle, J. *A Truth Maintenance System*. Artificial Intelligence, 1979.
6. W3C. *PROV-Overview*. https://www.w3.org/TR/prov-overview/
7. LATS. arXiv:2310.04406；SWE-Search. arXiv:2410.20285.
8. MAST. arXiv:2503.13657.
9. `F:\Spec_Workflow\spec\academic-writing-workflow\RESEARCH.md` §12-§13（二手同构调研）。
