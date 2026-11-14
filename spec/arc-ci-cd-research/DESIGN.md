---
id: arc-ci-cd-research-DESIGN
type: design
version: 1.3
status: verified
date: 2026-11-14
depends: [arc-ci-cd-research-RESEARCH]
upstream: arc-ci-cd-research-RESEARCH
---

# 设计文档：CI/CD 机制补全（P-108 设计批）

> **Feature**：P-108，CI/CD 补全设计（承接 P-107 调研批，零生产代码）。
> **创建日期**：2026-11-14
> **状态**：已验证（两轮 Step 4 独立复审 → v1.2；P-111 四文档一致性审计订正 §4.1 → v1.3）
> **Spec 步骤**：Step 3-4（T3 设计批）
> **基于调研**：[调研文档 v1.1](RESEARCH.md)

## 1. 设计目标

把「CI 存在但无约束力」转为「CI 绿、红即阻断、本地与 CI 同判」，同时消除三类系统性盲区：平台 EOL 偏差、引用未入库、测试清单漂移。判定标准：一次全新 clone 上，本地门禁与远端 CI 对同一提交给出**相同结论**；main 上的红牌会真实阻断合入（无 admin 旁路）。

本批只产出设计与实施契约，不改代码。实施分两批：B1 止血（恢复绿 + 建立阻断）、B2 硬化（消除漂移与平台盲区）；CD 仅留设计接缝，不实施。

## 2. 设计依据

### 2.1 调研结论

| 调研结论 | 设计决策 | 实施批 |
|---|---|---|
| R-1 vendored 字节断言平台偏差 | D-1 元数据锚定 git blob | B1 |
| R-2 spec 文档链接未入库文件 | D-2 链接改写 + 门禁 tracked 校验 | B1 |
| main 无分支保护、5 次 push 全红 | D-3 分支保护 runbook | B1 |
| G-1 测试清单漂移（45/149） | D-5 覆盖闭合 + 排除登记 | B2 |
| G-2 workflow 缺缓存/并发/超时/权限/dispatch；G-5 Node 20 弃用 | D-4 workflow 硬化 | B2 |
| G-3 无依赖自动化；G-4 无 CI 徽章 | D-6 依赖自动化与徽章 | B2 |
| G-6 无 linter / 类型检查 / 覆盖率 | D-8 **不实施**（见 §5.4） | — |
| G-7 仅 ubuntu-latest 单平台 | D-9 **不实施**（见 §5.4） | — |
| CD 缺失（当前无发布需求） | D-7 发布接缝（不实施） | 未来 |

判定口径：G-1..G-7 每条都有唯一承载决策（D-x），其中 D-8/D-9 为**显式「不实施」**，不是遗漏。

#### 2.1.1 关键实证补强（本设计批新增，均一手实测）

调研只指出「本地大、CI 小」。本批在 `HEAD=86e6d98` 上进一步实测，得到更严厉的结论：

1. **SOURCE.json 的 provenance 不可重现**：[SOURCE.json](../../researchclaw/vendor/auto_prover/SOURCE.json) 27 条目中 **12 条**记录的 `bytes`/`sha256` 是**本地 CRLF 工作树**的值（例：`datatypes/__init__.py` 记录 2680 / `d9c87092…`，而 blob 为 2549 / `bccb8c82…`）。即当前「字节级溯源」锚定的是一个不入库的本地工件，任何机器都无法复算。12 条错配与 CI 的 12 条失败**完全对应**。
2. **R-2 是系统性缺陷而非单点**：在仅含已提交文件的 detached worktree 中复跑 [dc_validator](../../scripts/spec/dc_validator.py)，得 **21 条 P2（档 1 相对链接不可解析）**，分布于 **10 个文件、6 个目标**（4 个根级设计/调研文档、`docs/failure-guards-design.md`、`docs/arc-g4-midpoint-20261113.md`）。本地全绿只因这些文件在磁盘上存在。
3. **计数边界**：上述 21/10/6 是 **spec/ 作用域**内的计数（dc_validator 的 hook 作用面 = `spec/**.md` + `docs/{PROGRESS,CONSOLE}.md`），不是全仓统计；全仓其他目录未计入（O-1 登记）。

### 2.2 相关 ADR

