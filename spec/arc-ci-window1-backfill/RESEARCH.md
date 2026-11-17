---
id: arc-ci-window1-backfill-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-17
depends: [arc-ci-post-window-order-RESEARCH, arc-ci-heavy-fixes-CHECKLIST, arc-ci-heavy-schedule-RESEARCH]
upstream: null
---

# 回填：Heavy 窗口 1 读数与 schedule 延迟诊断（P-138）

> **Feature**：P-138。兑现 `spec/arc-ci-post-window-order/RESEARCH.md` §4 的窗口核对项，并把「7h36m 延迟」的诊断与合并预演结果落档。
> **性质**：T3 单文档回填/分析；零代码、零测试、零 workflow。
> **结论先行**：① 窗口 1 的 `event=schedule` run 最终触发（延迟 7h36m）且 success，日志三项全部干净；② 延迟最可能是 GitHub 调度器的 best-effort 行为，不是 cron 写法、workflow 禁用、分支错误或平台事故；fork 因素未证实；③ 三层合并预演（P-135 → P-136 → P-137）成功，冲突只出现在 PROGRESS 与派生视图，按「保留全部行 + 重生成」即可；④ 窗口 2 改为全天多次核对，不再定点 02:17。

## 1. 窗口 1 读数

### 1.1 schedule run（最终成立）

| 项 | 读数 |
|---|---|
| run id | `43998910996` |
| event | `schedule` |
| headSha | `6dfd47e`（main） |
| 创建/开始 | 2026-11-17 01:53:11 UTC（北京 09:53） |
| 完成 | 2026-11-17 01:53:47 UTC（36s） |
| conclusion | `success` |
| 延迟 | 预期 2026-11-16 18:17 UTC ⇒ **7h36m** |
| run_attempt | 1 |

日志检查：

- `concurrency_key=heavy-Heavy-schedule-refs/heads/main`：True
- `2 passed, 3784 deselected, 1 warning in 8.23s`：True
- `Invalid response file`：False
- `HITL poll timeout`：False
- `keeper 必须在租约丢失时回调`：False

### 1.2 兜底 dispatch

| 项 | 读数 |
|---|---|
| run id | `43938974192` |
| event | `workflow_dispatch` |
| headSha | `6dfd47e` |
| 创建/完成 | 2026-11-16 19:24:16 UTC → 19:24:51 UTC（35s） |
| conclusion | `success` |

日志同样含 `concurrency_key=heavy-Heavy-workflow_dispatch-refs/heads/main` 与 `2 passed, 3784 deselected in 7.33s`，三个失败签名均 False。

## 2. 延迟诊断

### 2.1 已排除

| 假设 | 读数 | 结论 |
|---|---|---|
| workflow 被禁用 | `gh workflow list --all`：Heavy `active` | 排除 |
| 文件不在默认分支 | `.github/workflows/heavy.yml` 在 main，run 的 headSha=6dfd47e | 排除 |
| 60 天无活动自动禁用 | 仓库 11-16 仍有 push（pushed_at 16:04 UTC） | 排除 |
| cron 落在整点高负载 | cron 分钟为 17 | 排除（但非充分条件） |
| 平台事故 | GitHub Status 该窗口仅 minor「Incident with Pull Requests」11:59–16:26 UTC，无 Actions 事故 | 排除 |
| 已创建但排队 | `created_at` = `run_started_at` = 01:53:11 | 排除；是调度器晚创建 |

### 2.2 剩余解释

1. **GitHub 调度器 best-effort 延迟**：官方文档明确 scheduled runs 可延迟、整点为高负载、queued jobs 可能被 drop；社区实测每小时 cron 在 115 个槽位仅触发 22 次，缺口 2h35m–8h33m，7h36m 落在该区间。
2. **fork 因素（未证实）**：仓库是 fork（parent `aiming-lab/AutoResearchClaw`）；GitHub 对 fork 的 workflows 默认禁用，但本 fork 已启用 Actions 且 schedule 能运行；parent 无 schedule workflows 可对照。现有证据不足以证明 fork 额外增加数小时延迟。
3. **仓库/组织级负载**：无直接读数，与 (1) 同类，不单列。

