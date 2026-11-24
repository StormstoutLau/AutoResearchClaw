---
id: arc-output-fallback-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-node-equivalence-CHECKLIST]
upstream: null
---

# 调研：零产物账本的回退（P-151）

> **Feature**：P-151。关闭 P-150 CHECKLIST §11 登记的已知边界：账本非空但 `outputs` 为空时不回退节点索引。
> **性质**：T1 实施批；单分支、单 PR；不改 API 与 CLI。

## 1. 问题

P-150 的来源判定是「账本**有动作** → `ledger`」，因此下列组合仍会漏产物：

- `actions.jsonl` 有记录（例如只读查询、无文件输出的工具调用），但所有动作的 `outputs` 都为空；
- 同一 run 的阶段产物已由 `register_stage_artifacts` 写入 `artifacts/nodes.jsonl`。

此时 `artifacts_source="ledger"`、`artifacts=0`，节点索引被完全忽略，两次内容不同的 run 仍可能判等价。

## 2. 方案对比

| 方案 | 做法 | 问题 |
|---|---|---|
| A 保留边界 | 仅当账本完全没有动作时回退 | 有动作但零产物的 run 继续假绿 |
| **B 按产物是否为空回退（采用）** | 账本贡献 ≥1 个产物才用账本，否则回退节点索引 | 语义从「有动作」改为「有产物」，更贴近比较目标 |
| C 合并账本与节点索引 | 两源取并集 | 同 locator 冲突无法裁定；P-150 已否决 |

选择 B：产物比较的目标是「产出了什么」，不是「执行了什么动作」。动作数仍由 tool/params/status 序列承载。

## 3. 判定语义

| 账本产物 | 节点索引 | `artifacts_source` | 产物投影 |
|---|---|---|---|
| ≥1 | 任意 | `ledger` | 账本 `outputs` |
| 0 | 存在 | `node_index` | `locator → content_hash` |
| 0 | 不存在 | `none` | 空 |

`checks` 仍为 9；`run_summary` 检查不变。

## 4. 风险与边界

| 风险 | 处理 |
|---|---|
| 动作确实无产物，但索引有无关产物 | 投影是 run 级而非动作级；以「run 的产物集合」为准，语义可解释 |
| 账本部分动作有产物、部分无 | 只要账本产物 ≥1 就整体用账本，不混合两源（C 仍否决） |
| 回退后索引损坏 | 沿用 P-150 的 `ValueError` fail-closed |

## 5. Review 记录（Step 4）

- 对照 P-150 D-7：该决策被本批显式取代，P-150 文档保持历史原样，P-151 记录新语义。
- 对照 P-150 §3「单一来源」：原则不变，只把触发条件从动作数改为产物数。
- 未观察到该组合的真实 run；本批用夹具覆盖，诚实登记为逻辑补洞而非实验复现。

## 6. 范围

- 做：来源判定条件、2 条用例、四文档。
- 不做：两源合并、动作级产物归属、目录扫描、真实 LLM 重跑。

## 7. 诚实边界

- 「账本产物为空」的判定发生在路径相对化之后；目录外产物退化为 basename 仍然计数。
- 不保证回退能覆盖「账本有产物但漏记」的情况。
