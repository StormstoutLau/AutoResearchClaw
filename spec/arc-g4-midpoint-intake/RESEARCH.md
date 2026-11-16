---
id: arc-g4-midpoint-intake-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-ci-cd-research-DESIGN]
upstream: null
---

# 调研：G4 中期盘点文档入库（P-135）

> **Feature**：P-135。把长期未跟踪的 `docs/arc-g4-midpoint-20261113.md` 纳入版本控制，并以勘误横幅标注已订正的计数。
> **Spec 步骤**：Step 1-2（调研批）。
> **结论先行**：该文档不是普通工作区残留，而是**被 4 处已入库文档引用、且在干净检出中会导致 dc_validator 报 P2 的缺失工件**。处理方式采纳「入库 + 勘误横幅」：正文保持原样，顶部声明历史快照与订正指针；不改已封存的 M4/M5 文档与 PROGRESS 历史行。

## 1. 调研目标

1. 确认该文档的引用面与「未跟踪」造成的实际缺陷。
2. 判断入库、删除、维持现状三种处理的代价。
3. 给出不破坏已验收文档 digest 的最小动作。

## 2. 仓内事实（E1）

| 编号 | 读数 | 来源 |
|---|---|---|
| E1-1 | 文件 9,018 B（入库前），创建/修改时间 2026-11-13，无 front-matter | `Get-Item` / 读码 |
| E1-2 | 被 M4 RESEARCH、M5 RESEARCH、M4 复核报告引用 | 见下 |
| E1-3 | 在仅含已提交文件的 detached worktree 中，`dc_validator` 报 21 条 P2，目标之一是本文档 | [arc-ci-cd-research DESIGN §2.1.1](../../spec/arc-ci-cd-research/DESIGN.md#L48) |
| E1-4 | 部分计数已被订正：M4 的 F-12/F-13、M5 的 F-3/F-6 | [M4 RESEARCH](../../spec/arc-g4-m4-sandbox-limits/RESEARCH.md#L61-L62)、[M5 RESEARCH](../../spec/arc-g4-m5-host-boundary/RESEARCH.md#L55-L58) |

**引用点**：

- [M4 RESEARCH §7](../../spec/arc-g4-m4-sandbox-limits/RESEARCH.md#L156)：「未入仓工作区文档；其 §0.1 两处读数以本文 F-12/F-13 订正」
- [M5 RESEARCH §5.1](../../spec/arc-g4-m5-host-boundary/RESEARCH.md#L104)：「计数以本文 F-3/F-6 订正」
- [M4 复核](../../docs/arc-g4-m4-review-20261113.md#L20)：工作树仅保留该未入仓文档
- PROGRESS P-105 / P-106 依据列：「G4 中期盘点（docs/arc-g4-midpoint-20261113.md，未入仓…）」

## 3. 外部锚点

| 来源 | 结论 | 等级 |
|---|---|---|
| Git 官方《Recording Changes》 | untracked = 不在任何提交快照中；被 tracked 文档引用的工件必须显式加入 | T1 |
| Read the Docs 链接最佳实践 / 链接腐化实践 | 引用目标应有稳定 URL；目标缺失会持续产生 404/坏链 | T3 |
| Documentation Rot 与可追溯性 | 过期文档应标注被取代/订正关系，而非静默保留或删除 | T3 |
| P-133 决策锚点（本仓） | 对本仓而言，「本地有、干净检出无」已由 21 条 P2 实证 | E1 |

## 4. 方案比较

| 方案 | 做法 | 优点 | 代价/风险 |
|---|---|---|---|
| **A 入库 + 勘误横幅（推荐）** | `git add` 原文件；顶部加历史快照与订正指针 | 修复引用目标缺失；保留证据；不触碰已封存文档 | 旧「未入仓」措辞成为历史陈述 |
| B 原样入库 | 仅 add | 最小动作 | 已订正计数被固化为可引用事实 |
| C 删除并改写引用 | 删文件，改 M4/M5 与 PROGRESS | 无残留 | 需回填批并改写已验收文档 digest；丢失快照 |
| D 维持未跟踪 | 不动 | 零成本 | 干净检出持续 P2；每批都要声明批外保留 |

## 5. 与既有约束的映射

| 约束 | 本批结论 |
|---|---|
| dc_validator 作用域 | 该文档无 front-matter，仍不在 DC 契约内；不新增 DC1-DC5 负担 |
| step_enforce 的「验后改文档」 | 本批不修改 M4/M5 的 RESEARCH 与 PROGRESS 历史行，避免 digest 失配 |
| 批外工作树 | 入库后该文件不再以 `??` 出现；vendor CRLF 保持不动 |

## 6. 未决项

| ID | 内容 | 判据 | 触发条件 | 当前倾向 | 证据等级 |
|---|---|---|---|---|---|
| U-1 | 旧 PROGRESS / RESEARCH 的「未入仓」措辞是否回填 | 是否需要文义一致 | 后续回填批 | 不回填，作为历史陈述 | E1 |
| U-2 | 勘误横幅中的链接是否需要行号锚点 | 文档更新导致行号漂移 | 链接检查接入 | 只用文件级链接 | E1 |
| U-3 | 是否需要 front-matter 纳入 DC 契约 | 治理成本 vs 一致性 | 文档变更频率 | 不加，维持非契约文档 | E1 |

## 7. 诚实边界

- 本批只做入库与横幅，不逐条修正正文中的过期计数；订正以 M4/M5 RESEARCH 为真值源。
- 不在本批修改任何已验收文档或 PROGRESS 历史行。
- 未新增链接检查门禁；干净检出下的 P2 消除依赖本批入库动作本身。
