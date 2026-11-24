---
id: arc-pipeline-skill-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-science-workbench-reuse-RESEARCH, arc-action-ledger-RESEARCH, arc-master-roadmap]
upstream: null
---

# 调研：把一次成功运行固化为技能（P-145）

> **Feature**：P-145。承接 P-140 §4 的 P0-2「pipeline-as-skill」，本批只做决策与规格，不写代码。
> **性质**：T3 决策批；产出 RESEARCH + DESIGN，实施留 P-146。
> **结论先行**：① 需要的能力是「捕获成功路径 → 校验 → 以技能形式被发现 → 安全地复用」，不是自动重跑；② 证据源已经齐备：事件流的阶段序列、P-143 的动作账本、ArtifactNode 的产物哈希、审批表；③ 建议 manifest 用独立 `pipeline.json`，由 `SKILL.md` 指向，避免把大结构塞进 front-matter。

## 1. 问题

| 现状 | 缺口 |
|---|---|
| 20 个 `SKILL.md` 是预先写好的知识文档 | 不能表达「这次运行实际走了哪 23 个阶段中的哪几个」 |
| 成功运行的痕迹只留在 `<run>/` 目录 | 下次运行无法复用同一阶段序列、配置与工具组合 |
| `skills/loader.py` 已能扫描目录并加载 | 缺「运行记录 → 技能」的转换与校验 |
| `skills/schema.py` 有 `metadata` 字典 | 只适合短键值，不适合承载阶段子图与产物哈希 |

P-140 §1 把 Claude Science 的「pipeline 可保存为可复用 skill」列为核心差异项；P-140 §4 将其列为 P0-2。

## 2. 证据源

| 需要的事实 | 来源 | 现状 |
|---|---|---|
| 阶段序列与成败 | `events.jsonl` 的 `stage.started/completed/failed` | 已有 |
| 每步工具、参数、环境、种子 | `actions.jsonl`（P-143） | 已有 |
| 产物哈希 | `actions.jsonl` 的 `inputs/outputs`、`evidence/artifact_node.py` | 已有 |
| 审批人 | `approvals.json` 的 `by` | 已有 |
| 阶段名与编号 | `skills/schema.py` 的 `STAGE_NAME_TO_NUMBER` | 已有 |
| 技能发现与加载 | `skills/loader.py` + `skills/registry.py` | 已有 |

### 2.1 调研方法与外部锚点

**方法**：仓内接缝以源码与已入库文档为 T1；外部先例以官方规范/文档为 T2，本批未抓取原文的条目标注「未回原文」；产品能力沿用 P-140 的公开资料读数（T2）。不使用私有接口或逆向材料。

| 来源 | 层级 | 验证状态 | 与本设计的关系 |
|---|---|---|---|
| `researchclaw/skills/loader.py` + `schema.py` | T1（仓内源码） | 已读 | 确认 `SKILL.md` front-matter 与 `metadata` 可承载 `manifest` 指针 |
| agentskills.io `SKILL.md` 规范 | T2（公开规范） | 未回原文（本批） | 技能发现与元数据形态；`kind=pipeline` 是对 `metadata` 的扩展 |
| Nextflow modules（`main.nf` + `meta.yml`） | T2（官方文档） | 未回原文（本批） | 复用单元 = 有名字、有输入输出的过程；与「阶段子图」同构 |
| Snakemake wrappers（`wrappers/<tool>/<version>/`） | T2（官方文档） | 未回原文（本批） | 版本化复用单元的目录约定；对应 D-6 版本三元组 |
| CWL `CommandLineTool`（`cwlVersion`） | T2（规范） | 未回原文（本批） | 契约自带版本号；对应 `manifest_version` |
| GitHub Actions reusable workflow（`workflow_call` + ref pin） | T2（官方文档） | 未回原文（本批） | 复用入口与版本 pin；对应「加载不执行」与版本校验 |
| W3C PROV-O（Activity/Entity/Agent） | T1（标准） | 未回原文（本批） | 动作-产物-执行者三元关系；对应 `stages[]`/`outputs`/`approver` |
| P-140 产品矩阵（Claude Science） | T2（公开资料） | 已在 P-140 验证 | 「pipeline 可保存为复用 skill」的需求来源 |

> 标「未回原文」的条目只用于形态对照，不作为 A 类方法学结论；若 P-146 实施时需要精确引用，应在实施批补齐原文与版本号。

## 3. 需求

| 编号 | 需求 |
|---|---|
| R1 | 从一次「成功 run」导出 manifest：阶段子图、配置摘要、工具版本、产物哈希、验收读点 |
| R2 | manifest 可被现有 loader 发现为技能，且与普通 `SKILL.md` 共存 |
| R3 | 加载时校验版本与阶段映射，不匹配即拒绝 |
| R4 | manifest 不含密钥、原始 prompt、绝对路径 |
| R5 | 默认只「被发现」，不自动执行；复用需显式调用 |
| R6 | 为后续「按 manifest 重放」保留字段，但本批不实现重放 |

## 4. 方案空间

| 方案 | 形态 | 判断 |
|---|---|---|
| **A（采用）** | 技能目录内放 `pipeline.json`，`SKILL.md` front-matter 用 `metadata.manifest` 指向它 | 大结构独立、loader 零改动即可发现；manifest 可单独校验 |
| B | 全部塞进 `SKILL.md` front-matter | YAML 膨胀、解析慢、diff 噪声大 |
| C | 只用 `Skill.metadata` 字典 | 只能放短键值，无法表达阶段子图 |
| D | 新建独立 manifest 注册表，不接入 skills | 复用入口分裂，agent 看不到 |

## 5. 范围边界

- 做：manifest 规格、成功判据、子图折叠规则、版本与安全约束、加载语义。
- 不做：导出器与加载器代码、重放执行、自动技能推荐、跨 run 聚合。
- 非目标：替代 `SKILL.md` 的知识正文；pipeline 技能只是「怎么做成的」记录。

## 6. 编号与接缝

- 本批 P-145 为 T3 决策批。
- 实施批顺延 **P-146**；动作账本查询 CLI **P-147**（可选）。
- 决策冻结后，P-146 只需按 DESIGN 落地导出、加载与校验。

## 7. 诚实边界

- 本批不产生运行时证据，只做决策与规格。
- 「成功」的判据是机械可判的组合，不包含人类评审质量。
- 外部产品能力来自 P-140 的公开资料读数，未做私有接口验证。
- 外部先例标注「未回原文」的条目只用于形态对照，不是方法学结论。

## 8. 回退点

- 本批为纯文档决策；回退 = 对 P-145 的 squash 提交执行 `git revert`，删除两份文档、session 与 PROGRESS 行。
- 回退不影响运行时、接口或门禁；若 P-146 尚未开工，直接回到 P-140 §4 P0-2 的候选状态。
- 若 P-146 已按本 DESIGN 落地后再回退，需同时评估 P-146 的 manifest schema 来源；两者不共享 digest，但语义耦合。
