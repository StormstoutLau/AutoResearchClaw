---
id: arc-research-evidence-export-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [arc-research-evidence-export-RESEARCH]
upstream: arc-research-evidence-export-RESEARCH
---

# 设计：调研证据出口规范化（P-225）

## 1. 原则

1. **只约束形态**：档位与来源数可机械核对；不评价「调研得好不好」。
2. **不新增门禁**：沿用 [SPEC_PROCESS](../SPEC_PROCESS.md#L119) 的定位，留证靠 CHECKLIST 自证与 Review 复核。
3. **与档位正交**：T1/T3 管工件多少，S0/S1/S2 管调研强度。

## 2. 决策

| ID | 决策 | 依据 | 被拒替代 |
|---|---|---|---|
| D-1 | 新增 S0 实施型 / S1 缺陷型 / S2 探索型三档，写入 SPEC_PROCESS「调研强度分级」 | L-1 档位不覆盖调研强度 | 全批强制外部检索（成本高、缺陷批无收益） |
| D-2 | RESEARCH 模板增 §2.3 档位、§2.4 降级链；§3 来源字段增 `Layer` 与 `日期/版本` | L-3 硬约束需要落点、L-4 模板已有方法节 | 新建独立调研模板（重复） |
| D-3 | CHECKLIST 模板 §1.1 增一行「RESEARCH §2.3 声明档位、§2.4 写降级链」 | 让执行进入验收面 | 只在 SPEC_PROCESS 写（仍不落地） |
| D-4 | `RESEARCHCLAW_AGENTS.md` 五步第 2 步补一句：档位 + `metadata.sources` | 入口文档是每批必读 | 只改模板 |
| D-5 | session 的 research 决策增 `metadata.sources`（layer/id/date/status），`step-gate` 不校验内容 | L-5 外部锚点为软性，校验内容会变成新门禁 | 让 step-gate 校验条数（违反「不新增门禁」） |

## 3. 分档判据

| 档 | 判据（机械可读） | 最小来源 |
|---|---|---|
| S0 | 本批 PROGRESS「依据」列引用了上游 RESEARCH | ≥1 条上游（ID 或 `文件#L`） |
| S1 | 根因可由本机日志 / 测试 / 代码复现 | E1 ≥2 条 + 豁免说明 |
| S2 | 出现新失败模式 / 方法学选择 / 跨版本行为 | 外部 ≥5 条且 ≥1 T1 |

不可判 → 按 S2（fail-closed）。

## 4. 验收

- SPEC_PROCESS 新小节存在且含三档、最小来源、降级链、软性说明；
- 模板 §2.3/§2.4 与 `Layer`/`日期/版本` 字段存在；
- CHECKLIST 模板含自证行；AGENTS 第 2 步含档位与 sources；
- 本批自身按 S1 填写（自证）；
- 门禁零新增：`git diff .pre-commit-config.yaml` 为空，`spec_runner.py` 未改。

## 5. 非目标

- 不改 `verify-anchor` 行为（URL 仍软性）；
- 不新增 hook / CI；
- 不追溯改写历史 RESEARCH；
- 不要求 T3 轻批写四文档。
