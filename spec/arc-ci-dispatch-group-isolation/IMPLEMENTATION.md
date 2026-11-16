---
id: arc-ci-dispatch-group-isolation-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-ci-dispatch-group-isolation-DESIGN, arc-ci-dispatch-group-isolation-RESEARCH]
upstream: null
---

# 实施：dispatch × push 组键隔离（P-131）

> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **变更**：[.github/workflows/ci.yml](../../.github/workflows/ci.yml) 的 `concurrency.group` 一行 + 一行注释。
> **未改动**：`heavy.yml`、`tests/`、`researchclaw/`、分支保护设置、触发器集合、job 结构。

---

## 1. 变更清单

| 文件 | 改动 | 行数 |
|---|---|---|
| [.github/workflows/ci.yml](../../.github/workflows/ci.yml) | `concurrency.group` 加入 `github.event_name`；新增一行说明注释 | +2 / −1 |
| `spec/arc-ci-dispatch-group-isolation/` | 四文档 | 新增 |
| `tools/spec_runner/sessions/specwf-p131-ci-dispatch-group-isolation.jsonl` | 五步决策流 | 新增 |
| `docs/PROGRESS.md` | 追加 P-131 行 | 追加 |

`git diff --stat`：`ci.yml | 3 +-`（+2/−1）；`heavy.yml` 的 `git diff --exit-code` = 0。

## 2. 前后对照

```yaml
# 改前（L12-L14）
concurrency:                # D-4：同分支连续 push 取消前序 run
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

# 改后（L12-L15）
concurrency:                # D-4：同分支连续 push 取消前序 run
  # P-131：事件进组键，隔离 dispatch 与 push；同事件同 ref 仍取消
  group: ci-${{ github.workflow }}-${{ github.event_name }}-${{ github.ref }}
  cancel-in-progress: true
```

## 3. 机械校验（本机）

校验脚本（临时，不入库）读取 YAML 并断言：

| 断言 | 结果 |
|---|---|
| `ci.yml` 可被 `yaml.safe_load` 解析 | ✅ |
| 触发器集合 = `{push, pull_request, workflow_dispatch}` | ✅ |
| `push.branches == ["main"]` | ✅ |
| `concurrency.group` 逐字等于目标表达式（含 `event_name`） | ✅ |
| `cancel-in-progress is True` | ✅ |
| job 条目数 = 5；5 个 `name:` 逐字未变 | ✅ |
| 矩阵 `3.11/3.12/3.13` 必需 + `3.14` experimental | ✅ |
| `git diff --exit-code -- .github/workflows/heavy.yml` | exit 0 |

输出摘要：`yaml parse: OK` / `group: ci-${{ github.workflow }}-${{ github.event_name }}-${{ github.ref }}` / `jobs: 5 required names: OK` / `heavy_diff_exit=0`。

## 4. 只读远端读数

| 编号 | 观测 | 读数 |
|---|---|---|
| E1-1 | 分支保护必需检查 | 7 名，逐字与改前一致（见 RESEARCH §1 目标 4） |
| E1-2 | run 对象组名可得性 | run `43792161443` 的 `concurrency = null` ⇒ 无直读面 |
| E1-3 | 旧组键的历史取消基线 | P-124：run `43727211211` `cancelled`、后继 `43727260130` 执行（PROGRESS P-124 行） |
| E1-4 | 合并后行为读数 | 未发生；按 DESIGN §6 在合并后执行 push + D1 + D2 探针，记入 CHECKLIST §11 |

## 5. 不变式落点

| 不变式 | 落点 |
|---|---|
| K-1 三类组名不同 | §3 静态断言；合并后 push 与 D1 并发读数 |
| K-2 push→push 取消 | RESEARCH §4.2 字符串恒等；P-124 历史基线 |
| K-3 PR→PR 取消 | RESEARCH §4.2 字符串恒等 |
| K-4 main push 1 run | 触发器与 `branches: [main]` 未动；合并后计数 |
| K-5 7 检查名不变 | E1-1 只读比对 + §3 job 名断言 |
| K-6 范围卫生 | §1 `git diff --stat`；`heavy.yml` diff = 0 |

## 6. 偏差

| 编号 | 偏差 | 处置 |
|---|---|---|
| D-1 | 在组键上方新增一行注释 | 说明跨事件隔离意图并标注批次号；不含行为变更 |
| D-2 | 合并后探针会额外产生 2 个 dispatch run | 取得 D1 被 D2 取消的读数后手动取消 D2（U-4） |

## 7. 门禁读数

| 门禁 | 命令 | 读数 |
|---|---|---|
| dc_validator | `python scripts/spec/dc_validator.py --check-all` | 见 session 第 4 步 |
| grandfather_gate | `python scripts/spec/grandfather_gate.py` | 见 session 第 4 步 |
| step-gate | `python tools/spec_runner/spec_runner.py step-gate --session specwf-p131-ci-dispatch-group-isolation --expect research design implement verify finalize` | 见 session 第 4 步 |
| verify-anchor | `python tools/spec_runner/spec_runner.py verify-anchor --session specwf-p131-ci-dispatch-group-isolation` | 见 session 第 4 步 |
| step_enforce | `python scripts/spec/step_enforce.py <staged files>` | 见 session 第 4 步 |
| pre-commit | `pre-commit run --all-files` | 见 session 第 5 步 |

> 说明：门禁结构化读数记录在决策流第 4/5 步；本文档只保留可复现命令与稳定读数，避免「验后改文档」造成 digest 失配。

## 8. 未改动证明

- `heavy.yml`：`git diff --exit-code` = 0。
- `tests/`、`tests/ci_exclusions.yaml`、`pyproject.toml`、`researchclaw/`：零改动。
- 分支保护：只读，未发 PUT；`contexts` 仍为 7 名。
- 批外工作树保留：`researchclaw/vendor/auto_prover/datatypes/__init__.py`（CRLF 漂移）与 `docs/arc-g4-midpoint-20261113.md`（未跟踪）不纳入本批。
