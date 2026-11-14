---
id: arc-ci-cd-research-RESEARCH
type: design
version: 1.1
status: verified
date: 2026-11-14
depends: [arc-g4-m5-host-boundary]
upstream: null
---

# 调研文档：CI/CD 现状盘点与补全路线（P-107 立项调研批）

> **Feature**：P-107，CI/CD 机制盘点、缺口分析与补全路线（立项调研批，T3 Layer-0，零生产代码）。
> **Spec 步骤**：Step 1-2（T3 调研批）。
> **结论先行**：**CI 框架存在且完整度高于社区均值，但 main 分支最近 5 次 push CI 全部 failure 且分支无保护，红牌无约束力**。两项失败根因均已实证：R-1 vendored 字节断言的 CRLF/LF 平台偏差（本地绿、CI 红）；R-2 spec 文档引用了被 .gitignore 的未入库文件（本地存在、CI checkout 无此文件）。CD 侧完全缺失。本调研不动代码，产出分级补全路线供后续实施批裁决。

## 1. 调研目标

1. **有无**：仓库是否存在 CI/CD 机制（workflow 文件、触发器、job 覆盖面）？
2. **健康度**：远端 CI 是否真实在跑、结论如何、失败根因是什么？
3. **缺口**：对照社区标准，触发器/矩阵/缓存/守卫接线/CD/供应链各面缺什么？
4. **路线**：补全应如何分级，与本仓 fail-closed / 棘轮 / 声明=重数纪律如何对齐？

## 2. 调研方法与降级链

| 通道 | 用途 | 结果 |
|---|---|---|
| 仓内读码（E1） | workflow / pre-commit / .gitattributes / .gitignore / pyproject / 测试清单 | ✅ |
| gh 实证远端（E2） | `gh run list` / `gh run view` / `--log-failed` / 分支保护 API | ✅ 定位双根因 |
| 平台差探针（E2） | `git ls-files` 对账未入库文件、`git check-ignore -v` 定位 ignore 规则 | ✅ R-2 实锤 |
| 官方文档检索（T1） | Python Packaging Guide / PyPI Trusted Publishing / GitHub Blog / pre-commit 官方 | ✅ 对标完成 |

**降级链记录**：无静默跳过；gh API 分支保护查询返回 404（Branch not protected）本身即为实证结论。

## 3. 调研发现

### 3.1 CI 存在且设计完整（E1）

仓库根 `.github/workflows/` 仅 [ci.yml](../../.github/workflows/ci.yml) 一个 workflow，push + pull_request 双触发，5 个 job：

| Job | 内容 | 社区对标 |
|---|---|---|
| packaging | wheel 构建 + 重复路径校验 + 必备资产断言 + 装机 CLI 冒烟 + registry 探针 | 高于社区均值 |
| extras | server/mcp/voice 可选依赖导入 + mcp>=2.1 元数据断言（P-094） | 到位 |
| tests | Python 3.11/3.12/3.13 矩阵 + 3.14 experimental（`continue-on-error`、`fail-fast: false`） | 规范 |
| roadmap-coverage | D-6 验收覆盖检查 + 接线守卫 + 凭据守卫 | 本仓特色 |
| spec-gates | 门禁自测 + P-081 range 批绑定（`fetch-depth: 0` + BASE_SHA 双兜底）+ pre-commit 全量 9 钩子 | 消化了 P-081 边界 |

本地 pre-commit 9 钩子（A0-1 六必需 + 三额外守卫）与 CI spec-gates job 全量对应，接线完整（[.pre-commit-config.yaml](../../.pre-commit-config.yaml)）。

### 3.2 远端实证：main 最近 5 次 push CI 全部 failure（E2）

`gh run list --repo StormstoutLau/AutoResearchClaw`（2026-11-14 快照）：最近 5 次 push（P-103 至 P-106 批）结论全部 `failure`，时长 38–55 秒。最新 run 43587290844 分 job 结论：Extras / Packaging / Roadmap coverage 三 job 绿，Tests（3.11/3.12/3.13/3.14 四矩阵）与 Spec gates 红。

**分支保护缺失**：`gh api .../branches/main/protection` 返回 `404 Branch not protected`——红牌对合入无任何约束力，CI 的 fail-closed 语义在仓库层面被架空。

### 3.3 根因 R-1：vendored 字节断言的 CRLF/LF 平台偏差（E2）

