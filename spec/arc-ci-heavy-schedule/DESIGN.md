---
id: arc-ci-heavy-schedule-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-ci-heavy-schedule-RESEARCH]
upstream: null
---

# 设计：定时重型执行路径（P-129 实施批）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **变更面**：新增 `.github/workflows/heavy.yml` 一个文件；`ci.yml`、`tests/`、`researchclaw/`、分支保护零改动。
> **承接**：[P-128 DESIGN](../arc-ci-concurrency-semantics/DESIGN.md) §2 D-1..D-5 与 §3 J-1..J-7。

---

## 1. 目标与非目标

**目标**

1. 为 `-m heavy` 用例提供**定期执行路径**，兑现 arc-ci-flaky-heavy U-2。
2. 定时 run 与 main push run **不同组**，不击穿 P-127 I-3。
3. 工作流自身可手动触发，用于排障与补跑。
4. 不改变 `ci.yml` 的任何语义，不改变 7 个必需检查名。

**非目标**

- 不修复 F-1/F-2 的时序 flaky 根因（arc-ci-flaky-heavy U-1 另立）。
- 不把 heavy 加入分支保护必需检查集。
- 不改 `tests/ci_exclusions.yaml`、不改 marker 机制、不新增测试。
- 不引入 tag / release / pull_request 触发器。

## 2. 决策

| 决策 | 内容 | 依据 |
|---|---|---|
| D-1 | 采纳 P-128 方案 A：新建独立 `heavy.yml`，仅 `schedule` + `workflow_dispatch` | P-128 DESIGN D-1；RESEARCH §5.1 |
| D-2 | 组键 = `heavy-${{ github.workflow }}-${{ github.event_name }}-${{ github.ref }}` | P-128 D-2；RESEARCH §5.2 |
| D-3 | `cancel-in-progress: false`；**不写 `queue` 键** | RESEARCH §3.2（键存在性不可证）、§5.2 |
| D-4 | `heavy.yml` 不进入分支保护必需检查集 | P-128 D-4；RESEARCH §4 E1-5 |
| D-5 | cron = `17 18 * * 1`（UTC，周一 18:17 = 北京周二 02:17） | RESEARCH §3.1 整点告警、§5.1 频率论证 |
| D-6 | Python 3.11、依赖 `.[dev,server,mcp]`、`timeout-minutes: 60` | RESEARCH §5.3 |
| D-7 | 增加一步组键回显，作为 J-1 的运行期证据 | RESEARCH §5.4；U-1 登记强度上限 |

## 3. 不变式（验收口径）

| 编号 | 不变式 | 可观测读数 |
|---|---|---|
| J-1 | 定时 run 与 main push run **不同组** | YAML 组键静态断言 + 日志 `concurrency_key=heavy-Heavy-<event>-<ref>` + 并发不互杀 |
| J-2 | main push run 仍触发，且不因 heavy 被取消（承接 P-127 I-3） | 合并后 main push run `event=push`、`conclusion=success` |
| J-3 | `ci.yml` 的同事件取消语义不变 | `cancel-in-progress: true` 逐字未动；`git diff` 对 `ci.yml` 为空 |
| J-4 | 分支保护 7 个必需检查名逐字不变 | `required_status_checks.contexts` 只读比对 |
| J-5 | `ci.yml` 行为零变更 | `git diff --exit-code -- .github/workflows/ci.yml` |
| J-6 | heavy job 只跑 `-m heavy`，不重复全量 | 本机 `2 passed, 3778 deselected`；run 日志同口径 |
| J-7 | schedule 停摆可观测 | `workflow_dispatch` 手动补跑通道 + run 历史；登记观察项 |

## 4. 目标形态

```yaml
name: Heavy

on:
  schedule:
    - cron: "17 18 * * 1"    # UTC，周一 18:17 = 北京时间周二 02:17；避开整点高峰
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

      - name: Concurrency key evidence (J-1)
        run: echo "concurrency_key=heavy-${{ github.workflow }}-${{ github.event_name }}-${{ github.ref }}"

      - uses: actions/setup-python@v7
        with:
          python-version: "3.11"
          cache: pip

      - name: Install dev dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e ".[dev,server,mcp]"

      - name: Run heavy tests
        run: python -m pytest tests -m heavy -q
```

## 5. 不采用形态

- **并入 `ci.yml`**：会使 schedule 与 main push 同组，必须同时改组键，直接触发 P-128 的撞组面；J-5 也不再成立。
- **`queue: max`**：与 `cancel-in-progress: true` 互斥，且本批已不采用 `queue`。
- **job 级 `concurrency`**：workflow 级组仍作用于整个 run，不能逃逸（P-128 U-2 的 E1 推论）。
- **日级 cron**：会把已知 flaky 用例放大为每日噪声；周级已满足「定期执行路径」。

## 6. 风险与回退

| 风险 | 缓解 | 回退 |
|---|---|---|
| 已知 flaky 用例周期性红灯 | 非必需检查，不阻塞 main；周级低频 | 删除 `heavy.yml` 即完全回退 |
| schedule 延迟或排队任务被丢弃 | 分钟位避开整点；U-2 登记；`workflow_dispatch` 补跑 | 手动触发 |
| 60 天无活动自动禁用 | U-4 观察项 | 手动触发或提交 cron 变更重新激活 |
| 组键表达式写错仍撞组 | J-1 静态断言 + 日志回显 + 并发行为读数 | 修正组键（单行） |

## 7. 与后续批次接口

- **P-130**：`ci.yml` 组键补 `github.event_name`，修 `workflow_dispatch` 与 push 撞组（P-128 U-3 已裁决为独立小批）；本批不触碰 `ci.yml`。
- **遗留观察**：U-1 组名无 API 直读、U-3 heavy 根因专项、U-4 schedule 自动禁用。

## 8. 验收对齐

本设计对应的验收项见 [CHECKLIST.md](./CHECKLIST.md)（v1.0 / accepted），覆盖：文档一致性、工作流功能、J-1..J-7 不变式、错误处理、性能、兼容性与范围卫生。
