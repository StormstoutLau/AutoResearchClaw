---
id: arc-run-equivalence-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-reuse-plan-IMPLEMENTATION, arc-reuse-verify-IMPLEMENTATION]
upstream: null
---

# 调研：重跑等价性对照实验（P-149）

> **Feature**：P-149。兑现 P-148 §11 遗留「重跑等价性未验证」与 P-147 U-1 的第二档：先定义可机械判定的「等价」，再用确定性双 run 做对照实验。
> **性质**：T1 实施批；单分支、单 PR。
> **结论先行**：① 不比全量日志，也不只看最终产物，而是比较**确定性投影**（阶段序、失败序、工具序、参数哈希序、状态序、产物哈希、双链完整性）；② 易变字段（`run_id`/`ts`/`action_id`/绝对路径前缀）按构造排除；③ 任一侧空 run 或链坏一律 fail-closed；④ 判定器只读，不执行重跑。

## 1. 问题

P-147 能证明「记录的成功路径仍完好」；P-148 能生成「重跑计划」。但没有任何手段回答第三个问题：**这次重跑与原始 run 是否等价**。

真实 LLM 重跑在本仓 CI 不可行：需要密钥、耗时不可控、输出本身非确定性。因此本批先交付**判定器**，并用同一确定性夹具构建两个 run 做对照实验；真实 LLM 重跑登记为手动实验。

## 2. 三种判定口径

| 口径 | 做法 | 问题 |
|---|---|---|
| A 全量日志 diff | 逐行比较 `events.jsonl` / `actions.jsonl` | `run_id`、`ts`、`action_id`、绝对路径、重试次数都易变，必然误报 |
| B 仅最终产物 | 只比较产物哈希 | 漏掉行为差异（阶段顺序、工具选择、失败） |
| **C 确定性投影（采用）** | 阶段序、失败序、工具序、参数哈希序、状态序、产物哈希、双链完整性 | 边界见 §6 |

选择 C 的理由：等价性的最小可判语义是「同样的阶段、用同样的工具与参数、产出同样的内容」，而不是「同样的时间戳」。

## 3. 判据（8 类）

| # | 类别 | 来源 | 比较方式 |
|---|---|---|---|
| 1 | `stage_sequence` | `stage.completed` 事件 | 有序阶段号列表 |
| 2 | `stage_failures` | `stage.failed` 事件 | 有序阶段号列表 |
| 3 | `tool_sequence` | 动作账本 `tool` | 有序列表 |
| 4 | `params_sequence` | 动作账本 `params_sha256` | 有序列表 |
| 5 | `status_sequence` | 动作账本 `status` | 有序列表 |
| 6 | `artifacts` | 动作账本 `outputs` | run 相对路径 → 内容哈希 |
| 7 | `event_chain` | `EventLog.verify_chain` | 两侧均须通过 |
| 8 | `action_chain` | `ActionLedger.verify_chain` | 两侧均须通过 |

`checks` 恒为 8，避免「零检查假绿」。

## 4. 易变字段（按构造排除）

`run_id`、`ts`、动作 UUID、耗时、事件总数、绝对路径前缀、链上的具体哈希值（只比链完整性）、`stage.retried` 的计数。阶段重试折叠为一次 `stage.completed`，重试次数不参与判定。

## 5. 差异分类

`activity` / `stage_sequence` / `stage_failures` / `tool_sequence` / `params_sequence` / `status_sequence` / `artifacts` / `event_chain` / `action_chain`。每种差异带左侧、右侧读数，报告可直接 JSON 序列化。

## 6. 风险与边界

| 风险 | 处理 |
|---|---|
| 两侧都空被误判等价 | fail-closed：空 run 记 `activity` 差异，判不等价 |
| 一侧链坏导致比较失真 | 链坏直接判不等价，其余投影仍照常报告 |
| 产物路径为绝对路径 | 相对化到 run 目录；目录外退化为 basename |
| 同一路径被多次写入 | 按账本中最后一次记录的哈希比较（实现简单且可解释） |
| 未记入账本的产物 | 不在判定范围；判定器只信任 `actions.jsonl` 的 `outputs` |

## 7. Review 记录（Step 4）

- 对照 P-147：`verify` 是 manifest ↔ run；本批是 run ↔ run，职责不重叠。
- 对照 P-148：`plan` 生成命令；本批只判定两个已完成 run，不重跑。
- 修正一处：初稿把「事件总数」列为判据，会因重试与滚动分段误报，删除。
- 修正一处：初稿 artifacts 直接比较账本原始路径，Windows 绝对路径必然不等，改为 run 相对化 + basename 回退。

## 8. 范围

- 做：`compare_runs` 判定器、`runs compare` CLI、16 条用例（13 判定 + 3 CLI）、确定性双 run 对照实验。
- 不做：真实 LLM 重跑、prompt 重放、自动修复差异、跨机器环境对比、耗时/成本比较。

## 9. 诚实边界

- 本批的「对照实验」是**确定性夹具双 run**，证明判定器能识别等价与差异，不等于真实 pipeline 重跑已被验证。
- 判定器证明的是「投影一致」，不是「因果一致」：两个 run 可能在未记录的维度上不同。
- 真实 LLM 重跑仍需人工执行，登记为遗留项。
