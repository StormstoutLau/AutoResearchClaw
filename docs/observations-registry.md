# 观察项登记（G7 复审 backlog）

---
id: observations-registry
type: design
version: 1.1
status: active
date: 2026-11-25
depends: [arc-g7-soak-review-20261125, arc-g7-orchestration-review-20261125, arc-g7-review-fixes-review-20261125, arc-g7-drift-guard-review-20261125]
upstream: arc-master-roadmap
---

> **用途**：把 P-161 / P-163 / P-165 / P-168 四次复审的 O 表与批次自审（ADD 审计）发现集中为**单一可追踪 backlog**，避免观察项散落在各报告里无人承接。
> **状态词表**：`open`（已识别未解决）/ `resolved`（已修）/ `deferred`（明确不修，附理由）。
> **纪律**：本表只登记，不承诺修复；承接时另开 P 批次，并在此表回填 `resolved` 或 `deferred`。
> **优先级**：`high` = 有覆盖缺口或可能影响验收判据；`medium` = 语义/口径风险；`low` = 可读性/数据卫生。
> **修订**：v1.1（2026-11-25，P-169 审计批：补登 P-162/P-167 自审 P3、扩 O-161-4 适用面、新增未决项索引与 D 表关闭记录）。

## 1. 登记表

| ID | 来源 | 观察 | 优先级 | 触发条件 | 建议承接 | 状态 | 证据锚点 |
|---|---|---|---|---|---|---|---|
| O-161-1 | P-161 O-1 | `cursor_mismatch` 在静态日志上按构造恒等（cursor 与 expected 同源 `read_all`），真实价值仅是检出验证期间并发追加/改写 | medium | 引入并发写者或在线校验时 | 下次 soak 批次 | open | [arc-g7-soak-review-20261125.md §3](arc-g7-soak-review-20261125.md) |
| O-161-2 | P-161 O-2 | `EventLog.count` 语义由「active 可读行数」变为「历史最高 seq」，动机是重启后配额不重置；生产代码零消费点 | low | 新增 count 消费者时 | 文档批次 | open | 同上 |
| O-161-3 | P-161 O-3 | 对已完成 run 指定小于终态的 `inject_at_stages`，实际杀点=终态阶段，注入语义漂移 | medium | 在已完成 run 上做注入演练前 | 下次 soak 批次 | open | 同上 |
| O-161-4 | P-161 O-4 | `specwf-p160` session 的 ts 为补写估计值，CONSOLE 时间线排序可能失真（同模式亦适用于 P-161/163/165/168 复审 session，均为登记批一次性补写） | low | 重建时间线/审计排序时 | 文档批次 | open | 同上 |
| O-161-5 | P-161 O-5 | CLI `soak run --inject-at-stages` 默认 `"3,7,11"` 是破坏性默认（默认即注入硬杀），文档未明示 | medium | 用户首次跑 soak 前 | CLI/文档批次 | open | 同上 |
| O-163-1 | P-163 O-1 | `ADAPTERS` 为普通 dict（可变绑定），J-6「无模块级可变注册表」靠约定维持 | low | 新增插件/并行测试前 | orchestration 批次 | open | [arc-g7-orchestration-review-20261125.md §4](arc-g7-orchestration-review-20261125.md) |
| O-163-2 | P-163 O-2 | `SingleShotAdapter` 全程不调 `check_wall`；gold 仅层级间检查，单层执行中 wall 预算为软上限 | medium | 接真实 LLM/长任务前 | orchestration 批次 | open | 同上 |
| O-163-3 | P-163 O-3 | `_score_delegations` 的 OB-3 只检查每个 subgoal 的 `items[0]`，重复委派上的虚假 `parallel_with` 不被检查 | medium | 增加重复委派 fixture 时 | orchestration 批次 | open | 同上 |
| O-163-4 | P-163 O-4 | `keep_with_flag` 聚合策略在 15 任务中零覆盖（全部 `exclude`），分支零测试 | medium | 新增保留失效行任务时 | orchestration 批次 | open | 同上 |
| O-163-5 | P-163 O-5 | `usage_from_trace.wall_seconds` 含编排开销；`llm_calls=workers+2` 硬编码，dummy 自报 0 与反算 2 不一致（judge 不校验） | low | 接入真实计费口径时 | orchestration 批次 | open | 同上 |
| O-163-6 | P-163 O-6 | 能力错配（worker id 不存在）→ 委派 0 但总分 8，不门控；与 DESIGN §5.1 一致但威慑弱于 OB-3 | medium | 评估是否升级门控前 | DESIGN 修订批 | open | 同上 |
| O-165-1 | P-165 O-1 | 偏移链对首条可读事件的 `prev_sha256` 本质不可验（真值随被删段消失），零 prev 检查只拦截懒惰伪造 | low | 归档级验证需求出现时 | 文档批次 | open | [arc-g7-review-fixes-review-20261125.md §4](arc-g7-review-fixes-review-20261125.md) |
| O-165-2 | P-165 O-2 | 失败工件 token 语义双轨：trace 存在时取已成功计费之和，trace 缺失时合成 `exc.observed`；混合态未测试 | low | 接真实计费/部分工件时 | orchestration 批次 | open | 同上 |
| **O-165-3** | P-165 O-3 | **覆盖缺口**：CHECKLIST E-3 宣称 workers/wall/depth 均落工件，但提交的 T07 只测 workers；wall/depth 由复审探针补证，未固化回归 | **high** | 下次触碰 orchestration 时 | 下个 orchestration 批次 | open | 同上 |
| O-165-4 | P-165 O-4 | 摘要尾绑定只在 `events_summary.json` 存在时生效；soak verifier 不产摘要，偏移链在无摘要 run 上无尾闭包 | low | 引入摘要生产者时 | 文档批次 | open | 同上 |
| O-165-5 | P-165 O-5 | POSIX 真路径（真实子进程+真实 killpg）无提交测试；CI Linux 的 fake worker 无孙进程 | medium | A7-2 多 run 并发落地时 | A7-2 批次 | open | 同上 |
| **O-165-6** | P-165 O-6 | `validate_task` 校验 `max_workers ≥ 最宽层` 但**未校验** `max_depth ≥ 层数`；配错会使 gold 永久 budget_exceeded → OB-1 红 | **high** | 下次触碰任务语料时 | 下个 orchestration 批次 | open | 同上 |
| O-168-1 | P-168 O-1 | agent-mode requirements 路径的漂移接线无测试覆盖（集成用例只走标准决策路径）；代码读确认 `_analysis.py` L1176-1193 接线正确 | medium | 下次触碰 Stage 15 时 | 下次 Stage 15 批次 | open | [arc-g7-drift-guard-review-20261125.md §4](arc-g7-drift-guard-review-20261125.md) |
| O-168-2 | P-168 O-2 | agent 路径 drift PAUSE 时早退于 `requirements_verdict.json` 写出，verdict 仅存于 decision_structured.json | low | 下游依赖 verdict 文件时 | 下次 Stage 15 批次 | open | 同上 |
| O-168-3 | P-168 O-3 | p_only 分句要求 `。！？` 后有空白；无空格中文文本整段成单句 → `p_only_ratio` 恒 0（DESIGN D-4 已声明的限制，探针具体化） | medium | 中文 run 实际使用前 | 下次 drift 批次 | open | 同上 |
| O-168-4 | P-168 O-4 | `_read_prior` 捕获全部异常返回空串 → 接线错误会静默降级为 insufficient_inputs WARN | medium | Stage 15 报告异常偏低时 | 下次 drift 批次 | open | 同上 |
| O-162-1 | P-162 CHECKLIST §8.7 P3-1（批次自审） | C 类 gold 恰为 8/9（成本维 2），贴阈值；未来成本分档调整可能使 OB-1 的 C 类阈值失效 | low | 调整成本分档或 C 类阈值时 | orchestration 批次 | open | [../spec/arc-g7-orchestration/CHECKLIST.md §8.7](../spec/arc-g7-orchestration/CHECKLIST.md) |
| O-162-2 | P-162 CHECKLIST §8.7 P3-2（批次自审） | single_shot 在 L1..L3 恰为 7/12，贴 OB-1 上限；负向控制裕度小 | low | 增删 L 类任务或调 single_shot 行为时 | orchestration 批次 | open | 同上 |
| O-167-1 | P-167 CHECKLIST §9 P3（批次自审） | 词面后端语义分辨力有限（只抓明显跑题；O-168-3 的 CJK 分句是其子集）——DESIGN §8 已声明为能力边界，作为持续风险入册 | medium | 接真实语义后端（embed_fn）前 | drift 语义后端批次 | open | [../spec/arc-g7-drift-guard/CHECKLIST.md §9](../spec/arc-g7-drift-guard/CHECKLIST.md) |