- [test_vendor_auto_prover.py](../../tests/test_vendor_auto_prover.py) L32 断言 `path.stat().st_size == entry["bytes"]`（SOURCE.json 逐文件记录字节与 sha256）。
- CI 日志实证（Tests 3.11 job）：SOURCE.json 27 个 vendored 文件中 **12 个**在 L32 尺寸断言失败（4 矩阵 ×12 = 48 条同源断言失败；L33 sha256 断言与 license 文件零失败），如 `datatypes/__init__.py` 本地 2680 vs CI 2549、`datatypes/core.py` 本地 5362 vs CI 5242，方向**全部为「本地大、CI 小」**。
- [.gitattributes](../../.gitattributes) L3 已声明 `researchclaw/vendor/auto_prover/** -text`（blob 不做 EOL 转换），但本地 Windows 工作树是规则生效前检出、从未 renormalize，仍是 CRLF；SOURCE.json 按 CRLF 工作树记录。
- 后果：blob 为 LF 的字节记录若不重算，**本地绿、CI 红的平台偏差恒存在**；这是「声明=重数」纪律的典型盲区——P-105/P-106 各批本地 9 门禁全绿宣称与 CI 红并存。

### 3.4 根因 R-2：spec 文档引用未入库文件（E1+E2）

- CI spec-gates job 失败行：`[P2] spec/arc-g3-m2-stage-events/RESEARCH.md: 档 1 相对链接不可解析: ../../docs/failure-guards-design.md (L15)`。
- 实证链：`git ls-files docs/failure-guards-design.md` 为空（未跟踪）→ `git check-ignore -v` 命中 [.gitignore](../../.gitignore) L169 显式 ignore → `git log --all` 对该文件无任何历史。
- 即：**该文件被有意排除入库，但引用它的 spec 文档仍在 DC 契约内**。本地因文件实际存在而判绿，CI checkout 无此文件判红。非平台 bug，是「引用了永远不在仓库里的文件」的引用完整性缺陷（此判断订正本调研早期「疑似路径分隔符平台 bug」的假设——假设被证据证伪，如实登记）。

### 3.5 CD 完全缺失（E1）

无 release/publish workflow（`.github/workflows/` 仅 ci.yml 一个文件）；packaging job 只构建校验不发布产物；无 tag → GitHub Release 链路；无 PyPI 发布、无 Docker 镜像产出。

### 3.6 结构性缺口清单（E1，逐项实证）

| # | 缺口 | 实证 |
|---|---|---|
| G-1 | **测试清单漂移**：ci.yml tests job 手工枚举 45 个测试文件，tests/ 已提交测试文件 149 个（`git ls-files tests/test_*.py` 计数），104 个不进 CI；P-101/103/105/106 各批人肉补清单，无防漂移守卫；且 README「Tests-2699 passed」badge 的全量口径与 CI 仅跑 45 文件的覆盖面分裂 | 计数一手实测 |
| G-2 | ci.yml 无 pip 缓存、无 `concurrency` 取消过时 run、无 `timeout-minutes`、无 `permissions:` 最小权限收敛、无 `workflow_dispatch` | 文件全读 |
| G-3 | 无 dependabot/renovate（`.github/` 无 dependabot.yml）、无 CODEOWNERS、无 PR/Issue 模板 | glob 实测 |
| G-4 | README 无 CI badge（头部 8 枚 badge + 正文 1 枚 showcase 徽章，无一指向 Actions 状态） | 读码 |
| G-5 | Node 20 弃用警告：actions/checkout@v4、setup-python@v5 被 GitHub 强制跑在 Node 24 | CI annotations 实证 |
| G-6 | 无通用 linter/类型检查/覆盖率（pyproject dev extras 6 项 = pytest/pytest-asyncio/httpx/jsonschema/build/hatchling，无 ruff/mypy/coverage 配置） | pyproject 读码 |
| G-7 | 仅 ubuntu-latest 单平台；本仓大量 safe_join/路径边界代码，Windows 兼容性无 CI 证据 | 文件读码 |

## 4. 社区对标（T1 官方信息源）

| 信息源 | 要点 | 本仓借鉴 |
|---|---|---|
| Python Packaging Guide「Publishing via GitHub Actions」+ PyPI Trusted Publishing 安全模型 | CD 正解 = tag 触发、独立最小权限 release workflow、OIDC 免 token（`pypa/gh-action-pypi-publish`）；官方明确「勿信任主 CI workflow 做发布」 | G-5 CD 的形态基准 |
| GitHub Blog《Tame Dependabot》 | github-actions + pip 双生态、monthly 分组批量 + security 即时跟进为主流节奏 | G-3 直接可抄 |
| GitHub Actions 官方最佳实践 | `cache: pip`（指向真实 manifest）+ `concurrency` + `timeout-minutes` + workflow 级 `permissions: contents: read` 四件套 | G-2 直接可抄 |
| pre-commit.ci | 官方推荐托管（缓存 + 每周自动升级 hook 版本 PR） | 本仓 spec-gates 已自建等价物，**不引入**；仅借鉴 hook 自动升级思想 |
| Ruff pre-commit 集成 / NLSQ 等中型仓案例 | ruff + mypy + coverage 棘轮基线 | G-6 若补须走「基线冻结只升不降」，避免全量清洗违背棘轮纪律 |

