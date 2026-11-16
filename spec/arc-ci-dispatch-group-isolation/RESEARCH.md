---
id: arc-ci-dispatch-group-isolation-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-ci-concurrency-semantics-RESEARCH, arc-ci-heavy-schedule-IMPLEMENTATION]
upstream: null
---

# 调研：dispatch × push 撞组的组键隔离（P-131）

> **Feature**：P-131。P-128 登记的潜伏缺陷——`workflow_dispatch` 在 main 上与 `push` 解析同一并发组，且 `cancel-in-progress: true`，手动重跑会杀掉 push run。用户已裁决走独立小批，本批只改 `ci.yml` 组键一行。
> **Spec 步骤**：Step 1-2（实施批的研究步）。
> **结论先行**：撞组成立且方向对称；修法是组键加入 `${{ github.event_name }}`。改后 main 上 push / dispatch / PR 三类的组名两两不同，而同事件同 ref 的组名逐字不变，故「最新提交优先」的取消语义不受影响。

## 1. 调研目标

1. **复述撞组机制**：确认 `workflow_dispatch` 与 `push` 在 main 上确实同组，且取消方向对称。
2. **量化修法影响**：加 `event_name` 后，哪些组名变化、哪些关系不变。
3. **验收可得性**：组名仍无 API 直读面（P-129 已实测 `concurrency: null`），需给出可执行的合并后行为读数。
4. **零外溢**：确认 `heavy.yml`、`tests/`、分支保护、7 个必需检查名不受影响。

## 2. 方法与降级链

| 通道 | 用途 | 结果 |
|---|---|---|
| 仓内读码（E1） | `ci.yml` 触发器 / 组键 / `heavy.yml` 组键 | ✅ |
| 上游文档（E1/T1） | P-128 根因链与 U-3 裁决；P-129 的 API 组名不可读结论 | ✅ |
| GitHub REST 只读（E1） | run 对象 `concurrency`、分支保护 `contexts` | ✅ |
| 历史行为读数（E1） | P-124 的 push 连推取消实证 | ✅ 可复核 |

**降级链记录**：

1. `runs` API 仍不返回并发组（run `43792161443` 的 `concurrency = null`）⇒ 组名不能直读，J/K 类验收继续采用「静态表达式 + 合并后并发行为」双证据（P-129 U-1 已登记该平台限制）。
2. 无法在 PR 分支上制造 `push` 事件（P-127 已将 push 收窄为 main）⇒ 撞组的行为读数只能在合并后用「push run + 两次 dispatch」完成，写入 §11 观察项。

## 3. 撞组机制（承接 P-128 R-1..R-5）

`ci.yml` 当前组键（L12-L14）：

