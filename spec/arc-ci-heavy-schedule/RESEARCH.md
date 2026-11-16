---
id: arc-ci-heavy-schedule-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-ci-concurrency-semantics-DESIGN, arc-ci-flaky-heavy-DESIGN]
upstream: null
---

# 调研：定时重型执行路径的取值与可观测性（P-129 实施批）

> **Feature**：P-129。把 P-128 方案 A（独立 `heavy.yml`）从目标形态落为可运行工作流，并先钉死四个实施批变量：cron 时段、并发键支持面、依赖组、验收读数可得性。
> **Spec 步骤**：Step 1-2（实施批的研究步）。
> **结论先行**：① `heavy.yml` 触发器只保留 `schedule` + `workflow_dispatch`，组键含 `github.event_name`，`cancel-in-progress: false`；② cron 由 P-128 示意的 `0 18 * * *` 改为 **`17 18 * * 1`**——官方明确「整点是高负载时段，可能延迟甚至丢弃排队任务」，且本仓 heavy 两例是已知时序 flaky，周级频率足以兑现「定期执行路径」而不制造每日噪声；③ **不写 `queue` 键**——canonical reusable 未记载该键，默认单 pending 位已满足需求，不引入未验证语法；④ **组名无法从 API 直读**（run 对象 `concurrency: null`），J-1 改用「静态表达式 + 运行日志回显 + 行为不互杀」三重证据。

## 1. 调研目标

1. **规模与耗时**：`-m heavy` 当前有多少用例、本机跑多久、依赖哪些 extras。
2. **调度语义**：cron 的时区、默认分支约束、延迟/丢弃风险，据此定 cron 与频率。
3. **并发键支持面**：`queue` 是否属于可验证的 workflow 语法；`cancel-in-progress: false` 是否足够。
4. **读数可得性**：J-1 要求的「两个 run 的 `concurrency.group` 读数」能否从 GitHub API 取得；不能则给出替代证据。
5. **零改动边界**：`ci.yml`、`tests/`、`researchclaw/`、分支保护必需检查集。

## 2. 方法与降级链

| 通道 | 用途 | 结果 |
|---|---|---|
| 仓内实测（E1） | heavy 收集与运行、marker 真值源、YAML 结构 | ✅ |
| 官方文档仓 raw（T1） | `schedule-delay` reusable、`section-using-concurrency-jobs` reusable | ✅ 逐字取得 |
| GitHub REST 只读（E1） | run 对象字段、分支保护 `contexts` | ✅ |
| 上游文档（E1） | P-128 DESIGN 的 D-1..D-5 与 J-1..J-7、flaky-heavy U-2 | ✅ |

**降级链记录（SPEC_PROCESS 反模式③：工具失败不得静默跳过）**：

1. `docs.github.com` 的 `control-workflow-concurrency` 渲染页不适合逐字引用 → 取 `github/docs` 仓 raw；页面正文实为 include，最终定位到 `data/reusables/actions/jobs/section-using-concurrency-jobs.md`。
2. `content/actions/reference/workflows-and-actions/workflow-syntax.md` 的 `concurrency` 段在本仓版本中已拆分，取到的文件不含 `queue` 键 → 判定「键存在性不可证」，按 §5.2 不采用。
3. `runs` API 不返回并发组（实测 `concurrency: null`）→ 无法直读组名，降级为 §5.4 的三重间接证据。

## 3. 官方语义取证（T1）

### 3.1 schedule 的时区与运行分支

`data/reusables/actions/schedule-delay.md` 逐字：

> Use POSIX cron syntax … By default, scheduled workflows run in UTC. … Scheduled workflows run on the latest commit on the default branch. The shortest interval you can run scheduled workflows is once every 5 minutes.

同文件对延迟与丢弃的逐字告警：

> The `schedule` event can be delayed during periods of high loads of GitHub Actions workflow runs. High load times include the start of every hour. If the load is sufficiently high enough, some queued jobs may be dropped. To decrease the chance of delay, schedule your workflow to run at a different time of the hour.

