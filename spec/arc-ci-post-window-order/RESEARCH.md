---
id: arc-ci-post-window-order-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-17
depends: [arc-ci-heavy-followups-RESEARCH, arc-g4-midpoint-intake-RESEARCH, arc-ci-heavy-fixes-CHECKLIST]
upstream: null
---

# 分析：heavy 观察窗口结束后的执行顺序（P-137）

> **Feature**：P-137。把「窗口核对 → 合并 P-135/P-136 → U-3/U-2 实施 → 移出 heavy」的顺序、目的与依据落档。
> **性质**：T3 Layer-0 单文档分析；零代码、零测试、零 workflow。
> **结论先行**：顺序不可交换。窗口用于证明修复有效；P-135 用于让基线可重现；U-3/U-2 实施必须等窗口结束，否则污染归因；移出 heavy 必须最后，否则红灯会阻塞所有 PR。

## 1. 当前批次状态（2026-11-17 00:02 北京）

| 批次 | 内容 | 提交 / PR | 状态 | 合并 |
|---|---|---|---|---|
| P-134 | F-1/F-2 修复 | `6dfd47e`（main） | 已合并 | — |
| P-135 | midpoint 文档入库 + 勘误横幅 | `26d1bbe` / PR #17 | 8/8 检查 pass，`MERGEABLE / CLEAN` | **押后** |
| P-136 | U-3/U-2 调研 | `76261a0` / PR #18 | 8/8 检查 pass，`MERGEABLE / CLEAN` | **押后** |
| P-137 | 本分析 | 本文件 | 待合并 | 押后 |
| P-138 | U-3/U-2 实施（下一可用编号） | — | 未立项 | 窗口 2 后 |
| P-139 | 移出 heavy（原规划 P-135） | — | 未立项 | U-1 条件满足后 |

`main` 当前为 `6dfd47e`；窗口 1 的 Heavy run 将使用该 SHA。

## 2. 四步顺序与依据

### 2.1 第一步：核对窗口 1 与窗口 2

**目的**

1. 确认 F-1/F-2 的原始失败签名不再出现。
2. 确认 schedule 触发可用：`event=schedule`、组键 `heavy-Heavy-schedule-refs/heads/main`、结论非 `cancelled`。
3. 为移出 heavy 积累连续绿记录。

**为什么必须做**

- P-134 修的是竞态；本机 1000 次零失败只能降低概率，不能替代真实 CI 环境（Linux、四矩阵、调度）与周级触发。
- flaky test 实证研究（Luo 2014；Lam 2020）表明时序类缺陷必须在稳定代码上重复运行才能可靠复现或排除；单次通过没有统计意义。
- 两个周级周期而非一个，是为了降低误判；中断时间序列的 history threat（Shadish 2002；EPOC）说明观测期内的无关变更会损害归因。

**依据**

