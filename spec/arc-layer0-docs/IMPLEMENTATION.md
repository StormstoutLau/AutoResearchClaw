---
id: arc-layer0-docs-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-26
depends: [arc-master-roadmap]
upstream: arc-master-roadmap
---

# Layer-0 文档批索引与产出记录（P-179..P-189）

> **性质**：T3 批次索引。这 11 个批次都是 Layer-0（文档/调研/分析/审查），
> 零代码、零门禁变更，没有各自的实现目录；本文件是它们的**共享 feature 锚点**，
> 用于满足批次绑定门禁（`step_enforce` 对 P≥129 要求 `spec/<feature>/` 链接）
> 与 content-digest 绑定（session finalize 的 `evidence_digest` 指向本文件）。
>
> **不宣称**：本文件不是四文档实现规格，不描述代码行为；各批次的真实产出在
> 下表所列的 `docs/` 文档与 `arc-master-roadmap.md` 修订行中。

## 1. 批次与产出

| P | 主题 | 主要产出 |
|---|---|---|
| P-179 | 总纲进度回填与已调研未实现登记 | `arc-master-roadmap.md` §3.1/§3.2（G7 13/15、B-1..B-12） |
| P-180 | OpenScience 生态案例拆解与吸收方案 | `clawsgo-cleanroom-arc-reinforcement.md`（本地草稿，不入库） |
| P-181 | 补强项统一治理（R0–R9 / S0–S12 / B-1..B-12 并轨） | 同上 §12（台账、C-1..C-10 裁决、W0–W3） |
| P-182 | ClawsGO 1.1.4 逆向报告判断校准与全文更新 | 同上（新增 T0 证据层） |
| P-183 | `clawsgo-cleanroom-arc-reinforcement.md` 异构独立审查 | 审查记录（D/O 表） |
| P-184 | P-183 审查报告复核与 D/O 修复 | 同上（引文订正、D-1..D-6 维持） |
| P-185 | `approval_timeout_hours` README 注释修正 | 10 处 README + 配置样例 |
| P-186 | 已调研未实施报告的优先级与依赖分析 | `docs/arc-backlog-priority-dependency-20261126.md` |
| P-187 | 总纲 B-13..B-27 回填 | `arc-master-roadmap.md` §3.2 |
| P-188 | 总纲 §0 报告盘点口径订正 | `arc-master-roadmap.md` §0 |
| P-189 | 总纲 §3.3 波次依据补全 | `arc-master-roadmap.md` §3.3 |

## 2. 为什么共用本目录

- 这 11 批**没有实现代码**，单独为每批建 spec 目录会产生 11 个只有一两行的空壳目录，
  反而稀释 `spec/` 作为「实现规格」的语义。
- 本文件逐批列出产出物，使「P 行 → feature → 产出」仍可机械追溯；
  session 的 `evidence_digest` 绑定本文件，保证「验后改文档」可被检出。

## 3. 边界

- 本目录 T3：不提供 RESEARCH/DESIGN/CHECKLIST 四文档，也不承载验收断言。
- 若后续某批升级为 T1（出现代码改动），应另建独立 feature 目录并把该 P 行改指向新目录。
- 修改本文件会使 P-179..P-189 的 11 个 session digest 失效，需按 rebind 流程重签。
