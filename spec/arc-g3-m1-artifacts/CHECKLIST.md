---
id: arc-g3-m1-artifacts-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-11
depends: [arc-g3-m1-artifacts-IMPLEMENTATION]
upstream: arc-g3-m1-artifacts-IMPLEMENTATION
---

# 验收清单：G3 M1 ArtifactNode 与 summary 校验（P-075）

## 1. ArtifactNode / 血缘

- [x] 每个注册的 DONE 阶段产物有节点，`content_hash` 可复算（AN-1 内核）
- [x] `parent_ids` 可解析、无环（AN-2）
- [x] `inputs_digest = hash(sorted parent content_hash + params)`（AN-3）
- [x] `node_id` 由 type/locator/hash 确定性生成
- [x] 小文本入 `artifacts/blobs/`；敏感/大文件/二进制只存指针
- [x] `sensitive=true` 不得 materialized
- [x] 重复注册幂等；缺文件跳过
- [x] runner DONE 路径已接线（test_rc_runner 回归通过）

## 2. Summary 校验

- [x] canonical compact JSON + `.sha256` 侧车原子写
- [x] `verify_summary` 侧车双向核对
- [x] 手改 summary 不重写侧车 → `E_SUMMARY_TAMPERED`
- [x] 侧车/摘要缺失 → 明确错误
- [x] `require_event=True` 的事件锚定接口就绪（M2 启用）
- [x] runner `_write_pipeline_summary` 已改为侧车写入

## 3. 测试

- [x] `tests/test_artifact_node.py` 13 项
- [x] `tests/test_pipeline_summary_check.py` 8 项
- [x] 合计 21 passed（3.13.5 与 3.11.15）
- [x] runner/checkpoint/kb/report 回归 92 passed
- [x] 两个测试文件加入 CI 固定清单

## 4. 验收边界

- [x] AN-1/AN-2/AN-3：M1 全链
- [x] AN-4：投影 API + digest 覆盖（旧 fixture 全量回归留 M3）
- [x] AN-5/AN-6：节点侧规则（导出/预览过滤留 M3/M5）
- [x] A3-2：侧车双向（事件链三向留 M2）

## 5. 机检

- [x] DC 契约通过（四文档）
- [x] `step_enforce` exit 0（P-075 session 5/5）
- [x] `roadmap_coverage_check.py --check` accept=106 missing=0
- [x] `repo_stats --check` / `console_gen --check` 一致

## 6. 未纳入本批

- [ ] 事件链三向校验（M2 P-076）
- [ ] 旧 AR-01 fixture 全字段投影回归（M3 P-077）
- [ ] 导出/预览敏感过滤、inline_copy 上限（M3/M5）
- [ ] 精细语义父边（PIVOT 分支）与 `attempt` 版本化（M3）
