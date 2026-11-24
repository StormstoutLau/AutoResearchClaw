---
id: arc-plan-evolution-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-g5-implementation-DESIGN, research-plan-design, arc-master-roadmap]
upstream: null
---

# 调研：G8b 计划演进（P-156）

> **Feature**：P-156。G8b 的唯一实施批：Progress Ledger、版本化重规划、ADaPT 式懒惰分解、Stage 9 局部搜索。
> **性质**：T1 实施批，按总纲记为 **P2**（G6/G7/G8b 均为 P2；P1 已由 G5 收口）。
> **依据**：`docs/research-plan-design.md` §7/§12（该文件在 `.gitignore`，故用行内代码引用）、[总纲 G8b](../../arc-master-roadmap.md#L670-L689)、P-152 G8a 交付。

---

## 1. 问题

G8a 已交付「可校验、可存储、可追溯」的 `ResearchPlan v1`，但没有「演进」能力：

| 面 | 现状 | 缺口 |
|---|---|---|
| Progress Ledger | `plan/ledger.json` 不存在；Stage 15 只看 `analysis.md` | 无法回答「是否完成 / 是否循环 / 是否有进展 / 下一个节点」 |
| 版本化重规划 | `store.py` 固定写 `plan.v1.json`；`update_plan` 原地覆盖 | 无法 version+1、无 diff、无法拒绝原地改计划 |
| 完成节点保护 | 无 | 重规划可能重跑 `done` 节点、重复付费 |
| 目标变更审批 | 无 | 改 `goal` 无需人工批准，不可审计 |
| 懒惰分解 | `derive.py` 一次性按阶段生成节点 | 失败/歧义时无法按需拆分，也缺少「不许一上来全量拆」的闸门 |
| Stage 9 局部搜索 | 无 | 无法在预算内枚举/选择实验候选 |

## 2. 规范回溯（SPEC_PROCESS v1.7.1）

| 规范位置 | 要求 | 本批落点 |
|---|---|---|
| Step 1 调研 | 关键结论 ≥2 独立来源且 ≥1 个 T1；来源标 Layer + 日期 + 版本；失败写降级链 | §5 外部案例 + §6 引用核验/降级链 |
| Step 2 Review | 引用 ID 可解析；不可解析只能标「未验证」 | §6.1 引用核验表 |
| 来源阶梯 | T1 论文/标准/官方文档/源码；T3 社区只用于陷阱 | §5 分层 |
| Step 3 设计 | 每个关键决策写被拒绝的替代方案 + 理由 + 代价 | §7 方案对比 |
| Step 5 实施 | 每个接口写签名 + 回退点；低效排除表非空 | IMPLEMENTATION §4/§5 |
| Step 9 TDD | 先写会失败的测试；记录红→绿 | IMPLEMENTATION §3/§8 |

## 3. 现有代码（已核实）

| 位置 | 事实 |
|---|---|
| `researchclaw/plan/schema.py` | `SCHEMA_ID="research-plan/1"`、`NODE_TYPES` 7 类、`NODE_STATUSES` 5 态、`MAX_NODES=40`、`validate_plan` V1–V12、`seal_plan`/`plan_digest`（`canonical_json`） |
| `researchclaw/plan/store.py` | `PLAN_NAME="plan.v1.json"` 硬编码；`_atomic_write` + `os.replace`；`append_event` 写 `plan_events.jsonl`；`update_plan` 原地覆盖 |
| `researchclaw/plan/derive.py` | Stage 2/7/8/9/14 的确定性构建器；`_next_id`、`_base_node`；`mark_analysis_done` |
| `pipeline/stage_impls/_analysis.py:1163` | `_execute_research_decision` 解析 PROCEED/PIVOT/REFINE，写 `decision_structured.json`，返回 DONE |
| `tools/approvals.py` | `read_approvals`/`is_approved(run_dir, tool)`；缺失/损坏 = 未批准（fail-closed）；`approvals.json` 为唯一放行源 |
| `runtime/event_log.py` | `canonical_json` 是计划 digest 与事件行的规范序列化 |
| `tests/test_research_plan.py` | G8a 21 条用例；断言 `plan/plan.v1.json` 与 `plan_meta.json` |

## 4. 设计输入

| 输入 | 取值 | 依据 |
|---|---|---|
| Q15 `max_versions` | 3（provisional） | P-152 采用；总纲 Q15 |
| Q16 懒惰分解阈值 | 失败 ≥2 次；或歧义；或「已花 ≥50% 预算且 done <30%」 | research-plan-design §5.1/§7.2；本批 provisional |
| 循环判定 | 连续 2 轮同一 `next_node` 且无新增 `done` | Magentic-One Progress Ledger |
| 版本存储 | `plan.v{n}.json` + `index.json` + `plan_events.jsonl` | design §8 |
| 审批源 | `approvals.json` 的 `plan_goal_change` 条目 | 复用既有 fail-closed 机制 |
| 搜索 | 确定性枚举 + 预算上限；不调用 LLM | AI Scientist-v2 只借「预算内搜索」形态 |

## 5. 外部案例（按来源分层）

| # | 来源 | Layer | 日期/版本 | 机制/事实 | 本批借用 | 不借用 |
|---|---|---|---|---|---|---|
| E1 | [Magentic-One（arXiv:2411.04468）](https://arxiv.org/abs/2411.04468) | T1 | v1 / 2024-11 | 外层 Task Ledger + 内层 Progress Ledger；每步自问「完成？循环？有进展？谁做？做什么」 | Progress Ledger 五问与循环检测 | 通用多智能体团队与浏览器工具 |
| E2 | [AutoGen Magentic-One 文档](https://microsoft.github.io/autogen/stable//reference/python/autogen_ext.teams.magentic_one.html) | T1 | stable / 访问 2026-11-25 | `MagenticProgressLedger` 字段：`IsRequestSatisfied` / `IsInLoop` / `IsProgressBeingMade` / `NextSpeaker` / `InstructionOrQuestion` | 字段命名与语义对齐 | 不引入 AutoGen 运行时 |
| E3 | [ADaPT（arXiv:2311.05772）](https://arxiv.org/abs/2311.05772) | T1 | v2 / NAACL 2024 Findings | 「as-needed」：执行失败时才递归拆子任务；能力越弱越需要拆 | 失败/歧义触发的懒惰分解 | 任意深度递归（本批 ≤3） |
| E4 | [AI Scientist-v2（arXiv:2504.08066）](https://arxiv.org/abs/2504.08066) | T1 | v1 / 2025-04 | Agentic Tree Search + experiment manager；每个候选节点执行后回写结果 | Stage 9 预算内候选搜索形态 | 全流程树搜索与并行实验 |
| E5 | [PlanBench（arXiv:2206.10498）](https://arxiv.org/abs/2206.10498) | T1 | v4 | LLM 规划能力不足；含 replanning 评测；必须用确定性校验 | 「规划必须可机械校验」的动机 | 不引入 PDDL 求解器 |
| E6 | [RFC 6902 JSON Patch](https://www.rfc-editor.org/rfc/rfc6902) | T1 | 2013-04 | `add/remove/replace/move/copy/test` 操作与路径语义 | 重规划 diff 的四分类（added/removed/changed/preserved）口径 | 不引入 JSON Patch 运行时 |
| E7 | [jsonpatch.com](https://jsonpatch.com/) | T3 | 访问 2026-11-25 | 社区对 RFC 6902 操作集的整理 | 仅作陷阱对照：diff 必须逐条显式，不能静默原地改 | 不作为规范依据 |

### 5.1 源码锚点

| 项目 | 源码 | 核验状态 | 用途 |
|---|---|---|---|
| AutoGen Magentic-One | [magentic_one 参考页](https://microsoft.github.io/autogen/stable//reference/python/autogen_ext.teams.magentic_one.html) | 文档页已核验；具体 `.py` 行号未抓取 | Progress Ledger 字段 |
| ARC ResearchPlan | [schema.py](../../researchclaw/plan/schema.py) / [store.py](../../researchclaw/plan/store.py) / [derive.py](../../researchclaw/plan/derive.py) | 逐行已读 | 版本存储与校验复用 |
| ARC 审批 | [approvals.py](../../researchclaw/tools/approvals.py) | 逐行已读 | 目标变更审批 fail-closed |

## 6. 引用核验与降级链

### 6.1 引用核验

| 引用 | 核验方式 | 结果 |
|---|---|---|
| arXiv:2411.04468 | WebSearch 命中 arXiv HTML/PDF，标题与摘要一致 | 可解析 |
| arXiv:2311.05772 | WebSearch 命中 arXiv v2 与 ACL Anthology（2024.findings-naacl.264） | 可解析 |
| arXiv:2504.08066 | WebSearch 命中 arXiv 摘要页与 PDF | 可解析 |
| arXiv:2206.10498 | WebSearch 命中 arXiv v4 与 HTML（含 replanning 节） | 可解析 |
| RFC 6902 | WebSearch 命中 rfc-editor.org | 可解析 |
| AutoGen 文档 | WebSearch 命中 microsoft.github.io/autogen stable 参考页 | 可解析 |
| jsonpatch.com | WebSearch 命中 | 可解析（T3） |

### 6.2 降级链

1. arXiv 搜索 MCP 返回空 → 改用 WebSearch 逐条核验标题/摘要（已执行）。
2. 论文全文未逐段抓取 → 只引用摘要/HTML 可见段落，不引用具体页码。
3. AutoGen 源码行号未抓取 → 只引用官方参考页的字段名，不声称具体实现细节。
4. 若后续 CI 无网络 → 本批代码与测试不依赖任何外部 URL；证据只用于设计依据。

## 7. 方案对比

| 决策 | 采用 | 被拒绝的替代 | 理由与代价 |
|---|---|---|---|
| Ledger 计算 | 纯函数，输入 plan + events + previous | LLM 自评进展 | LLM 自评不可复算；纯函数可测、确定性 |
| 循环检测 | 连续 2 轮同 `next_node` 且无新增 `done` | embedding 相似度 | 零新依赖；代价是对「换节点但空转」不敏感 |
| 重规划 | 显式 `replan()` + version+1 + diff | 原地改 `plan.v1.json` | 原地改不可审计；代价是磁盘多存版本 |
| 目标变更 | `approvals.json` 的 `plan_goal_change` 放行 | 配置开关 | 复用 fail-closed 审批源；代价是需人工写审批 |
| 懒惰分解 | `attempts>=2` 或歧义触发 | 规划时一次拆到最细 | ADaPT 证据；代价是首次执行可能多一轮 |
| 局部搜索 | 确定性枚举 + 预算上限 | LLM 生成候选 + 树搜索 | 可复算、零 LLM 成本；代价是搜索空间有限 |

## 8. 风险与边界

| 风险 | 处置 |
|---|---|
| 旧 run 无 `plan/` | 所有钩子 no-op（沿用 G8a 的 `load_plan is None` 语义） |
| 旧 run 只有 `plan.v1.json` 无 index | `load_plan` 回退 `plan.v1.json` |
| `update_plan` 与 replan 版本冲突 | `update_plan` 写当前 index 版本文件，不写死 v1 |
| 目标变更被绕过 | `replan()` 在纯函数层拒绝；审批只从 `approvals.json` 读 |
| 懒惰分解被滥用 | `decompose_node` 要求显式 trigger，且受深度/扇出/节点上限 |
| 搜索超预算 | 逐候选累计，超限即停并标 `exhausted` |
| 循环误判 | 只判「同节点 + 无新增 done」；换节点不判循环 |

## 9. Review 记录（Step 4）

- E1/E2 的字段语义与 E3 的触发条件一致；E4 只借「预算内搜索」，不借全流程树搜索。
- E5 支持「必须确定性校验」，与 G8a V1–V12 一致。
- E6 提供 diff 四分类的规范口径；E7 仅作陷阱对照。
- 未验证项已在 §5.1/§6.1 显式标注。

## 10. 范围

- 交付：`ledger.py`、`replan.py`、`decompose.py`、`search.py`、`store.py` 版本化、Stage 15 ledger 钩子、Stage 9 搜索报告钩子、tests。
- 验收：A8b-1..A8b-4。
- 不做：LLM 自动生成重规划节点、全流程树搜索、G6 模型分层、G7 72h soak。

## 11. 诚实边界

- Q15/Q16 仍为 provisional；本批采用其建议值，不宣称正式裁决。
- Stage 15 只写 ledger 与 `replan_requested` 事件，不自动改计划；重规划由显式 API/人工触发。
- Stage 9 搜索只产出候选报告，不删减 `exp_plan.yaml` 条件，避免破坏 G8a 双向一致性。
