# 审查验收 Checklist：CI/CD 机制补全（P-110 验收基线）

---
id: arc-ci-cd-research-CHECKLIST
type: design
version: 1.4
status: pending
date: 2026-11-15
depends: [arc-ci-cd-research-IMPLEMENTATION, arc-ci-cd-research-DESIGN]
upstream: null
---

> **Feature**: P-110，CI/CD 补全验收 Checklist（承接 P-107 调研 / P-108 设计 / P-109 实施文档，本批零代码实施）
> **创建日期**: 2026-11-14
> **状态**: 待验收
> **Spec 步骤**: Step 7-8, 10
> **基于实施**: [IMPLEMENTATION.md](./IMPLEMENTATION.md)（v1.2 / verified）
> **基于设计**: [DESIGN.md](./DESIGN.md)（v1.3 / verified）

> **验收边界（诚实声明）**：P-110 只建立验收基线，不实施 B1/B2。凡需运行代码、改 workflow 或改仓库设置的验收项一律标 ☐，**不得预填** ✅；仅「已发生的文档事实」（四文档链对齐、既有配置一手实测）可标 ✅。因此本文件当前为 `pending`，§10.2 三选项均不勾选，代码项等待 B1/B2 实施后回填。2026-11-15 首轮回填（P-114）：B1/B2 已实施（P-112），本机可验项回填 ✅；push 依赖项保持 ☐，§10.2 按三选项口径勾选「有条件通过」，待第二轮回填终裁。2026-11-15 第二轮回填（P-122）：CI 连续两次全绿（run 43711274731 attempt 1/2）达成、分支保护按 runbook 应用并读回，§2.3 行 89、§2.5 行 105 与 §4 I-5 翻 ✅，§10.1 复算 86/50/0/36。2026-11-15 第三轮回填（P-122 续）：故意违规 PR #2 实证阻断（`BLOCKED` + `--admin` 亦被拒 `3 of 7 required status checks are failing`），直推 `main` 被拒；§2.5 行 106 翻 ✅，§10.1 复算 86/51/0/35。

---

## 1. 文档一致性验收（Step 8）

### 1.1 RESEARCH.md ↔ DESIGN.md 对齐

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN.md 的设计决策可追溯到 RESEARCH.md | ✅ | DESIGN §2.1 映射表 R-1/R-2/G-1..G-7 全部落到唯一 D-x；D-8/D-9 为显式「不实施」而非遗漏 |
| RESEARCH.md 的关键发现被 DESIGN.md 使用 | ✅ | R-1→D-1、R-2→D-2、G-1→D-5、G-2→D-4、G-3/G-4→D-6；DESIGN §2.1.1 三项补强均标为一手实测 |
| 无文档间矛盾 | ✅ | R↔D↔I 三层无未决矛盾：DESIGN §5.1 显式登记对 RESEARCH U-1 的改判（有理由）；D↔I 层唯一偏差（DESIGN §4.1 返回注解）已由 P-111 订正（DESIGN v1.3） |

### 1.2 DESIGN.md ↔ IMPLEMENTATION.md 对齐

| 检查项 | 状态 | 说明 |
|--------|------|------|
| DESIGN.md 的模块在 IMPLEMENTATION.md 中有对应实施 | ✅ | DESIGN §3.2 十行 ↔ IMPL §2.3 十一行（多出第 11 行 `.pre-commit-config.yaml` 属 I-6 接线，已注明非新增设计面） |
| IMPLEMENTATION.md 的接口签名与 DESIGN.md 一致 | ✅ | IMPL §4.1/§4.3 与 DESIGN §4.1/§4.2 一致；原残留的 DESIGN §4.1 返回注解 `-> list[CheckResult]` 已由 DESIGN v1.3 删除（真实源码 L352 无返回注解），IMPL §9.5 O-4 关闭 |
| DESIGN.md 的不变式在 IMPLEMENTATION.md 中有实施 | ✅ | I-1..I-6 在 IMPL §7 逐条落到文件与验证方式（F34-F37 / C1-C4 / 27 参数化 / runbook） |
| 无设计未覆盖的实施 | ✅ | derived-requirement 三项 = `vendor_source_sync.py` CLI 签名、`ci_coverage_check --write` 语义、两处 `--selftest`，IMPL §4.2/§4.3/§9.3 已显式登记 |

