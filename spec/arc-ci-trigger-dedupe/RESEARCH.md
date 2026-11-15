---
id: arc-ci-trigger-dedupe-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: []
upstream: null
---

# 调研：CI 双触发去重（P-127）

> **档位**：T1（单文件、可逆、零产品代码）。
> **决策**：`.github/workflows/ci.yml` 的 `push` 触发器收窄到 `main`，PR 分支只走 `pull_request`。
> **本文性质**：现状取证 + 方案空间 + 取舍依据。**未改代码**。

---

## 1. 问题陈述

同一提交在 PR 分支上会同时触发 `push` 与 `pull_request` 两个 workflow run，8 个 job 全跑两遍。本批要回答：**能否在不损失必需检查覆盖的前提下，把每个提交的 CI 运行数从 2 降到 1。**

## 2. 现状取证（E1）

| 编号 | 观测 | 读数 |
|---|---|---|
| E1-1 | PR #6（P-125）双 run，同一 headSha | push `43736549562` + pull_request `43736560954` |
| E1-2 | PR #7（P-126）双 run，同一 headSha | push `43739399629` + pull_request `43739428763` |
| E1-3 | PR #5（P-124）同样双 run | push `43732450853` + pull_request `43732486982` |
| E1-4 | 工作流数量 | `.github/workflows/` 仅 `ci.yml`，无第二工作流可分摊或去重 |
| E1-5 | 触发器原文 | `on: push`（无分支过滤）+ `on: pull_request`（默认 opened/synchronize/reopened）+ `workflow_dispatch` |
| E1-6 | 并发组原文 | `group: ci-${{ github.workflow }}-${{ github.ref }}`，`cancel-in-progress: true` |
| E1-7 | 分支保护 | `main` 需 7 个必需检查（`Packaging / wheel smoke`、`Extras import`、`Tests (3.11)`、`Tests (3.12)`、`Tests (3.13)`、`Roadmap coverage gates`、`Spec gates (pre-commit all-files)`），`enforce_admins=true` |
| E1-8 | 单 run 成本 | 探针 run `43748816610` 的 8 个 job 时长求和 = 544 s（约 9.1 分钟），墙钟 118 s |
| E1-9 | 语义探针 | 把 `push` 收窄为 `branches: [main]` 后：分支推送（commit `992d268`）产生 **0** 个 run；同 commit 开草稿 PR 后产生 **1** 个 `pull_request` run，8 job 全 success，7 个必需检查名全部出现 |

E1-9 是本批的**决定性命中**：它同时证伪了「去重必然损失 PR 检查覆盖」的担心，也证实了 GitHub 对 `pull_request` 事件取 **PR 版本的 workflow 文件**（而非默认分支版本），故配置改动在 PR 自身即可生效并自证。

## 3. 根因

双 run 不是并发配置失效，而是**事件语义叠加**：

1. 在 PR 分支上 `git push` 会触发 `push` 事件（`github.ref = refs/heads/<branch>`）。
2. 同一提交同时让 PR 进入 `synchronize`，触发 `pull_request` 事件（`github.ref = refs/pull/<N>/merge`）。
3. 两个 ref 字符串不同 ⇒ `concurrency.group` 不同 ⇒ 互不取消（E1-6）。
4. 事件过滤器未限定分支 ⇒ `push` 对任意分支生效（E1-5）。

因此「同分支连续 push 取消前序」这条既有能力（D-4）在 push×PR 维度上从未生效——它只在同一事件、同一 ref 内生效。

## 4. 方案空间

| 方案 | 做法 | 判定 |
|---|---|---|
| **A 收窄 push 分支** | `push.branches: [main]`，PR 分支只走 `pull_request` | **采用**：改动 1 处、语义可推导、E1-9 已实证 |
| B 跨事件共享并发组 | group 改用 `github.event.pull_request.head.sha || github.sha` | 否决：push 与 PR 共用组后 `cancel-in-progress` 会**随机**取消其中一个，被取消的多半是 `pull_request` run；必需检查显示 cancelled ⇒ PR 永久卡住，且哪一侧存活不可预测 |
| C job 级 `if` 过滤 | 每个 job 加 `if: github.event_name != 'push' \|\| github.ref == 'refs/heads/main'` | 否决：run 仍被创建，7 个检查名以 `skipped` 形态出现在 push run 中，与 PR run 的 `success` 同名并存，检查聚合语义变糊 |
| D 路径过滤去重 | `paths-ignore: ['spec/**','docs/**']` | 否决：与目标无关（不能消除同提交双 run），且会让 spec-gates 漏跑 |

## 5. 影响面

| 面 | 影响 |
|---|---|
| `spec-gates` 的 `BASE_SHA` | 表达式为 `github.event.before \|\| github.event.pull_request.base.sha`；PR 路径本就走 `base.sha`，push 路径收窄后 `before` 仍存在（main 推送），**零改动** |
| 分支保护 | 检查名不变 ⇒ 保护规则无需改；`enforce_admins=true` 保证「7 检查缺失即不可合并」成为去重的**兜底验收** |
| 合并后 main | squash 合并产生 main 的 push ⇒ 仍会跑 1 次，main 状态不丢 |
| fork PR | `push` 事件发生在 fork 仓，基线仓本就无该事件；收窄不减少任何既有覆盖 |
| 无 PR 的分支推送 | **不再有 CI 反馈**（见 §7 U-1） |

## 6. 外部锚点

均为 T1 官方文档（语义引用，本批未逐字抓取；锚点形态稳定）：

1. `push` 事件的 `branches` 过滤器仅对匹配分支触发：<https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#onpushbranches>
2. `pull_request` 默认活动类型为 `opened` / `synchronize` / `reopened`：<https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#pull_request>
3. `concurrency.group` 按字符串相等判定互斥，`github.ref` 在 push 与 PR 下取值不同：<https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#concurrency>
4. PR 的 workflow 取自 PR 的合并提交（故改动可在自身 PR 中生效）：<https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#pull_request>

## 7. 遗留与风险

- **U-1（已接受）**：无 PR 的纯分支推送失去 CI 反馈。缓解：`main` 受保护必须走 PR；`workflow_dispatch` 可手动补跑；团队约定「先开 PR 再迭代」。
- **U-2（观察）**：若将来新增 tag / release / schedule 触发器，需重新评估去重矩阵（本批不涉及）。
- **R-1**：首次推送到 `main` 时 `before` 为全 0，`spec-gates` 已有显式跳过分支（`ci.yml` L182-L185），无需改动。

## 8. 结论

采用方案 A：`push` 收窄至 `main`。它以一处三行改动消除每个 PR 提交约 9.1 分钟的重复算力，且 7 个必需检查名、`BASE_SHA` 逻辑、分支保护全部零改动；行为读数已在探针中实证（E1-9），无需回填窗口。
