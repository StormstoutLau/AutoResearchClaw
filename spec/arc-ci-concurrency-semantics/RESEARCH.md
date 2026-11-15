---
id: arc-ci-concurrency-semantics-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-ci-trigger-dedupe-RESEARCH, arc-ci-flaky-heavy-DESIGN]
upstream: null
---

# 调研文档：并发组撞组语义与 schedule × push 互杀根因（P-128 调研批）

> **Feature**：P-128，`concurrency` 组键跨事件撞组的根因、社区案例与外部锚点（T3 Layer-0 调研批，零生产代码、零 workflow 变更）。
> **Spec 步骤**：Step 1-2（调研批）。
> **结论先行**：**陷阱成立，且比提问描述的更宽**。`schedule` 的 `GITHUB_REF` 官方表述为「Default branch」，按 `refs/heads/<branch_name>` 全形态落地即 `refs/heads/main`；本仓 `concurrency.group = ci-${{ github.workflow }}-${{ github.ref }}` 因此让 **schedule run 与 main push run 解析出同一个字符串**，而该组 `cancel-in-progress: true` 会**双向互杀**——不仅定时 run 会被 push 杀掉，push run 也会被定时 run 杀掉，直接击穿 P-127 刚验收的 I-3。同一缺陷已存在于 `workflow_dispatch`（D-4 引入，main 上手动重跑会杀掉 push run），P-127 未覆盖该面。调研结论：**根因是组键缺少事件维度，不是 schedule 本身**；推荐修法是**组键加入 `${{ github.event_name }}`**，并优先以**独立 `heavy.yml`** 承载定时重型任务（`ci.yml` 零改动、I-1..I-6 天然保持）。

## 1. 调研目标

1. **语义核实**：`schedule` 事件的 `github.ref` 究竟解析成什么？该事实的可信等级是什么？
2. **根因定位**：互杀是哪一个键、哪一条语义共同造成的？是否只影响 schedule？
3. **外部锚点**：官方文档、官方项目、真实仓库与社区文章是否已记录同一陷阱？修法形态有几种？
4. **方案空间**：给出可选方案、淘汰理由与推荐，供实施批裁决（本批不动手）。

## 2. 调研方法与降级链

| 通道 | 用途 | 结果 |
|---|---|---|
| 仓内读码（E1） | [ci.yml](../../.github/workflows/ci.yml) 的 `on` / `concurrency` / job 结构；P-127 四文档与 PROGRESS 行 | ✅ |
| 官方文档原文（T1） | GitHub Docs 仓库 `events-that-trigger-workflows.md` / `contexts.md` / `workflow-syntax.md` / `data/reusables/actions/*` | ✅ 逐字取得 |
| 官方项目实践（T2） | GitHub Agentic Workflows 官方站点的 concurrency 矩阵 | ✅ |
| 真实仓库锚点（T3） | 直读公开仓 workflow 文件（`gh api` raw） | ✅ 命中同构案例 |
| 社区文章（T3/T4） | runs-on.com / dev.to / devopsaitoolkit / PyPI 包说明 | ✅ 仅作发现线索 |
| StackExchange MCP | 检索 Stack Overflow 同题问答 | ⚠️ 降级（`total=0` 且 `quota_remaining=-1`，服务不可用） |

**降级链记录（SPEC_PROCESS 反模式③：工具失败不得静默跳过）**：

1. `WebFetch raw.githubusercontent.com/.../events-that-trigger-workflows.md` **返回空**（`local crawler returned empty content`）→ 降级为 **GitHub REST contents API**（`gh api -H "Accept: application/vnd.github.raw"`），成功取得官方仓原文 69,263 B。
2. `WebFetch https://docs.github.com/en/actions/reference/contexts` 返回 **404**（旧路径已迁移）→ 降级为新路径 `/en/actions/reference/workflows-and-actions/contexts`，并进一步以 REST API 取 `contexts.md` 原文 51,480 B。
3. StackExchange MCP 两次检索均为 `total=0`、`quota_remaining=-1` → 判定为**工具侧不可用**而非「无此问题」，降级为 WebSearch + `gh search issues/code`。
4. `gh search code` 连续两次返回 `[]`（GitHub 代码搜索索引限制）→ 降级为**直读候选仓文件**（`gh api repos/<owner>/<repo>/contents/...`），最终命中 `nativesoil/handover` 同构案例。
5. `jsdelivr` 镜像取官方 md 仅前 228 行（截断，未含 `schedule` 节）→ 判定不可用，改用方案 1 的全量原文。

## 3. 官方语义取证（T1 逐字）

> 取证时点 2026-11-16；来源为 GitHub 官方文档仓 `github/docs@main` 与 docs.github.com 渲染页。