本批不引用 ADR：治理约束以 [SPEC_PROCESS.md](../SPEC_PROCESS.md) 为准（仓内无 ADR 目录、无 AGENTS.md，已用 `git ls-files` 核实），避免链接到未入库文件（正是 D-2 要消除的缺陷类）。

### 2.3 职责边界

**职责内**：workflow 编排、门禁脚本行为、测试元数据与登记表、仓库设置操作手册（runbook）、徽章口径。
**职责外**：业务/生产代码语义、发布渠道与版本策略决策、运行时依赖升级的取舍（交 Dependabot + 人工评审）、`researchclaw/vendor/**` 的源码内容（只校验不修改）、通用 lint/类型/覆盖率基线（D-8 显式不实施）。

## 3. 架构设计

### 3.1 整体架构（三层结构）

| 层 | 载体 | 职责 | 真值源 |
|---|---|---|---|
| 执行层 | [.github/workflows/ci.yml](../../.github/workflows/ci.yml) | 在干净 runner 上跑 5 个 job | 提交后的仓库态 |
| 门禁层 | [.pre-commit-config.yaml](../../.pre-commit-config.yaml) + `scripts/spec/*.py` | 本地与 CI 同判 | git index |
| 登记层 | `tests/ci_exclusions.yaml` + `SOURCE.json` | 显式声明例外与溯源 | git blob |

设计核心是**把每层的真值源统一为「仓库态」（index/blob），而不是「工作树」**。这是 R-1/R-2 两个根因的共同解。

### 3.2 模块划分

| 模块 | 变更类型 | 说明 |
|---|---|---|
| `tests/test_vendor_auto_prover.py` | 改 | 断言对象从工作树字节改为 git blob 字节（D-1） |
| `scripts/spec/vendor_source_sync.py` | 新增 | `--write` 由 blob 重算 `bytes`/`sha256`；`--check` 只校验（D-1） |
| `scripts/spec/dc_validator.py` | 改 | `check_links` 增 tracked 校验：链接目标必须在 git index 内（D-2） |
| `spec/**`（10 文件 21 处） | 改 | 未入库目标的链接改为行内代码引用（D-2） |
| [.github/workflows/ci.yml](../../.github/workflows/ci.yml) | 改 | permissions/concurrency/timeout/cache/dispatch/actions 版本（D-4）；测试改为全量收集（D-5）；spec-gates job 增 `ci_coverage_check --check`（I-6 接线） |
| `scripts/spec/ci_coverage_check.py` | 新增 | 覆盖闭合双向守卫（D-5）；**同时接入** `.pre-commit-config.yaml` 与 spec-gates job（O-2） |
| `tests/ci_exclusions.yaml` | 新增 | 排除登记表（唯一声明源），含 reason/owner/since（D-5） |
| [pyproject.toml](../../pyproject.toml) | 改 | 注册 `heavy` marker（仅作运行时开关，不承载声明） |
| `.github/dependabot.yml` | 新增 | actions + pip，monthly 分组（D-6） |
| [README.md](../../README.md) | 改 | 增 CI 徽章，移除静态用例计数徽章（D-6） |

### 3.3 数据流：一次 push 的判定路径

```
push → ci.yml（5 job 并行）
  ├ packaging         : build + wheel 内容断言 + 装机冒烟
  ├ extras            : 可选依赖导入 + mcp 元数据断言
  ├ tests(3.11/12/13) : pytest tests -m "not heavy"   ← B2 起改为全量收集
  ├ roadmap-coverage  : D-6 覆盖 + 接线/凭据守卫
  └ spec-gates        : pre-commit --all-files（dc_validator 含 tracked 校验）
                        + ci_coverage_check --check（I-6：本地与 CI 同判）
      ↓
分支保护聚合 7 个必需状态检查 → 全绿才允许经 PR 合入 main
```

### 3.4 控制流（D-3 的阻断语义）

job 之间无 `needs`（保持并行、失败互不掩盖）。聚合阻断由分支保护承担，必需集合为 **7 个具体检查名**（GitHub 只认 job 实际产生的名字，写未展开的 `Tests (${{ matrix.python-version }})` 会永久 pending）：

1. `Packaging / wheel smoke`
2. `Extras import`
3. `Tests (3.11)`
4. `Tests (3.12)`
5. `Tests (3.13)`
6. `Roadmap coverage gates`
7. `Spec gates (pre-commit all-files)`

`Tests (3.14)` 保持 `continue-on-error`，**不列入必需检查**（实验位不得阻断合入）。