### 1.3 IMPLEMENTATION.md ↔ CHECKLIST.md 对齐

| 检查项 | 状态 | 说明 |
|--------|------|------|
| IMPLEMENTATION.md 的功能点在本 checklist 有验收项 | ✅ | IMPL §3.1-§3.10 十一个模块 ↔ §2.1-§2.7；IMPL §4 四个接口 ↔ §3.1-§3.4；§7 六不变式 ↔ §4；§6 六错误场景 ↔ §5 |
| 本 checklist 的验收项可追溯到 IMPLEMENTATION.md | ✅ | 每条验收项均标注对应 Step/模块（证据列写 B1/B2 步骤号），无自造验收面 |

### 1.4 术语一致性

| 术语 | RESEARCH.md | DESIGN.md | IMPLEMENTATION.md | 一致 |
|------|------------|-----------|-------------------|------|
| 仓库态真值（blob） | 「仓库态（blob/committed file）为唯一真值源」 | 「git blob」 | 「git blob 字节」 | ✅ |
| tracked 校验 | 未直接使用（同义表述：committed file） | `check_links` 增 tracked 校验 | `check_links(..., tracked=None)` | ✅ |
| 覆盖闭合 | 未直接使用（同义表述：测试清单漂移 G-1） | 覆盖闭合双向守卫 | `closure_violations` 三集合 | ✅ |
| 必需检查 | 「分支保护」缺约束力 | 7 个具体检查名 | 7 个必需检查名（3.14 不入集） | ✅ |
| 单一真值 | 「唯一真值源」 | I-4 单一真值 | README 徽章单一真值 | ✅ |
| heavy / 登记表 | 未使用 | `heavy` marker 仅运行时开关 | `heavy` marker + `ci_exclusions.yaml` 唯一声明源 | ✅ |

## 2. 功能验收

### 2.1 D-1：vendored 元数据锚定 git blob（B1）

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| `--check` 先红 | `python scripts/spec/vendor_source_sync.py --check` | exit 1，12 条差异且与 DESIGN §2.1.1 同名 | ✅ | P-112 TDD 先红读数 12 条差异同名（PROGRESS P-112）；`--write` 后转绿，P-114 复跑 exit 0 |
| `--write` 后元数据自洽 | `--write` 后复跑 `--check` | exit 0；`file_count` = 27 | ✅ | P-114 复跑 exit 0（「SOURCE.json 与 git blob 一致（29 条目）」，27 files + 2 license） |
| 断言改锚 blob | `pytest tests/test_vendor_auto_prover.py -q` | 27 passed；本地 CRLF 工作树与 clean checkout 同判 | ✅ | P-114 复跑 34 passed（27 vendored 条目 + 许可 7，IMPL §8.2 口径）；CI run 43635083591 四矩阵 0 vendored 断言失败（R-1 修复在 CI 生效） |
| `license_files[]` 仅重写 `sha256` | 比对 `--write` 前后 SOURCE.json | 仅 `sha256` 变更，无 `bytes` 键新增 | ✅ | P-112 `--write` diff 24 行 = 12 条 × 2 字段；license 条目无 `bytes` 键的不对称复核（P-114） |
| 未入库 vendored 路径 fail-closed | 临时移出 index 后 `--check` | exit 1 并列明路径，无 `git add -f` 兜底 | ✅ | P-114 实测：`git rm --cached` 后 `--check` exit 1 列明「未入库（git index 无此 blob）」；恢复注意 `git add` 会把工作树 CRLF 版本重新入库（`-text` 无转换），须 `git restore --staged` 自 HEAD 恢复，恢复后 exit 0 |

