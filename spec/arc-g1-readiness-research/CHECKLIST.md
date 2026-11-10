---
id: arc-g1-readiness-research-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-10
depends: [arc-g1-readiness-research-IMPLEMENTATION]
upstream: arc-g1-readiness-research-IMPLEMENTATION
---

# 验收清单：G1 前置调研（Q5/Q9）

## 1. 调研完整性

- [x] Q5 与 Q9 各自拆出「现状 → 方案空间 → 判定矩阵 → 建议」
- [x] 现状事实 10 项，均有文件与行号
- [x] 事件量级有推导过程（由 `cost_log.jsonl` 外推），非拍脑袋
- [x] Q5 三方案、Q9 三方案，均给加权分与权重说明
- [x] 反向证据单列（fsync 不可重试、SQLite 写锁整库级）
- [x] 明确「不选 B/C」的理由与「何时改选 B」的触发条件

## 2. 锚点质量

- [x] 锚点 16 项，覆盖 Q5（9）与 Q9（7）
- [x] T1 官方/标准占比 ≥ 60%（SQLite/PostgreSQL/Kafka/PCI/NIST/GDPR/Azure/MS Learn）
- [x] T3 单源（SQLite 队列压测、事件溯源博客）仅作反例，未作为最佳实践唯一依据
- [x] 每条锚点给出可回源 URL 或仓内路径
- [x] 注明「未回原文」的项（无）

## 3. 设计可实施性

- [x] `EventEnvelope v1` 字段完整，链定义可机械实现
- [x] fsync 失败处置明确（不重试 → FAILED），与 X-4/X-5 一致
- [x] 租约与 fencing 字段完整（A1-4）
- [x] 保留/滚动/归档三态与阈值明确（A1-6）
- [x] 摘要文件保留链头尾 digest，归档后仍可验证
- [x] 与既有 `checkpoint.json` / `heartbeat.json` / `cost_log.jsonl` 的接缝写明
- [x] 回滚路径明确

## 4. 边界

- [x] 未改 `researchclaw/` 代码
- [x] 未创建运行期产物（`events.jsonl` 等）
- [x] 未改总纲（Q5/Q9 仍「待确认」）
- [x] 未改门禁与 `SPEC_PROCESS.md`

## 5. 机检

- [x] V1 `dc_validator` 四文档 → 0 违规
- [x] V2 `step-gate --expect` → 5/5
- [x] V3 `console_gen --check` → 一致
- [x] V4 `private_config_check` → exit 0
- [x] V5 `step_enforce --base HEAD` → exit 0

## 6. 裁决后的下一批

- [ ] 总纲 Q5/Q9 状态更新为「已裁决」
- [ ] G1 开工批：事件层（`events.jsonl` + fsync + 链哈希）、租约、supervisor
- [ ] 修正 `cost_log.jsonl` 缺 fsync（本批 §4-1）
- [ ] 修正 WS `QueueFull` 丢弃（本批 §4-2）
