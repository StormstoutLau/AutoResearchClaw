---
id: arc-ci-dispatch-group-isolation-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-ci-dispatch-group-isolation-RESEARCH]
upstream: null
---

# 设计：dispatch × push 组键隔离（P-131）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **变更面**：`.github/workflows/ci.yml` 的 `concurrency.group` 一行 + 一行注释；其余零改动。
> **上游**：[P-128 DESIGN](../arc-ci-concurrency-semantics/DESIGN.md) §6 方案 B；[P-128 RESEARCH](../arc-ci-concurrency-semantics/RESEARCH.md) U-3 已裁决为独立小批。

---

## 1. 目标与非目标

**目标**

1. main 上 `workflow_dispatch` 与 `push` 不再共享并发组，手动重跑不再杀掉 push run。
2. 同事件同 ref 的取消语义逐字保持（push→push、PR→PR 仍取消前序）。
3. 7 个必需检查名、分支保护、`heavy.yml`、`tests/` 零改动。

**非目标**

- 不改 `heavy.yml`（其组键已含事件维）。
- 不改触发器集合、job 结构、矩阵、超时、缓存。
- 不新增门禁脚本；验收复用现有静态断言与合并后行为读数。

## 2. 决策

| 决策 | 内容 | 依据 |
|---|---|---|
| D-1 | `concurrency.group` 改为 `ci-${{ github.workflow }}-${{ github.event_name }}-${{ github.ref }}` | RESEARCH §4.1；P-128 方案 B |
| D-2 | `cancel-in-progress: true` 保持不变 | RESEARCH §4.2：同事件取消语义需保留 |
| D-3 | 仅改 `ci.yml`；`heavy.yml` 与其余文件零改动 | RESEARCH §1 目标 4 |
| D-4 | 组键改动不进入分支保护必需检查集 | 组名不是检查名；7 名逐字不变 |
| D-5 | 行为读数在合并后以「push run + 两次 dispatch」完成 | RESEARCH §5；提交前无 push 事件可制造 |
| D-6 | 回退 = 删除 `-${event_name}` 一段 | 单行可逆 |

## 3. 不变式（验收口径）

| 编号 | 不变式 | 可观测读数 |
|---|---|---|
| K-1 | main 上 push / dispatch / PR 三类组名两两不同 | 静态表达式断言；合并后 push run 与 D1 并发且均非 `cancelled` |
| K-2 | push→push 同分支仍取消前序 | 组字符串中 `event_name` 恒为 `push`，同 ref 逐字相同；P-124 历史基线 |
| K-3 | PR→PR 同 PR 仍取消前序 | 组字符串中 `event_name` 恒为 `pull_request`、ref 恒定 |
| K-4 | main 每次 push 仍产生 1 个 run | 合并后 `event=push` 计数 = 1 |
| K-5 | 7 个必需检查名逐字不变 | `required_status_checks.contexts` 只读比对 |
| K-6 | 范围卫生 | `git diff --stat` 仅 `ci.yml`；`heavy.yml` 哈希不变 |

## 4. 目标形态

```yaml
concurrency:                # D-4：同分支连续 push 取消前序 run
  group: ci-${{ github.workflow }}-${{ github.event_name }}-${{ github.ref }}  # P-131：事件进组键，隔离 dispatch 与 push
  cancel-in-progress: true
```

改后解析：

| 事件 | 组名 |
|---|---|
| `push`（main） | `ci-CI-push-refs/heads/main` |
| `workflow_dispatch`（main） | `ci-CI-workflow_dispatch-refs/heads/main` |
| `pull_request`（PR N） | `ci-CI-pull_request-refs/pull/N/merge` |

## 5. 不采用形态

- **拆独立手动工作流**：会复制 8 个 job 或引入 `workflow_call`，改动面远大于一行，且必需检查聚合面变化。
- **`cancel-in-progress` 表达式只对 dispatch 放行**：取消由新进入者执行，单向放行无法阻止 push 杀掉 dispatch（P-128 方案 D 已淘汰）。
- **job 级 `concurrency`**：无法逃逸 workflow 级组（P-128 U-2 的 E1 推论）。

## 6. 风险与回退

| 风险 | 缓解 | 回退 |
|---|---|---|
| 组键表达式写错导致仍撞组 | 静态逐字断言；合并后 push/D1/D2 三点行为读数 | 修正组键 |
| 误伤同事件取消 | §4.2 字符串恒等论证 + D2 取消 D1 的实测 | 删除 `event_name` 段 |
| 手动探针消耗 runner | D2 取得取消读数后手动取消 | `gh run cancel` |
| 未来在 `ci.yml` 加 `schedule` | 组键已含事件维，天然隔离（U-3） | 无需额外动作 |

## 7. 与后续批次接口

- **观察项**：合并后行为读数回填 CHECKLIST §11（若需回填则按 P-126/P-130 先例另开小批）。
- **无后续实施依赖**：P-128 的 U-3 在本批关闭；U-1（组名无 API 直读）继续保留。

## 8. 验收对齐

本设计对应的验收项见 [CHECKLIST.md](./CHECKLIST.md)（v1.0 / accepted），覆盖文档一致性、工作流功能、K-1..K-6、错误处理、性能、兼容性与范围卫生。