### 2.2 D-2：链接改写与 tracked 校验（B1）

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| tracked 判定先红 | 在 detached worktree（仅已提交文件）中对 hook 作用域（`spec/**` + `docs/{PROGRESS,CONSOLE}.md`）跑 `python scripts/spec/dc_validator.py --check-links <files>` | 21 条 P2 / 10 文件 / 6 目标（本地工作树与无参全仓扫描不作判据） | ✅ | P-112/P-113 先红读数 21 P2 / 10 文件 / 6 目标（PROGRESS P-112/P-113，detached worktree 判据） |
| 21 处链接改写 | 改写后在同一 detached worktree 的 hook 作用域内复跑 | 0 违规 | ✅ | P-114 复跑：detached worktree（HEAD b135b4f 已提交文件）hook 作用域 252 文件 0 违规 |
| detached worktree 复验 | 仅含已提交文件的工作树内复跑 | 0 违规（排除「磁盘上有文件」假绿） | ✅ | 同上，`git worktree add --detach` + `git ls-files` 取文件清单，exit 0 |
| 自测 F34-F37 | `python scripts/spec/dc_validator.py --selftest` | 未入库判 P2 / 已入库不判 / 无 .git 空集 / 行内代码不判，全 PASS | ✅ | P-114 复跑 selftest 43/43 PASS（含 F34-F37） |

### 2.3 D-4：workflow 硬化（B2）

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| `workflow_dispatch` 可手动触发 | Actions 页面手动 Run workflow | 出现并成功启动 | ☐ | push 依赖项，留待第二轮回填（遗留待办） |
| 同分支连推取消前序 | 连续两次 push 同分支 | 前序 run 状态为 Cancelled | ☐ | push 依赖项（run 43635083591 为单推、无取消事件），留待第二轮回填（遗留待办） |
| 超时与 pip 缓存 | 读 run 日志 | 5 个 job 均有 `timeout-minutes`；`cache: pip` 命中 | ☐ | ci.yml 静态半项已验（5 job `timeout-minutes` 15/15/30/10/20）；缓存命中日志待后续 run 取证（run 43635083591 首轮 miss 属正常，Roadmap job 有「no dependencies to cache」提示） |
| actions 版本与 job name | 读 ci.yml + 分支保护读回 | `checkout@v7` / `setup-python@v7`；5 个 job `name:` 未改 | ✅ | ci.yml 静态半项已验（`checkout@v7` / `setup-python@v7`，P-112 `gh api` 实测 latest v7.0.1 / v7.1.0；5 个 `name:` 未改）；分支保护读回半项已验（P-122：7 个 required contexts 全部由现行 job `name:` 派生——`Packaging / wheel smoke` / `Extras import` / `Tests (3.11..3.13)` / `Roadmap coverage gates` / `Spec gates (pre-commit all-files)`，改名即失效的约束下读回成功） |

### 2.4 D-5：覆盖闭合守卫（B2）

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 守卫先红 | `python scripts/spec/ci_coverage_check.py --check` | exit 1，104 文件未进 C | ✅ | P-112 接表前缺表 fail-closed 红（PROGRESS P-112）；旧 45 枚举反事实缺口 103（P-111 记 104 系含 `__init__.py` 口径） |
| 全量收集后闭合 | tests job 改 `pytest tests -m "not heavy" -q` 后复跑 | exit 0 | ✅ | P-114 复跑 exit 0（L=148 / R=0 / C=148）；CI spec-gates 侧 collect error（缺 `mcp` extra）为 fail-closed 设计语义生效，红面登记为遗留待办 |
| 守卫自测 C1-C4 | `--selftest` | 闭合 / 死项 / 未进 CI / marker 不一致四类全 PASS | ✅ | P-114 复跑 selftest 4/4 PASS |
| 登记表空表契约 | `yaml.safe_load` 解析 `tests/ci_exclusions.yaml` | `version: 1` + `exclusions: []`，五字段契约在注释 | ✅ | P-114 实读 `version: 1` + `exclusions: []`（五字段契约在文件头注释） |
| `heavy` marker 注册 | `pytest tests -m "not heavy" --collect-only -q` | 无 `PytestUnknownMarkWarning` | ✅ | P-114 复跑 3778 collected，`heavy` 无 UnknownMark 警告；存量 `pytest.mark.asyncio` 未注册警告与本项无关（登记观察，遗留待办） |

