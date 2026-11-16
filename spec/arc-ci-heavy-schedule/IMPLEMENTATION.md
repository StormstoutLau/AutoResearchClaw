---
id: arc-ci-heavy-schedule-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-ci-heavy-schedule-DESIGN, arc-ci-heavy-schedule-RESEARCH]
upstream: null
---

# 实施：定时重型执行路径（P-129）

> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **变更**：新增 [.github/workflows/heavy.yml](../../.github/workflows/heavy.yml) 一个文件。
> **未改动**：`ci.yml`、`tests/`、`researchclaw/`、`tests/ci_exclusions.yaml`、分支保护设置。

---

## 1. 变更清单

| 文件 | 改动 | 性质 |
|---|---|---|
| [.github/workflows/heavy.yml](../../.github/workflows/heavy.yml) | 新建 36 行工作流 | 新增 |
| `spec/arc-ci-heavy-schedule/` | 四文档 | 新增 |
| `tools/spec_runner/sessions/specwf-p129-ci-heavy-schedule.jsonl` | 五步决策流 | 新增 |
| `docs/PROGRESS.md` | 追加 P-129 行 | 追加 |

`git diff --stat` 对既有受版本控制文件应只出现 `docs/PROGRESS.md`；`heavy.yml` 为新增未跟踪文件（提交时纳入）。

## 2. 最终形态

```yaml
name: Heavy

on:
  schedule:
    - cron: "17 18 * * 1"    # UTC，周一 18:17 = 北京时间周二 02:17；避开整点高峰
  workflow_dispatch:         # P-129：手动补跑与排障入口

permissions:
  contents: read

concurrency:
  group: heavy-${{ github.workflow }}-${{ github.event_name }}-${{ github.ref }}
  cancel-in-progress: false  # P-129：定时任务不应被新 run 取消

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

## 3. 机械校验（本机）

校验脚本（临时，不入库）读取 YAML 并断言：

| 断言 | 结果 |
|---|---|
| `heavy.yml` 可被 `yaml.safe_load` 解析 | ✅ |
| `on` 键集合 = `{schedule, workflow_dispatch}` | ✅ |
| `schedule[0].cron == "17 18 * * 1"` | ✅ |
| `concurrency.group` 含 `heavy-` / `github.workflow` / `github.event_name` / `github.ref` 四段 | ✅ |
| `concurrency.cancel-in-progress is False` | ✅ |
| `concurrency` 无 `queue` 键 | ✅ |
| `jobs.heavy.timeout-minutes == 60` | ✅ |
| 步骤含 `pytest tests -m heavy -q` 与组键回显 | ✅ |
| `ci.yml` 语义未变（触发器集合 / `push.branches=[main]` / 组键 / `cancel-in-progress: true`） | ✅ |
| `git diff --exit-code -- .github/workflows/ci.yml` | exit 0 |

输出摘要：`yaml parse: OK` / `heavy triggers: ['schedule', 'workflow_dispatch']` / `ci.yml unchanged semantics: OK` / `ci_diff_exit=0`。

## 4. 行为读数

| 编号 | 观测 | 读数 |
|---|---|---|
| E1-1 | heavy 收集数 | `2/3780 tests collected (3778 deselected)` |
| E1-2 | heavy 本机运行 | `2 passed, 3778 deselected`，pytest 4.28 s，墙钟 5.4 s |
| E1-3 | 组名 API 可得性 | run `43773285738` 的 `concurrency = null` ⇒ 无直读面 |
| E1-4 | 分支保护必需检查 | 7 名，均不含 heavy（见 RESEARCH §4 E1-5） |
| E1-5 | 首次 schedule run | 未发生（合并后按 cron 观察，登记 §11 / U-2） |

## 5. 不变式落点

| 不变式 | 落点 |
|---|---|
| J-1 不同组 | §3 静态断言 + 工作流内回显步骤 + 合并后并发行为读数 |
| J-2 main push 不被误杀 | `ci.yml` 零改动；合并后 push run 读数 |
| J-3 同事件取消不变 | `ci.yml` 的 `cancel-in-progress: true` 逐字未动 |
| J-4 7 检查名不变 | E1-4 只读比对 |
| J-5 `ci.yml` 零变更 | §3 `git diff --exit-code` |
| J-6 只跑 heavy | E1-2 `-m heavy`，3778 deselected |
| J-7 停摆可观测 | `workflow_dispatch` 入口 + U-4 观察项 |

## 6. 偏差

| 编号 | 偏差 | 处置 |
|---|---|---|
| D-1 | cron 由 P-128 示意的 `0 18 * * *` 改为 `17 18 * * 1` | P-128 DESIGN §4 明写 cron 由实施批实测决定；依据 RESEARCH §3.1 整点告警与 §5.1 频率论证 |
| D-2 | 未写 `queue: single`（P-128 D-3 提及） | canonical reusable 未记载该键（RESEARCH §3.2）；默认单 pending 位等价，未验证语法不采用 |
| D-3 | 增加一步「Concurrency key evidence (J-1)」 | J-1 无 API 直读面（E1-3），需运行期回显作为替代证据；不计入行为变更 |
| D-4 | job 名保持默认 `heavy`（未加 `name:`） | 与 P-128 DESIGN §4 形态一致，减少与 J-4 的检查名面接触 |

## 7. 门禁读数

| 门禁 | 命令 | 读数 |
|---|---|---|
| dc_validator | `python scripts/spec/dc_validator.py --check-all` | 见 session 第 4 步 |
| grandfather_gate | `python scripts/spec/grandfather_gate.py` | 见 session 第 4 步 |
| step-gate | `python tools/spec_runner/spec_runner.py step-gate --session specwf-p129-ci-heavy-schedule --expect research design implement verify finalize` | 见 session 第 4 步 |
| verify-anchor | `python tools/spec_runner/spec_runner.py verify-anchor --session specwf-p129-ci-heavy-schedule` | 见 session 第 4 步 |
| step_enforce | `python scripts/spec/step_enforce.py <staged files>` | 见 session 第 4 步 |
| pre-commit | `pre-commit run --all-files` | 见 session 第 5 步 |

> 说明：门禁自身的结构化读数记录在决策流第 4/5 步；本文档只保留可复现命令与稳定的行为读数，避免「验后改文档」造成 digest 失配。

## 8. 未改动证明

- `ci.yml`：`git diff --exit-code` 为 0；语义断言逐项通过（§3）。
- `tests/`、`tests/ci_exclusions.yaml`、`pyproject.toml`、`researchclaw/`：零改动。
- 分支保护：只读，未发 PUT；`contexts` 仍为 7 名。
- 批外工作树保留：`researchclaw/vendor/auto_prover/datatypes/__init__.py`（CRLF 漂移）与 `docs/arc-g4-midpoint-20261113.md`（未跟踪）不纳入本批。
