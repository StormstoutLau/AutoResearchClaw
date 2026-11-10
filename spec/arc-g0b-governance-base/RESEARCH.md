---
id: arc-g0b-governance-base-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-master-roadmap, arc-spec-workflow-install-RESEARCH]
upstream: arc-master-roadmap
---

# 调研：G0b 完整治理基座的可落地路径

> **Feature**：把 G0b 从“未就绪”推进到可验收，先回答路径、钩子组成、存量豁免、统计门禁与 CI 五个问题。
> **状态**：verified（实测 + 外部锚点 + 方案对比；未改代码）
> **Spec 步骤**：Step 1-2

## 1. 调研目标

1. G0b 的 A0-1..A0-6 当前分别卡在哪里？
2. `spec/SPEC_PROCESS.md` 与 `scripts/spec/*` 应迁移、做门面，还是重写全部引用？
3. 六钩子应为哪六道？现有 `private-config` / `code-agent-wiring` 如何处置？
4. Q3「新文档立即、存量入 grandfather」在當前仓库是否还有存量需要豁免？
5. `m7_stats` / `repo_stats` / `blackbox` / `spec-gates` 的最小可执行语义是什么？

## 2. 现状实测（2026-11-10）

| # | 事实 | 证据 |
|---|---|---|
| F-1 | `pre-commit run --all-files` 当前 **exit 0**，六钩子全绿 | 实际运行：private-config / dc-validator / step-enforce / console-gen / code-agent-wiring / rework-graph 全 Passed |
| F-2 | 但六钩子组成是 `private/dc/step/console/code-agent/rework`，**缺 m7/repo/blackbox** | `.pre-commit-config.yaml` |
| F-3 | `spec/SPEC_PROCESS.md` **不存在**；根目录 `SPEC_PROCESS.md` 存在 | `Test-Path` |
| F-4 | `SPEC_PROCESS.md` 被 **23 处**引用；文内相对链接 `adr/` 9、`docs/` 6、`spec/` 13 | Grep + regex |
| F-5 | `scripts/spec/` **不存在**；治理脚本在 `scripts/` 根 | Glob |
| F-6 | 治理脚本路径被 **88 处 / 27 文件**引用 | Grep |
| F-7 | 五个脚本用 `ROOT = parents[1]` / `dirname(dirname(...))`；迁到 `scripts/spec/` 后会指向 `scripts/` | `dc_validator.py:28`、`console_gen.py:49`、`step_enforce.py:38`、`rework_graph_check.py:44`、`roadmap_coverage_check.py:24` |
| F-8 | `console_gen` 与 `step_enforce` 依赖同目录 `spec_map` | `console_gen.py:47`、`step_enforce.py:36` |
| F-9 | `spec/grandfather.yaml` **不存在** | `Test-Path` |
| F-10 | `docs/M7_EVIDENCE_LOG.md` 存在但**无样本**（286 B，`（暂无）`） | 文件内容 |
| F-11 | 根 `CODE_WIKI.md` **不存在**；`code_wiki/` 有 15 个 md | `Test-Path` + `Get-ChildItem` |
| F-12 | CI 只有 `packaging` / `extras` / `tests` / `roadmap-coverage`，**无 `spec-gates`** | `.github/workflows/ci.yml` |
| F-13 | `dc_validator` 在 pre-commit 下通过全部 spec 文档；用**绝对路径**扫全部 spec 时模板报 6 条 P2（路径解析伪差，非仓库缺陷） | 实际运行对比 |
| F-14 | `step_enforce` 已实现 finalize digest 绑定（`EVIDENCE_MIN_P=137`） | `step_enforce.py:52-59`、`:204-253` |

## 3. A0-1..A0-6 缺口

| ID | 断言 | 现状 | 缺口 |
|---|---|---|---|
| A0-1 | 六钩子全绿（dc/m7/repo/step/console/blackbox） | 当前六钩子全绿但组成不符 | 新增 m7/repo/blackbox；决定 extras 去留 |
| A0-2 | 新 `.md` 缺 DC1 七字段 → 拒绝 | `dc_validator` 有 `SEVEN_FIELDS` 校验 | 负向用例未固化 |
| A0-3 | 缺 `verify` 的 finalize → 拒绝 | `step_enforce` 有五步链校验 | 负向用例未固化 |
| A0-4 | verify 后改正文 → digest 不匹配 → 拒绝 | `step_enforce` 已实现 per-file sha256 | 负向用例未固化 |
| A0-5 | 手改 `CONSOLE.md` → `--check` 非 0 | `console_gen --check` 已实现 | 已有机制，无需新增 |
| A0-6 | `spec-gates` job 与 3.11–3.13 矩阵并行且全绿 | 无该 job | 新增 CI job |

