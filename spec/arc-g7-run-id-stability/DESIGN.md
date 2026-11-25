---
id: arc-g7-run-id-stability-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-g7-run-id-stability-RESEARCH, arc-g7-field-run-decision-20261125]
upstream: arc-master-roadmap
---

# 设计：run_id 稳定性与 A7-1 现场适配（P-174）

## 1. 决策表

| ID | 决策 | 被拒替代 | 理由 |
|---|---|---|---|
| D-1 | 显式 `--output` 时 `run_id = run_dir.name` | 每次生成时间戳 id | E1/E2：目录是用户声明的身份；重试不得换实体 |
| D-2 | 重启/`--from-stage` 沿用同一 `run_id` | 在 mandate 里覆盖 id | 覆盖会丢历史；稳定 id 让 mandate/事件/verify 自然一致 |
| D-3 | 默认 `artifacts/<rc-ts-hash>` 路径仍用生成 id | 全部改成目录名 | 保持既有 CLI 行为与测试 |
| D-4 | A7-1 分两阶段启动：阶段 1-3 到 `--to-stage search_strategy`，seed 英文 queries 后再 `--from-stage literature_collect` | 一次跑到 Stage 5 再人工重跑 | 减少一次 PAUSED 与无谓 LLM 调用；两阶段同一 run_id |
| D-5 | `research.domains` 补英文域词（liquid neural networks / change point detection / time series / finance 等） | 改 topic 为英文 | 保留中文提案主题；只影响 Stage 5 关键词预过滤 |
| D-6 | 现场干预写入 field decision 与 CHECKLIST，不计入注入重启 | 静默修正 | 诚实边界；A7-1 的无人值守声明需另跑不干预 run |

## 2. 程序流程

```
cmd_run:
  run_id ← generate(topic)
  run_dir ← Path(output or artifacts/run_id)
  if output: run_id ← run_dir.name        # D-1
  ... resume/from-stage 搜索仅在无 output 时生效
  execute_pipeline(run_dir, run_id, ...)
```

- 两阶段启动复用同一 `--output`，因此 `run_id` 不变；事件链连续。
- `ensure_run_mandate` 不再报 id 不一致；`verify_run(expected_run_id=None)` 以目录名匹配。

## 3. 不变式

| ID | 不变式 |
|---|---|
| J-1 | `--output` 的 `run_id` 恒等于目录名 |
| J-2 | 同一目录的两次 `run`（含 `--resume/--from-stage`）`run_id` 相同 |
| J-3 | 默认无 `--output` 的 `rc-*` id 格式不变 |
| J-4 | 事件 `run_id`、`checkpoint.json.run_id`、mandate 的 `run_id` 三者一致 |
| J-5 | 现场两阶段（1-3 / 4-23）使用同一 id，`verify_run` 无 `run_id_mismatch` |
| J-6 | 现场干预不改验收判据 |

## 4. 错误语义

| 场景 | 行为 |
|---|---|
| `--output` 目录已存在且有 mandate | 沿用同一 id，不再抛 `MandateError` |
| `--output` 是相对路径 | `run_dir.name` 取最后一段 |
| `--output` 为空 | 走原 `artifacts/<generated>` 路径 |
| 两阶段之间 crash | 第二阶段仍用同一目录名，事件链继续 |