### 3.1 schedule 的 ref 与运行分支

`events-that-trigger-workflows.md` 的 `schedule` 节（原文 L957-L967）：

| Webhook event payload | Activity types | `GITHUB_SHA` | `GITHUB_REF` |
| --- | --- | --- | --- |
| Not applicable | Not applicable | Last commit on default branch | Default branch |

> * Scheduled workflows will only run on the default branch.
> * In a public repository, scheduled workflows are automatically disabled when no repository activity has occurred in 60 days.

### 3.2 push 的 ref

同文件 `push` 节（L780-L784）：

| Webhook event payload | Activity types | `GITHUB_SHA` | `GITHUB_REF` |
| --- | --- | --- | --- |
| `push` | Not applicable | Tip commit pushed to the ref. | Updated ref |

### 3.3 ref 的全形态与相关上下文

`contexts.md`（官方 `github` context 表）：

- `github.ref`（L197）→ 引用 `ref-description`：「The fully-formed ref of the branch or tag that triggered the workflow run. … For other triggers, this is the branch or tag ref that triggered the workflow run. … for branches the format is `refs/heads/<branch_name>`」。
- `github.workflow`（L215）：「The name of the workflow.」
- `github.event_name`（L191）：「The name of the event that triggered the workflow run.」

**推论（E1，两条 T1 语句合成，非单条逐字）**：schedule 的 `GITHUB_REF` = 「Default branch」+ 「ref 为 `refs/heads/<branch_name>` 全形态」⇒ 本仓 main 分支上解析为 `refs/heads/main`，与 main 的 push run 逐字相同。该推论的可证伪方式见 §8 U-1。

### 3.4 并发组语义

`control-workflow-concurrency`（docs.github.com 渲染页）逐字：

- 「there can be at most one running job or workflow in a concurrency group at any time.」
- 「To also cancel any currently running job or workflow in the same concurrency group, specify `cancel-in-progress: true`.」
- 「If a new workflow run or job starts with the same concurrency key, GitHub Actions will cancel any workflow or job already running with that key.」
- 「By default, any existing `pending` job or workflow in the same concurrency group will be canceled and the new queued job or workflow will take its place.」（即默认**只有一个 pending 位**）
- 「The concurrency group name is case insensitive.」
- 「Jobs or workflow runs in the same concurrency group are processed in first-in-first-out (FIFO) order … ordering is not guaranteed.」
- `queue` 取值 `single`（默认）/ `max`（最多 100）；「The combination of `queue: max` and `cancel-in-progress: true` is not allowed」。

`workflow-syntax.md` / `section-using-concurrency.md`：

- 「Use `concurrency` to ensure that only a single job or workflow using the same concurrency group will run at a time. A concurrency group can be any string or expression.」
- 顶层表达式允许上下文：`github`、`inputs`、`vars`；job 级另允许 `needs`、`strategy`、`matrix`（how-to 页 L25）。

### 3.5 官方示例正是本仓蓝图（陷阱来源）

`control-workflow-concurrency` 的「Example: Using concurrency and the default behavior」：