仓库设置三件（runbook）：
- `Require a pull request before merging` = **true**，`required_approving_review_count` = **0**。前者是必需检查生效的前提（`required_status_checks` 只在 PR 合并路径上评估），后者避免要求不存在的第二评审者。
- `enforce_admins` = **true**。唯一维护者即 admin，若为 false 则红牌可被旁路，直接违反 §1 判定标准与 I-5。
- 不启用 `required_pull_request_reviews` 的评审人数 >0（当前无第二位评审者）。

## 4. 接口定义

### 4.1 `dc_validator.check_links` 扩展（D-2）

现状签名（真实，非模板占位，源码 L352 **无返回注解**）：`check_links(file, text, root=ROOT)`，由 `run_checks` 在 `links` 检查项下逐文件调用。

```python
TRACKED: set[str] | None = None   # 进程级一次载入：{normpath(p) for p in git ls-files}

def check_links(file, text, root=ROOT, tracked: set[str] | None = None):
    """M5/DC3：档 1 相对链接——(1) 可解析；(2) 目标在 git index 内。

    tracked=None：有 .git 时自动 `git ls-files` 载入一次（模块级缓存）；
                  sdist / 无 .git 场景置空集并打印一行 skip 提示。
    """
```

判定：对每个可解析的相对链接目标 `p`，额外要求 `normpath(p) ∈ TRACKED`。一条新 `CheckResult("dc3", file, "P2", ...)`，文案固定为：`档 1 相对链接目标未入库（CI 将判红）：<p>（修复：入库，或改为行内代码引用）`。

O-3 边界：sdist/无 `.git` 场景的 skip **不削弱 I-1**——CI 恒在 `actions/checkout` 的 git worktree 内执行，判红面始终是仓库态；skip 只服务于非 git 的打包消费场景。

### 4.2 `ci_coverage_check.py` CLI 契约

```
python scripts/spec/ci_coverage_check.py [--check|--write]
退出码：0 闭合；1 存在未登记差异（fail-closed）
```

双向闭合判定（I-3）：

- 左集 `L` = `git ls-files tests/test_*.py`
- 右集 `R` = `ci_exclusions.yaml` 登记的 `path` 集合
- 必有 `R ⊆ L`（登记项不得指向已删除文件），且 `L \ R` 全部由 CI 收集执行（通过 `pytest --collect-only -q` 的实际文件集 `C` 验证 `L \ R ⊆ C`）

### 4.3 `tests/ci_exclusions.yaml` schema

```yaml
version: 1
exclusions: []
# 首条登记形态（占位示例，非现有文件）：
#  - path: tests/test_<真实外部依赖用例>.py
#    reason: 需要真实 <服务/守护进程>；runner 可用而本地开发者未必具备
#    marker: heavy
#    owner: P-108
#    since: 2026-11-14
```

**本批不登记任何现有文件**：CI 现枚举的 45 个文件均不依赖真实外部环境（`test_rc_docker_sandbox.py` 头部自述 *all mocked, no real Docker needed*，且已在 45 个之内，**不得**作为 heavy 示例）。首批登记项由 B2 的 `--collect-only` 盘点结果决定。

O-4 消解「双件套 = 第二真值源」：`ci_exclusions.yaml` 是**唯一声明源**；`heavy` marker 只是 pytest 的运行时选择开关，不声明任何集合成员。二者一致性由 `ci_coverage_check` 双向校验（登记项必须有 marker；有 marker 的必须已登记）。

### 4.4 `SOURCE.json` 语义修正

条目 `{path, source, bytes, sha256}` 的 `bytes`/`sha256` 定义为**该路径在 git blob 中的原始字节数与摘要**（LF 规范态），与环境、`core.autocrlf`、工作树状态无关。`vendor_source_sync.py --check` 与测试共用同一实现，禁止手工编辑条目。

## 5. 替代方案

### 5.1 D-1（vendored 校验）

