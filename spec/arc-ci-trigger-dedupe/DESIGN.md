---
id: arc-ci-trigger-dedupe-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-ci-trigger-dedupe-RESEARCH]
upstream: null
---

# 设计：CI 双触发去重（P-127）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **变更面**：`.github/workflows/ci.yml` 的 `on` 块，一处三行。
> **不变量**：7 个必需检查名逐字不变；`spec-gates` 的 `BASE_SHA` 逻辑不变。

---

## 1. 目标与非目标

**目标**

1. 每个 PR 提交只产生 1 个 CI run（`pull_request`），消除同 commit 的 `push` 重复 run。
2. `main` 合并后仍有 1 次 CI run，`main` 状态不丢。
3. 7 个必需检查名、分支保护配置、`BASE_SHA` 推导全部零改动。

**非目标**

- 不优化单 run 内部耗时（job 并行/缓存已由 D-4 覆盖）。
- 不改测试选择、矩阵维度、heavy 排除机制。
- 不引入 tag / release / schedule 触发器。

## 2. 决策

### 2.1 决策 → 调研依据

| 决策 | 内容 | 依据 |
|---|---|---|
| D-1 | `push` 增加 `branches: [main]` 过滤 | RESEARCH §2 E1-5、§3、§4 方案 A、E1-9 |
| D-2 | `concurrency` 原样保留（`group` 与 `cancel-in-progress` 不动） | RESEARCH §3 第 3 条：PR ref 在 `synchronize` 之间稳定，取消语义仍有效；push 路径只剩 main |
| D-3 | 否决 job 级 `if` 过滤 | RESEARCH §4 方案 C（skipped 检查污染聚合） |
| D-4 | 否决跨事件共享并发组 | RESEARCH §4 方案 B（随机取消必需检查） |
| D-5 | 保留 `workflow_dispatch` | RESEARCH §5、§7 U-1（无 PR 分支的手动补跑通道） |

### 2.2 决策展开

**D-1**：`on.push` 从「无过滤」变为「仅 `main`」。这是唯一的行为改动点。选择分支过滤而非事件删除，是因为仍需 `main` 的推送后验证（squash 合并产生的 main 提交必须过 CI）。

**D-2**：并发组保持 `ci-${{ github.workflow }}-${{ github.ref }}`。改动后：

- PR 路径 `github.ref = refs/pull/<N>/merge`，同一 PR 的新提交（`synchronize`）仍落在同一组 ⇒ 前序 run 被取消，**保留「最新提交优先」语义**。
- push 路径只剩 `refs/heads/main`，连续直推 main 仍互相取消。
- 两条路径的 ref 天然不同，不再需要额外隔离。

## 3. 变更面

唯一文件：`.github/workflows/ci.yml`（第 3-6 行）。

```yaml
on:
  push:
    branches: [main]        # P-127：分支推送不再触发，PR 分支一律走 pull_request，消除同 commit 双 run
  pull_request:
  workflow_dispatch:        # D-4：允许手动触发排障与重跑
```

其余 194 行（permissions / concurrency / 8 个 job / 步骤）逐字不动。

## 4. 触发器契约（变更后）

| 事件 | 触发条件 | 产生的 run 数 | 检查聚合用途 |
|---|---|---|---|
| `push` | 目标分支为 `main` | 1 | 合并后 main 状态 |
| `pull_request` | PR 的 opened / synchronize / reopened | 1（同 PR 新提交取消前序） | **7 个必需检查的唯一来源** |
| `workflow_dispatch` | 手动 | 1 | 排障 / 补跑 |
| `push`（非 main 分支） | — | **0** | 无（由 PR 路径覆盖） |

## 5. 不变式

| 编号 | 内容 | 落点 |
|---|---|---|
| I-1 | 每个 PR head sha 恰产生 1 个 CI run（`event=pull_request`） | RESEARCH E1-9；本批 PR 读数 |
| I-2 | 7 个必需检查名逐字不变 | `ci.yml` job `name:` 字段零改动；分支保护读取 |
| I-3 | `main` 每次 push（含 squash 合并）产生 1 个 run | `branches: [main]` 白名单 |
| I-4 | 同 ref 连续 push 仍取消前序 | `concurrency` 未改动 |
| I-5 | 触发器集合 = `push(main)` + `pull_request` + `workflow_dispatch` | §4 契约表 |
| I-6 | 零产品代码、零测试、零其他工作流变更 | `git diff --stat` 仅 1 文件 |

## 6. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 无 PR 的分支推送无 CI 反馈 | 开发者失去早期信号 | `main` 受保护必须走 PR；`workflow_dispatch` 可手动补跑；约定先开 PR |
| 未来加 tag/release 触发器 | 去重矩阵可能失效 | 登记为 U-2 观察项，新增触发器时重评 |
| 首次推 main 的 `before=0` | `spec-gates` range 检查退化 | 已有显式跳过分支（`ci.yml` L182-L185），不改 |

## 7. 不采用方案（摘要）

见 RESEARCH §4：B 会随机取消必需检查 run；C 产生 skipped 同名检查；D 与目标无关且会漏跑 spec-gates。

## 8. 验收对齐

本设计对应的验收项见 [CHECKLIST.md](./CHECKLIST.md)（v1.0 / accepted），覆盖：配置形态、触发器契约、7 检查名、main 推送、并发语义、范围卫生。