### 2.5 D-3：分支保护 runbook（B1）

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 7 个必需检查名读回 | `gh api repos/<owner>/<repo>/branches/main/protection` | 7 名逐字符一致；`Tests (3.14)` 不在集 | ✅ | P-122 已应用并读回：7 名逐字符一致（`Packaging / wheel smoke` / `Extras import` / `Tests (3.11)` / `Tests (3.12)` / `Tests (3.13)` / `Roadmap coverage gates` / `Spec gates (pre-commit all-files)`），实测 `Tests (3.14)` 不在集；前置「CI 连续两次全绿」= commit `e34ad40` 的 run 43711274731 **attempt 1 与 attempt 2 均 `success`**（8/8 job 全绿） |
| 无 admin 旁路且红即阻断 | 读回 `enforce_admins` + 一次故意违规 PR | `enforce_admins=true`；违规 PR 被阻断后 revert | ✅ | P-122 取证三连（临时 PR #2 已关闭、分支已删，`main` 未留探针提交）：① 直推 `main` 被服务端拒绝——`- Changes must be made through a pull request.` / `7 of 7 required status checks are expected.`；② 故意违规 PR（`probe/bp-violation` 新增 `tests/test_bp_probe_violation.py` 断言失败）`mergeStateStatus=BLOCKED`、8 项检查 fail，`gh pr merge --squash` 报 `the base branch policy prohibits the merge`；③ 管理员绕过 `gh pr merge --admin` 仍被拒——`GraphQL: 3 of 7 required status checks are failing`（`Tests (3.14)` 的 fail 不计入，恰证必需集为 7 名）。读回侧：`enforce_admins.enabled=true`、approvals=0、force_push/deletions 均 false |

### 2.6 D-6：依赖自动化与徽章（B2）

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| dependabot 配置形态 | 读 `.github/dependabot.yml` | github-actions 与 pip 均 monthly + `groups` 全量 patterns | ✅ | P-114 实读：两 package-ecosystem 均 monthly + `groups` 全量 patterns |
| 首个分组 PR | 观察一个周期 | 每月 1 个 actions PR + 1 个 python PR，非逐条 | ☐ | push 依赖项，dependabot 首轮调度待第二次回填（遗留待办） |
| 徽章单一真值 | 读 README + 请求徽章 URL | 静态 `Tests-2699 passed` 已删；`ci.yml/badge.svg?branch=main` 可解析 | ☐ | README 半项已验（静态数字徽章已删，改 `ci.yml/badge.svg?branch=main`，P-114 实读）；徽章 URL 请求取证待第二次回填（遗留待办） |

### 2.7 I-6：本地与 CI 同判接线（B2）

| 验收项 | 测试方法 | 通过条件 | 状态 | 证据 |
|--------|---------|---------|------|------|
| 两处 entry 逐字符一致 | 比对 `.pre-commit-config.yaml` 与 ci.yml spec-gates | 字符串完全相同 | ✅ | P-114 比对 `python scripts/spec/ci_coverage_check.py --check` 两处 entry `-ceq` 相等 |
| 钩子与 job 同判 | `pre-commit run ci-coverage --all-files` | 与 spec-gates job 内命令同结论 | ✅ | P-114 复跑 Passed（与 job 同 entry 同判 exit 0）；CI spec-gates 实跑 collect error 为环境差异（缺 `mcp` extra），登记为遗留待办 |

## 3. 接口验收

### 3.1 `dc_validator.check_links`

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| 签名与 DESIGN.md §4.1 一致 | 类型、参数名、返回类型完全一致（含 `tracked=None` 默认） | ☐ |
| 正常输入返回正确结果 | 已入库链接不判；返回 `list[CheckResult]` | ☐ |
| 边界输入处理正确 | 无 `.git` ⇒ 空集 + 一行 skip 提示，不误红 | ☐ |
| 异常输入抛出正确异常 | 不可解析链接仍走原「档 1 相对链接不可解析」，不重复报 dc3 | ☐ |