### 2.3 结论与动作

- 最可能原因：**调度器 best-effort 延迟**；不是配置错误。
- weekly heavy 任务可接受该延迟（最终成功、日志干净），但**不能把 cron 时刻当作观测不变式**。
- 不在窗口 2 前修改 cron：分钟 17 已避开整点，改时间不能消除 best-effort 延迟；若未来需要精确时刻，改用外部调度器调用 `workflow_dispatch`，但那是另一种 event，不能替代 schedule 读数。

## 3. 合并预演（本地，不推送）

按「P-135 → P-136 → P-137」顺序在临时分支上模拟 squash + rebase：

| 步骤 | 冲突 | 解决 |
|---|---|---|
| P-135 squash | 无 | 直接提交 |
| P-136 rebase | `docs/PROGRESS.md`、`docs/CONSOLE.md` | PROGRESS 保留 P-135/P-136 两行；CONSOLE 取 ours 后重生成 |
| P-137 rebase | `docs/PROGRESS.md`、`docs/CONSOLE.md`、`docs/REPO_STATS.md` | PROGRESS 保留三行；两个派生视图重生成 |

最终读数：

- PROGRESS 行序：P-135 → P-136 → P-137
- dc_validator 三个 feature 零命中
- grandfather `0/0/0`
- step-gate 3/3、verify-anchor 3/3
- pre-commit 10 钩子全绿
- 工作树干净；临时分支已删除

**结论**：P-137 §5 的冲突预案可执行；正式合并时按同一路径处理即可。

## 4. 窗口 2 核对方案

- 预期：2026-11-23 18:17 UTC（北京 2026-11-24 02:17）
- 鉴于本次延迟 7h36m，核对改为**全天多次**：从北京 11-24 09:00 起，至少检查 09:00、12:00、18:00、23:00 四个时点
- 判据：`event=schedule`、`headSha` 为当时 main、`concurrency_key=heavy-Heavy-schedule-refs/heads/main`、`2 passed`、三个失败签名不存在、结论非 cancelled
- 若全天无 run：才升级为「schedule 触发失效」，并评估外部调度或 cron 调整
- 若延迟仍达数小时：视为已证实的调度器行为，不判红

## 5. 编号与接缝

| 编号 | 内容 | 状态 |
|---|---|---|
| P-135 | midpoint 文档入库 | PR #17，合并押后 |
| P-136 | U-3/U-2 调研 | PR #18，合并押后 |
| P-137 | 窗口后执行顺序 | PR #19，合并押后 |
| P-138 | 本回填 | 本文件，合并押后 |
| P-139 | U-3/U-2 实施 | 未立项，窗口 2 后 |
| P-140 | 移出 heavy | 未立项，U-1 满足后 |

本批不修改 P-137 的正文；P-137 §7 的编号表由本表接续（P-138 回填、P-139 实施、P-140 移出）。

## 6. 未决项

| ID | 内容 | 判据 | 当前倾向 | 证据等级 |
|---|---|---|---|---|
| U-1 | fork 是否加剧 schedule 延迟 | parent 无 schedule，需更多样本 | 暂不归因 fork | E1 |
| U-2 | 7h36m 是否为单次异常 | 窗口 2 的延迟量级 | 单次样本，不下结论 | E1 |
| U-3 | 是否改用外部调度 | 精确时刻需求是否出现 | 不改；weekly heavy 可接受 | E1 |
| U-4 | dispatch 兜底是否保留 | 窗口 2 若再次长延迟 | 保留，作为观测兜底 | E1 |

## 7. 诚实边界

- 本批只回填读数与诊断，不修改 `heavy.yml`、不合并任何 PR、不改代码。
- 延迟结论基于单次样本与外部案例，不是受控实验。
- fork 因素未证实；parent 无 schedule 可对照。
- 预演在本地临时分支完成，正式合并仍需按 PR 流程复跑门禁与检查。
