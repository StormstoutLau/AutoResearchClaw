---
id: arc-ci-trigger-dedupe-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-ci-trigger-dedupe-DESIGN, arc-ci-trigger-dedupe-RESEARCH]
upstream: null
---

# 实施：CI 双触发去重（P-127）

> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **变更**：`.github/workflows/ci.yml` 一处一行新增。
> **实测**：探针分支 + 草稿 PR 已取得行为读数（§4）。

---

## 1. 变更清单

| 文件 | 改动 | 行数 |
|---|---|---|
| [.github/workflows/ci.yml](../../.github/workflows/ci.yml) | `on.push` 下新增 `branches: [main]` 与说明注释 | +1 |

`git diff --stat` 实测：`1 file changed, 1 insertion(+)`。

## 2. 前后对照

```yaml
# 改前（L3-L6）
on:
  push:
  pull_request:
  workflow_dispatch:

# 改后（L3-L7）
on:
  push:
    branches: [main]        # P-127：分支推送不再触发，PR 分支一律走 pull_request，消除同 commit 双 run
  pull_request:
  workflow_dispatch:
```

`permissions`、`concurrency`、5 个 job 定义、全部 step 逐字未动。

## 3. 机械校验（本机）

校验脚本（临时，不入库）读取 YAML 并断言：

| 断言 | 结果 |
|---|---|
| `on.push == {branches: [main]}` | ✅ |
| `pull_request` / `workflow_dispatch` 存在 | ✅ |
| job 条目数 = 5（`tests` 矩阵展开后运行时检查 = 8） | ✅ |
| 必需 job 名全在：`Packaging / wheel smoke`、`Extras import`、`Tests (${{ matrix.python-version }})`、`Roadmap coverage gates`、`Spec gates (pre-commit all-files)` | ✅ |
| 矩阵 `python-version == ["3.11","3.12","3.13"]`，`3.14` 为 `experimental: true` | ✅ |
| `concurrency.group` 与 `cancel-in-progress` 原值 | ✅ |

输出摘要：`jobs: 5` / `yaml parse: OK` / `required subset: OK (3.11-3.13 required, 3.14 experimental)`。

## 4. 行为读数（探针，P-127 实施期）

为在**提交前**取得真实读数，先在临时分支 `probe/ci-trigger-dedupe` 上落地同一改动（commit `992d268`），取证后关闭草稿 PR #8 并删除分支：

| 编号 | 观测 | 读数 |
|---|---|---|
| E2-1 | 探针分支 `push` 是否产生 run | `runs(head_sha=992d268).total_count = 0` |
| E2-2 | 同 commit 开草稿 PR 后的 run 数 | **1**（`43748816610`，`event=pull_request`） |
| E2-3 | 该 run 的 job 数 | **8**，全部 `success` |
| E2-4 | 运行时检查名 | `Packaging / wheel smoke`、`Extras import`、`Tests (3.11)`、`Tests (3.12)`、`Tests (3.13)`、`Tests (3.14)`、`Roadmap coverage gates`、`Spec gates (pre-commit all-files)` |
| E2-5 | 墙钟 / job 时长和 | `18:48:28Z → 18:50:26Z`（118 s）/ 544 s |

E2-1 + E2-2 合起来即「同 commit 由 2 run 降为 1 run」的直接证据；E2-4 证明 7 个必需检查名未变（3.14 为 experimental，非必需）。

## 5. 不变式落点

| 不变式 | 落点 |
|---|---|
| I-1 PR 单 run | E2-2（探针）+ 本批 PR 复验 |
| I-2 7 检查名不变 | E2-4；§3 断言 |
| I-3 main 仍跑 | `branches: [main]` 白名单；合并后 main push 读数 |
| I-4 同 ref 取消 | `concurrency` 零改动（§3 断言） |
| I-5 触发器集合 | §2 前后对照 |
| I-6 范围卫生 | `git diff --stat` 仅 1 文件 |

## 6. 偏差

| 编号 | 偏差 | 处置 |
|---|---|---|
| D-1 | 实施期额外产生探针分支与草稿 PR #8 | 已在取得读数后 `gh pr close 8 --delete-branch`；探针 commit 不进入 main（squash 合并只含正式批次） |
| D-2 | 首次机械校验脚本错把 5 个 job 条目当作 8 个检查 | 修正断言（矩阵展开口径），非代码缺陷，已记录以免后续复算踩同坑 |

## 7. 门禁读数

| 门禁 | 读数 |
|---|---|
| `grandfather_gate.py` | 0 违规（DC1-DC5 + R7） |
| `step-gate --expect research design implement verify finalize` | 决策链一致，exit 0 |
| `verify-anchor` | 锚点全部真实，0 硬性 / 0 软性 |
| `step_enforce.py` | `mode=batch pid=P-127 digest_bound=1` |
| `pre-commit run --all-files` | 10 钩子全 Passed |
