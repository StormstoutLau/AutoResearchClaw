---
id: arc-g3-m0-design-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g3-readiness-RESEARCH, arc-g3-readiness-RESEARCH-2]
upstream: arc-g3-readiness-RESEARCH-2
---

# 调研：G3 M0 设计冻结输入

> **Feature**：P-074，G3 M0（生产脊柱 + 证据血缘 + 循环护栏）设计冻结。
> **Spec 步骤**：T1 完整管线（四文档；本批零生产代码/零测试，施工从 M1 开始）。
> **结论先行**：G3 的 9 项决策（Q-1..Q-9）与 6 项观察（O-1..O-6）已全部定案；本批冻结 **ArtifactNode v1、pipeline_summary 校验、stage_events/循环规则、claim 脊柱、RunMandate/StageHandback/prompt_version、K5/retrieval 门禁** 六组接口，并把 20 个验收 ID 映射到 M1..M5。实现批次：**M0=P-074、M1=P-075、M2=P-076、M3=P-077、M4=P-078、M5=P-079**。

## 1. 输入

| 来源 | 内容 |
|---|---|
| P-069 | G3 前置/现状盘点/切片；H-4 已落地 |
| P-070 | Q-1..Q-9 决策（v1.2 已采纳）；S-1..S-16 锚点 |
| P-072 | 独立复核零缺陷；O-1..O-6 观察项 |
| P-073 | O-1..O-6 深挖方案（vendor 词表、断链、cap_reasons、绑定表、事件链排期、plan_sig 字段） |

## 2. 一手现状（冻结依据）

- 已有：Stage 9/20/23 claim 门禁；`pipeline_summary.json` 程序派生（无校验）；`retrieval_degraded`（未接门禁）；G1a `events.jsonl` 哈希链；vendor `CitationLabel` 7 值枚举与 `decide_citation_label`。
- 缺失：`ArtifactNode`、`stage_events`/循环检测、Stage 14/17/22 claim 接线、`RunMandate`/`StageHandback`/`prompt_version`、K5 `tb:`/`paper:` 解析器、`pipeline_summary` 防篡改校验。
- 已裁决：Q-1 允许 `PARTIALLY_FORMALIZED` 但标注；Q-2 大文件指针；Q-3 annotation 跟随封顶状态；Q-4 Stage 14 生产 annotation；Q-5 JCS+侧车+事件链；Q-6 签名+零新增+网络豁免；Q-7 mandate 不可变；Q-8 K5 未解析即阻断；Q-9 敏感产物只存指针。

## 3. M0 范围

**冻结**：六组接口的字段、错误码、落盘位置、验收映射、施工顺序。
**不做**：任何生产代码、测试、schema 文件、迁移；M1 起按 [IMPLEMENTATION.md](IMPLEMENTATION.md) 施工。

## 4. 验收映射（20 项）

| 组 | 验收 ID | 归属批次 |
|---|---|---|
| Claim 脊柱 | A3-1、A3-3 | M3（P-077） |
| Summary/血缘 | A3-2、AN-1..AN-6 | M1（P-075） |
| 循环护栏 | FC-1..FC-3 | M2（P-076） |
| 治理 | A3-6、A3-7、A3-8 | M4（P-078） |
| 检索/K5 | A3-4、A3-5 | M5（P-079） |

## 5. 风险

- A3-1 跨 Stage 14/17/22，且依赖 Q-3/Q-4 的 annotation 语义；M3 工作量最大。
- ArtifactNode 需覆盖所有 DONE 阶段产物，M1 要先定「入树/指针」边界，避免返工。
- M1 的 summary 校验只做侧车双向；事件链三向校验在 M2 升级（O-5）。
- `plan_sig`/`new_rows` 取数依赖既有产物，M2 不得新增采集路径（O-6）。