| 方案 | 结论 | 理由 |
|---|---|---|
| A 重算 SOURCE.json + `git add --renormalize`（RESEARCH U-1 原倾向） | 否 | 真实否决理由：`--renormalize` 在 `.gitattributes` 的 `researchclaw/vendor/auto_prover/** -text` 下**不做归一**，只会把工作树 CRLF 原样提交为 blob；且元数据仍由本地工作树人肉生成、换机不可复算。**订正**：v1.0 原写「换机 `autocrlf` 一开即复发」为误判——`-text` 属性下新检出即为 blob 原样（LF，CR=0）。 |
| B **断言 git blob**（选定） | 是 | 真值源=仓库态，环境无关；与 I-2 一致；实现仅需批量 `cat-file` |
| C 测试内静默 `\r\n→\n` 归一 | 否 | 会掩盖「CRLF 被提交」的真实损坏，违反 fail-closed |

**对 RESEARCH U-1 的改判**：RESEARCH §7 U-1 当前倾向为「重算 + renormalize」，本设计改判为「测试断言 git blob」，理由如上（E1：`-text` 下 renormalize 行为实测）。

### 5.2 D-2（未入库链接）

| 方案 | 结论 | 理由 |
|---|---|---|
| A **改行内代码引用**（选定） | 是 | 与 `.gitignore`「本地留存、永不入库」策略一致；21 处机械改动；保留可检索路径 |
| B `git add -f` 入库 6 个文件 | 否 | 违背既有排除策略，扩大仓库面（含评审/调研底稿） |
| C grandfather 白名单豁免 | 否 | 既有机制**确实存在**（[grandfather_gate.py](../../scripts/spec/grandfather_gate.py) L31 `EXEMPTIBLE = ("dc1","dc2","dc3")`，dc3 本可豁免），因此否决理由不是「过度设计 / 不存在该机制」，而是：① 豁免仅把红推迟至 expires（[grandfather.yaml](../grandfather.yaml)：过期即红、续期 ≤1 次、总寿命 ≤ cutoff+180 天），期间 21 处链接仍指向本地文件、I-1 违规持续存在；② 豁免不解决「本地绿 / CI 红」的判据分裂——到期转红虽是 fail-closed，却把修复推迟最长半年，期间 spec 消费者仍会点开失效链接。 |

### 5.3 D-5（测试覆盖）

| 方案 | 结论 | 理由 |
|---|---|---|
| A **全量收集 + 登记排除**（选定） | 是 | 新增测试自动进 CI，漂移面归零；排除项显式可审 |
| B 保留枚举 + 加清单比对守卫 | 否 | 仍需人肉维护清单，守卫只能发现「漏登记」不能自动纳入 |

### 5.4 D-8 / D-9（显式不实施）

| 项 | 内容 | 结论 | 理由 |
|---|---|---|---|
| D-8 | 通用 linter / 类型检查 / 覆盖率（G-6） | 不实施 | 三者均需先建「基线冻结、只升不降」的棘轮，否则全量清洗违背仓库棘轮纪律；当前 dev extras 无 ruff/mypy/coverage，属独立治理批次，混入 CI 止血批会放大 B1 的失败面。触发条件见 U-8。 |
| D-9 | windows-latest 附加 job（G-7） | 不实施 | 本批用「断言 git blob」从根上消除 CRLF 平台偏差（D-1），平台矩阵不再是该缺陷的必要解；加 Windows job 会引入第二套失败面而无对应验收。触发条件见 U-9。 |

## 6. 数据结构

### 6.1 `dependabot.yml` 关键字段（G-3）

```yaml
version: 2
updates:
  - package-ecosystem: github-actions
    directory: "/"
    schedule: {interval: monthly}
    groups: {actions: {patterns: ["*"]}}
  - package-ecosystem: pip
    directory: "/"
    schedule: {interval: monthly}
    groups: {python-deps: {patterns: ["*"]}}
```

选择 monthly 分组而非 weekly 逐条：本仓为单维护者，逐条 PR 会被 CI 修复批淹没。

### 6.2 `ci_exclusions.yaml` 条目契约

见 §4.3。字段固定五项 `path / reason / marker / owner / since`；`path` 必须是 `git ls-files` 内的相对路径，`reason` 必须指出「哪个外部依赖不可得」，禁止写「跑得慢」。

## 7. 错误处理（失败语义表）