```yaml
on:
  push:
    branches:
      - main
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

本仓 `ci.yml` 的组键即在此例基础上加 `ci-` 前缀。**结论：该写法在「只有 push」时正确，一旦叠加 schedule/dispatch（同一 workflow 内）即产生跨事件误杀**——官方示例没有覆盖多触发器场景，社区大量文章直接照抄。

## 4. 根因链（E1）

| 编号 | 环节 | 依据 |
|---|---|---|
| R-1 | 组键只含「工作流名 + ref」，**不含事件维度** | 本仓 `ci.yml` L12-L14；T1 §3.5 |
| R-2 | schedule 与 main push 解析出**同一组名** `ci-CI-refs/heads/main` | T1 §3.1-§3.3（`github.workflow` = `name: CI`；`github.ref` = `refs/heads/main`） |
| R-3 | 同组 ⇒ 互斥；`cancel-in-progress: true` ⇒ 新进入者杀掉在跑的 run，**方向对称** | T1 §3.4 |
| R-4 | 默认仅 1 个 pending 位 ⇒ 高峰期连排队者也会被顶掉 | T1 §3.4 |
| R-5 | schedule **只**在默认分支运行 ⇒ 与 main push 撞组是**必然**而非概率 | T1 §3.1 |

**后果（按严重度）**：

1. **I-3 被击穿**：main 的 push run 可能被定时 run 取消，P-127 的验收前提不复存在。
2. **必需检查变 cancelled**：分支保护要求的 7 个检查若在 push run 中被取消，状态为 `cancelled` 而非 `success`，`enforce_admins=true` 下 main 会停在红/取消态。
3. **既有潜伏缺陷（P-127 未覆盖）**：`workflow_dispatch` 在 main 上同样 `refs/heads/main`，与 push run 同组；D-4 引入后一直存在「手动重跑会杀掉 push run」的面，只是尚未被观测到。
4. **PR 面不受影响**：`pull_request` 的 ref 为 `refs/pull/N/merge`，故 P-127 的 I-1/I-2 仍成立——这正是该缺陷此前未被发现的原因。

## 5. 外部案例锚点

### 5.1 T2：GitHub 官方项目的并发矩阵

GitHub Agentic Workflows 官方站点（`github.github.io/gh-aw/reference/concurrency/`）按触发器分三行，schedule 单独成行且**组键不含 ref、`cancel-in-progress` 为 No**：

| Trigger Type | Concurrency Group | Cancel In Progress |
| --- | --- | --- |
| Pull Requests | `gh-aw-${{ github.workflow }}-${{ pr.number \|\| ref }}` | Yes |
| Push | `gh-aw-${{ github.workflow }}-${{ github.ref }}` | No |
| Schedule/Other | `gh-aw-${{ github.workflow }}` | No |

**读法**：官方团队自己的产品在触发器维度上**主动拆组**，且 schedule 不参与取消。这是「组键必须带事件维度」的官方侧实践背书。

### 5.2 T3：同构真实仓库（最强锚点）

`nativesoil/handover`（公开仓，18 stars，default branch `main`，文件 sha `84ddaa770e485a32b362b2206297ac45c477e267`）的 [.github/workflows/ci.yml](https://github.com/nativesoil/handover/blob/main/.github/workflows/ci.yml)：

```yaml
on:
  push:
    branches: ["**"]
  pull_request:
  workflow_dispatch:
  schedule:
    - cron: "0 5 * * 1"

# A branch and its pull request are the same commits, and a force-push
# supersedes what came before. One run per ref and event, and cancel the run
# it replaces; the event in the group keeps a dispatched or scheduled rate
# run from being cancelled by an unrelated push.
concurrency:
  group: ci-${{ github.workflow }}-${{ github.event_name }}-${{ github.ref }}
  cancel-in-progress: true
