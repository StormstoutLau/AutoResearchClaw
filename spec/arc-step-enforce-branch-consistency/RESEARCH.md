---
id: arc-step-enforce-branch-consistency-RESEARCH
type: design
version: 1.0
status: draft
date: 2026-11-10
depends: [arc-master-roadmap, arc-g1-readiness-research-CHECKLIST]
upstream: arc-g1-readiness-research-CHECKLIST
---

# 调研：step_enforce 两分支的 feature 绑定门槛不一致（R-5）

> **Feature**：修复 P-023 复核登记的 R-5——`step_enforce` 的两个批次分支对「P 行必须声明 `spec/<feature>/` 链接」采用不同门槛。
> **Spec 步骤**：Step 1-2（T1：改 Layer-1 门禁脚本，命中强制升级条款）

## 1. 问题复现

| 场景 | 结果 |
|---|---|
| P-022（T1，有 spec/ 链接）+ P-023（T3，无 spec/ 链接）**同一提交** | ❌ `step-enforce: P-023 未声明任何 spec/<feature>/ 链接` |
| 两笔提交（`99dc102` 后 `2b18473`） | ✅ 各自通过 |

即：**同一份 PROGRESS 内容，因提交粒度不同而判定不同**。

## 2. 源码取证

| # | 事实 | 位置 |
|---|---|---|
| F-1 | 有 spec 文档改动时走 `_resolve_declared`：对**每个**声明 P 无条件要求 `row["features"]` 非空 | `step_enforce.py:379-395` |
| F-2 | 仅有 PROGRESS 改动时走 `batch-registration`：`features` 仅在 `_pid_num(pid) >= BATCH_BINDING_MIN_P` 时要求 | `step_enforce.py:471-480` |
| F-3 | `BATCH_BINDING_MIN_P = 129` | `step_enforce.py:51` |
| F-4 | 同一常量在两处使用：L418（`_resolve_maintenance`）、L478（`batch-registration`），**唯独 `_resolve_declared` 未用** | Grep `BATCH_BINDING_MIN_P` 共 3 命中 |
| F-5 | ARC 现有 P 编号 1..23，全部 `< 129` ⇒ 该门槛在 ARC **从未生效** | `docs/PROGRESS.md` |

## 3. 语义分析

`BATCH_BINDING_MIN_P` 的原意（源项目语境）：P-129 起的批次必须把 P 行绑定到 feature 目录；此前批次为历史豁免。

- **L478 的实现是正确口径**：新批次（≥129）必须绑定，历史批次豁免。
- **L386 的实现是更严口径**：无论编号，一律要求绑定。
- 两者冲突时取哪一个？**应取已登记的一致口径（L478）**——因为：
  1. 常量是同一份，语义应单一真源（I-10 同源）；
  2. L386 的更严口径在 ARC 下不可满足：T3 批次按定义不产出四文档，**结构上没有 feature 可绑定**（P-020/P-023 两例实证）；
  3. 「T1 批次是否真的绑定了 feature」并**不会因此失守**：`_resolve_declared` 后段仍有覆盖检查 `missing = docs_features - allowed`（L392-395），P 行漏链接会导致变更 feature 未被覆盖 → 仍然红。

**结论**：修复 = 让 L386 采用与 L478 相同的谓词；不新增规则、不放宽覆盖检查。

## 4. 修复方案对比

| 方案 | 做法 | 评价 |
|---|---|---|
| **A 对齐门槛**（推荐） | L386 改为 `if not row["features"] and _pid_num(pid) >= BATCH_BINDING_MIN_P: error` | 最小改动；两分支同谓词；覆盖检查兜底 |
| B 重定门槛为 1 | 让绑定在 ARC 立即生效 | 会让所有 T3 批次永久红；需要另造「T3 免绑定」标记，规则膨胀 |
| C 拆分批次 | 规定 T3 与 T1 不得同提交 | 用流程约束掩盖工具缺陷；且 CI 单提交场景无法保证 |

**裁决 = A**。

## 5. 影响面

| 面 | 影响 |
|---|---|
| 门禁严格度 | 等价于 L478 现有口径；覆盖检查不变 |
| 存量批次 | 零变化（历史 P 行不受影响；P-001..P-023 均 < 129） |
| CI | 无配置变更 |
| 回滚 | 单行还原 |

## 6. 未决项

- **U-1 门槛在 ARC 的实际生效点**：判据 = ARC 的 P 编号何时接近 129；触发 = P ≥ 129 前；倾向 = 届时不重定门槛、直接进入绑定（与源项目同构）；E2。
- **U-2 混合批的覆盖语义**：T3 行无 feature 时，`allowed` 仅由 T1 行贡献；判据 = 变更 feature 是否被覆盖；倾向 = 保持现状（覆盖检查已兜底）；E1。

## 7. 引用

1. 仓内：[arc-g1-readiness-review-20261110.md §7 C-8](../../docs/arc-g1-readiness-review-20261110.md)
2. 仓内：`scripts/spec/step_enforce.py` L51 / L379-395 / L471-480
3. 仓内：[docs/PROGRESS.md](../../docs/PROGRESS.md)（P-022/P-023 两笔提交先例）