P-128 已取证的另两条约束继续有效：schedule 只在默认分支运行；公开仓连续 60 天无活动后自动禁用（见 [P-128 RESEARCH](../arc-ci-concurrency-semantics/RESEARCH.md) §3.1）。

### 3.2 concurrency 的支持面

`section-using-concurrency-jobs.md` 覆盖 `group` 与 `cancel-in-progress` 的用法；本批在该 reusable 中**未检索到 `queue` 键**。P-128 曾从渲染页引用 `queue: single|max`，但本批未能复现该键的仓内出处，故按「未验证语法不采用」处理：不写 `queue`，仅用 `cancel-in-progress: false`，默认单 pending 位即 P-128 D-3 所需语义。

## 4. 仓内事实（E1）

| 编号 | 读数 | 来源 |
|---|---|---|
| E1-1 | `pytest tests -m heavy --collect-only -q` → `2/3780 tests collected (3778 deselected)` | 本机执行 |
| E1-2 | `pytest tests -m heavy -q` → `2 passed, 3778 deselected`，pytest 计时 4.28 s，进程墙钟 5.4 s | 本机执行 |
| E1-3 | heavy 集合真值源 = `tests/ci_exclusions.yaml` 两条五字段条目；marker 声明在 `pyproject.toml` L63-L65 | 仓内读码 |
| E1-4 | 现有唯一工作流 `ci.yml`：触发器 `push(main)` / `pull_request` / `workflow_dispatch`；组键 `ci-${{ github.workflow }}-${{ github.ref }}`；`cancel-in-progress: true` | 仓内读码 |
| E1-5 | 分支保护必需检查 7 名：`Packaging / wheel smoke`、`Extras import`、`Tests (3.11)`、`Tests (3.12)`、`Tests (3.13)`、`Roadmap coverage gates`、`Spec gates (pre-commit all-files)` | `gh api .../branches/main/protection` |
| E1-6 | run 对象 `43773285738` 的 `concurrency` 字段 = `null` ⇒ 组名无 API 直读面 | `gh api .../actions/runs/43773285738` |
| E1-7 | 仓库当前只有 `ci.yml` 一个 workflow 文件，无 `heavy.yml` | `Glob .github/workflows/*` |

## 5. 实施批取值裁决

### 5.1 cron 与频率

**取值**：`17 18 * * 1`（UTC，周一 18:17 = 北京时间周二 02:17）。

理由：

1. 官方告警明确「整点高负载、可能延迟或丢弃」⇒ 分钟位取 `17`，避开 `:00`；
2. heavy 两例是**已知时序 flaky**（`test_poll_with_delayed_response` 已四次误红、`test_lease_keeper_reports_loss` 一次），日级运行会把已知噪声放大成每日红灯；周级已足够兑现 arc-ci-flaky-heavy U-2 的「定期执行路径」；
3. 外部锚点 `nativesoil/handover` 同样采用周级 cron（`0 5 * * 1`）。

### 5.2 并发键与取消语义

**取值**：

```yaml
concurrency:
  group: heavy-${{ github.workflow }}-${{ github.event_name }}-${{ github.ref }}
  cancel-in-progress: false
```

- 组键前缀 `heavy-` + 工作流名 `Heavy` ⇒ 与 `ci-CI-refs/heads/main` 在构造上不同组；
- `event_name` 区分 schedule 与 dispatch，避免两者互相顶掉 pending 位；
- `cancel-in-progress: false`：定时任务被新 run 取消等于丢一次观测；
- 不写 `queue`（§3.2）。

### 5.3 job 形态

| 项 | 取值 | 依据 |
|---|---|---|
| runner | `ubuntu-latest` | 与 `ci.yml` tests job 一致 |
| Python | `3.11` | 与 `ci.yml` 主轨一致；heavy 用例不依赖 3.12+ 特性 |
| 依赖 | `python -m pip install -e ".[dev,server,mcp]"` | 与 `ci.yml` tests job 同口径，避免缺 extras 产生假红 |
| 超时 | `timeout-minutes: 60` | 当前实测 5.4 s；为未来真实外部依赖留余量，仍低于 360 上限 |
| 命令 | `python -m pytest tests -m heavy -q` | 只跑 heavy，不重复全量（J-6） |