**对标结论**：本仓 CI 框架完整度（wheel 冒烟 / extras 断言 / range 批绑定 / 9 钩子全量）高于社区均值，缺的不是框架而是**治理闭环**——红牌无约束力 + 平台偏差盲区 + 引用完整性缺陷 + 依赖与发布自动化为零。

## 5. 综合分析

1. **最高风险不是没有 CI，而是 CI 长期红且无分支保护**：fail-closed 门禁语义在 main 上被架空，所有「CI 全清单零失败」宣称只对本地成立（P-105/P-106 口径即如此）。[★★★★★]
2. **R-1/R-2 同构**：两者都是「本地环境态 ≠ 仓库态」导致本地绿 CI 红——前者是 EOL 工作树漂移，后者是 gitignore 排除的本地文件。修复方向都应回归「以仓库态（blob/committed file）为唯一真值源」。[★★★★★]
3. **G-1 清单漂移是持续性风险**：每批新增测试都要人肉同步 ci.yml，漏登即静默缩减 CI 覆盖（fail-open 方向）。[★★★★☆]
4. **CD 缺失当前无害**（尚无发布需求），但 packaging job 的 wheel 校验资产已为发布备好接缝。[★★★☆☆]

## 6. 补全路线建议（分级，供实施批裁决）

**P0 止血（恢复 main CI 绿 + 约束力）**
1. R-1 修复：以仓库 blob 字节重算 SOURCE.json（LF 口径）+ 本地 `git add --renormalize` 重检出，双平台字节一致（未决项 U-1 备选：测试改断言 git blob hash）；
2. R-2 修复：订正 spec/arc-g3-m2-stage-events/RESEARCH.md L15 引用（删除或改指已入库文档；未决项 U-2 备选：解除 ignore 入库 / grandfather 豁免登记）；
3. GitHub 仓设置启用分支保护（require CI 全绿；仓库设置操作，不入代码）。

**P1 健壮性（社区标准，低成本）**
4. ci.yml 加 pip cache / concurrency / timeout-minutes / permissions / workflow_dispatch（G-2）；
5. 测试清单防漂移（G-1）：方向 A = `pytest tests/` 全量 + marker 排除重型/live；方向 B = repo_stats 式棘轮守卫（ci.yml 清单 vs tests 目录差集白名单，fail-closed）——未决项 U-3 留设计批裁决；
6. dependabot.yml（github-actions + pip，monthly 分组）+ README CI badge（G-3/G-4/G-5 一并处理）。

**P2 CD 与供应链（按需）**
7. 独立 release.yml：tag → GitHub Release + wheel artifact；若上 PyPI 走 Trusted Publishing 独立最小权限 workflow（§4 基准）；
8. actions 升级消 Node 20 警告（checkout@v5 / setup-python@v6，可由 Dependabot 自动化）；
9. 可选：windows-latest 附加 job（G-7，本仓 safe_join/路径代码有真实价值）、coverage 棘轮基线（G-6）。

## 7. 未决项

| ID | 内容 | 当前倾向 | 证据等级 |
|---|---|---|---|
| U-1 | R-1 修复形态：重算 SOURCE.json+renormalize vs 测试断言 blob hash | 前者（真值源归仓） | E1+E2 实证 |
| U-2 | R-2 修复形态：改链 vs 入库 vs grandfather 豁免 | 改链（该文件被有意 ignore，入库违背原意） | E1 实证 |
| U-3 | G-1 防漂移形态：全量自动发现 vs 棘轮守卫 | A（根治漂移，重型用例用 marker 显式排除） | E1 计数实证 |

## 8. 诚实边界

- 本批为 T3 调研批（Layer-0）：零生产代码、零门禁变更、零 workflow 变更；全部结论为 2026-11-14 快照，gh 实证数据随远端演化。
- **独立复审（2026-11-14，独立上下文子代理证伪式）**：D-1（P1）vendored 失败面夸大（原写「其余 26 个同模式」，实测 12/27）→ §3.3 订正；D-2（P2）尺寸例子张冠李戴（2549/2680 属 `datatypes/__init__.py` 非 core.py）→ §3.3 订正；D-3（P2）dev extras 口径（实为 6 项非 2 项）→ G-6 订正；O-1 badge 计数口径与 O-3「Tests-2699」badge 口径分裂 → G-4/G-1 并入。R-1/R-2 根因链、5 job 结构、45/149/104 计数、5 次全红、分支保护 404、全部相对链接目标入库状态均 CONFIRM。
- R-2 早期假设「疑似平台 bug」已被证据证伪订正（§3.4），如实登记假设修正过程。
- 社区对标为 T1 官方文档检索（WebSearch 2026-11-14），未逐仓复跑社区 CI 配置；借鉴形态而非参数。
- 调研会话与独立复审会话基座均为 GLM-5.3-Flash，上下文异构达成，基座级异构待外部模型补位（RULE-5 诚实声明）。