| 失败点 | 门禁行为 | 对使用者的一句话 |
|---|---|---|
| 链接目标未入库 | dc_validator P2，阻断 | 「目标文件不在仓库里，CI 必红：入库或改行内代码」 |
| SOURCE.json 与 blob 不符 | 测试失败 | 「vendored 元数据与提交内容不一致：跑 `vendor_source_sync.py --write`」 |
| 测试文件新增但未进 CI | ci_coverage_check 退出 1 | 「新测试未被 CI 收集：确认可运行，或登记到 ci_exclusions.yaml」 |
| 登记项指向已删文件 | ci_coverage_check 退出 1 | 「排除表有死项：删除该登记」 |
| 登记项缺 marker / 有 marker 未登记 | ci_coverage_check 退出 1 | 「声明源与运行时开关不一致：二者必须同改」 |
| git 不可用（sdist 场景） | tracked 校验自动 skip 并打印 | 「非 git 工作树，跳过入库校验（CI 不受影响）」 |

原则：每条失败文案必须给出**下一步动作**，不做静默降级。

## 8. 不变式（Invariants）

- **I-1 入库真值**：spec 文档中可点击的相对链接目标必须在 git index 内。
- **I-2 可重现元数据**：`SOURCE.json` 的 `bytes`/`sha256` 必须能仅由 `git cat-file` 重算，跨平台一致。
- **I-3 覆盖闭合**：每个 `tests/test_*.py` 要么被 CI 收集，要么在 `ci_exclusions.yaml` 登记；两向差集为空。
- **I-4 单一真值**：仓库内任何徽章/统计不得声明未经 CI 实测的数字。
- **I-5 红即阻断**：main 的必需状态检查全绿才可合入；实验位（3.14）不得进入必需集合；不设 admin 旁路（`enforce_admins=true`）。
- **I-6 本地=CI**：CI 会红的静态违规，本地 pre-commit 必须同判；唯一例外是已登记的 heavy 用例。**接线要求**：`ci_coverage_check` 必须同时接入 `.pre-commit-config.yaml` 与 spec-gates job，否则 I-6 无承载。

## 9. 幻觉抑制审查（Step 4 Review）

### 9.1 设计基于已验证的调研结论

- [x] 所有设计决策可追溯到 RESEARCH.md（§2.1 映射表，G-1..G-7 全覆盖，D-8/D-9 为显式不实施）
- [x] 无未经验证的假设：§2.1.1 三项补强均为一手实测（`git cat-file` 逐条对账、detached worktree 复跑、文件枚举计数）
- [x] 无归因扭曲：R-1 的失败面由「26 个」订正为「12/27」；RESEARCH U-1 的倾向被本设计显式改判并说明理由（§5.1）
- [x] 接口签名真实：§4.1 采用 `dc_validator.py` L352 实际签名，非模板占位

### 9.2 替代方案审查

- [x] 至少列 2 个替代方案（D-1 三案、D-2 三案、D-5 两案）
- [x] 每个替代方案有明确的否决理由，且否决理由不含已被证伪的断言（D-2/C 已改以「既有豁免机制确实存在」为前提）

### 9.3 职责边界审查

- [x] 职责边界清晰（§2.3：只碰 CI 编排、门禁脚本、登记表、runbook、徽章）
- [x] 不越界吞并其他研究范式：linter/类型/覆盖率（D-8）与 Windows 平台矩阵（D-9）明确不纳入本批

**独立复审登记（2026-11-14，独立上下文子代理证伪式）**：返回 8 缺陷（D-1..D-8）+ 5 观察，缺陷全部回填本版——D-1(P1) `enforce_admins` 与 I-5 矛盾 → §3.4/§10.1 订正；D-2(P2) §5.1 否决理由已被实测证伪 → 改述并登记对 RESEARCH U-1 的改判；D-3(P2) §4.1 签名失真 → 改真实签名；D-4(P2) §3.4 必需检查数 → 改为 7 个具体名；D-5(P2) G-6/G-7 无承载 → 新增 D-8/D-9；D-6(P2) §11 未决项缺四元块 → 重写；D-7(P2) §4.3 示例用例失当 → 改占位；D-8(P2) §5.2 否认既有豁免机制 → 改述。观察 O-1..O-4 已并入 §2.1.1/§3.2/§4.1/§4.3，第 5 条为记录性观察、无需改文。CONFIRM：12/27 与 CI 12 条失败同名、45/149/104 计数、21/10/6、5 连红 + 保护 404 + 7 必需名、3.14 `continue-on-error`。