- 本仓：[P-133 DESIGN J-4](../arc-ci-heavy-rootcause/DESIGN.md#L44-L52)、[P-134 CHECKLIST §11](../arc-ci-heavy-fixes/CHECKLIST.md#L107-L113)、[P-129 U-2](../arc-ci-heavy-schedule/RESEARCH.md#L137-L145)。
- 外部：Luo et al. 2014；Lam et al. 2020；Shadish et al. 2002；Cochrane EPOC ITS。

### 2.2 第二步：先合 P-135，再 rebase/合 P-136

**为什么 P-135 先**

- P-135 修的是可重现性缺陷：被 4 处已入库文档引用的 midpoint 快照未入仓，干净检出下 `dc_validator` 报 21 条 P2；纯文档、无运行时影响，先落地可让后续批次基线变干净。

**为什么 P-136 要 rebase**

- 两个分支都基于 P-134 之后的 main，均在 PROGRESS 末尾追加行并重算 `REPO_STATS`/`CONSOLE`；顺序合并会产生可预期冲突。
- P-136 四文档字节不变，finalize digest 仍成立；rebase 只需解决 PROGRESS/派生视图冲突并重跑门禁与 PR 检查。

**依据**

- 本仓：`spec/arc-g4-midpoint-intake/RESEARCH.md` §2、`spec/arc-ci-cd-research/DESIGN.md` §2.1.1、`spec/arc-heavy-followups/DESIGN.md` D-5。

### 2.3 第三步：开 U-3/U-2 实施批（P-138）

**为什么必须等窗口结束**

- 该批要改 `file_wait.py`、`ws_adapter.py`、`feedback.py`、`lease.py`，正是 heavy 观测路径的邻近模块；窗口内合并会直接污染归因。
- 这正是「作用域冻结」：冻结 in-scope 运行时输入，允许 out-of-scope 文档变更。外部先例是 Megatron 冻结策略「out-of-scope changes still allowed」。

**目的**

1. U-3：`waiting.json` 改原子写；feedback 读方去掉 `exists()` 预检并捕获 `FileNotFoundError`。
2. U-2：`renew` 锁内校验 `released`，让释放成为不可逆终态。

**依据**

- `spec/arc-heavy-followups/RESEARCH.md` §3（released 复活确定性复现）、`spec/arc-heavy-followups/DESIGN.md` §4 + J-1..J-5。

### 2.4 第四步：满足 U-1 后开移出 heavy 批（P-139）

**为什么最后**

- 移出 heavy 会把两条用例放回默认 CI；若修复不稳，红灯落在四矩阵上，而 main 有 7 个必需检查 + `enforce_admins=true`，会阻塞所有 PR。
- 必须先满足：连续 10 次 CI 全绿 + 1000 次压测零失败 + 两个窗口无原始签名。
- 放在 P-138 之后，是让「10 次绿」统计在包含邻近修复的代码上，避免之后再引入变量。

**目的**

- 恢复 2 条被隔离测试的覆盖，清掉 `tests/ci_exclusions.yaml` 与 marker 的治理债。
- 用真实 CI 证明修复持久，而非暂时未撞上。

**依据**

- [P-133 U-4](../arc-ci-heavy-rootcause/RESEARCH.md#L150-L158)、[P-134 CHECKLIST §11](../arc-ci-heavy-fixes/CHECKLIST.md#L107-L113)、P-125「隔离≠治愈」。

## 3. 时间线

| 时点（UTC） | 北京时间 | 事项 |
|---|---|---|
| 2026-11-16 18:17 | 2026-11-17 02:17 | 窗口 1：首次 Heavy schedule run（尚未发生，写作时 16:02 UTC） |
| 2026-11-23 18:17 | 2026-11-24 02:17 | 窗口 2：第二次周级 run |
| 窗口 2 后 | — | 合并 P-135 → rebase/合 P-136 → 合 P-137 |
| 合并后 | — | 开 P-138（U-3/U-2 实施） |
| U-1 满足后 | — | 开 P-139（移出 heavy） |

## 4. 窗口读数清单

1. `gh run list --workflow heavy.yml --event schedule`：应有 1 条，`headBranch=main`、`headSha=6dfd47e`（窗口 1）。
2. 日志 `concurrency_key=heavy-Heavy-schedule-refs/heads/main`。
3. `2 passed, 3778 deselected`。
4. 无 `Invalid response file`、`HITL poll timeout`、`keeper 必须在租约丢失时回调`。
5. 结论非 `cancelled`。

**延迟处置**：官方明示 schedule 可能延迟；若 03:17 北京前仍无 run，判为 schedule-delay（P-129 U-2），不判红；整周无 run 则手动 dispatch 补跑，但标注 `event=workflow_dispatch`，不能替代 schedule 读数。

## 5. 合并冲突预案

1. 合并 P-135（先）。
2. P-136 rebase 到新 main：PROGRESS 保留 P-135/P-136 两行；`repo_stats.py --write` + `console_gen.py --stage` 重新生成；四文档字节不变 ⇒ digest 不变；复跑 step-gate/verify-anchor/step_enforce/pre-commit 与 PR 检查。
3. P-137 同样 rebase 后合并，追加第三行并重算派生视图。
4. 三批全部合并后，`main` 的 P 行顺序为 P-135 → P-136 → P-137。

## 6. 顺序失效的判据（kill criteria）

| 若发生 | 处置 |
|---|---|
| 任一窗口出现 F-1/F-2 原始签名 | 停止后续步骤，重开根因；P-138/P-139 顺延 |
| schedule 整周未触发 | 手动 dispatch 补跑并标注 `event=workflow_dispatch`；评估 cron 是否调整 |
| P-136/P-137 rebase 后 digest/门禁红 | 只修 PROGRESS/派生视图；四文档字节不动则 digest 不受影响；复跑门禁 |
| P-138 改动导致 heavy 用例红 | 不进入 P-139；先修 P-138 或回退 |

## 7. 编号调整说明

原规划「P-135 = 移出 heavy」已被两个文档批与一个实施批占用，最终编号为：

- P-135 midpoint 入库
- P-136 U-3/U-2 调研
- P-137 本分析
- P-138 U-3/U-2 实施
- P-139 移出 heavy

## 8. 诚实边界

- 本文件是执行顺序与依据的落档，不产生新的运行时证据。
- 写作时窗口 1 尚未发生；时间线与读数清单为待执行口径。
- 两个 PR 已通过检查但未合并；合并前的冲突解决与复跑是预期动作，不是异常。