### 3.2 `vendor_source_sync.py` CLI

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| CLI 形态与 IMPLEMENTATION.md §4.2 一致 | `--check`（默认）/ `--write`，退出码 0/1 | ☐ |
| 正常输入返回正确结果 | 27 条 + 2 条许可条目一致 ⇒ exit 0 | ☐ |
| 边界输入处理正确 | `file_count` ≠ `len(files)` ⇒ 判差异 | ☐ |
| 异常输入抛出正确异常 | 未入库路径 ⇒ fail-closed exit 1 | ☐ |

### 3.3 `ci_coverage_check.py` CLI

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| CLI 形态与 IMPLEMENTATION.md §4.3 一致（DESIGN §4.2 基线 + 已登记 `--selftest`） | `--check`（默认）/ `--write` / `--selftest`，退出码 0/1 | ☐ |
| 正常输入返回正确结果 | `R ⊆ L` 且 `L\R ⊆ C` ⇒ exit 0 | ☐ |
| 边界输入处理正确 | 空表起步 ⇒ 0 违规 | ☐ |
| 异常输入抛出正确异常 | 缺表 / 非 git 工作树 ⇒ exit 1 + 明确文案 | ☐ |

### 3.4 `tests/test_vendor_auto_prover.py::_blob_bytes`

| 验收项 | 通过条件 | 状态 |
|--------|---------|------|
| 判据与 DESIGN.md §4.4 一致 | 返回 blob 原始字节（LF 规范态），非工作树字节 | ☐ |
| 边界（无 `.git`）降级 | `pytest.skip`，不误红 | ☐ |
| 单一实现 | 直接复用 `vendor_source_sync.blob_facts`，无第二份哈希算法 | ☐ |

## 4. 不变式验收

| 不变式（来自 DESIGN.md §8） | 验证方法 | 状态 |
|---------------------------|---------|------|
| I-1 入库真值 | `--selftest` F34/F35 + detached worktree 复跑 0 违规 | ✅（P-114：selftest 43/43 含 F34/F35 + detached worktree 252 文件 0 违规） |
| I-2 可重现元数据 | `vendor_source_sync --check` exit 0；27 例全绿 | ✅（P-114 复跑 exit 0，29 条目；34 passed） |
| I-3 覆盖闭合 | `ci_coverage_check --check` exit 0 + `--selftest` 三类违规可判 | ✅（P-114 复跑 exit 0，L=148 / R=0 / C=148；selftest 4/4） |
| I-4 单一真值 | 人工核对 README 无「未经 CI 实测」的数字徽章 | ✅（P-114 实读 README：静态 `Tests-2699 passed` 已删） |
| I-5 红即阻断 | 分支保护 API 读回逐字段核对（7 必需名 / `enforce_admins=true` / 3.14 不入集） | ✅（P-122 读回：7 必需名逐字符一致、`Tests (3.14)` 不在集、`enforce_admins.enabled=true`、PR 必走且 `required_approving_review_count=0`；前置两次全绿 = run 43711274731 attempt 1/2 均 `success`） |
| I-6 本地=CI | 两处 entry 字符串一致 + `pre-commit run ci-coverage` 与 job 同判 | ✅（P-114：entry 逐字符相等 + 钩子 Passed；CI 侧 env 差异红面登记为遗留待办） |

## 5. 错误处理验收

| 错误场景（来自 DESIGN.md §7） | 触发方式 | 预期行为 | 状态 |
|------------------------------|---------|---------|------|
| 链接目标未入库 | 写入指向未入库路径的档 1 链接后跑 dc_validator | P2 阻断，文案含「入库或改行内代码」 | ☐ |
| SOURCE.json 与 blob 不符 | 手改一条 `sha256` 后跑测试 | 测试失败，文案指向 `vendor_source_sync.py --write` | ☐ |
| 测试文件新增但未进 CI | 新增 `tests/test_*.py` 且不改枚举 | `ci_coverage_check` exit 1，指向「确认可运行或登记」 | ☐ |
| 登记项指向已删文件 | 在 `ci_exclusions.yaml` 写不存在路径 | exit 1，文案「排除表有死项：删除该登记」 | ☐ |
| 登记项缺 marker / 有 marker 未登记 | 只改登记表或只加 marker | exit 1，文案「声明源与运行时开关必须同改」 | ☐ |
| git 不可用（sdist 场景） | 无 `.git` 目录下跑 `--check-links` | 空集 + 一行 skip，不误红且 CI 判红面不变 | ☐ |

