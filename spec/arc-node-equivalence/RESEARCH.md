---
id: arc-node-equivalence-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-run-equivalence-CHECKLIST, arc-g3-m1-artifacts-DESIGN]
upstream: null
---

# 调研：产物节点等价性与 summary digest（P-150）

> **Feature**：P-150。承接 P-149 真实 LLM 重跑实验暴露的判定盲区：stages 1-3 不写 `actions.jsonl`，判定器只读账本，导致「产物内容不同却判等价」。
> **性质**：T1 实施批；单分支、单 PR；P-149 的 9 条核心判据不推翻，只扩充产物来源并新增第 9 类检查。

## 1. 真实实验证据（P-149 遗留复现）

2026-11-24 用 `deepseek/deepseek-chat` 对同一 topic 连跑两次前 3 阶段：

| 读数 | run A | run B |
|---|---|---|
| 阶段 | 1,2,3 | 1,2,3 |
| `actions.jsonl` | 不存在（0 动作） | 不存在（0 动作） |
| `pipeline_summary` digest | `sha256:40c6bd70…` | `sha256:02fbc377…` |
| `stage-01/goal.md` | `761cd9d3…` | `7CF78F0B…` |
| `stage-02/problem_tree.md` | `6908dee8…` | `85942522…` |
| `stage-03/search_plan.yaml` | `e777bbee…` | `2bfd88d2…` |

P-149 判定器返回 `equivalent=true, checks=8, differences=[]`。原因是产物投影只取账本 `outputs`，两跑账本皆空，tool/params/status/artifacts 四类实际未比。**这是弱等价，属于假绿**。

## 2. 可用证据源

| 来源 | 路径 | 字段 | 覆盖 |
|---|---|---|---|
| 动作账本 | `actions.jsonl` | `outputs{path: sha256}` | 已接入工具的输出；stages 1-3 为空 |
| 产物节点索引 | `artifacts/nodes.jsonl` | `locator`、`content_hash`、`producer.stage` | 每阶段完成时登记的全部产物；两跑各 6 条 |
| 管线摘要 | `pipeline_summary.json` + `pipeline.summary` 事件 | canonical JSON 的 `sha256` | 顶层整体指纹；两跑不同 |

节点索引由 `register_stage_artifacts` 在阶段完成时写入，`content_hash` 直接来自文件字节，是目前唯一覆盖「无工具动作阶段」的确定性产物证据。

## 3. 方案对比

| 方案 | 做法 | 问题 |
|---|---|---|
| A 只补 summary digest | 比对 `pipeline_summary.json` 的 digest | 只能给出「有差异」，无法定位到产物；summary 缺失时无信号 |
| B 扫描 run 目录全部文件 | 逐文件哈希比较 | 会把日志、时间戳、心跳、临时文件纳入，误报严重 |
| **C 账本为空时回退 nodes.jsonl + 新增 summary digest（采用）** | 账本非空仍以账本为准；为空则用节点索引；另加第 9 类 summary 检查 | 节点索引语义需明确（重复 locator、非 stage 节点） |

选择 C：与 P-149 的「确定性投影」原则一致，不引入目录扫描噪声，同时把真实实验中暴露的盲区补上。

## 4. 判定语义

- **产物来源**：`actions.jsonl` 有动作 → `artifacts_source="ledger"`；无动作且存在 `artifacts/nodes.jsonl` → `"node_index"`；两者皆无 → `"none"`。
- **节点索引投影**：`locator → content_hash`；同一 locator 多次出现时按文件顺序后写覆盖（与账本一致）；不区分子目录。
- **summary 检查**：读取 `pipeline_summary.json`，按 `summary_check.summary_digest` 计算 canonical digest；两侧不同（含一侧缺失）记 `run_summary` 差异。
- **检查数**：8 → 9；`checks` 仍为固定值，防止零检查假绿。

## 5. 风险与边界

| 风险 | 处理 |
|---|---|
| 节点索引被篡改 | 只读 `content_hash`；篡改会体现为两跑差异或解析失败 |
| 索引行缺字段 | 解析失败 → `ValueError`，CLI exit 2，fail-closed |
| 非 stage 节点混入 | 只要有 `locator` 与 `content_hash` 就纳入；语义是「产物内容」而非「阶段产物」 |
| 账本非空但输出为空 | 仍标 `ledger`（不静默回退）；报告 `artifacts=0` 可见 |
| summary 一侧缺失 | 记 `run_summary` 差异，不视为等价 |

## 6. Review 记录（Step 4）

- 对照 P-149：8 类判据语义不变，仅第 6 类（artifacts）增加来源选择，并新增第 9 类；`checks` 从 8 升 9 是显式契约变更。
- 对照 P-147：`verify_reproducibility` 是 manifest ↔ run 的完整性校验；本批是 run ↔ run，不重叠。
- 否决「始终合并账本与节点索引」：同一 locator 冲突时无法裁定谁对，静默覆盖会掩盖问题；回退语义更可解释。
- 否决「重算磁盘文件哈希」：会把未登记文件纳入，且与 P-149 的「只信记录」原则冲突。

## 7. 范围

- 做：`compare_runs` 产物回退、summary digest 检查、报告增加 `artifacts_source`、测试与文档。
- 不做：真实 LLM 再跑、目录全量扫描、节点索引完整性校验（`verify_tree` 已在别处）、自动修复差异。

## 8. 诚实边界

- 回退仅在账本**完全没有动作**时生效；账本非空但 `outputs` 为空的情况仍不覆盖。
- summary digest 只能证明整体指纹不同，不能定位差异；定位依赖 artifacts 投影。
- 本批用真实实验产物形状构造测试夹具，但不重新调用 LLM。