**复审 2（2026-11-14，独立上下文子代理证伪式，针对 v1.1）**：PASS-with-fixes，2 缺陷回填本版——W-1(P2) U-4 判据含 status 分句（index stat 缓存假阴性可使其为空而 12 处 CRLF 缺陷仍在）→ 改单一 sha256 机械判据、补救由 `git checkout --` 改强制重检；W-2(P2) §5.2 理由①「常设且不回溯/永久留白」与 grandfather.yaml 有期豁免事实不符 → 改述为「红推迟 ≤180 天，期间 I-1 违规持续」；O-A 复审登记计数如实化；O-E §12 并入 §10.3 回模板 11 节；O-B/O-C/O-D 记录不改文。CONFIRM：check_links 签名 L352、EXEMPTIBLE L31、12/27 错配全量复算成立、21/10/6 精确复现、45/149 计数、8 检查名与 7 必需名逐字符一致、v1.0 八项订正全部落实。

**一致性审计（2026-11-14，P-111，Step 8 + Step 10）**：四文档交叉审计（RESEARCH v1.1 / DESIGN v1.2 / IMPLEMENTATION v1.1 / CHECKLIST v1.0）发现 2 项 P2 + 3 项 P3 + 1 观察，本文件承载并订正 2 项——**A-1(P2)** §4.1 现写「`-> list[CheckResult]`」与真实源码 [dc_validator.py](../../scripts/spec/dc_validator.py) L352（`def check_links(file, text, root=ROOT):`，无返回注解）不符，且与本文件 §9.1「接口签名真实」自相矛盾，与 IMPL §9.5 O-4 / CHECKLIST §1.2 唯一 ☐ 同源 → 本版删除该注解并注明源码无注解（O-4 关闭）；**A-2(P2)** 属 IMPL/CHECKLIST 的命令口径缺陷（`--check-links` 无参 = 全仓扫描，含域外 docs 与未入库本地笔记，改写后亦不归零；21 条 P2 只在 detached worktree 的 hook 作用域内可复现），本文件 §2.1.1 已给出正确方法，故仅在 IMPL/CHECKLIST 订正口径，本文件 §2.1.1 计数（21/10/6）**经本轮独立复现确认成立**（文件级精确复算 21 处 / 10 文件 / 6 目标）。CONFIRM：§2.1 映射表覆盖 R-1/R-2/G-1..G-7、§3.2 十行与 IMPL §2.3 十一行对应、§3.4 七必需检查名逐字符一致、§7 六行失败语义与 CHECKLIST §5 一致、§8 I-1..I-6 全部落到 IMPL §7。

## 10. 对实施的输入

### 10.1 关键工程约束

1. **顺序**：B1 先以直接 push 清红（此时保护未开），再开保护。保护开启后（PR 必走 + 7 检查必需），红牌提交无法经 PR 合入；因不设 admin 旁路，不会退化为无门禁操作，**不构成硬锁**（直接 push 仍可用于紧急断链，但须在 runbook 中留痕并事后补绿）。
2. 分支保护为仓库设置，属 runbook 非代码；须在 B1 的 CI 连续两次绿后执行。
3. 所有新增守卫必须在 sdist/无 `.git` 场景优雅降级（打印跳过，不误红），降级不得改变 CI 判红面。
4. `repo_stats.py --write` 与本批计数链同步；PROGRESS/CONSOLE 计数一致。
5. 不引入 pre-commit.ci / Renovate（调研已裁决，避免外部服务与过度工程）。
6. `ci_exclusions.yaml` 为空表起步；任何新增登记必须先有 `--collect-only` 证据。

### 10.2 风险与缓解

| ID | 风险 | 缓解 |
|---|---|---|
| RI-1 | 全量 collected 暴露 104 文件的真实失败，可能牵连缺失依赖 | B2 先 `--collect-only` 盘点，再按目录分批跑；失败项三分法：修/登记/标记 heavy |
| RI-2 | `enforce_admins=true` 后 flaky 阻断紧急修复 | 先观察两次绿再开保护；对 flaky 用例登记 heavy 而非关旁路；紧急场景按 runbook 临时停用保护并留痕 |
| RI-3 | tracked 校验在 detached HEAD 或有未暂存新文件时误报 | 以 index 为集合；文案明确「先 `git add` 再提交」 |
| RI-4 | Dependabot 分组 PR 引入 breaking | 只对 actions 与 dev 依赖自动分组；运行时依赖保留人工评审 |
| RI-5 | 21 处链接改写后仍在本地指向真实文件，改写可能误删有用路径 | 统一改为行内代码保留原路径文本；改后以 detached worktree 复跑 dc_validator 验证 0 违规 |

