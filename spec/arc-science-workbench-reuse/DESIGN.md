---
id: arc-science-workbench-reuse-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-19
depends: [arc-science-workbench-reuse-RESEARCH]
upstream: null
---

# 设计：科研组件的吸收路线与验收口径（P-140 调研批产出）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **本批不含实施**：只给吸收架构、优先级与后续批次的验收口径。
> **上游**：23 阶段流水线、HITL/CoPilot、skills、tools registry、evidence、event_log。

---

## 1. 目标与非目标

**目标**

1. 把外部产品的六个组件映射到本仓已有接缝，避免重复造轮子。
2. 给出 P0/P1/P2 三级吸收顺序与每级的验收不变式。
3. 明确许可证与「不吸收」边界。

**非目标**

- 不做桌面应用壳。
- 不复制闭源产品 UI/资产/文案。
- 不在本批改任何代码、测试、workflow。

## 2. 决策

| 决策 | 内容 | 依据 |
|---|---|---|
| D-1 | 证据/动作账本复用 `runtime/event_log.py`，扩展 action 类型与 artifact 哈希 | RESEARCH §3 P0 |
| D-2 | pipeline-as-skill 用 `SkillManifest`（阶段子图 + 配置 + 依赖 + 验收读点 + 版本） | RESEARCH §3 P0 |
| D-3 | Plan/Execute/Review 合同挂在 Stage 9 门禁前，复用 HITL 审批 | RESEARCH §3 P1 |
| D-4 | Scientific Model Router 先做静态能力表，写入选择理由 | RESEARCH §3 P1 |
| D-5 | 连接器优先 UniProt/PDB/ChEMBL/PubMed/arXiv 五个 | RESEARCH §3 P1 |
| D-6 | 持久内核与算力编排列 P2，单独立项 | RESEARCH §4 P2 |
| D-7 | 只复用 MIT/Apache 且保留 NOTICE；无许可证/泄漏源码零复用 | RESEARCH §2 |

## 3. 目标架构映射

| 层 | 现有接缝 | 扩展 |
|---|---|---|
| 执行 | `pipeline/stages.py`（23 阶段） | 阶段子图快照、计划合同 |
| 技能 | `skills/builtin`（20 个 SKILL.md） | `SkillManifest`、pipeline-as-skill |
| 工具 | `tools/registry.yaml`（6 个） | 5 个科学连接器 + 风险/审批字段 |
| 证据 | `runtime/event_log.py`、`evidence/` | action 记录、artifact 哈希、时间线 |
| 人机 | `hitl/`、`copilot/` | 计划审批、只读审计视图 |
| 模型 | `llm/`、`agents/` | 能力表 + 路由理由 |
| 知识 | `knowledge/`、`memory/` | 产物回链与版本 |

## 4. 后续批次验收不变式

| 编号 | 不变式 | 可观测读数 |
|---|---|---|
| J-1 | 每个阶段动作有账本记录 | 工具、参数、环境、种子、输入/输出产物哈希齐全 |
| J-2 | 账本可离线校验 | `verify_chain` 通过；篡改末行转红 |
| J-3 | 流水线可固化为技能并重载 | 同一 manifest 两次加载一致；版本号递增 |
| J-4 | 计划先于执行 | Stage 9 前存在计划产物；无审批不执行 |
| J-5 | 路由可追溯 | 每次模型选择有理由与候选集 |
| J-6 | 许可证合规 | 第三方代码有 NOTICE/版权；无泄漏源码 |

## 5. 优先级

| 级别 | 内容 | 理由 |
|---|---|---|
| P0 | 证据/动作账本、pipeline-as-skill | 直接增强现有 spec/证据体系，复用成本最低 |
| P1 | Plan 合同、模型路由、连接器、产物时间线 | 提升可审计性与领域覆盖 |
| P2 | 持久内核、算力编排 | 价值高但涉及沙箱/配额/运维，需独立设计 |

## 6. 风险与回退

| 风险 | 缓解 | 回退 |
|---|---|---|
| 账本写入放大 | 只记阶段级动作与产物哈希，不记全量日志 | 关闭 action 类型 |
| pipeline-as-skill 版本膨胀 | manifest 内容寻址 + 版本号 | 删除 manifest |
| 模型路由不可解释 | 选择理由强制入账 | 回退静态映射 |
| 许可证污染 | 复用前登记来源/许可证/NOTICE | 移除代码，仅保留思路 |

## 7. 接缝

- P0 可作为下一实施批；P1 拆分；P2 单独立项。
- 与 P-139（U-3/U-2 修复）无代码重叠；合并顺序按窗口 2 后的统一安排。