## 6. 性能验收

| 性能指标 | 目标 | 实测 | 状态 |
|---------|------|------|------|
| blob 读取子进程数 | ≤1（`git cat-file --batch` 单进程） | `blob_facts` 单次 `Popen git cat-file --batch`（`vendor_source_sync.py` 实读，无逐文件子进程） | ✅ |
| 链接判定复杂度 | 集合成员 O(1)，`git ls-files` 进程级 1 次 | tracked 为 set 成员 O(1)，每 root 缓存 1 次 `ls-files`（`dc_validator.check_links` 实读） | ✅ |
| 覆盖守卫开销 | `--collect-only` 单次；本地仅在 `files` 正则命中时触发 | P-114 实跑 `--check` 3.7s（`--collect-only` 单次）；pre-commit 钩子仅 `spec/**` 与 `docs/{PROGRESS,CONSOLE}.md` 命中时触发 | ✅ |

## 7. 兼容性验收

| 环境 | 版本 | 状态 | 说明 |
|------|------|------|------|
| Python | 3.11 | ☐ | CI 必需矩阵位；本批只用 3.11 可用 stdlib |
| Python | 3.12 | ☐ | CI 必需矩阵位 |
| Python | 3.13 | ☐ | CI 必需矩阵位；本机 3.13.5 |
| Python | 3.14（实验位） | ✅ | 现状已 `continue-on-error`（ci.yml L96 实测），DESIGN §3.4 明确不入必需集 |
| OS | Linux（ubuntu-latest） | ☐ | CI 判定环境 |
| OS | Windows（CRLF 工作树） | ☐ | D-1 修复后须与 Linux 同判（本机 git 2.53.0.windows.2） |
| 无 `.git` / sdist | — | ☐ | `check_links` 空集 skip；两个脚本仅门禁侧调用，不进 wheel |
| PyYAML | 6.0.3 | ☐ | `yaml.safe_load` 只解析基础类型，`ci_exclusions.yaml` 无自定义标签 |

## 8. ADD 审计（Step 10）

### 8.1 Spec 质量门（Phase 0）

> 本节按 **1 个验收单元**整体计数（见 §10.1「ADD 审计」行）。

| 维度 | 得分（0-1） | 说明 |
|------|-----------|------|
| 可测试约束 | 1 | 每条 D-x 都有先红读数与退出码判据（12 条差异 / 21 P2 / 104 未进 CI） |
| 模块映射 | 1 | DESIGN §3.2 十行与 IMPL §2.3 十一行一一对应，第 11 行注明为 I-6 接线 |
| 接口契约 | 1 | `check_links` 为真实源码签名；`vendor_source_sync` 签名属 derived 但已显式登记 |
| 修正项 | 0.8 | D-1..D-9 均有唯一承载；D-8/D-9 为显式不实施，验收面天然缺席 |
| 跨模块契约 | 1 | I-1..I-6 全部落到具体文件 + 验证方式，无悬空不变式 |
| **总分** | 4.8/5 | **档位**: A |

### 8.2 ADD 审计发现

| 严重性 | 发现 | 证据 | 修复建议 |
|--------|------|------|---------|
| P1 | 无 | 四文档链交叉核对 + dc_validator 0 违规 | — |
| P2 | 无 | 计数（25/21/104/27/7）与 IMPL/DESIGN 逐一复算一致 | — |
| P3 | 无（原 P3「DESIGN §4.1 多写返回注解」已由 P-111 一致性审计订正：DESIGN v1.3 删除该注解，见 IMPL §9.6） | `scripts/spec/dc_validator.py` L352 实读 | — |

### 8.3 ADD Iron Law 检查

