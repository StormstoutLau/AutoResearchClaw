---
id: arc-g0b-implementation-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-master-roadmap, arc-g0b-governance-base-RESEARCH, arc-q3-grandfather-policy-RESEARCH]
upstream: arc-g0b-governance-base-RESEARCH
---

# 调研：G0b 实施前的现状复核与设计前提

> **Feature**：G0b 完整治理基座 **实施批**（P-021）。本文件不重复 P-017 的调研，只做「实施前现状复核 + 未决设计题裁决」，为 DESIGN 提供可直接落地的输入。
> **Spec 步骤**：Step 1-2（T1 完整管线）

## 1. 本批要解决的问题

P-017 已给出路径结论（S-1 + T-1 + H-1），P-019/P-020 已裁决 Q3。剩余的是**实施前必须钉死的三类问题**：

1. P-020 复核提出的 4 项实施前提（F-1/F-2/F-3/F-5）如何落到代码与文档；
2. 迁移的**精确影响面**（链接数、ROOT、同目录 import）是否与 P-017 记录一致；
3. `m7_stats` / `repo_stats` / `blackbox` 三个新门禁的**可执行最小语义**在当前仓库是否可满足（尤其 blackbox 依赖的 CLI 入口）。

## 2. 现状复测（2026-11-10，本批独立重跑）

| # | 事实 | 证据 |
|---|---|---|
| G-1 | `pre-commit run --all-files` exit 0；六钩子组成 = private/dc/step/console/code-agent/rework，**缺 m7/repo/blackbox** | 实际运行 + `.pre-commit-config.yaml` |
| G-2 | `spec/SPEC_PROCESS.md` 不存在；根 `SPEC_PROCESS.md` v1.7.1 | `Test-Path` + 文件头 |
| G-3 | 根 `SPEC_PROCESS.md` 被 17 行含相对链接；其中 **`adr/` 目录在 ARC 不存在**、`spec/academic-writing-workflow`、`spec/stage-tooling-contract`、`spec/project-console`、`docs/discoveries/` 均不存在 | `Test-Path` 逐项 |
| G-4 | 治理脚本引用 113 处 / 35 文件 | Grep |
| G-5 | 五个脚本 ROOT = `parents[1]`/`dirname(dirname(...))`；`console_gen`/`step_enforce` 依赖同目录 `spec_map` | Grep |
| G-6 | `docs/M7_EVIDENCE_LOG.md` 存在，§1/§2 均为「（暂无）」 | 文件内容 |
| G-7 | 根 `CODE_WIKI.md` 不存在；`code_wiki/` 15 个 md | `Test-Path` |
| G-8 | `python -m researchclaw --help` **exit 0**；`researchclaw` 控制台脚本**未安装**（`shutil.which` = None） | 实际运行 |
| G-9 | `dc_validator.run_checks(files, checks)` 可编程调用，返回 `list[CheckResult]`；`CheckResult.check_id ∈ {dc1,dc2,dc3,dc4,dc5,r7}` | `dc_validator.py:481-501`、`:52-58` |
| G-10 | CI 无 `spec-gates` job | `.github/workflows/ci.yml` |

**与 P-017 的差异**：P-017 F-4 记「23 处引用 / 28 个相对链接」，本批复测为 17 行含链接、且 **`adr/` 链接在 ARC 本就断裂**。P-017 §4.1 的「`adr/→../adr/`」重写规则不成立——该目录不存在，重写后仍断链。这是本批必须修正的方案偏差。

## 3. 关键裁决：F-1（不变式冲突）

P-020 复核 F-1：让 `dc_validator` 直接读 `spec/grandfather.yaml` 会同时引入第二真值源与行为变更，破坏其 I-3（零新规则）/ I-4（单一真值源）。

| 方案 | 做法 | 评价 |
|---|---|---|
| (a) 修订权威源 | 新增 ADR 或扩 `spec/doc-contract/PLAN.md §1`，把豁免语义纳入 DC 契约，再改 `dc_validator` | 改动契约本体；`dc_validator` 从「契约的机器可读定义」变成「契约 + 策略」，职责混合；且本仓无 `adr/` 目录，需先建体系 |
| **(b) 独立策略层** | 新增 `grandfather_gate.py`，**复用** `dc_validator.run_checks()` 的结果，按 `(file, check_id)` 过滤后再判红绿；`dc_validator` 本体零改动 | **推荐**：I-1..I-6 全部保持；豁免逻辑可单测；回滚 = 换回 hook entry |

**裁决 = (b)**。理由：`dc_validator` 的权威源是 `spec/doc-contract/PLAN.md §1` + ADR-0007 + R7；豁免是**门禁策略**而非契约规则，放在契约校验器里会重犯「为判断造门禁」之病。策略层由 hook entry 承载，语义边界清晰。

## 4. F-2：豁免机制的可行性验证

`CheckResult.check_id` 按 DC 打标（G-9 已证）。因此：

