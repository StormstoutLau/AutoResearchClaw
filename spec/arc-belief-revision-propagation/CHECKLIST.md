---
id: arc-belief-revision-propagation-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-10
depends: [arc-belief-revision-propagation-IMPLEMENTATION]
upstream: arc-belief-revision-propagation-IMPLEMENTATION
---

# 验收清单：信念修正与多步传播调研

## 1. 调研完整性

- [x] 场景 A 的触发面、回退链、留痕能力有代码事实（`runner.py`/`stages.py`/`_analysis.py`）
- [x] 场景 A 的 7 项缺陷（A-1..A-7）逐条有证据与后果
- [x] 场景 B 的 5 条注入通道与 5 项传播缺口（B-1..B-5）有代码位置
- [x] 项目内既有调研覆盖表（failure-guards、G1/G3/G7、评测计划）完整
- [x] 外部锚点 ≥12 项，含 Saga、durable execution、backjumping、provenance、HARKing、living review
- [x] 每条锚点标验证状态（✅ 已抓取 / ⚠️ 二手书目）
- [x] `F:\Spec_Workflow\spec\academic-writing-workflow` 的复用/不复用清单与结论明确
- [x] 差距矩阵覆盖触发、目标、影响集、留痕、恢复、传播、收敛、外部过期
- [x] R-1/R-2/R-3 有成本、收益、风险与明确建议

## 2. 设计输入

- [x] `revision_log.json` 字段含 trigger/premise/impact_set/target/old/new/evidence/operator/convergence
- [x] `revision_targets` 覆盖研究问题、假设、实验设计、执行、分析、论文 claim
- [x] 评审响应表包含意见、类型、受影响 claim/产物、改动锚点、验证证据、状态
- [x] 收敛判据含轮次上限、每轮消解项、kill criteria、人工升级
- [x] 明确不引入 Saga/Temporal/DAG 引擎
- [x] 明确不复制外部文档全文、不引入外部脚本

## 3. 边界与一致性

- [x] 未修改 `arc-master-roadmap.md`
- [x] 未修改 `researchclaw/` 代码
- [x] 未修改 P-011/P-012/P-013 归档文档
- [x] 新文档不含私网地址、真实端口或密钥
- [x] RESEARCH ↔ DESIGN ↔ IMPLEMENTATION ↔ CHECKLIST 的 A/B/U 编号互相引用且不悬空
- [x] 外部文档以“概念/矩阵/模板”复用，未照搬结论作为本仓事实

## 4. 机检

- [x] V1 `dc_validator` → 0 违规
- [x] V2 `step-gate` → 5/5 pass
- [x] V3 `console_gen --check` → 一致
- [x] V4 `private_config_check` → exit 0
- [x] V5 `step_enforce --base HEAD` → mode=batch, exit 0

## 5. 未纳入本批

- R-1 最小修复（checkpoint/to_stage/revision_log/targets）
- R-2 标准修复（Stage 20 拒绝回退、评审响应表、影响集）
- U-1 影响集自动闭包
- U-2 外部评审分类实测
- U-3 收敛阈值实测
- U-4 外部过期重检
- U-5 revision record 实现
- U-6 外部文档复用评审