**结论**：A0-2..A0-5 的机制已存在，主要缺“负向用例固化”；真正缺的是 A0-1 的组成与 A0-6 的 job。

## 4. 路径方案对比

### 4.1 `SPEC_PROCESS.md`

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| S-1 迁移 + 根指针 | 正文迁到 `spec/SPEC_PROCESS.md`；根文件改为一行指针 | 满足交付物；历史 23 处引用仍可解析 | 需重写 28 个相对链接 |
| S-2 双份 | 根保留，`spec/` 放副本 | 改动小 | 双真值源，必然漂移 |
| S-3 迁移 + 全量改引用 | 迁正文并改所有 23 处引用 | 路径最干净 | 改动历史文档，违反追加式证据 |

**建议 S-1**：正文迁 `spec/`，根文件留一行 `Moved to spec/SPEC_PROCESS.md`；历史文档不改。迁移时按 `adr/→../adr/`、`docs/→../docs/`、`spec/→./` 重写 28 个链接，并跑 `dc_validator` 验证。

### 4.2 `scripts/spec/*`

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| T-1 迁移 + 根兼容壳 | 六个治理脚本迁 `scripts/spec/`；根路径留薄壳 `runpy` 转发 | 满足交付物；88 处历史引用仍可用 | 多 6 个壳文件；需防壳与实现漂移 |
| T-2 仅门面 | 根保持真身，`scripts/spec/` 放转发壳 | 改动最小 | 交付物是空壳；单一真值源被破坏 |
| T-3 迁移 + 全量改引用 | 迁脚本并改 88 处引用 | 无壳 | 需改历史 IMPLEMENTATION/会话，破坏证据 |

**建议 T-1**：迁移 `dc_validator`、`step_enforce`、`console_gen`、`rework_graph_check`、`spec_map`、`roadmap_coverage_check` 到 `scripts/spec/`；根路径保留 6 个薄壳，打印弃用提示后 `runpy.run_path` 转发。壳只做转发，不含逻辑。
**必改**：五个脚本 `ROOT` 上移一级；`spec_map` 随同迁移，`console_gen`/`step_enforce` 的同目录 import 保持不变；pre-commit entry 与 CI 改新路径。

## 5. 钩子组成方案

| 方案 | 组成 | 评价 |
|---|---|---|
| H-1 必需六 + 两个额外 | dc/m7/repo/step/console/blackbox + private-config/code-agent-wiring | **推荐**：满足 A0-1，又不丢安全/接线守卫 |
| H-2 替换 | 去掉 private/code-agent，仅六道 | 丢安全守卫，不建议 |
| H-3 合并 | 把 private 并入 repo-stats、code-agent 并入 blackbox | 语义混杂，难定位失败 |

**建议 H-1**：A0-1 的“六钩子”解释为**必需集**；总数 8 道，README/roadmap 注明“6 必需 + 2 额外”。

## 6. 存量豁免（Q3）

当前 `pre-commit run --all-files` 与 `dc_validator` 在 pre-commit 语义下全绿，**没有需要 grandfather 的存量违规**。因此 Q3 可采用：

- 新文档：**立即**执行 DC1/DC2/Step 链；
- 存量文档：`spec/grandfather.yaml` **空清单** + `cutoff: 2026-11-10` + 过期策略；
- 未来若出现存量违规，按 `path/reason/owner/expires` 登记，`dc_validator` 读取并跳过，过期即红。

这比“先造一批豁免”更符合最小治理，也避免把模板/历史文档误列入。

## 7. 统计与黑盒门禁

### 7.1 `m7_stats`

- 输入：`docs/M7_EVIDENCE_LOG.md`。
- 最小语义：解析“样本/统计”表；无样本时输出 `samples=0` 并 exit 0；表结构损坏或声明计数与行数不一致时 exit 1。
- 当前账本为空，门禁为“结构有效 + 零样本可见”，不是永久 no-op。

### 7.2 `repo_stats`

- 输入：`code_wiki/`（15 个 md）+ `docs/PROGRESS.md`。
- 最小语义：统计代码文件/行、测试文件/行、P 批次数；输出 `docs/REPO_STATS.md` 或 stdout；源缺失/解析失败 exit 1。
- 不用根 `CODE_WIKI.md`（不存在）；以 `code_wiki/README.md` §1 的“代码规模”行为声明基准。

### 7.3 `blackbox`

- 最小语义：`python -m researchclaw --help` 与 `researchclaw --help` 各跑一次，超时 30s；非 0/超时/缺命令 → exit 1。
- 这是 CLI 级烟雾测试，不替代 pytest；pre-commit 全量运行时必须保持 <10s（实测 `--help` <1s）。

### 7.4 `spec-gates` CI

