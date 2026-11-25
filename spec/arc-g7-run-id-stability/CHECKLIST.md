---
id: arc-g7-run-id-stability-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-25
depends: [arc-g7-run-id-stability-IMPLEMENTATION, arc-g7-run-id-stability-DESIGN]
upstream: arc-master-roadmap
---

# 审查验收 Checklist：run_id 稳定性与 A7-1 现场适配（P-174）

> **状态**：**17/18 通过 + 1 待现场**（C-3 72h 未启动，不伪绿；C-2 两轮 CI 8/8）。
> **计数**：**18 项 = 文档 4 + 功能 5 + 接口 2 + 不变式 3 + 错误 1 + 兼容 3**。

## 1. 文档一致性

| 检查项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| D-1 RESEARCH 回原文 | RESEARCH v1.0 | E1-E2 含 URL/要点 | ✅ | §2 两条 |
| D-2 DESIGN 覆盖实现 | 四文档 | D-1..D-6 有落点 | ✅ | D-1..D-6 ↔ IMPLEMENTATION §1 |
| D-3 IMPLEMENTATION 源码锚点 | 四文档 | ≥5 锚点 | ✅ | §1 表 4 行 + 现场表 |
| D-4 术语一致 | 四文档 | run_id/名称/幂等键同义 | ✅ | 四文档一致 |

## 2. 功能验收

| 验收项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| F-1 `--output` 的 run_id=目录名 | T-C1 | `g7-baseline` | ✅ | `test_output_dir_name_is_the_stable_run_id` |
| F-2 重启沿用同一 id | T-C1 + 现场 | 两阶段 checkpoint 同 id | ✅ | B 站 `checkpoint.json`、`events.jsonl` |
| F-3 三方一致 | 现场 | mandate/事件/checkpoint | ✅ | 现场 `run_id=g7-baseline`；mandate 无报错 |
| F-4 两阶段同 id | 现场 | stage 1-3 与 4-23 | ✅ | 两次启动均 `--output g7-baseline` |
| F-5 默认路径不变 | 既有用例 | `artifacts/rc-*` 仍生成 | ✅ | `test_generate_run_id_format` + 全量回归 |

## 3. 接口验收

| 验收项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| I-1 CLI 行为 | DESIGN §1 | 仅 `--output` 分支改变 | ✅ | [cli.py L243-L251](../../researchclaw/cli.py#L243-L251) |
| I-2 回归用例 | DESIGN §2 | 断言 run_id/run_dir | ✅ | [test_rc_cli.py L364](../../tests/test_rc_cli.py#L364) |

## 4. 不变式

| 不变式 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| J-1 `--output` id=目录名 | DESIGN §3 | 单测 + 现场 | ✅ | F-1/F-2 |
| J-2 两次 run 同 id | DESIGN §3 | 事件链连续 | ✅ | 现场 events 前两行同 id |
| J-3 事件/checkpoint/mandate 一致 | DESIGN §3 | 无 MandateError | ✅ | 现场日志无 mandate 报错 |

## 5. 错误处理

| 场景 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| E-1 已存在 mandate 不报错 | DESIGN §4 | 沿用同 id | ✅ | 现场两阶段启动 |

## 6. 兼容性与现场

| 环境/项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| C-1 本机 3.13 | 3.13.5 | 定向 + 全量 | ✅ | 61 passed；全量 3953 passed / 6 环境态 |
| C-2 CI 3.11–3.14 | CI 矩阵 | 两轮 8/8 | ✅ | run `45608919405` attempt 1 & 2：8/8 全 success |
| C-3 A7-1 72h 现场 | 基线收敛后启动 | wall≥259200、restarts≥3 | ⏳ 待现场 | 基线运行中；72h 未启动，不伪绿 |

## 7. 诚实边界

1. 两次现场干预（seed queries / 英文 domains）已记录，不计作注入重启；A7-1 的无人值守需后续不干预 run 复核。
2. 基线尚未完成，72h field run 未启动。
3. 本批只改 `--output` 分支，默认路径行为不变。

## 8. 批次自审（ADD）

| 项 | 级别 | 内容 | 处置 |
|---|---|---|---|
| P3-1 | low | `run_dir.name` 对以 `.`/`..` 结尾的路径可能异常 | 现有 CLI 不接受此类路径；不额外校验 |
| P3-2 | medium | 现场两次人工干预削弱「无人值守」证据 | 记录并在后续不干预 run 复核 |

## 9. 门禁读数

| 门禁 | 读数 |
|---|---|
| `dc_validator` | 4 文件 / 0 结果 / **0 违规** |
| `step-gate` | **5/5 pass** |
| `verify-anchor` | **10 真实 / 0 硬性 / 0 软性** |
| `step_enforce` | `mode=batch pid=P-174 digest_bound=1` |
| `pre-commit` | **10/10 Passed**（含 private-config 脱敏后） |
| 两轮 CI | run `45608919405` attempt 1 & 2，**8/8 success** |
