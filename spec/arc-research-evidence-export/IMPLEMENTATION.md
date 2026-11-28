---
id: arc-research-evidence-export-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [arc-research-evidence-export-DESIGN]
upstream: arc-research-evidence-export-DESIGN
---

# 实施：调研证据出口规范化（P-225）

> 零代码、零门禁。只改规范/模板/入口文档各一处，并新增本 feature 四文档。

## 1. 改动清单

| 文件 | 改动 | 位置 |
|---|---|---|
| [spec/SPEC_PROCESS.md](../SPEC_PROCESS.md) | 版本 1.7.1 → **1.8.0**；新增「调研强度分级（S0/S1/S2）」小节 | §Step 工具与提示词契约，调研阶段之前 |
| [spec/templates/RESEARCH_TEMPLATE.md](../templates/RESEARCH_TEMPLATE.md) | 新增 §2.3 档位、§2.4 降级链；§3 来源字段增 `Layer`、`日期/版本` | §2 调研方法 / §3 发现 |
| [spec/templates/CHECKLIST_TEMPLATE.md](../templates/CHECKLIST_TEMPLATE.md) | §1.1 增一行「RESEARCH §2.3 声明档位、§2.4 写降级链」 | §1.1 表格 |
| [RESEARCHCLAW_AGENTS.md](../../RESEARCHCLAW_AGENTS.md) | 五步第 2 步补：档位 + `metadata.sources` | §Spec Workflow |

## 2. 新增段落要点

- 三档：S0 实施型（≥1 上游）/ S1 缺陷型（E1 ≥2 + 豁免）/ S2 探索型（外部 ≥5 且 ≥1 T1）。
- 降级链：目标通道 → 备用通道 → 本地事实 → 未取证声明；单点通道无效。
- 外部锚点的软性说明：`verify-anchor` 标「外部证据，本地不可核」属预期，但不免除可解析 ID。
- 不可判即升级到 S2（fail-closed）。

## 3. 验证读数

```
grep -c "S0 实施型" spec/SPEC_PROCESS.md                  → 1
grep -c "2.3 调研档位" spec/templates/RESEARCH_TEMPLATE.md → 1
grep -c "2.4 降级链" spec/templates/RESEARCH_TEMPLATE.md   → 1
grep -c "调研档位" spec/templates/CHECKLIST_TEMPLATE.md    → 1
grep -c "metadata.sources" RESEARCHCLAW_AGENTS.md          → 1
git diff --stat .pre-commit-config.yaml tools/spec_runner/spec_runner.py → 空
```

## 4. 回归

- 无代码改动，不跑 pytest；跑 DC 校验、`console_gen --check`、`rework_graph_check`、pre-commit 全链。
- 本批自身按 S1 填写（RESEARCH §2.3 已写豁免说明），作为新规则的第一个自证样本。

## 5. 未做

- 未改 `verify-anchor`、未加 hook、未追溯改写历史 RESEARCH；
- 未把 `metadata.sources` 纳入 step-gate 校验（按 D-5 刻意保持软性）。
