---
id: arc-g1a-event-core-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-10
depends: [arc-g1a-event-core-IMPLEMENTATION]
upstream: arc-g1a-event-core-IMPLEMENTATION
---

# 验收清单：G1a 事件内核

## 1. 交付物

- [x] `researchclaw/runtime/event_log.py`（信封/链/fsync/滚动/配额/保留/摘要/重放/重建）
- [x] `researchclaw/runtime/lease.py`（独占/续期/释放/fencing 单调）
- [x] `runner.py` 接入（阶段事件、run 收口、递归守卫）
- [x] `heartbeat.json` 原子写
- [x] `read_checkpoint` 事件重建路径
- [x] 三份测试文件（24 用例）

## 2. 验收（A1-1 / A1-4 / A1-5 / A1-6）

- [x] A1-1 链哈希可校验；中间行篡改必失败；尾行由 `chain_tail` 兜底
- [x] A1-4 异 owner 抢占被拒；过期/释放后接管 fencing 递增
- [x] A1-5 损坏 checkpoint → 事件重建 → `recovered:true` → 返回下一阶段
- [x] A1-6 段滚动 + 单 run 配额 + 归档/删除
- [x] Q9 参数（30/365/摘要永久）落地并可配置

## 3. 不变式

- [x] fsync 失败不重试，抛 `EventDurabilityError`
- [x] 撕裂尾行丢弃后续写，seq 不跳号
- [x] 事件 payload 不含原文/凭据
- [x] 递归 PIVOT/REFINE 不重复 `run.started`、不提前释放租约
- [x] `checkpoint.json` 权威地位不变（事件是投影）

## 4. 机检

- [x] V1 G1a 单测 24 passed
- [x] V2 回归 106 passed（runner/checkpoint/run_state）
- [x] V3 `pre-commit run --all-files` 9/9
- [x] V4 `step_enforce --base HEAD` exit 0
- [x] V5 `test_packaging` / `test_docs_and_adapters` 无回归

## 5. 未纳入本批（G1b）

- [ ] A1-2 SSE / `Last-Event-ID` / 游标 API
- [ ] A1-3 supervisor 拉起
- [ ] A1-7 退出码分类
- [ ] A1-9 `StageAttempt` + session 续接
- [ ] A1-10 outbox
- [ ] A1-11 三层状态模型
- [ ] A1-12 `resume_note`