- 可豁免集合 = `{dc1, dc2, dc3}`（front-matter 七字段/词表、相对链接）；
- **不可豁免**：`dc4`（id 全仓唯一）、`dc5`（版本引用）、`r7`（计数自洽）——按 P-020 F-2，这三者是**全仓扫描**语义（I-6），豁免单个文件并不能让全仓命题成立，故按文件豁免本身不适用；策略层对它们只做透传且显式拒绝登记。
- 实现 = 过滤器，不是开关：先跑全部检查，再丢弃命中 `(path, check_id)` 且未过期的结果。

## 5. F-3 / F-4 / F-5

| 项 | 处理 |
|---|---|
| F-3 | 「90 天」标为**内部政策参数（E3，可调）**，与 U-1（豁免数量趋势复审）绑定；不作为外部推导结论 |
| F-4 | 负向用例固化：作用域外文件（`docs/*.md` 等）**不消耗**豁免条目，也不产生 `grandfathered` 计数 |
| F-5 | 续期基准 = 原 `expires` + `expires_days`；总寿命 ≤ `cutoff + 2*expires_days`；续期须在 `renewals` 数组**追加**记录，禁止就地改日期 |

## 6. 三个新门禁的最小语义（含环境约束）

### 6.1 m7_stats

- 输入：`docs/M7_EVIDENCE_LOG.md` §1 样本表 / §2 统计表。
- 语义：无样本 → `samples=0` 且 exit 0；有样本 → 声明计数必须等于行数；结构损坏（表头缺失/列数不符）→ exit 1。
- 当前账本为空（G-6），门禁为「结构有效 + 零样本可见」，不是永久 no-op。

### 6.2 repo_stats

- 输入：`researchclaw/**/*.py`、`tests/**/*.py`、`docs/PROGRESS.md`（P 行）。
- 语义：机械统计文件数与行数、P 批次数；`--check` 模式与 `docs/REPO_STATS.md` 声明比对，漂移即 exit 1；源缺失/解析失败 exit 2（fail-closed，独立复核 N-1 订正：原稿误写 exit 1，以 DESIGN §5.2 与实现为准）。
- 不用根 `CODE_WIKI.md`（G-7 不存在）。

### 6.3 blackbox_check

- **环境约束（G-8）**：`researchclaw` 控制台脚本未安装，若强制两次都跑会永久红。
- 语义：`python -m researchclaw --help` **强制**（超时 30s，非 0 即红）；`researchclaw --help` 仅在 `shutil.which("researchclaw")` 命中时执行，未安装则打印 `[skip] console script not installed` 并计入跳过数。
- 理由：CLI 入口在打包层已由 CI `packaging` job 用 wheel 验证（`researchclaw --help`），本地门禁重复该断言只会引入环境依赖。

## 7. 外部锚点（本批新增/复用的判定依据）

| # | 锚点 | 结论 | 等级 |
|---|---|---|---|
| X-1 | pre-commit 官方文档 | 钩子按 `files` 正则过滤，`entry` 可替换为任意可执行 | T1（官方） |
| X-2 | pre-commit `lang: system` | 本仓六钩子均用 system，新增钩子沿用 | T1（官方） |
| X-3 | GitHub Actions `jobs.<id>` 并行 | 新 job 默认与既有 job 并行，无需 `needs` | T1（官方） |
| X-4 | Python `runpy.run_path` | 可在保持 `sys.path` 的前提下以 `__main__` 语义执行目标脚本 | T1（官方） |
| X-5 | SonarQube Clean as You Code | 新代码立即干净、存量按基线 | T1（官方） |
| X-6 | Android Lint baseline / PHPStan baseline / ESLint bulk suppressions | 基线文件的通行形态 = 清单 + 过期/重报策略 | T1（官方） |
| X-7 | ISO/IEC/IEEE 29148 双向追溯 | 验收项 ↔ 测试用例需可追踪 | T2（标准页） |
| X-8 | P-020 复核报告 | F-1..F-5 的原始出处 | T1（仓内） |

## 8. 未决项

- **U-1 豁免数量趋势复审**：判据 = `entries` 非空且连续 2 个批次未减少；触发 = 首个 entry 落档；倾向 = 复审并收紧 `expires_days`；E3。
- **U-2 根兼容壳保留期**：判据 = 新文档不再引用根路径；触发 = 下个大版本；倾向 = 保留 2 个批次；E1。
- **U-3 blackbox 控制台脚本断言的恢复**：判据 = CI 已覆盖 wheel 安装后 `--help`；触发 = 本地安装 `researchclaw` 后；倾向 = 保持跳过；E2。
- **U-4 repo_stats 是否纳入 CI**：判据 = 统计漂移是否真实发生；触发 = 首次漂移；倾向 = 先只在 pre-commit 跑 `--check`；E2。

## 9. 引用

1. pre-commit. https://pre-commit.com/
2. GitHub Actions — Workflow syntax. https://docs.github.com/en/actions/reference/workflow-syntax-for-github-actions
3. Python `runpy`. https://docs.python.org/3/library/runpy.html
4. [P-017 调研](../arc-g0b-governance-base/RESEARCH.md)
5. [P-019 调研](../arc-q3-grandfather-policy/RESEARCH.md)
6. [P-020 复核](../../docs/arc-q3-grandfather-review-20261110.md)
