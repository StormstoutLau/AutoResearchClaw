---
id: arc-ci-concurrency-semantics-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-ci-concurrency-semantics-RESEARCH]
upstream: null
---

# 设计文档：并发组事件隔离与 heavy 定时执行路径（P-128 调研批产出，供实施批）

> **Feature**：P-128。本文件是调研批的设计产物，**不含实施**；实施由后续批次按本设计落地。
> **Spec 步骤**：Step 3-4（调研批）。
> **依据**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。

## 1. 设计目标

1. 定时重型任务进入**非人工触发路径**（兑现 arc-ci-flaky-heavy U-2），且不与 main 的 push run 互杀（保住 P-127 I-3）。
2. 任何新增触发器**不得**改变 `ci.yml` 的既有语义（I-1/I-2/I-3/I-4/I-5/I-6 全保持）。
3. 组键在触发器维度上**自证隔离**：不同事件、不同工作流解析出的组名互不相同。
4. 修法必须可证伪：每组不变式都对应一条可观测读数。

## 2. 决策（承接 RESEARCH §6）

| 决策 | 内容 | 依据 |
|---|---|---|
| D-1 | **采纳方案 A**：新建独立 `heavy.yml`（`.github/workflows/heavy.yml`，本批不创建），仅 `schedule` + `workflow_dispatch`，`ci.yml` 零改动 | RESEARCH §6；A 对 I-1..I-6 零触碰 |
| D-2 | 组键 = `heavy-${{ github.workflow }}-${{ github.event_name }}-${{ github.ref }}` | RESEARCH §5.1/§5.2（官方项目与同构仓均带事件维） |
| D-3 | `cancel-in-progress: false` + `queue: single` | RESEARCH §8 U-4；定时重型用例被取消等于丢一次观测 |
| D-4 | `heavy.yml` **不进入**分支保护必需检查集 | 定时任务不在 PR 路径上，进入必需集会让 PR 永久 pending |
| D-5 | 备选方案 B（`ci.yml` 组键加事件维）**本批不采纳**；仅当 D-1 被否决时启用，且须重验 P-127 I-4 | RESEARCH §6 |

## 3. 不变式（实施批验收口径）

| 编号 | 不变式 | 可观测读数 |
|---|---|---|
| J-1 | 定时 run 与 main push run **不同组** | 两个 run 的 `concurrency.group` 读数不同；并发时互不 `cancelled` |
| J-2 | main push run 仍触发，且不因 schedule/dispatch 被取消（承接 I-3） | main push run 的 `event=push`、`conclusion=success` |
| J-3 | 同事件重复触发仍去重 | 同分支连续 push 时前序 run `cancelled` |
| J-4 | 分支保护 7 个必需检查名逐字不变 | `branches/main/protection` contexts 比对 |
| J-5 | `ci.yml` 行为零变更（选 A 时） | `git diff` 对 `ci.yml` 为空 |
| J-6 | heavy job 只跑 `-m heavy`，不重复全量 | run 日志收集数 ≈ heavy 用例数 |
| J-7 | schedule 停摆可观测 | 连续 2 个周期无 run 时有人工告警路径（登记为观察项） |

## 4. 目标形态（实施批照此落地）

```yaml
name: Heavy

on:
  schedule:
    - cron: "0 18 * * *"      # UTC；对应北京时间次日 02:00
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: heavy-${{ github.workflow }}-${{ github.event_name }}-${{ github.ref }}
  cancel-in-progress: false

jobs:
  heavy:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.11"
          cache: pip
      - run: python -m pip install --upgrade pip
      - run: python -m pip install -e ".[dev,server,mcp]"
      - run: python -m pytest tests -m heavy -q
```

> 仅为形态示意，具体 cron、超时与依赖组由实施批按当时 `pyproject.toml` 实测确定。

## 5. 为什么不是其它形态（承接 RESEARCH §6）

- **C（job 级覆写）**：workflow 级组作用于整个 run，job 级只新增本 job 的组；无法把 run 从上游组里摘出来（E1，U-2 待实测）。
- **D（`cancel-in-progress` 表达式）**：取消判定由**新进入者**执行，单向放行只解决一半方向（RESEARCH §6）。
- **E（`queue: max`）**：与 `cancel-in-progress: true` 组合非法，且串行不解决误杀。
- **F（错峰）**：不可证伪，push 时间不可控。

## 6. 风险与回退

| 风险 | 缓解 | 回退 |
|---|---|---|
| 新增 workflow 增加维护面 | 单文件、单 job、无产物 | 删除 `heavy.yml` 即完全回退 |
| 公开仓 60 天无活动自动禁用 schedule（RESEARCH U-5） | J-7 观察项 + 运维提醒 | 手动 `workflow_dispatch` 补跑 |
| heavy 用例本身 flaky（arc-ci-flaky-heavy U-1 未定位） | 定时 run 失败只红自己，不影响 main 必需检查 | 保持非必需检查 |
| 组键表达式写错导致仍撞组 | J-1 以两个真实 run 的组名读数验证，不靠推断 | 回到方案 B（1 行改动） |

## 7. 与后续批次的接口

- **实施批（建议 P-129）**：按 §4 落地 `heavy.yml` + 8 项验收（J-1..J-7 + 组名读数）。
- **可选同批项**：`ci.yml` 组键补 `event_name`（修 `workflow_dispatch` 撞 push，RESEARCH U-3）；若不并入，单独登记。
- 本设计不修改任何 `researchclaw/` 代码、`tests/` 与分支保护设置。
