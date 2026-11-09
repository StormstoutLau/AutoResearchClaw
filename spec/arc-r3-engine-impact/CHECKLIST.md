---
id: arc-r3-engine-impact-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-10
depends: [arc-r3-engine-impact-IMPLEMENTATION]
upstream: arc-r3-engine-impact-IMPLEMENTATION
---

# 验收清单：R-3 影响面补充分析

## 1. 分析完整性

- [x] R-3 拆成 C-1 Saga / C-2 Temporal / C-3 DAG / C-4 自动闭包
- [x] 每项有“最小形态 vs 重型形态”对照
- [x] 当前前置缺口（事件链/依赖/补偿/哈希/pivot）逐项有证据
- [x] 影响面矩阵覆盖代码、数据、运行、运维、安全、成本、兼容、失败模式
- [x] 可控性判定区分低/中/高，并给出理由
- [x] R-3a/R-3b/R-3c 分层与触发条件明确
- [x] 外部锚点 ≥8 项，标验证状态
- [x] 明确“完整引擎当前不引入”不等于“永久拒绝”

## 2. 设计输入

- [x] `dependencies.yaml` 与 `artifact_manifest.json` 字段明确
- [x] `impact_plan.json` 含 changed_nodes/impact_set/conservative/human_confirm/cost
- [x] `compensation_registry.yaml` 区分 local/manual
- [x] `WorkflowRuntime` 适配器接口与 local 实现边界明确
- [x] R-3c 五项触发条件可机械判定
- [x] kill criteria：2 个迭代无净收益即回退

## 3. 边界与一致性

- [x] 未修改 `arc-master-roadmap.md`
- [x] 未修改 `researchclaw/` 代码
- [x] 未编辑 P-014 归档文档；以本批结论取代其 R-3 拒绝表述
- [x] 新文档不含私网地址、真实端口或密钥
- [x] RESEARCH/DESIGN/IMPLEMENTATION/CHECKLIST 的 C/D/U 编号互相引用
- [x] 外部文档只作概念引用，未复制全文

## 4. 机检

- [x] V1 `dc_validator` → 0 违规
- [x] V2 `step-gate` → 5/5 pass
- [x] V3 `console_gen --check` → 一致
- [x] V4 `private_config_check` → exit 0
- [x] V5 `step_enforce --base HEAD` → mode=batch, exit 0

## 5. 未纳入本批

- R-3a 依赖清单/内容哈希/保守闭包
- R-3b 补偿注册表/pivot 标记
- R-3c Temporal/Saga 适配器与基准
- 并发/恢复 SLA/成本/checkpoint 损坏实测