- [x] 断言恒真式：本批零代码，未引入新断言；B1/B2 实施后须复核 27 例参数化与 C1-C4 非恒真
- [x] 单文件检查盲区：已实证 `ci.yml` 枚举 45 文件 vs 已提交 149（差 104），由 D-5 承载
- [ ] 设计文档独有约束无测试：I-1..I-6 已完成「约束 → 测试/自测/runbook」映射，实际测试待 B1/B2 落地
- [ ] 修正阻断性项无测试：D-1/D-2/D-3 的阻断性修复尚无已运行测试，待 B1 先红-后绿举证

### 8.4 取证矩阵（RULE-6，P-111 一致性审计）

> 本表是 §8.1-§8.3 的证据形态，不新增验收单元（§10.1「ADD 审计」仍按 8 项计）。

| 取证手段（等级） | 覆盖项 | 结果 |
|---|---|---|
| `git ls-files` + 文档自述计数逐项复算（E1） | A-2：21 处 / 10 文件 / 6 目标；45/149/104；27/12 | ✅ 精确复现 |
| `python scripts/spec/dc_validator.py --check-links` 实跑（E1） | A-2：无参 = 64 P2（域外 docs + 未入库本地笔记），改写后不归零 | **发现 1 项**（判据口径不可达绿） |
| 静态读码 + 行号绑定（E3：`scripts/spec/dc_validator.py:352`） | A-1：`check_links(file, text, root=ROOT)` 无返回注解 | **发现 1 项**（DESIGN §4.1 失真） |
| `dc_validator --check-counting` + 逐节行数重数（E1） | §10.1 两条算术（逐行 / 列和）与八类行数 | ✅ 自洽 |
| 盲区扫描（E4，扫描范围：四文档全部 P2/P3 宣称 + 6 处命令/行号/计数引用） | A-3 / A-4 / A-5 / A-6 | **发现 4 项** |

**未覆盖项（E5，不入结论）**：B1/B2 的全部实施读数（§2/§3/§5/§6 的 ☐ 项）——本批零代码，不得据本表宣称任何功能已落地。

## 9. 文档完整性

| 文档 | 存在 | 与实现一致 |
|------|------|----------|
| RESEARCH.md | ✅ | ✅ |
| DESIGN.md | ✅ | ✅ |
| IMPLEMENTATION.md | ✅ | ✅ |
| CHECKLIST.md（本文件） | ✅ | ✅ |
| ADR（如有） | ✅（不适用） | ✅（仓内无 ADR 目录，DESIGN §2.2 已核实） |
| 开发日志 | ✅（docs/PROGRESS.md） | ✅（P-110 / P-111 行已登记） |

## 10. 验收结论

### 10.1 验收统计

| 类别 | 总数 | 通过 | 失败 | 待办 |
|------|------|------|------|------|
| 文档一致性 | 15 | 15 | 0 | 0 |
| 功能 | 25 | 20 | 0 | 5 |
| 接口 | 15 | 0 | 0 | 15 |
| 不变式 | 6 | 6 | 0 | 0 |
| 错误处理 | 6 | 0 | 0 | 6 |
| 性能 | 3 | 3 | 0 | 0 |
| 兼容性 | 8 | 1 | 0 | 7 |
| ADD 审计 | 8 | 6 | 0 | 2 |
| **总计** | **86** | **51** | **0** | **35** |

> **统计口径（RULE-2）**：上表来自本文件**逐项核对**（每一项均有独立标记），非事后汇总推算。
>
> **规范形态（P-050 交付 A，由 `dc_validator` M4 分支② 机械校验）**：① 章节号固定 `### 10.1 验收统计`（禁改号、禁标题加括注）；② 数值单元格 = **纯十进制整数**（禁 `**N + M**` / `N 项 + M 发现` / 括注；`**N**` 加粗允许）；③ 表内两条算术必须成立——逐行 `总数 = 通过 + 失败 + 待办`，总计行 = 8 类行**按列求和**。

### 10.2 验收决定

- [ ] **验收通过**：所有 P1 项通过，无阻塞性问题
- [x] **有条件通过**：本机可验项全部通过（§2.1 / §2.2 / §2.4 / §2.6 形态 / §2.7 / §4 I-1..I-6 / §6），push 依赖项（§2.3 3 项、§2.6 2 项）保持 ☐ 待后续回填；CI push run 43635083591 红面已由修复批（P-121，commit `e34ad40`）转绿——run 43711274731 attempt 1/2 均全绿；分支保护已按 runbook 应用并读回，且经故意违规 PR 实证阻断（P-122）
- [ ] **验收失败**：<原因>

