---
id: arc-ci-heavy-exit-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-ci-window2-backfill-RESEARCH, arc-ci-heavy-fixes-CHECKLIST, arc-ci-flaky-heavy-CHECKLIST]
upstream: null
---

# 调研：把两条 heavy 用例移回默认 CI（P-141）

> **Feature**：P-141。兑现 P-137 §2.4 / P-142 §4 的后续动作：U-1 满足后移出 heavy。
> **性质**：T1 实施批；改 2 个测试文件、1 个登记表、1 个 workflow、1 个项目配置。
> **结论先行**：① U-1 三条件已全部满足，隔离的原始理由消失；② 移出的最小完整集合是 5 处接缝，缺一处会留下死引用或假闭合；③ 采用「删除独立 workflow + 清空登记表 + 去标记」方案，接受回归风险并约定 30 天回退规则。

## 1. 触发条件与证据

| U-1 条件 | 读数 | 来源 |
|---|---|---|
| 两个窗口无原始失败签名 | 窗口 1 `43998910996`（延迟 7h36m，success）；窗口 2 `45323125502`（延迟 9h41m26s，attempt=1，success） | P-138 §1、P-142 §1 |
| 1000 次压测零失败 | F-1 1000/1000（408.9s）、F-2 1000/1000（163.8s） | 本机合并预演态 `2b65304` |
| 连续 CI 全绿 | P-134 后 PR run 与 main push 均 success；末次 main push 晚于所有计入的 PR run | `18f3ed4` 的 push run |

补充证据：

- 两个窗口的日志均逐字含 `concurrency_key=heavy-Heavy-schedule-refs/heads/main` 与 `2 passed`，三个失败签名均不存在。
- 窗口 2 的 `headSha=7362330`，与基线 `6dfd47e` 的运行时目录 diff 为空，归因未被文档合并污染。
- 分支保护的 7 个必需检查全部来自 `ci.yml`，没有任何 `Heavy` 上下文（`gh api .../protection` 实读）。

## 2. 变更面盘点

| # | 接缝 | 现状 | 移出后 |
|---|---|---|---|
| 1 | `tests/test_hitl_advanced.py` | `@pytest.mark.heavy` | 去掉标记，随默认 CI 收集 |
| 2 | `tests/test_supervisor.py` | `@pytest.mark.heavy` | 同上 |
| 3 | `tests/ci_exclusions.yaml` | 2 条登记 | `exclusions: []`，保留契约注释 |
| 4 | `.github/workflows/heavy.yml` | 周级 `pytest -m heavy` | 删除；否则每周空跑 0 条 |
| 5 | `pyproject.toml` | 注册 `heavy` marker | 删除定义；无标记后无引用 |
| 6 | `spec/arc-ci-heavy-schedule/IMPLEMENTATION.md` | 两条指向 `heavy.yml` 的相对链接 | 改为行内代码；该批 session digest 重绑 |

保留不变的两处：

- `ci.yml` 的 `pytest tests -m "not heavy"`：无标记时等价于全量收集，保留可让 `ci_coverage_check.py` 的「未登记必须被收集」契约继续成立。
- `ci_coverage_check.py`：仍是排除表的双向闭包守卫；表空时读数为 `L=149，R=0，C=149`。

## 3. 风险分析

| 风险 | 量化 | 缓解 |
|---|---|---|
| 回归到四矩阵后误红 | 暴露频率从每周 1 次变为每次 PR × 4 个 Python 版本 | 已有两窗口 + 各 1000 次零失败；误红时按 DESIGN §5 单提交回退 |
| 删除 workflow 破坏必需检查 | 无：7 个必需检查不含 Heavy | 已用 API 实读确认 |
| 登记表清空导致守卫假闭合 | 无：`--check` 输出 `R=0` 且 `C=149`，`--selftest` 4/4 | IMPLEMENTATION §3 留读数 |
| 删除 workflow 导致跨批悬空链接 | 2 条，均在 `arc-ci-heavy-schedule/IMPLEMENTATION.md` | 由 dc/grandfather 实测暴露后改为行内代码，并重绑 P-129 digest |
| 未来重新隔离时缺声明源 | 契约注释保留，恢复路径写入 DESIGN §5 | 三处同时恢复：marker / 登记 / workflow |

## 4. 备选方案

| 方案 | 内容 | 否决理由 |
|---|---|---|
| A（采用） | 删 workflow、清登记表、去标记 | — |
| B | 保留 `heavy.yml`，改成「必须存在 heavy 用例」的守护 | 永久空跑，只增维护面 |
| C | 保留现状，继续周级观察 | U-1 已满足；继续隔离会让两条用例长期脱离主回归面 |
| D | 只去标记，不删 workflow | `pytest -m heavy` 收集 0 条，每周仍触发一次无意义 run |

## 5. 结论

- 采用方案 A。
- 变更面共 7 个文件：5 处移出接缝 + 2 处入链修复（文档与 session 各一）。
- 回归风险已量化并由用户裁决接受；约定 30 天内出现原始签名即回退。
- 本批不修改 `ci.yml` 的测试命令，也不修改 `ci_coverage_check.py` 的判定逻辑。
