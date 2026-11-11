---
id: arc-g3-m0-design-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g3-m0-design-DESIGN]
upstream: arc-g3-m0-design-DESIGN
---

# 实施记录：G3 M0 设计冻结（P-074）

> **状态**：设计冻结完成；本批**零生产代码/零测试**。施工从 M1（P-075）开始，按本文件 §3 顺序推进。
> **依据**：[DESIGN.md](DESIGN.md) §2（接口）、§3..§8（契约）、§10（验收映射）。

## 1. 冻结的接口

| # | 接口 | 冻结内容 |
|---|---|---|
| 1 | `ArtifactNode` | 12 字段、content_hash/inputs_digest 算法、指针/blob 边界、`project_to_evidence` 投影 |
| 2 | `pipeline_summary` | JCS canonical、SHA-256 侧车、M2 事件链锚定、`verify_summary` 两阶段 |
| 3 | `stage_events` | 事件字段、`plan_sig`/`new_rows`/`network_error` 取数、3 次空转 PAUSE |
| 4 | Claim 脊柱 | vendor `CitationLabel` 复用、`claim_annotations.json`、`[c-xxxxxxxx]`、`claim_export.json`、`cap_reasons` |
| 5 | 治理 | `RunMandate` 字段与不可变、`StageHandback` schema、`prompt_version` 哈希 |
| 6 | K5/retrieval | 引用文法、未解析错误码、`retrieval_degraded` 标注 |

## 2. 关键决策落点

| 决策 | 落点 |
|---|---|
| Q-1 `PARTIALLY_FORMALIZED` 放行但标注 | Stage 22 标签映射；`formalization_gap` 进入 annotation |
| Q-2 大文件指针 | `ArtifactNode.materialized=false` + `locator` |
| Q-3 annotation 跟随封顶状态 | `ClaimDecision.cap_reasons` + Stage 22 渲染 |
| Q-4 Stage 14 生产 annotation | `stage-14/claim_annotations.json` + 外部覆盖 |
| Q-5 summary 防篡改 | JCS + `.sha256` + M2 事件链 |
| Q-6 循环检测 | `stage_events.jsonl` + 3 次规则 |
| Q-7 治理 | `run_mandate.json`、`handback.json`、请求日志 |
| Q-8 K5 | `k5_refs.py` + Stage 22/23 门禁 |
| Q-9 敏感产物 | `sensitive=true` → 指针，不入 blobs/导出 |

## 3. 施工顺序（M1..M5）

| 批次 | 交付 | 主要文件 | 验收 |
|---|---|---|---|
| M1 P-075 | ArtifactNode + summary 校验 | `evidence/artifact_node.py`、`evidence/summary_check.py`、runner 注册 | AN-1..6、A3-2（侧车）、A3-3 基础 |
| M2 P-076 | stage_events + 循环 + 事件链 | `runtime/stage_events.py`、`EVENT_TYPES` 扩展 | FC-1..3、A3-2（三向） |
| M3 P-077 | claim 脊柱 | `evidence/claim_spine.py`、Stage 14/17/22 接线 | A3-1、A3-3 |
| M4 P-078 | 治理 | `runtime/mandate.py`、runner/LLM 请求日志 | A3-6/7/8 |
| M5 P-079 | K5 + retrieval | `knowledge/k5_refs.py`、Stage 22/23 | A3-4、A3-5 |

## 4. 测试计划（施工批落地）

- M1：节点哈希/父节点/环/inputs_digest、指针与敏感产物、summary 篡改负例。
- M2：3 次同签名空转 PAUSE、有新行放行、网络错误豁免、事件链缺失。
- M3：14→17→20→22→23 三出口一致、digest 断网复算、cap_reasons、未标注 numeric 阻断。
- M4：mandate 不可变、配置变更不影响在跑 run、handback 越界拒绝、prompt_version 可追溯。
- M5：`tb:`/`paper:` 未解析阻断并定位、`retrieval_degraded` 标注。

具体用例数与文件在对应批次登记，不在 M0 预估。

## 5. 验证（本批）

- DC 契约：四文档 front-matter/链接通过。
- step_enforce：P-074 session 5/5。
- pre-commit 9/9；roadmap coverage missing=0。
- 无代码/测试变更（T1 设计冻结）。

## 6. 未纳入本批

- 任何生产代码、schema 文件、迁移脚本。
- M1..M5 的测试与读数。
- G7 的多 run 并发/跨平面长期审计。
