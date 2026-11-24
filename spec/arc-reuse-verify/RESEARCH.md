---
id: arc-reuse-verify-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-pipeline-skill-impl-IMPLEMENTATION, arc-action-ledger-IMPLEMENTATION]
upstream: null
---

# 调研：账本查询 CLI 与 manifest 复现性校验（P-147）

> **Feature**：P-147。收口 P-140 P0-2「下次复用」的可机械验证形态；实施批 P-146 的直接后续。
> **性质**：T1 实施批；单分支、单 PR、10 步一次跑完（吸收 P-145/P-146 拆两批的教训）。
> **结论先行**：① manifest 刻意不含 prompt（D-7/I-4），**按 manifest 重跑不可实现**，重执行登记为 U-1；② 「复用」的可交付形态是**复现性校验**：离线核对产物哈希、动作归属与事件链；③ 交付只读 CLI 两条命令，接入既有 `audit` 范式。

## 1. 问题

P-146 之后，一次成功 run 可以导出为 pipeline skill 并被发现，但没有任何工具回答「这个技能记录的成功路径现在还成立吗」。三个可核对的事实散在三个文件里：

| 事实 | 位置 |
|---|---|
| 产物是否还在、哈希是否一致 | manifest `stages[].outputs` ↔ run 目录 |
| 动作是否可追溯 | manifest `stages[].actions` ↔ `actions.jsonl` |
| 事件链是否完整 | `events.jsonl` ↔ `verify_chain` |

## 2. 「重放」的技术裁定

| 问题 | 裁定 |
|---|---|
| 能否按 manifest 重跑 23 阶段？ | **不能**。manifest 不含 prompt、不含阶段配置（P-145 D-7 刻意排除，防密钥/上下文泄漏） |
| 能否校验「成功路径仍完好」？ | **能**。产物哈希、动作归属、事件链、readpoint 全部可离线机械核对 |
| 重执行的路径？ | **U-1**：需要先决策「manifest 是否携带配置指针/ prompts 哈希 + 配置」——安全权衡另立批次 |

因此本批把「复用」落地为**复现性校验**（verify），并把引导式重执行登记为 U-1。这不是缩水：校验是重执行的前置——没有它，重执行无从判断基线是否仍然成立。

## 3. 需求

| 编号 | 需求 |
|---|---|
| R1 | `actions` 查询命令：按 tool/status/seq 过滤账本，`--json` 机读 |
| R2 | `pipeline-skill verify`：manifest + run 目录 → 复现性判定 |
| R3 | 校验项：产物存在且哈希一致、动作可解析、事件链通过、readpoint 一致 |
| R4 | 退出码语义与 `audit` 一致：0 通过 / 1 有差异 / 2 输入不可用 |
| R5 | 只读；不修改 run 目录与技能目录 |

## 4. 方案空间

| 方案 | 判断 |
|---|---|
| A（采用） | 纯函数核（`query_actions` + `verify_reproducibility`）+ CLI 薄壳，复用 `audit` 范式 | 核心可测，CLI 只做 I/O |
| B | 校验逻辑塞进 `pipeline_manifest.py` | 该模块已承载导出/校验/发现三职责，再塞会过载 |
| C | 不做 CLI，只留函数 | 用户裁决要 CLI；且 P-145/P-146 文档已把 CLI 登记为 P-147 |

## 5. Review 记录（Step 4）

- 对照 P-145 D-7/I-4 复核：重跑确不可行，U-1 登记成立。
- 对照 P-146 `load_pipeline_skill`：发现入口已 fail-closed，verify 直接复用，不重复校验逻辑。
- 发现并修正：初稿把校验函数放进 `pipeline_manifest.py`（方案 B），违反职责分离；改为纯函数核独立模块。

## 6. 编号与接缝

- 本批占用 **P-147**（吸收 P-145 §6 原登记的「账本 CLI」与本批「复现性校验」两个口径）。
- U-1 引导式重执行 → **P-148 候选**。
- 本批不改 `pipeline_manifest.py`、`action_ledger.py` 既有行为；只新增。

## 7. 诚实边界

- 复现性校验只证明「记录的成功路径仍完好」，不证明「重跑会得到同样结果」。
- 账本查询不做聚合统计、不跨 run。
- CLI 输出格式为给人读的摘要 + `--json` 机读，不做表格对齐美化。
