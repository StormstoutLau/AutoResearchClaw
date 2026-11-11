---
id: arc-g3-m0-design-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-11
depends: [arc-g3-m0-design-IMPLEMENTATION]
upstream: arc-g3-m0-design-IMPLEMENTATION
---

# 验收清单：G3 M0 设计冻结（P-074）

## 1. M0 DoD

- [x] Q-1..Q-9 决策全部纳入设计（§2 决策落点表）
- [x] O-1..O-6 观察全部纳入（vendor 词表、断链修法、cap_reasons、绑定表、事件链排期、plan_sig 字段）
- [x] 六组接口冻结：ArtifactNode、summary、stage_events、claim 脊柱、治理、K5/retrieval
- [x] 20 个验收 ID 全部映射到 M1..M5（DESIGN §10）
- [x] 错误码表冻结（10 个 `E_*`）
- [x] 施工顺序与文件计划冻结（IMPLEMENTATION §3）
- [x] 编号顺延：M0=P-074、M1..M5=P-075..P-079

## 2. 接口完整性

- [x] `ArtifactNode` 字段/哈希/指针规则/投影完整
- [x] `pipeline_summary` JCS+侧车+M2 事件链两阶段完整
- [x] `stage_events` 字段与 `plan_sig`/`new_rows`/`network_error` 取数完整
- [x] Claim 三出口（14/17/22）+ Stage 20/23 复用关系完整
- [x] `RunMandate`/`StageHandback`/`prompt_version` 完整
- [x] K5 文法与 `retrieval_degraded` 标注完整

## 3. 不变式

- [x] 不改 C4 schema、判定内核、M0–M4 契约
- [x] 词表单一真值源（vendor `CitationLabel` + `CURRENT_POLICY_VERSION`）
- [x] 所有落盘原子写；校验只读
- [x] 正常 1:1 claim/decision 不触发新增错误；续跑语义不变

## 4. 机检

- [x] DC 契约校验通过（四文档 front-matter + 内部链接）
- [x] `step_enforce` exit 0（P-074 session 5/5）
- [x] `roadmap_coverage_check.py --check` accept=106 missing=0
- [x] `repo_stats --check` / `console_gen --check` 一致

## 5. 未纳入本批

- [ ] 生产代码与测试（M1 P-075 起）
- [ ] ArtifactNode/claim_export schema 文件落地
- [ ] 事件链 `pipeline.summary` 扩展（M2）
- [ ] 多 run 并发/跨平面长期审计（G7）
