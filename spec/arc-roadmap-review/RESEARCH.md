---
id: arc-roadmap-review-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-06
depends: [arc-master-roadmap]
upstream: arc-master-roadmap
---

# 调研：ARC 总纲及关联调研文档审查

## 1. 审查对象

- 主对象：[arc-master-roadmap.md](../../arc-master-roadmap.md)（v0.1，12 阶段 / 106 条验收）
- 关联文档 14 份：`academic-reasoning-base-fusion`、`arb-v2-decisions-research-design`、`arc-knowledge-paper-textbook-integration`、`clawsgo-*`（4 份）、`dsh-superagent-absorption-analysis`、`docs/` 下 6 份设计文档。

## 2. 审查问题

1. 文档中的代码事实断言是否真实（防幻觉）。
2. 外部引用（arXiv 编号、标准、开源项目）是否真实且标题匹配。
3. 15 份文档之间的依赖与术语是否闭合。
4. 12 阶段路线的依赖、验收可判定性与平台可行性是否成立。

## 3. 方法

按 [SPEC_PROCESS.md](../../SPEC_PROCESS.md) §Review 检查清单执行：

- 代码事实：`rg --no-ignore` 全仓检索 + 静态读码，证据绑定 `7d0e70a`。
- 源数据：`python -c` 直读 `D:\Paper\Paper_Organized_v2_report.json` 与 `D:\Textbook\output\pilot\knowledge_graph.json`。
- 外部引用：WebSearch/WebFetch 逐条核对标题与编号。
- 文档一致性：脚本解析 front-matter 的 `id/depends/upstream` 并检查闭合。
- 路线可行性：人工比对 §1–§11 的依赖图、C 套件覆盖与 Q1–Q16 闸门。

## 4. 结论摘要

**事实底座可信**：8 条代码缺口断言 8/8 成立；Paper 2,487 条、Textbook 1,824 节点 / 20,235 边与源文件实测一致；106 条验收计数复算无误。

**发现 2 项 P1、10 项 P2、6 项 P3**：

- P1-01：roadmap L296 声称「H-4 已落地」，与 L165 的 G-1 待做项矛盾，且 `retrieval_degraded` 全仓 0 命中。
- P1-02：§5 C 套件未覆盖 H-1..H-4，G-1 数据正确性无回归闸门。
- P2 主要项：依赖 id 断链 6 处；arXiv 2609.00006 实为 7 子系统而非「四层」；PROV-O 字段名应为 `wasGeneratedBy`；MCP 2026-07-28 非「v2」且移除了 SSE `Last-Event-ID`；E2B/Daytona/Firecracker 非等价三档；Kosmos「逐句引用」为推断；A2-3「65 项 verdict 测试」口径无法复现；`kill -9`/退出码 137 在 Windows 不可验收；ClawsGO 与 ClawGo 混用；自出版综述作 L1–L5 标尺。

完整取证矩阵与逐条证据见 [docs/arc-roadmap-review-20261106.md](../../docs/arc-roadmap-review-20261106.md)。

## 5. 审查局限

单基座、单视角（RULE-4/5 未满足）；外部引用只做到存在性与标题匹配，未逐篇读全文验证因果；代码证据随重构会腐烂。
