---
id: arc-ci-window2-backfill-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-ci-post-window-order-RESEARCH, arc-ci-window1-backfill-RESEARCH, arc-ci-heavy-fixes-CHECKLIST]
upstream: null
---

# 回填：Heavy 窗口 2 读数与 U-1 达成判定（P-142）

> **Feature**：P-142。兑现 `spec/arc-ci-post-window-order/RESEARCH.md` §4 与 §4.1 的窗口 2 核对，并给出 U-1 三条件的达成判定。
> **性质**：T3 单文档回填/分析；零代码、零测试、零 workflow。
> **结论先行**：① 窗口 2 的 `event=schedule` run `45323125502` 于 2026-11-24T03:58:26Z 触发，延迟 **9h41m26s**，success，五项判据全部通过；② U-1 三条件（两窗口无原始签名、1000 次压测零失败、连续 CI 全绿）全部满足；③ §4.1 的人工兜底与类别 A/B/C 分流**未触发**；④ 可立项 P-141 移出 heavy。

## 1. 窗口 2 读数

### 1.1 schedule run

| 项 | 读数 |
|---|---|
| run id | `45323125502` |
| event | `schedule` |
| headBranch / headSha | `main` / `7362330` |
| 创建 / 开始 | 2026-11-24T03:58:26Z（北京 11:58:26） |
| 完成 | 2026-11-24T03:58:57Z（31s） |
| 计划时刻 | 2026-11-23T18:17:00Z |
| 延迟 | **9h41m26s** |
| run_attempt | 1（非重跑） |
| conclusion | `success` |

日志检查：

| 判据 | 结果 |
|---|---|
| `concurrency_key=heavy-Heavy-schedule-refs/heads/main` | True |
| `2 passed, 3784 deselected, 1 warning in 7.16s` | True |
| `Invalid response file` | False |
| `HITL poll timeout` | False |
| `keeper 必须在租约丢失时回调` | False |

### 1.2 归因有效性

- run 的 `headSha=7362330` 是当时的 main（P-135..P-138 已合并，P-139/P-140 尚未合并）。
- 已核实 `git diff 6dfd47e..7362330 -- researchclaw/ scripts/ .github/` 为空：窗口 2 观测到的运行时与窗口 1 基线 `6dfd47e` 完全一致。
- 因此窗口 2 的证据覆盖的仍是 P-134 修复后的代码，未被他批污染。
- `3784 deselected` 比 P-137 §4 写的 `3778` 多 6 个，是分支合并后用例总数增长，不是异常。

## 2. 延迟趋势

| 窗口 | 计划时刻 | 实际时刻 | 延迟 | attempt | 结论 |
|---|---|---|---|---|---|
| 窗口 1 | 2026-11-16T18:17Z | 2026-11-17T01:53:11Z | 7h36m | 1 | success |
| 窗口 2 | 2026-11-23T18:17Z | 2026-11-24T03:58:26Z | **9h41m26s** | 1 | success |

- 两次均成功、均 `attempt=1`、均未 cancelled，排除「重跑洗绿」与「功能失效」。
- 9h41m 超过此前查到的社区观测上限 8h33m，说明该仓库的 schedule 处于调度器延迟分布的尾部。
- 结合 P-138 §2 的排除清单（workflow 禁用、分支错误、60 天无活动、整点 cron、平台事故、排队），延迟仍归因于 GitHub 调度器的 best-effort 行为；本批不新增归因结论。
- 结论：**cron 时刻不能当作观测不变式**；判定必须按「事件是否最终出现」而非「是否准点」。

## 3. U-1 三条件核对

| 条件 | 证据 | 判定 |
|---|---|---|
| 两个窗口无原始失败签名 | 窗口 1 `43998910996`（success，三签名 False）；窗口 2 `45323125502`（success，三签名 False） | 满足 |
| 1000 次压测零失败 | 合并预演态 `2b65304` 上 F-1 1000/1000（408.9s）、F-2 1000/1000（163.8s） | 满足 |
| 连续 CI 全绿 | P-134 合并（2026-11-16T08:05Z）后，所有 CI 的 PR run 与 main push run 均 success；含 11-24 合并序列的 6 次 PR run 与 4 次 main push | 满足 |

补充说明：

- 压测为本机 Windows、in-process 调用，与 Linux 四矩阵不同质，只作概率证据；但窗口 1/2 已在真实 CI 上各自验证一次，两者互补。
- 「连续全绿」按 P-137 §4.1 讨论的口径统计：计 CI 运行，并要求最后一次 main push 晚于所有计入的 PR run（`18f3ed4` 的 push run 满足）。

## 4. 判定与后续动作

- **窗口 2 判定：PASS**（五项判据全过）。
- `spec/arc-ci-post-window-order/RESEARCH.md` §4.1 的人工兜底**不触发**；类别 A/B/C 均不适用。
- 四个当天核对任务已完成使命，18:00 / 23:00 两场可删除，避免重复报告与 2027 年误触发。
- 后续动作：立项 P-141「移出 heavy」，把两条用例放回默认 CI，删除 `pytest.mark.heavy` 与 `tests/ci_exclusions.yaml` 登记。

## 5. 编号与接缝

| 编号 | 内容 | 状态 |
|---|---|---|
| P-135 | midpoint 文档入库 | 已合并（`446fa2d`，PR #17） |
| P-136 | U-3/U-2 调研 | 已合并（`496fde6`，PR #18） |
| P-137 | 窗口后执行顺序 | 已合并（`2aa627a`，PR #19） |
| P-138 | 窗口 1 回填 | 已合并（`7362330`，PR #20） |
| P-139 | U-3/U-2 实施 | 已合并（`a7c03b2`，PR #21） |
| P-140 | 科研工作台吸收调研 | 已合并（`18f3ed4`，PR #22） |
| P-142 | 本回填 | 本文件 |
| P-141 | 移出 heavy | 未立项，U-1 已满足 |

编号说明：P-141 已在 P-140 的 PROGRESS 行中预留给「移出 heavy」，本回填因此占用 P-142；P-141 立项时其 PROGRESS 行需插入到 P-142 之前，保持行序升序。

## 6. 未决项

| ID | 内容 | 判据 | 当前倾向 | 证据等级 |
|---|---|---|---|---|
| U-1 | 延迟是否继续变长 | 窗口 3（若保留 heavy）或移出后默认 CI 的稳定性 | 移出后在默认 CI 观察 | E1 |
| U-2 | 9h41m 是否尾部极值 | 更多周级样本 | 单次样本，不下结论 | E1 |
| U-3 | 是否保留 heavy.yml | 移出后是否还有 heavy 用例 | 若无用例则删除 workflow 或改为空壳守护 | E1 |
| U-4 | 四个核对任务是否清理 | 本批合并后 | 删除剩余两场 | E1 |

## 7. 诚实边界

- 本批只回填读数与判定，不修改 `heavy.yml`、不合并任何 PR、不改代码。
- 窗口 2 的 headSha 不是 `6dfd47e`，而是文档合并后的 `7362330`；运行时等价性由 diff 为空的读数支撑，不是同一 commit。
- 延迟归因沿用 P-138 的结论，本批只增加一个样本，不构成受控实验。
- 压测环境与 CI 不同质，已在上文标注。
