---
id: arc-g1-readiness-research-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1-readiness-research-DESIGN]
upstream: arc-g1-readiness-research-DESIGN
---

# 实施记录：G1 前置调研（Q5/Q9）

> 本批为**调研批**：只产出决策依据与设计契约，不写代码、不改总纲。

## 1. 执行步骤

| # | 步骤 | 动作 |
|---|---|---|
| S-1 | 现状取证 | Grep/Read：`runner.py`（checkpoint/heartbeat）、`run_state.py`、`websocket/manager.py`、`cost_tracker.py`、四类 JSONL 先例 |
| S-2 | 量级估计 | 由 `cost_log.jsonl`「每 LLM 调用一行」外推单 run 事件量 10²–10³、体积 0.5–2 MB |
| S-3 | 外部检索 | 4 轮 WebSearch：SQLite WAL/适用边界、PostgreSQL fsync、Kleppmann fencing、Kafka 保留、PCI DSS 10.7、NIST SP 800-92、GDPR Art.5、事件溯源快照 |
| S-4 | 方案构造 | Q5 三方案、Q9 三方案，各 6–8 维权重量化 |
| S-5 | 落档 | 四文档；结论 Q5=A、Q9=A（待裁决） |

## 2. 产出

| 文件 | 内容 |
|---|---|
| `spec/arc-g1-readiness-research/RESEARCH.md` | 10 项现状事实、16 项外部锚点、6 维/8 维判定矩阵、建议 |
| `spec/arc-g1-readiness-research/DESIGN.md` | EventEnvelope v1、写入协议、租约/fencing、保留/滚动状态机、验收映射 |
| `spec/arc-g1-readiness-research/CHECKLIST.md` | 调研质量与边界自检 |

## 3. 边界声明

- [x] 未修改 `researchclaw/` 任何代码
- [x] 未创建 `events.jsonl` / `lease.json` / `events_summary.json`
- [x] 未修改 `arc-master-roadmap.md`（Q5/Q9 状态仍为待确认）
- [x] 未修改 `SPEC_PROCESS.md` / 门禁配置
- [x] 外部锚点均标注等级；T3 单源仅作反例，不作最佳实践依据

## 4. 关键发现（供 G1 开工直接引用）

1. **既有 fsync 缺口**：`cost_log.jsonl` 只 `flush()` 不 `fsync()`（`cost_tracker.py:224-234`）——G1 若复用该写入器需同步修正，否则「已记录」承诺不成立。
2. **WS 丢事件**：`QueueFull` 直接丢弃（`manager.py:67-78`）——A1-2 的「无缺口」必须先解决该丢弃路径。
3. **heartbeat 非原子**：`runner.py:133-135` 直接 `write_text`，与 checkpoint 的原子写不一致，G1 应统一。
4. **事件日志即 outbox** 可省掉数据库事务，是选 A 的最强论据（RESEARCH X-4/X-5 反向约束 fsync 语义）。

## 5. 机检

| # | 检查 | 结果 |
|---|---|---|
| V1 | `dc_validator` 四文档 | 0 违规 |
| V2 | `step-gate --expect` 5 步 | pass |
| V3 | `console_gen --check` | 一致 |
| V4 | `private_config_check` | exit 0 |
| V5 | `step_enforce --base HEAD` | exit 0 |