## 2. 承接规则

1. **high 优先**：O-165-3 / O-165-6 在下一次触碰 `experiments/arc_bench/orchestration/` 的批次中必须二选一——修复并回填，或写明 `deferred` 理由。
2. **不夹带**：观察项不得为了"顺手修"而塞进无关批次；承接必须在 PROGRESS 行显式引用本表 ID。
3. **状态回填**：修复批合并后，在本表把对应行改为 `resolved` 并附 PR/commit；明确不修的改 `deferred` 并写一句理由。
4. **证据**：每条保持可追溯的来源链接；新增观察项按 `<来源>-<序号>` 编号追加。

## 2.5 未决项索引（DESIGN/RESEARCH 层 open 项）

> 观察项之外，各批次设计文档还留有带触发条件的未决项；此处集中索引，防止散落。

| ID | 来源 | 内容 | 触发条件 | 锚点 |
|---|---|---|---|---|
| U-162-6 | P-162 DESIGN §11 | `run_baseline.py` 字面 OB-2 与 F-1/F-2 修复（五域 topic 加载 + 通用 adapter/judge 分派） | 下一次 ARC-Bench runner 修复批 | [../spec/arc-g7-orchestration/DESIGN.md §11](../spec/arc-g7-orchestration/DESIGN.md) |
| U-162-7 | P-162 DESIGN §11 | LLM judge 语义残差校准（≥30 条人工标注一致率）；本段 residual 默认关闭不产读数 | 首次接真实 LLM judge 前 | 同上 |
| U-167-5 | P-167 RESEARCH §4 | 漂移阈值校准（≥30 条人工标注上报告 PAUSE/WARN 精确率/召回率）；当前阈值为经验初值 | 首次接入真实运行前 | [../spec/arc-g7-drift-guard/RESEARCH.md §4](../spec/arc-g7-drift-guard/RESEARCH.md) |