- 新 job：Python 3.11，`pip install pre-commit`，`pre-commit run --all-files`。
- 与 `tests` 3.11–3.13 矩阵并行；不依赖 `tests` 产物。
- 风险：pre-commit 全量运行含 blackbox/private 扫描，预计 <2 min；若超时，改为分步执行并缓存。

## 8. 外部锚点

| # | 锚点 | 可复用结论 | 验证 |
|---|---|---|---|
| X-1 | GitHub Spec Kit | 规范→计划→任务→实现→收敛，Markdown 工件逐阶段传递 | ✅ 官网/文档 |
| X-2 | OpenSpec | 轻量 spec 框架；规范需可验证、与实现对齐 | ✅ 官网 |
| X-3 | ISO/IEC/IEEE 29148:2018 | 双向追溯支持影响分析；需求/设计/测试应可追踪 | ✅ 标准页 |
| X-4 | SonarQube Clean as You Code | “新代码”基线：新变更立即干净，存量按基线管理 | ✅ 官方文档 |
| X-5 | pre-commit | 钩子只对 staged 内容运行；`--all-files` 用于全量门禁 | ✅ 官网 |
| X-6 | ADR / Nygard | 一决策一记录，状态可 superseded；模板与决策流同构 | ⚠️ 二手 |
| X-7 | GitHub Actions 必需检查 | 分支保护可要求 job 通过；spec-gates 应作为 required check | ⚠️ 官方文档，未抓正文 |
| X-8 | pytest | 黑盒 CLI 烟雾测试与单元测试分层 | ⚠️ 官方文档 |
| X-9 | Open Policy Agent | 策略即代码：门禁可执行、可测试、可审计 | ⚠️ 官方文档 |
| X-10 | Spec_Workflow v1.7.1 | 十步流程、DC1-DC5、四元未决项、T1/T3 批次档位 | ✅ 仓内权威源 |

## 9. 影响面与风险

| 维度 | 风险 | 缓解 |
|---|---|---|
| 路径迁移 | 88 处引用、5 个 ROOT、2 个同目录 import | 根壳兼容 + 迁移后全量 pre-commit |
| SPEC_PROCESS 迁移 | 28 个相对链接 | 机械重写 + dc_validator |
| 钩子新增 | pre-commit 全量变慢 | blackbox <10s；m7/repo 纯本地解析 |
| CI | spec-gates 与矩阵并发，重复安装 | 独立 job，仅装 pre-commit；不跑 pytest |
| 统计门禁 | m7 无样本、repo 无根 wiki | 明确输入与零样本语义；以 `code_wiki/` 为源 |
| 历史证据 | 改历史文档会破坏 E1 | 只加根壳/指针，不改历史正文 |

## 10. 建议

按 **S-1 + T-1 + H-1 + 空 grandfather + 最小统计/黑盒 + spec-gates** 实施。预计改动集中在：
`SPEC_PROCESS.md`、`spec/SPEC_PROCESS.md`、`scripts/spec/*`、6 个根壳、`.pre-commit-config.yaml`、`.github/workflows/ci.yml`、`spec/grandfather.yaml`、`docs/M7_EVIDENCE_LOG.md`（如需）、`docs/REPO_STATS.md`（如需）。

## 11. 未决项

- **U-1 路径迁移的壳保留期**：判据=历史引用不再被新文档使用；触发=下一个大版本；倾向=保留 2 个批次；E1。
- **U-2 钩子运行时长**：判据=全量 pre-commit <2 min；触发=CI 超时；倾向=blackbox 限 10s；E1。
- **U-3 m7_stats 零样本语义**：判据=空账本 exit 0 但输出可见；触发=首批 M7 样本；倾向=结构校验 + 零样本；E1。
- **U-4 repo_stats 输入**：判据=`code_wiki/README.md` 可解析；触发=统计漂移；倾向=以 `code_wiki/` 为源；E1。
- **U-5 grandfather 过期策略**：判据=过期条目自动红；触发=首个豁免条目；倾向=90 天；E1。
- **U-6 spec-gates 是否 required**：判据=GitHub 分支保护配置；触发=CI 稳定 2 周；倾向=required；E2。

## 12. 参考文献

1. GitHub Spec Kit. https://github.github.io/spec-kit/
2. OpenSpec. https://openspec.dev/
3. ISO/IEC/IEEE 29148:2018. https://www.iso.org/obp/ui/fr/#!iso:std:72089
4. SonarQube. *Clean as You Code*. https://docs.sonarsource.com/sonarqube/latest/user-guide/clean-as-you-code/
5. pre-commit. https://pre-commit.com/
6. ADR. https://adr.github.io/
7. GitHub Actions. https://docs.github.com/en/actions
8. pytest. https://docs.pytest.org/
9. Open Policy Agent. https://www.openpolicyagent.org/docs/latest/
10. 仓内：`SPEC_PROCESS.md` v1.7.1、`arc-master-roadmap.md` §4 G0b。
