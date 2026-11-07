---
id: arc-roadmap-gaps-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-07
depends: [arc-roadmap-gaps-IMPLEMENTATION]
upstream: arc-roadmap-gaps-IMPLEMENTATION
---

# 验收清单：盲区调研

## 1. 调研完整性

- [x] 八维评分覆盖目标、依赖、可判定性、门禁、交付物、证据、治理、成本
- [x] 6 条结构性缺口（P0-1..P1-6）每条都有总纲行号或代码事实
- [x] 8 条执行盲区（B-1..B-8）每条都有“后果”而非仅描述
- [x] 12 项外部锚点：标准 6、论文 4、工程文档 2
- [x] 每条锚点含可访问来源 URL 与“结论要点”
- [x] 采用矩阵覆盖全部 12 项，且区分“采用 / 只借语义 / 拒绝”
- [x] D-1..D-7 明确标注“未执行”，未与已批准变更混淆
- [x] 与前序运行时审计衔接：A3-7 与 GAP-1 相互引用

## 2. 证据可复现

- [x] C 套件差集可由 RESEARCH §6 脚本重放，输出 15 条
- [x] 106 条验收在 `tests/` 无映射（检索零命中，会话文件除外）
- [x] 预算字段事实：`cost_budget_usd` 默认 0、`max_budget_usd` 默认 5.0
- [x] 状态模型事实：`StageAttempt/RunMandate/StageHandback/prompt_version` 全仓零命中
- [x] CI 载体事实：三 job 均 `ubuntu-latest`，无 `timeout-minutes`
- [x] 认证默认值事实：`host=0.0.0.0`、`auth_token=""`、`cors_origins=("*",)`

## 3. 边界与一致性

- [x] 未修改 `arc-master-roadmap.md`（V4 为空 diff）
- [x] 未修改任何代码与配置
- [x] 论文只用于方法论，未作为验收判据
- [x] D-1/D-2 标注为“需裁决”，未擅自改变阶段出口
- [x] 106 条验收计数不变

## 4. 机检

- [x] V1 `dc_validator`（spec 作用域）0 违规
- [x] V2 `step-gate` 五步齐全
- [x] V3 `console_gen --check` 退出码 0
- [x] V4 `git diff --stat HEAD -- arc-master-roadmap.md` 无输出
- [x] V5 差集脚本输出 15 条

## 5. 未纳入本批

- D-1..D-7 的实际修改（需裁决后另开批次）
- 72h soak、kill -9、多 run 并发的实测
- G5 语料仓的路径与版本盘点
