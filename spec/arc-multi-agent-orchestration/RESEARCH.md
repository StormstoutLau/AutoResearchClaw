---
id: arc-multi-agent-orchestration-RESEARCH
type: design
version: 0.1
status: draft
date: 2026-11-27
depends: [arc-stage10-generation-budget-contract, arc-stage10-repair-quality, arc-runtime-progress-heartbeat]
upstream: arc-master-roadmap
---

# 调研（草案）：多模型 / 多工作站 Agent 编排（B-37）

> **状态**：仅立项登记。DESIGN / IMPLEMENTATION / CHECKLIST 待实施时补齐。
> **主文档**：[多模型 / 多工作站 Agent 编排的可行性与路线](../../docs/arc-multi-agent-orchestration-20261127.md)（v0.1，含外部来源与代码锚点）。

## 1. 触发与问题

Stage 10 三次 attempt 连续失败（运行 I：12 541.6 s、`exit_code=75`），单端点单调用链的收益已接近上限。问题：**能否用多 LLM API 或 ACP 调其他工作站的 agent CLI，缩短科研推理的墙钟时间/提高成功率**，以及在 ARC 的线性产物语义下哪些拓扑真正可行。

## 2. 已核事实（本地）

| # | 事实 | 锚点 |
|---|---|---|
| L-1 | 多模型能力已存在但**顺序执行**：`debate` 逐角色、`tournament` 逐候选 | [debate.py](../../researchclaw/pipeline/debate.py)、[tournament.py](../../researchclaw/pipeline/tournament.py) |
| L-2 | 唯一业务级并行是 PRM 多票 judge | [prm_gate.py L176-L204](../../researchclaw/metaclaw_bridge/prm_gate.py#L176-L204) |
| L-3 | ACP 客户端是「整管线 LLM 后端」，`max_turns=1`，无会话池 | [acp_client.py](../../researchclaw/llm/acp_client.py) |
| L-4 | CLI Agent（claude_code / codex）只接 Stage 10/13，失败回退 | [config.py L592-L612](../../researchclaw/config.py#L592-L612)、[_code_generation.py L650-L714](../../researchclaw/pipeline/stage_impls/_code_generation.py#L650-L714) |
| L-5 | 独立 reviewer 模型已可配置（破解生成者=评审者） | [config.py L213-L224](../../researchclaw/config.py#L213-L224) |
| L-6 | 心跳/步骤账本/trace 均为**单分支**语义 | [runtime/progress.py](../../researchclaw/runtime/progress.py)、[step_journal.py](../../researchclaw/pipeline/step_journal.py)、[repair_trace.py](../../researchclaw/pipeline/repair_trace.py) |
| L-7 | 远端算力只用于实验执行（`ssh_remote` 沙箱） | [config.py L632](../../researchclaw/config.py#L632) |

## 3. 已核事实（外部）

- ACP v2（2026-11-20 Preview）把 **subagents（child sessions）、background work、replay、idempotencyKey** 纳入基线；remote transport 与 steering 未定。
- CLI agent 的非交互形态成熟：`claude -p`、`codex exec --json`、`gemini -p --output-format json`，均有沙箱/审批约束与结构化输出。
- 学术：AI Scientist-v2（树搜索）、Agent Laboratory（角色分工）、AI co-scientist（generate-debate-evolve）、AgentRxiv（共享成果）、multi-agent debate 及其失败模式、MoA、test-time compute scaling、RouteLLM/FrugalGPT/AgentRouter 成本路由。
- 详见主文档 §3 与 §8 来源清单。

## 4. 结论与分级

1. **收益取决于可判定选择器**：ARC 已有三层判据（`validate_code` → 沙箱 → 符号契约/证据门），因此「扇出 + 判据筛选」最匹配。
2. **并发不解决当前 repair 截断**：那是单次调用预算与错误闭环问题（B-36 P1/P2 的领域）。
3. 建议分级：
   - **P0** Stage 10 模块级 best-of-2（默认关，仅在有判据时启用）；
   - **P1** 跨站路由（机械→A/C、核心→B）+ 独立 reviewer 恒成立；
   - **P2** 外部 agent 分支（CLI / ACP）+ `branch_id` 观测；
   - **P3** 并行化现有 debate/tournament（先 Stage 8/9）。
4. 前置：分支维度必须进入 `steps.jsonl` / `heartbeat.json` / `repair_trace.jsonl`。
5. **不做**：全局 MoA、无判据 N 倍采样、把 ACP 当阶段间协议、多 agent 自由对话自治循环。

## 5. 待实施时的验收口径（草案）

- P0：同一 `data.py` fixture「至少一版通过校验」比例、单模块 wall-clock 与成本上限、无判据不触发。
- P1：机械模块成本降幅 ≥30% 且失败率不升；`reviewer != generator` 恒成立。
- P2：子会话可按 `branch_id` 追溯；超时/预算可中断；失败可回退且留证据。
- P3：Stage 8/9 质量分不降、wall-clock 下降。

## 6. 已知边界

- ACP v2 仍 Preview，接口可能小幅破坏性变更。
- CLI agent 的 token/时序不可预测，需要硬预算门。
- 跨站路由依赖三站端点可用性（A/B/C），且需成本归因。
- 本批不改代码；P0 实施前需先补分支可观测（属 B-31b/B-36 的扩展）。
