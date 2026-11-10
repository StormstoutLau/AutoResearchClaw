---
id: arc-g1b-supervisor-protocol-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1b-supervisor-protocol-DESIGN]
upstream: arc-g1b-supervisor-protocol-DESIGN
---

# 实施记录：G1b 调研批

> 本批为**调研批**：只产出决策依据与待实施契约，**未写代码**。

## 1. 执行步骤

| # | 步骤 | 动作 |
|---|---|---|
| S-1 | 现状取证 | CLI 子命令、`_call_with_retries`、`StageResult`、`StageStatus`、`stage-NN_v{k}` 先例、路由清单 |
| S-2 | 外部检索 | 3 轮 WebSearch：crash-only/microreboot、AWS 全抖动、systemd/K8s 重启策略、SSE 规范、Temporal 重试策略、outbox/幂等消费者、Stripe 幂等键、SRE 重试预算 |
| S-3 | 方案对比 | 四个子问题各 3 方案，给出推荐与理由 |
| S-4 | 契约设计 | 退出码表、supervisor 循环、三层状态与 `attempt.json`、SSE/WS 语义、outbox 事件形态 |
| S-5 | 落档 | 四文档；结论见 DESIGN §1 D-1..D-9 |

## 2. 产出

| 文件 | 内容 |
|---|---|
| `spec/arc-g1b-supervisor-protocol/RESEARCH.md` | 10 项现状、10 锚点、四子问题方案空间与建议 |
| `spec/arc-g1b-supervisor-protocol/DESIGN.md` | D-1..D-9、退出码契约、supervisor 伪代码、attempt 模型、SSE/WS/outbox、验收映射、风险 |
| `spec/arc-g1b-supervisor-protocol/CHECKLIST.md` | 调研质量与边界自检 |

## 3. 边界声明

- [x] 未修改 `researchclaw/` 任何代码
- [x] 未新增 CLI 子命令、未新增路由
- [x] 未修改 `arc-master-roadmap.md`（G1b 状态待实施批更新）
- [x] 未改门禁与 `SPEC_PROCESS.md`
- [x] 外部锚点标注等级；T1 为主

## 4. 关键结论（供实施批直接引用）

1. **退出码契约先行**：它是 supervisor 与 worker 的唯一接口，可脱离进程单测；未识别错误默认 `75`（保守）。
2. **attempt 与 `_v{k}` 分离**：语义回滚快照 ≠ 执行重试记录，混用会让目录含义漂移。
3. **缺口必须显式**：`after` 早于最旧段时返回 `stream.gap`，而不是静默从最旧段开始——否则「无缺口」断言无法证伪。
4. **outbox 不需要事务**：G1a 的追加日志本身就是入队点，`effect.queued` + `(kind,key)` 去重即可获得至少一次 + 幂等。
5. **重试预算**：supervisor 的 `max_restarts=5` / 30 分钟是 SRE 重试预算思想的本地化，防止自愈变成重试风暴。

## 5. 机检

| # | 检查 | 结果 |
|---|---|---|
| V1 | `dc_validator` 四文档 | 0 违规 |
| V2 | `step-gate --expect` | 5/5 pass |
| V3 | `console_gen --check` | 一致 |
| V4 | `private_config_check` | exit 0 |
| V5 | `step_enforce --base HEAD` | exit 0 |