> 首轮回填（P-114，2026-11-15）：B1/B2 已实施（P-112），本机可验项回填 ✅ 并复算 §10.1（86/47/0/39）；「有条件通过」已勾选——条件为 CI 红面修复批与分支保护执行（均遗留待办）完成后，push 依赖项第二轮回填（遗留待办）再按实际读数复算并终裁。
>
> 第二轮回填（P-122，2026-11-15）：两项前置已闭环——① CI 红面修复批（P-121）使 commit `e34ad40` 的 run 43711274731 **连续两次全绿**（attempt 1 与 rerun 的 attempt 2 均 `success`，8/8 job）；② 分支保护按 IMPLEMENTATION §10 Step 5 runbook 应用，`gh api .../branches/main/protection` 读回 7 必需名逐字符一致、`Tests (3.14)` 不在集、`enforce_admins.enabled=true`、PR 必走且 approvals=0。§2.5 行 105、§2.3 行 89、§4 I-5 翻 ✅，§10.1 复算 **86/50/0/36**（功能 19/0/6、不变式 6/0/0）。仍维持「有条件通过」：§2.3 3 项、§2.6 2 项、§3/§5/§7 未验项待回填后终裁。
>
> 第三轮回填（P-122 续，2026-11-15）：§2.5 行 106「无 admin 旁路且红即阻断」由故意违规 PR 实证关闭——PR #2（`probe/bp-violation`，新增失败断言用例）`mergeStateStatus=BLOCKED`，`gh pr merge --squash` 与 `--admin` 均被拒（后者报 `3 of 7 required status checks are failing`，`Tests (3.14)` 的 fail 不计入），且直推 `main` 被拒（`Changes must be made through a pull request` / `7 of 7 required status checks are expected`）；PR 已关闭、分支已删，`main` 无探针提交。§10.1 复算 **86/51/0/35**（功能 20/0/5）。剩余 ☐：§2.3 3 项、§2.6 2 项、§3/§5/§7 未验项。

### 10.3 签字

| 角色 | 签字 | 日期 |
|------|------|------|
| 实施者 | DeepSeek-V4.1-Flash（Step 7 文档编写，零代码） | 2026-11-14 |
| 一致性审计 | DeepSeek-V4.1-Flash（Step 8 + Step 10，P-111） | 2026-11-14 |
| 审查者 | 待指派（独立上下文复审） | — |

## 11. 后续行动

| 行动 | 责任人 | 期限 | 状态 |
|------|--------|------|------|
| B1 步骤 1-2：`vendor_source_sync.py` + 断言改锚 blob | 实施者 | B1 | ✅（P-112） |
| B1 步骤 3-4：`tracked` 校验 + 21 处链接改写 | 实施者 | B1 | ✅（P-112 / P-113） |
| B1 步骤 5：分支保护 runbook（CI 连续两次绿后） | 实施者 | B1 | ✅（P-122：run 43711274731 两次全绿后应用并读回 7 名 / `enforce_admins=true` / 3.14 不入集） |
| B2 步骤 6-9：workflow 硬化 / 登记表 / 覆盖守卫 / dependabot | 实施者 | B2 | ✅（P-112） |
| 回填 §2-§6 并复算 §10.1，择一勾选 §10.2 | 审查者 | B2 后 | 首轮完成（P-114：本机项 + 有条件通过）；第二轮完成（P-122：分支保护应用 + 两次全绿）；第三轮完成（P-122 续：违规 PR 阻断实证），复算 86/51/0/35；终裁待剩余 ☐ 项回填 |
| DESIGN v1.3 订正 §4.1 返回注解（IMPL O-4） | 设计者 | 下一设计版 | ✅（P-111 已订正） |
| 更新 PROGRESS.md | 实施者 | 每批 | ✅（P-114） |
| 记录开发日志 | 实施者 | 每批 | ✅（P-114） |