### 5.4 J-1 的替代证据

由于 §4 E1-6，组名不可直读。三重证据：

1. **静态**：YAML 组键表达式逐字断言（含 `heavy-`、`github.workflow`、`github.event_name`、`github.ref` 四段）；
2. **运行回显**：工作流内加一步 `echo "concurrency_key=heavy-${{ github.workflow }}-${{ github.event_name }}-${{ github.ref }}"`，日志里得到解析后的完整组名字符串；
3. **行为**：合并后 main push run 与一次 Heavy dispatch 并发期间，两者结论均非 `cancelled`（J-2 的读数同时覆盖该面）。

该替代证据的强度上限登记为 U-1：回显的是同一表达式的求值结果，不是 GitHub 内部组键的直读；但组键语义由官方文档定义（表达式字符串即组名），因此静态 + 回显已足以证伪「组名相同」。

## 6. 外部锚点

| 来源 | 要点 | 等级 |
|---|---|---|
| `schedule-delay` reusable | UTC 默认、默认分支、5 分钟下限、整点延迟/丢弃 | T1 |
| `nativesoil/handover` `.github/workflows/ci.yml` | 四触发器共存、组键含 `event_name`、周级 cron | T3（经 P-128 取证） |
| GitHub Agentic Workflows 矩阵 | Schedule/Other 不参与取消 | T2（经 P-128 取证） |

## 7. 与 P-128 不变式的映射

| P-128 不变式 | 本批落点 |
|---|---|
| J-1 定时 run 与 main push run 不同组 | §5.2 组键；§5.4 三重证据 |
| J-2 main push 仍触发且不被误杀 | `ci.yml` 零改动；合并后 push run 读数 |
| J-3 同事件重复触发仍去重 | `ci.yml` 的 `cancel-in-progress: true` 逐字未动 |
| J-4 7 个必需检查名不变 | heavy 不入必需集；`contexts` 只读比对 |
| J-5 `ci.yml` 零变更 | `git diff` 对该文件为空 |
| J-6 heavy job 只跑 `-m heavy` | §5.3 命令 |
| J-7 schedule 停摆可观测 | `workflow_dispatch` 手动补跑 + run 历史；登记观察项 |

## 8. 未决项

| ID | 内容 | 判据 | 触发条件 | 当前倾向 | 证据等级 |
|---|---|---|---|---|---|
| U-1 | J-1 的组名只有间接证据（API `concurrency: null`） | GitHub 是否新增组名 API 字段 | 若官方开放字段则补直读 | 接受三重间接证据 | E1 实测 |
| U-2 | 首次 schedule run 的实际触发时刻可能晚于 cron（官方延迟告警） | 首个周级 run 的 `createdAt` 与 `17:18 UTC` 偏差 | 首次定时 run 后 | 接受延迟，不据此判红 | T1 |
| U-3 | heavy 两例根因未修（F-1/F-2），周级红灯属已知噪声 | 是否出现新的、非时序类的失败 | 连续两次非同因失败 | 先观察，根因专项另立 | E1 |
| U-4 | 公开仓 60 天无活动自动禁用 schedule | 进入低活动期后是否停摆 | 实际发生 | 手动 dispatch 补跑 | T1 |

## 9. 诚实边界

- 本批只新增一个工作流文件与四文档，**不改** `ci.yml`、`tests/`、`researchclaw/` 与分支保护设置。
- cron 与频率不是 P-128 的硬性裁决，而是其 DESIGN §4 明确留给实施批的取值项；本批按 §3.1 的 T1 告警与 §4 的实测规模定值，并在此登记理由。
- 组名不可直读是**平台事实**，不是本批的取巧；三重证据的强度上限已写入 U-1，不以「组名读数」冒充 API 直读。
- heavy 用例本身的 flaky 根因未在本批修复（arc-ci-flaky-heavy U-1 仍在）；本批只提供隔离后的定时观测路径。