### 10.3 实施批次建议

| 批 | 范围 | 验收 |
|---|---|---|
| B1 止血 | D-1、D-2、D-3 | 干净 worktree 中 dc_validator 0 违规；`test_vendor_auto_prover` 双平台通过；远端 CI 连续 2 次全绿；分支保护生效（7 必需检查，无 admin 旁路）且红即阻断 |
| B2 硬化 | D-4、D-5、D-6 | 覆盖闭合守卫 0 差异；pip 缓存命中；同分支连续 push 取消前序 run；Dependabot 首个分组 PR 出现；徽章指向真实 workflow |
| B3 未来 | D-7 | 无（不启动） |
| 不实施 | D-8、D-9 | 以 U-8 / U-9 的触发条件挂起 |

## 11. 未决项登记（四元块）与决策矩阵

**对上游未决项的处置**：RESEARCH §7 U-1 由本设计改判（§5.1）；U-2（改链）与 U-3（全量自动发现）与本设计 D-2/D-5 一致，不改判。

**11.1 未决项登记**

- **U-4 本地工作树 12 个 CRLF 文件是否强制恢复为 blob 态**
  - **判据**：逐文件工作树 `sha256` = `git cat-file blob` 摘要（单一机械判据；**禁用** `git status --porcelain` 作判据——index stat 缓存假阴性可使其为空而缺陷仍在，实测 index stat size=2680 vs blob 2549）
  - **触发条件**：B1 实施首日，首次运行 `test_vendor_auto_prover` 时
  - **当前倾向**：无需「renormalize」；`-text` 属性下新检出即为 LF（CR=0）；对既有本地 CRLF 工作树用强制重检（先删除后检出或 `git checkout-index -f`），不用 `git checkout -- <paths>`（其依赖 git 察觉差异，在 stat 缓存假阴性下可能 no-op）；清理不作为提交内容
  - **证据等级**：E1（`-text` 语义、blob 字节、index stat 尺寸失配均本批实测）

- **U-5 104 个未纳入文件的最终三分法结果**
  - **判据**：`ci_coverage_check --check` 退出 0，且 `ci_exclusions.yaml` 每项都有 reason
  - **触发条件**：B2 首次运行 `pytest tests/ --collect-only -q` 后
  - **当前倾向**：无法静态判定；先修依赖缺失，再对真实外部依赖项登记 heavy
  - **证据等级**：待核（需 B2 实测）

- **U-6 `Tests (3.14)` 实验位保留与否**
  - **判据**：Python 3.14 成为稳定目标版本，且该 job 连续 10 次 run 全绿
  - **触发条件**：3.14 GA + 连续 10 次绿，或该 job 连续 5 次因上游预发布失败
  - **当前倾向**：保留且 `continue-on-error`，不列入必需检查
  - **证据等级**：E1（当前 CI 配置实测）

- **U-7 是否上 PyPI / GitHub Release**
  - **判据**：出现首个真实外部发布需求（对外分发 wheel 或打 tag 发布）
  - **触发条件**：用户提出发布诉求，或出现第三方安装反馈
  - **当前倾向**：不启动；只保留设计接缝（tag 触发 + 独立最小权限 workflow）
  - **证据等级**：E2（T1 官方发布指南）

- **U-8 D-8 的启动条件**
  - **判据**：存在覆盖率或类型基线读数，且落地为「只升不降」棘轮
  - **触发条件**：CI 连续 4 周全绿后，或出现类型相关线上缺陷
  - **当前倾向**：不实施（本批）
  - **证据等级**：E2（社区案例，本仓未实测）

- **U-9 D-9 的启动条件**
  - **判据**：出现 Windows 专属缺陷，且无法由「断言 git blob」覆盖
  - **触发条件**：Windows 用户报告的路径/换行缺陷 ≥2 例
  - **当前倾向**：不实施（本批）
  - **证据等级**：E1（G-7 现状实测）

**11.2 决策矩阵**：本设计全部决策均为 **Type-2（可逆）**——受影响面为 CI 配置、门禁脚本与文档，可单点回滚，故**不启动**矩阵（`spec/templates/DECISION_MATRIX_TEMPLATE.md` 仅在不可逆且多方案必须择一时启用）。

---

**Review 签字**：独立子代理（证伪式复审，两轮） 日期: 2026-11-14