## 2.6 D 表关闭记录

| 来源缺陷 | 处置 | 证据 |
|---|---|---|
| P-161 D-1（retention 逃生舱） | resolved by P-164 | PR #45（squash `992d6c1`），`verify_chain(start_seq)` + verifier 起点偏移 |
| P-161 D-2（POSIX 进程树） | resolved by P-164 | 同上，`start_new_session` + killpg 组长守卫 |
| P-161 D-3（死代码） | resolved by P-164 | 同上，重复 is_dir/killed/mtime 清零 |
| P-163 D-1（真实溢出零工件） | resolved by P-164 | 同上，`_write_budget_failure` |
| P-163 D-2（P-162 行读数陈旧） | resolved by P-163 登记批 | PR #44 内订正（44/45 → 45/45） |
| P-165 D-1..D-3 | 无（复审结论 0 缺陷） | [arc-g7-review-fixes-review-20261125.md](arc-g7-review-fixes-review-20261125.md) |
| P-168 D-1..D-3 | 无（复审结论 0 缺陷） | [arc-g7-drift-guard-review-20261125.md](arc-g7-drift-guard-review-20261125.md) |

## 3. 本批范围声明

- 本表由 P-167 批次先行登记（Layer-0），P-168 追加 O-168-*，P-169 审计批补登自审发现并新增索引；均不改变代码/门禁。
- P-167 的漂移护栏（FA-1..FA-3）与 O 表无依赖关系；O-165-3/O-165-6 仍待下个 orchestration 批次承接。