```

**同构度**：同一 workflow 内同时挂 push / PR / dispatch / schedule 四个触发器；组键前缀同为 `ci-`；与本仓唯一差异是**多了一个 `${{ github.event_name }}` 维度**。其注释直接陈述了修法动机——「事件进组键，防止 dispatch 或 schedule 的 run 被无关 push 取消」。

### 5.3 T3：社区文章与包说明（只作线索，不作 A 类断言）

| 来源 | 要点 | 等级 |
|---|---|---|
| dev.to/robsonheals《…cancel-in-progress mistake in most snippets》 | 扫描 139 个 1k–20k star 仓库，129 个有 push/PR 工作流的仓中 97 个（75%）无 concurrency；明确批评 `cancel-in-progress: true` 会取消 main 上的 run，改用 `cancel-in-progress: ${{ github.event_name == 'pull_request' }}` | T3 |
| gha-utils（PyPI 5.14.1）说明 | 缺陷表列「Cross-event concurrency cancellation ✅ Addressed — event_name in changelog.yaml concurrency group」 | T3 |
| runs-on.com「Concurrency」 | 组键与方法论：`group` 为解析后同串即同组、大小写不敏感、`cancel-in-progress` 可为表达式；「Gotchas」列取消误杀与组名撞车 | T3 |
| devopsaitoolkit.com | 「Canceling since a higher priority waiting request for … exists」症状与排查 | T3 |
| GitHub Agentic Workflows | 见 §5.1 | T2 |

**反例检索结果（如实登记）**：未检索到「schedule 与 push 同组互杀」的**逐字事故报告**（Stack Overflow / GitHub Community Discussions / issues 均无命中；StackExchange MCP 本身不可用）。因此本批不使用「社区共识」措辞：根因结论全部由 §3 的 T1 原文推出，§5 仅提供同构实现与修法先例。

## 6. 方案空间（供实施批裁决）

| 方案 | 做法 | 修根因 | 对 I-1..I-6 | 改动面 | 淘汰/保留理由 |
|---|---|---|---|---|---|
| **A 独立 heavy.yml** | 新建 `heavy.yml`，仅 `schedule` + `workflow_dispatch`，组键 `heavy-${{ github.workflow }}-${{ github.event_name }}-${{ github.ref }}` | ✅ 组名天然不同（工作流名不同） | ✅ 零触碰 | 新增 1 文件 | **推荐**：定时任务与 CI 生命周期解耦，I-3 无风险 |
| **B ci.yml 组键加事件维** | `group: ci-${{ github.workflow }}-${{ github.event_name }}-${{ github.ref }}` | ✅ | ⚠️ 改变 push/dispatch 的取消语义（I-4 重定义） | 1 行 | 备选：若 heavy 必须留在 ci.yml 内；需重跑 P-127 的 I-4 验收 |
| C job 级 concurrency 覆写 | 在 heavy job 上加 `concurrency` | ❌ | ⚠️ | 数行 | **淘汰**：workflow 级组仍作用于整个 run，job 级只增加本 job 的组，**不能逃逸**上游组（E1 推论，见 U-2） |
| D cancel-in-progress 表达式 | `cancel-in-progress: ${{ github.event_name != 'schedule' }}` | ❌ 半解 | ⚠️ | 1 行 | **淘汰**：只阻止 schedule **杀别人**，无法阻止 push **杀 schedule**（方向不对称） |
| E `queue: max` | 排队不取消 | ❌ | ⚠️ | 1 行 | **淘汰**：与 `cancel-in-progress: true` 组合非法；且仍串行、仍会被 killer 取消 |
| F 错峰 cron | 把 cron 挪到低峰 | ❌ | ✅ | 1 行 | **淘汰**：概率缓解，不可证伪，push 时间不可控 |

**推荐组合**：A（独立 `heavy.yml`）+ 组键含 `event_name` + `cancel-in-progress: false`（定时重型用例不应被任何新 run 取消）；`ci.yml` 一行不改。若后续确认 `workflow_dispatch` 撞 push 是必须修的面，则在同一实施批用 B 的方式只改 `ci.yml` 组键（1 行）。

## 7. 与本仓既有不变式的映射

| 既有约束 | 本批结论 |
|---|---|
| P-127 I-1（PR 单 run） | 不受影响（PR ref 独立） |
| P-127 I-3（main 仍触发且不被误杀） | 方案 A 零风险；方案 B 门禁后需复验 |
| P-127 I-4（同 ref 取消前序） | 方案 A 保持原义；方案 B 语义变为「同 ref 同事件」 |
| arc-ci-flaky-heavy U-2（heavy 无定期执行路径） | 方案 A 是唯一不引入撞组的兑现方式 |
| 分支保护 7 必需检查 | A/B 均不改检查名；heavy 不应进入必需集 |

## 8. 未决项

| ID | 内容 | 判据 | 触发条件 | 当前倾向 | 证据等级 |
|---|---|---|---|---|---|
| U-1 | schedule 的 `GITHUB_REF` 未经本仓实测（schedule 只在默认分支运行，无法在探针分支验证；main 上实测需真等待 cron） | 官方原文与实测一致 | 实施批首次定时 run 的 `GITHUB_REF` 读数 | 采用官方原文 `refs/heads/main` | T1 原文 + E1 推论 |
| U-2 | job 级 `concurrency` 是否**完全无法**逃逸 workflow 级组（本批为 E1 推论） | 探针：workflow 级组 `G`、job 级组 `H`，两个 run 并发时是否仍被 workflow 级取消 | 实施批需要 job 级方案时 | 视为不可逃逸，直接选 A | E1 推论，待实测 |
| U-3 | `workflow_dispatch` 与 push 在 main 上撞组是否同批修复 | 手动 dispatch 与 push run 是否互杀 | 用户裁决 | 同批修复或独立批 | E1 推论 |
| U-4 | heavy 的 `cancel-in-progress` / `queue` 取值 | 定时 run 是否允许被新 run 取消 | 实施批设计 | `cancel-in-progress: false` + `queue: single` | E1 |
| U-5 | 公开仓 schedule 60 天无活动自动禁用 | 仓库连续 60 天无活动后定时任务是否停摆 | 实际进入低活动期 | 接受并登记运维提醒 | T1 原文 |

## 9. 诚实边界

- 本批为 T3 Layer-0 调研批：**零生产代码、零 workflow 变更、零门禁变更**；仅新增 `spec/` 文档与决策流。
- 根因链的每一环均有 T1 原文支撑；但「schedule 的 ref 恰为 `refs/heads/main`」是把两条 T1 语句合成为一条推论（E1），已在 U-1 显式标注，未冒充逐字事实。
- 未检索到同题事故报告（§5.3 末段）；外部锚点的作用是**证明修法在真实工程中存在**，不是「社区共识」。
- 「job 级无法逃逸 workflow 级组」为 E1 推论，未见 T1 逐字否证，故列入 U-2 并在实施前以探针验证。
- 取证命令与原始文档落盘于本机会话临时目录，文档中只保留可公开复核的官方 URL 与逐字引文。
