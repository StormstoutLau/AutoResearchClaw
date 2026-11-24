---
id: arc-ci-heavy-exit-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-ci-heavy-exit-DESIGN]
upstream: null
---

# 实施：heavy 用例回归默认 CI（P-141）

> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **变更面**：7 个文件（5 处移出 + 2 处入链修复）；零新增依赖、零运行时产品代码改动。

---

## 1. 变更清单

| 文件 | 动作 | 内容 |
|---|---|---|
| `tests/test_hitl_advanced.py` | 修改 | 删除 `@pytest.mark.heavy` 装饰器行（用例体不变） |
| `tests/test_supervisor.py` | 修改 | 删除 `@pytest.mark.heavy` 装饰器行（用例体不变） |
| `tests/ci_exclusions.yaml` | 修改 | `exclusions: []`；保留五字段契约注释并补恢复说明 |
| `.github/workflows/heavy.yml` | 删除 | 周级 `pytest -m heavy` 容器 |
| `pyproject.toml` | 修改 | 删除 `[tool.pytest.ini_options]`（唯一内容为 heavy marker） |
| `spec/arc-ci-heavy-schedule/IMPLEMENTATION.md` | 修改 | 两条指向 `heavy.yml` 的相对链接改为行内代码 |
| `tools/spec_runner/sessions/specwf-p129-ci-heavy-schedule.jsonl` | 修改 | 按 canonical 值重绑该批 `IMPLEMENTATION.md` 的 sha256 |

`ci.yml`、`scripts/spec/ci_coverage_check.py` 零改动（DESIGN D-5）。

## 2. 收集与执行读数

```text
$ python -m pytest tests --collect-only -q -m "not heavy"
tests/test_hitl_advanced.py::TestFileWait::test_poll_with_delayed_response
tests/test_supervisor.py::test_lease_keeper_reports_loss
3790 tests collected in 4.58s

$ python -m pytest tests/test_hitl_advanced.py::TestFileWait::test_poll_with_delayed_response \
                   tests/test_supervisor.py::test_lease_keeper_reports_loss -q
2 passed in 0.68s
```

说明：`3790` 是移出后的默认收集总数；移出前为 `3784 collected`（`-m "not heavy"`）+ 2 条 heavy = `3786`，差值来自 P-139 新增用例与合并后的计数变化，不是本批引入。

## 3. 覆盖守卫读数

```text
$ python scripts/spec/ci_coverage_check.py --check
覆盖闭合：L=149，R=0，C=149

$ python scripts/spec/ci_coverage_check.py --selftest
selftest: 4/4 PASS
```

- `R=0`：登记表已清空。
- `C=149`：149 个测试文件全部被默认 CI 收集。
- 自测 4/4 证明守卫的闭合逻辑未被本批破坏。

## 4. 残留引用检查

```text
$ Select-String -Path tests\*.py -Pattern "pytest\.mark\.heavy"
marker_hits=0

$ Get-ChildItem .github\workflows
ci.yml

$ Select-String -Path .github\workflows\*.yml -Pattern "-m heavy"
（无命中；`ci.yml` 仅含 `-m "not heavy"`）
```

入链检查：删除 `heavy.yml` 后，`spec/arc-ci-heavy-schedule/IMPLEMENTATION.md` 的两条相对链接立即不可解析，`grandfather_gate` 报 2 条 P2（L14、L23）。已改为行内代码，并把该批 session 的 `IMPLEMENTATION.md` digest 从 `aa8f91db…` 重绑为 `da00ee9e…`；复跑后 `grandfather` 回到 `0/0/0`。

## 5. 门禁读数

| 门禁 | 读数 |
|---|---|
| dc_validator（本批 feature） | 0 违规（全仓 148 条存量） |
| grandfather_gate | 0/0/0 |
| step-gate | 5/5 pass |
| verify-anchor | 10 真实 / 0 硬性 / 0 软性 |
| step_enforce | `mode=batch pid=P-141 digest_bound=1` |
| pre-commit | 适用钩子全绿 |
| PR CI | 8/8 success（合并前） |

## 6. 未做与边界

- 未修改 `ci.yml` 的 `-m "not heavy"`：无标记时等价全量，且覆盖守卫的收集口径与之保持一致。
- 未修改 `ci_coverage_check.py`：它仍是未来排除表的守卫；表空是合法状态。
- 未做故障注入：两条用例的时序性质由既有断言覆盖。
- 未在 Linux 四矩阵本地复现：由 PR CI 的 3.11/3.12/3.13/3.14 承担。
- 跨批编辑了 P-129 的 `IMPLEMENTATION.md` 与其 session：仅修悬空链接与重绑 digest，不改该批结论。