```yaml
concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

| 事件 | `github.ref` | 解析组名 | 与 main push 同组？ |
|---|---|---|---|
| `push`（main） | `refs/heads/main` | `ci-CI-refs/heads/main` | — |
| `workflow_dispatch`（main） | `refs/heads/main` | `ci-CI-refs/heads/main` | **是** |
| `pull_request`（PR N） | `refs/pull/N/merge` | `ci-CI-refs/pull/N/merge` | 否 |

同组 + `cancel-in-progress: true` ⇒ 后进入者杀掉在跑者，方向对称：手动 dispatch 会杀掉 main push run，main push 也会杀掉手动 dispatch run。`workflow_dispatch` 是 D-4 引入的排障入口，P-127 未覆盖该面，P-128 将其登记为 U-3。

## 4. 修法影响分析

### 4.1 改后组名

```yaml
group: ci-${{ github.workflow }}-${{ github.event_name }}-${{ github.ref }}
```

| 事件 | 解析组名 |
|---|---|
| `push`（main） | `ci-CI-push-refs/heads/main` |
| `workflow_dispatch`（main） | `ci-CI-workflow_dispatch-refs/heads/main` |
| `pull_request`（PR N） | `ci-CI-pull_request-refs/pull/N/merge` |

三类两两不同。

### 4.2 哪些关系不变

- **push→push**：同分支连续 push 仍解析同一字符串（`event_name` 恒为 `push`）⇒ 前序 run 仍被取消；
- **PR→PR**：同一 PR 的新提交仍解析同一字符串（`event_name` 恒为 `pull_request`，ref 恒为 `refs/pull/N/merge`）⇒ 前序 run 仍被取消；
- **dispatch→dispatch**：同 ref 连续手动触发仍互相取消（这既是保留的语义，也是 §5 行为探针的抓手）。

即：改动只切断「跨事件」的取消，不改变「同事件」的取消。

### 4.3 历史基线读数

P-124 已在旧组键下实测 push 连推取消：探针分支 `probe/concurrency-cancel` 两次 push（`ff718f5` → `2438158`），前序 run `43727211211` 结论 `cancelled`、后继 `43727260130` 继续执行（[PROGRESS P-124 行](../../docs/PROGRESS.md#L131)）。改后同事件组名逐字不变，该语义由 §4.2 的字符串恒等关系保持。

## 5. 验收证据方案

组名不可直读（§2 降级链），故采用「静态 + 行为」双证据：

**静态（提交前）**

1. YAML 断言组键表达式逐字含 `github.workflow` / `github.event_name` / `github.ref` 三段；
2. 断言 `cancel-in-progress: true` 未动；
3. 断言触发器集合与 job 结构未动；
4. `git diff --stat` 仅 `ci.yml` 一个文件。

**行为（合并后，写入 CHECKLIST §11）**

1. 合并产生 push run `P` 后，立即 `gh workflow run ci.yml --ref main` 得到 dispatch run `D1`；
2. 观察 `P` 是否仍为 `in_progress` / 最终 `success`，而非 `cancelled` ⇒ 证明跨事件不再互杀；
3. 再立即触发 `D2`：`D1` 应被 `cancelled`（同事件同 ref 仍取消）⇒ 证明取消语义未被误伤；
4. 读数记入 §11；必要时手动取消 `D2` 以节省 runner。

## 6. 外部锚点与上游依据

| 来源 | 要点 | 等级 |
|---|---|---|
| P-128 RESEARCH §4 / U-3 | 根因链与「dispatch 同类潜伏面」判定 | E1（本仓文档） |
| P-128 RESEARCH §5.1/§5.2 | gh-aw 官方矩阵、`nativesoil/handover` 组键含 `event_name` | T2/T3（经 P-128） |
| P-129 IMPLEMENTATION E1-3 | run 对象 `concurrency = null` | E1（本仓实测） |
| P-124 PROGRESS 行 | 旧组键下 push 连推取消的真实读数 | E1（本仓实测） |

## 7. 与既有不变式的映射

| 既有约束 | 本批结论 |
|---|---|
| P-127 I-1（PR 单 run） | 不变（PR 组名仍按 PR 唯一） |
| P-127 I-3（main 仍触发且不被误杀） | 增强：dispatch 不再能杀 push |
| P-127 I-4（同 ref 取消前序） | 收窄为「同 ref 同事件」；同事件内逐字不变 |
| P-129 J-1（heavy 与 CI 不同组） | 仍成立（工作流名不同） |
| 分支保护 7 必需检查 | 不改名、不入集 |

## 8. 未决项

| ID | 内容 | 判据 | 触发条件 | 当前倾向 | 证据等级 |
|---|---|---|---|---|---|
| U-1 | 组名无 API 直读 | 官方是否新增字段 | 官方新增则补直读 | 接受双证据 | E1 实测 |
| U-2 | 合并后行为探针需真实并发窗口 | push run 与 D1 是否重叠 | 合并后立即触发 | 一次性完成 | 待执行 |
| U-3 | 未来新增 `schedule` 到 `ci.yml` | 组键是否再次发生跨事件面 | 新增触发器时 | 组键已含事件维，天然隔离 | E1 |
| U-4 | `D2` 探针会消耗一次完整 CI run | 是否手动取消 | 取得取消读数后 | 手动取消省钱 | 待执行 |

## 9. 诚实边界

- 本批只改 `ci.yml` 组键一行与一行注释；`heavy.yml`、`tests/`、`researchclaw/`、分支保护零改动。
- 「组名不同」在提交前只有静态证据；行为读数必须在合并后取得，列入 §11，不使用推断冒充实测。
- 同事件取消语义的保持由字符串恒等关系论证，历史行为基线来自 P-124；本批不复跑旧组键探针。
