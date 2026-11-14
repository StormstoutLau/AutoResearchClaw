# 实施文档：CI/CD 机制补全（P-109 实施批）

---
id: arc-ci-cd-research-IMPLEMENTATION
type: design
version: 1.2
status: verified
date: 2026-11-14
depends: [arc-ci-cd-research-DESIGN, arc-ci-cd-research-RESEARCH]
upstream: null
---

> **Feature**: P-109，CI/CD 补全实施文档（承接 P-107 调研、P-108 设计，本批零生产代码）
> **创建日期**: 2026-11-14
> **状态**: verified（Step 6 独立证伪式复审 PASS-with-fixes，7 缺陷回填后定稿 v1.1；P-111 四文档一致性审计订正为 v1.2）
> **Spec 步骤**: Step 5-6
> **基于设计**: [DESIGN.md](./DESIGN.md) v1.3
> **基于调研**: [RESEARCH.md](./RESEARCH.md) v1.1

---

## 1. 实施概述

本文件把 [DESIGN.md](./DESIGN.md) 的 D-1..D-6 契约落成可执行步骤，分两批交付：**B1 止血**（D-1 vendored 断言改锚 git blob、D-2 链接改写 + dc_validator tracked 校验、D-3 分支保护 runbook），**B2 硬化**（D-4 workflow 五件套、D-5 全量收集 + 覆盖闭合守卫、D-6 依赖自动化与徽章）。D-7 只留接缝，D-8/D-9 显式不实施（DESIGN §5.4 / §10.3）。

实施半径严格等于 DESIGN §3.2 的模块清单：2 个新增脚本、1 个新增登记表、1 个新增 dependabot 配置、7 个改文件、1 个 runbook（不落新文档）。**不碰** `researchclaw/**` 业务代码与 `researchclaw/vendor/**` 源码内容。宣称边界：本批可验收的是「脚本/配置/文档 + 门禁读数」；分支保护属仓库设置，只能按 §10 Step 5 的 runbook 人工执行并留痕，代码侧无法自证。

## 2. 工程细节

### 2.1 技术栈

| 组件 | 技术 | 版本 | 验证状态 |
|------|------|------|---------|
| 语言 | Python | `requires-python = ">=3.11"`（[pyproject.toml](../../pyproject.toml) L5） | ✅ |
| CI 运行器 | GitHub Actions `ubuntu-latest` | 仓库现有配置 | ✅ |
| CI 触发 | `push` + `pull_request` + `workflow_dispatch` | 后者本批新增（D-4） | ✅ |
| 门禁 | pre-commit（9 钩子）+ `scripts/spec/*.py` | [.pre-commit-config.yaml](../../.pre-commit-config.yaml) 实读 | ✅ |
| Git CLI | git（`ls-files` / `cat-file` / `check-ignore`） | 本机 `git version 2.53.0.windows.2` | ✅ |
| 测试 | pytest | 本机 `8.3.4`（pin `>=7.0`） | ✅ |
| YAML 解析 | PyYAML（核心依赖 `pyyaml>=6.0`） | 本机 `6.0.3` | ✅ |

**零新增第三方依赖**：`ci_coverage_check.py` / `vendor_source_sync.py` 只用 stdlib（`subprocess`、`hashlib`、`json`、`argparse`、`pathlib`、`os`）+ 已有核心依赖 PyYAML（读 `ci_exclusions.yaml` 用 `yaml.safe_load`）。

### 2.2 依赖版本验证

| 依赖 | 声明版本 | 实测/最新 | 兼容性 | 验证方式 |
|------|---------|----------|--------|---------|
| Python | `>=3.11` | 本机 3.13.5；CI 矩阵 3.11/3.12/3.13/3.14(实验) | ✅ | 仓内 pyproject + ci.yml 实读 |
| pytest | `>=7.0` | 8.3.4 | ✅ | 本机 `pytest.__version__`（E1） |
| PyYAML | `>=6.0` | 6.0.3 | ✅ | 本机 `yaml.__version__`（E1） |
| `actions/checkout` | `@v7` | latest = `v7.0.1` | ✅ | `gh api repos/actions/checkout/releases/latest`（2026-11-14，E1） |
| `actions/setup-python` | `@v7` | latest = `v7.1.0` | ✅ | `gh api repos/actions/setup-python/releases/latest`（2026-11-14，E1） |

**stdlib API 下限检查（Step 6 硬项）**：本批仅用 `subprocess.run(capture_output=True, text=True)`、`hashlib.sha256`、`json.load/dumps`、`argparse`、`pathlib.Path`、`os.path.normpath`、`tempfile`——均为 3.11 可用；不使用 `Decimal.ulp`（3.12+）一类高版本 API。CI 缓存走 `setup-python` 的 `cache: pip`，不引入 `actions/cache` 第三方 pin。

### 2.3 文件结构

| # | 文件 | 动作 | 内容 | 回退点 |
|---|------|------|------|--------|
| 1 | [tests/test_vendor_auto_prover.py](../../tests/test_vendor_auto_prover.py) | 改 | 断言语义从工作树字节改为 git blob 字节（D-1） | 单文件 revert；元数据重算由脚本可重放 |
| 2 | `scripts/spec/vendor_source_sync.py` | 新增 | `--write` 由 blob 重算 `bytes`/`sha256`；`--check` 只校验（D-1） | 删文件即回退（无调用方依赖，除测试 helper 同源常量） |
| 3 | [scripts/spec/dc_validator.py](../../scripts/spec/dc_validator.py) | 改 | `check_links` 增 `tracked` 参数与 dc3「目标未入库」判定（D-2） | revert 该文件；21 处链接改写可独立保留 |
| 4 | `spec/**`（10 文件 21 处） | 改 | 未入库目标的链接改行内代码引用（D-2） | 逐文件 revert；改写不改变正文语义 |
| 5 | [.github/workflows/ci.yml](../../.github/workflows/ci.yml) | 改 | permissions/concurrency/timeout/cache/dispatch/actions 版本（D-4）；tests 改全量收集（D-5）；spec-gates 增 `ci_coverage_check --check`（I-6） | 单文件 revert；与分支保护解耦（保护只认检查名） |
| 6 | `scripts/spec/ci_coverage_check.py` | 新增 | 覆盖闭合双向守卫 + `--selftest`（D-5） | 删文件 + 摘钩子 |
| 7 | `tests/ci_exclusions.yaml` | 新增 | 排除登记表（唯一声明源），空表起步（D-5） | 删文件（守卫随之走「缺表 fail-closed」路径，需同时 revert 钩子） |
| 8 | [pyproject.toml](../../pyproject.toml) | 改 | `[tool.pytest.ini_options] markers` 注册 `heavy`（仅运行时开关） | revert 单段 |
| 9 | `.github/dependabot.yml` | 新增 | actions + pip，monthly 分组（D-6） | 删文件即停用 |
| 10 | [README.md](../../README.md) | 改 | 增 CI 徽章、移除静态用例计数徽章（D-6） | revert 徽章行 |
| 11 | [.pre-commit-config.yaml](../../.pre-commit-config.yaml) | 改 | 新增 `ci-coverage` 钩子（I-6 接线，DESIGN §3.2 内嵌要求 / O-2） | 摘钩子；脚本可保留 |

> 第 11 行不是新增设计面：DESIGN §3.2 第 6 行与 §8 I-6 明确要求脚本「同时接入 `.pre-commit-config.yaml` 与 spec-gates job」，此处只是把该要求落到文件行。

## 3. 模块实施

### 3.1 模块 1：`tests/test_vendor_auto_prover.py`（D-1）

#### 职责

vendored 字节溯源断言的对象从工作树改为 git blob（DESIGN §3.2 第 1 行）。

#### 接口签名

```python
def _blob_bytes(rel: str) -> bytes:
    """返回 `researchclaw/vendor/auto_prover/<rel>` 在 git index 中的原始字节。
    无 .git / 路径未入库 ⇒ pytest.skip（sdist 场景优雅降级，DESIGN §4.1 O-3）。"""

@pytest.mark.parametrize("entry", SOURCE["files"], ids=lambda item: item["path"])
def test_vendored_file_matches_sha256(entry): ...
```

#### 实施要点

- 保留 `test_upstream_pin_is_frozen`、`test_license_files_are_intact`、`test_apache_license_and_notice_present`、`test_declared_additions_and_modifications_exist`（另含 `test_excluded_modules_are_not_vendored`、`test_vendored_python_files_are_covered_by_source_json`，均不动）的现有语义；只改第 32-33 行两处字节断言（第 31 行 `is_file` 断言保留）。
- `bytes` 与 `sha256` 同时由 blob 判定（尺寸是同一事实的冗余表达，不能留工作树口径）。
- 模块级缓存 `_blob_bytes`（`functools.lru_cache` 或 dict）避免 27 次 `git cat-file` 子进程；一次 `git cat-file --batch` 可变现（低效排除见下）。
- 断言语义与 `vendor_source_sync.py --check` 共用同一实现（DESIGN §4.4「禁止手工编辑」）：测试直接 import 该模块的 `blob_facts()`，不复制算法。

#### 低效操作排除

| 潜在低效 | 排除措施 |
|---------|---------|
| 27 个参数化用例各起一个 `git` 子进程（27×fork） | 模块级一次性 `git cat-file --batch` 载入全部条目，测试只查内存表 |
| 测试与脚本各写一份 blob 读取/哈希逻辑（双实现漂移） | 单一实现 `vendor_source_sync.blob_facts()`，测试 import 复用 |

### 3.2 模块 2：`scripts/spec/vendor_source_sync.py`（D-1）

#### 职责

由 git blob 重算 SOURCE.json 的 `bytes`/`sha256`，并提供只读校验（DESIGN §3.2 第 2 行）。

#### 接口签名

```python
VENDOR_DIR = "researchclaw/vendor/auto_prover"
SOURCE_JSON = f"{VENDOR_DIR}/SOURCE.json"

def blob_facts(paths: list[str], root: Path = ROOT) -> dict[str, tuple[int, str]]:
    """{rel: (nbytes, sha256hex)}，一次性 `git cat-file --batch`；未入库路径不出现在结果中。"""

def diff_entries(source: dict, facts: dict[str, tuple[int, str]]) -> list[str]:
    """返回差异描述行（空列表 = 一致）；覆盖 files[] 与 license_files[]。"""

def main(argv=None) -> int:   # --write | --check（默认 --check）
```

#### 实施要点

- `--write`：`files[]` 重写 `bytes`/`sha256` 两字段；`license_files[]` 条目仅有 `sha256`（无 `bytes` 键），只重写 `sha256`；其余顶层键（`upstream`/`vendored_at`/`batch`/`root`/`file_count`/`added`/`modifications`/`excluded`/`verification`）保持原样，JSON 缩进沿用现有格式（2 空格），保证 diff 最小。
- `--check`：有不一致 ⇒ 打印逐条差异 + 固定文案「跑 `vendor_source_sync.py --write` 后提交」，退出 1；一致 ⇒ 退出 0。
- 未入库路径（`git ls-files` 不含）⇒ 视为 fail-closed 差异（blob 语义下不存在「未入库的 vendored 文件」）；不做 `git add -f` 兜底。
- `file_count` 与 `len(files)` 不一致同样判差异（DESIGN §4.4 元数据自洽）。
- 只读 git index（`:<path>`），不读工作树：`--write` 后必须 `git add` 才反映到提交（与 I-1 真值源一致）。

#### 低效操作排除

| 潜在低效 | 排除措施 |
|---------|---------|
| 每文件一次 `git cat-file`（27+ 子进程） | `git cat-file --batch` 单进程流式读取 |
| `--write` 全量重排 JSON 造成大 diff | 只改两字段、保留键序与缩进，diff 行数 = 差异条目数 |
| 重复读 SOURCE.json（校验 + 写回各一次） | 单次读入内存，写回前做一次等价比对 |

### 3.3 模块 3：`scripts/spec/dc_validator.py::check_links`（D-2）

#### 职责

档 1 相对链接除「可解析」外，增「目标在 git index 内」判定（DESIGN §4.1）。

#### 接口签名

```python
TRACKED: set[str] | None = None   # 进程级一次载入：{normpath(p) for p in git ls-files}

def check_links(file, text, root=ROOT, tracked: set[str] | None = None):
    """M5/DC3：档 1 相对链接——(1) 可解析；(2) 目标在 git index 内。"""
```

#### 实施要点

- `tracked=None`：有 `.git` 时一次 `git ls-files -z` 载入模块级缓存；无 `.git` ⇒ 空集 + 打印一行 skip 提示（DESIGN §4.1 O-3）。
- 新增判定只对**已可解析**的链接生效（不可解析仍走原 `档 1 相对链接不可解析` 文案），避免同一链接报两条。
- 文案固定：`档 1 相对链接目标未入库（CI 将判红）：<p>（修复：入库，或改为行内代码引用）`，`severity="P2"`，`id="dc3"`。
- `tracked` 参数向 `run_checks` 透传（默认 None 即自动载入），保持既有 9 个调用点零改动（默认值兼容；全仓计 1 处定义 + 9 处调用）。
- `run_selftest()` 追加用例（现有编号已用至 F33，顺延）：F34 未入库链接判 P2；F35 已入库链接不判；F36 无 `.git` 时空集 skip 不误红；F37 行内代码中的同名路径不参与判定（与 M5 既有排除上下文一致）。

#### 低效操作排除

| 潜在低效 | 排除措施 |
|---------|---------|
| 每个文件都跑一次 `git ls-files`（全仓 342 代码文件 × N） | 模块级缓存，进程内只载入一次 |
| 每条链接做一次 `git ls-files --error-unmatch`（数千子进程） | 集合成员判定 O(1) |
| 路径分隔符/大小写在 Windows 与 Linux 不一致导致误判 | 统一 `replace("\\","/")` + `normpath` 后比对（与 `_norm` 同口径） |

### 3.4 模块 4：`spec/**` 21 处链接改写（D-2）

#### 职责

把指向未入库目标的 21 处档 1 相对链接改为行内代码引用（DESIGN §3.2 第 4 行、§10.2 RI-5）。

#### 接口签名

无代码接口（文档改写）。判定接口 = `python scripts/spec/dc_validator.py --check-links` 退出 0。

#### 实施要点

- 以 DESIGN §2.1.1 的 21 处 / 10 文件 / 6 目标为基线；改写形态统一为 `` `docs/failure-guards-design.md` ``（保留原路径文本，可检索）。
- 只改链接语法，不改正文措辞与编号；同一行多处链接逐一改写。
- 验证方式：在**仅含已提交文件**的 detached worktree 中复跑 `dc_validator`，0 违规（RI-5）；本地全绿不算验收。
- 改写清单以 `--check-links` 的实时输出为准（不改写未被判红的链接）。

#### 低效操作排除

| 潜在低效 | 排除措施 |
|---------|---------|
| 全仓逐文件人工找 21 处（易漏、易误改模板） | 由 `--check-links` 输出驱动，仅改被判红行；模板目录本就不在判定面 |
| 改写后反复全仓全检查（每次数十秒） | 单次 `--check-links` 定向复跑，最后做一次 `--check-all` |

### 3.5 模块 5：`.github/workflows/ci.yml`（D-4 + D-5 + I-6）

#### 职责

workflow 硬化（permissions/concurrency/timeout/cache/dispatch/actions 版本）、测试改全量收集、spec-gates 增覆盖闭合校验（DESIGN §3.2 第 5 行）。

#### 接口签名

```yaml
on:
  push:
  pull_request:
  workflow_dispatch:            # D-4 新增
permissions:
  contents: read                # D-4：最小权限
concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true      # D-4：同分支连续 push 取消前序
jobs:
  packaging:  { runs-on: ubuntu-latest, timeout-minutes: 15, ... }
  extras:     { runs-on: ubuntu-latest, timeout-minutes: 15, ... }
  tests:      { runs-on: ubuntu-latest, timeout-minutes: 30, ... }
  roadmap-coverage: { runs-on: ubuntu-latest, timeout-minutes: 10, ... }
  spec-gates: { runs-on: ubuntu-latest, timeout-minutes: 20, ... }
```

#### 实施要点

- 每个 job 加 `timeout-minutes`（数值按现有 run 时长 38-55s 的 10 倍以上留余量，避免误杀）；`actions/checkout@v7`、`actions/setup-python@v7`（版本见 §2.2，E1 查证）。**不改 job `name:`**——7 个必需检查名依赖它们（DESIGN §3.4），改名等于分支保护失效。
- `setup-python` 增 `cache: pip`（缓存命中走 runner 本机缓存目录，不新增第三方 action）。
- tests job：把 L112-156 的 45 文件枚举替换为 `python -m pytest tests -m "not heavy" -q`；矩阵与 `continue-on-error: ${{ matrix.experimental || false }}` 保持不动（3.14 仍为实验位、不入必需集合）。
- spec-gates job：在 `Gate selftests` 增 `python scripts/spec/ci_coverage_check.py --selftest`；在 `Run all pre-commit gates` 之前增 `python scripts/spec/ci_coverage_check.py --check`（I-6：本地与 CI 同判）。
- `push`/`pull_request` 触发器与 `fetch-depth: 0` 不动（P-081 range 校验依赖祖先可见）。

#### 低效操作排除

| 潜在低效 | 排除措施 |
|---------|---------|
| 5 个 job 各自冷装依赖（重复下载） | `setup-python` 的 `cache: pip` 按 lock 指纹复用缓存 |
| 同分支连推时前序 run 继续占用 runner | `concurrency: cancel-in-progress: true` |
| 全量收集后单 job 串行跑 149 文件 | 矩阵 3 个稳定版本并行；不额外拆分目录（避免第二套失败面） |

### 3.6 模块 6：`scripts/spec/ci_coverage_check.py`（D-5）

#### 职责

以「唯一声明源」`tests/ci_exclusions.yaml` 为右集，校验测试覆盖双向闭合（DESIGN §4.2）。

#### 接口签名

```python
def load_left(root: Path = ROOT) -> set[str]:
    """L = git ls-files 匹配 tests/test_*.py（相对路径、正斜杠）。"""

def load_right(path: Path, root: Path = ROOT) -> set[str]:
    """R = ci_exclusions.yaml 的 exclusions[].path 集合（缺文件 ⇒ 抛错由 main fail-closed）。"""

def load_collected(root: Path = ROOT) -> set[str]:
    """C = `python -m pytest tests --collect-only -q` 解析出的实际测试文件集。"""

def closure_violations(L: set[str], R: set[str], C: set[str]) -> list[str]:
    """三条违规：R ⊄ L（死项）/ (L\\R) ⊄ C（未进 CI）/ marker 与登记不一致。"""

def main(argv=None) -> int:   # --check（默认）| --write | --selftest
```

#### 实施要点

- `--check`：`closure_violations` 为空 ⇒ 退出 0；否则逐条打印三类文案（DESIGN §7 第 3-5 行）并退出 1。
- `--write`：本批**不自动登记任何文件**（DESIGN §4.3「空表起步」）；仅校验 schema 并把 `version` 规范为 `1`，不产生 `exclusions` 条目（避免把 104 文件一次性写入）。
- schema 校验：`version: 1`、`exclusions` 为列表、每项五字段齐全且 `path` 在 L 内、`reason` 非空且不得为「跑得慢」类描述。字段缺失 ⇒ 退出 1。
- `heavy` marker 一致性：对每个登记项要求在 `C` 中出现（marker 只是运行时开关，O-4）——本批空表，该分支以 `--selftest` 覆盖。
- `--selftest`：用内存集合驱动 `closure_violations`，覆盖 C1 闭合 / C2 未进 CI / C3 死项 / C4 marker 不一致四类；不依赖真实 git 仓库（4 个断言）。
- `git` 不可用 / 非仓内目录 ⇒ 退出 1 并打印「非 git 工作树，覆盖闭合无法判定」。

#### 低效操作排除

| 潜在低效 | 排除措施 |
|---------|---------|
| `--collect-only` 在 149 文件上做完整 import（秒级） | 只在 `--check` 主路径执行一次；不按文件重复调用 |
| 每次校验都跑 pytest 子进程 | `--selftest` 与静默路径不触发 pytest；`--check` 单次执行 |
| 三个集合各自遍历比较（重复扫描） | 集合运算一次算三个差集 |

### 3.7 模块 7：`tests/ci_exclusions.yaml`（D-5）

#### 职责

排除登记表，唯一声明源（DESIGN §4.3）。

#### 接口签名

```yaml
version: 1
exclusions: []
```

#### 实施要点

- 空表起步（DESIGN §10.1 第 6 条）：**本批不登记任何现有文件**；`test_rc_docker_sandbox.py` 全 mocked 且在 45 个枚举文件内，**不得**作为 heavy 示例（DESIGN §4.3）。
- 五字段契约固定在文件头注释中（`path/reason/marker/owner/since`），首批登记项由 B2 的 `--collect-only` 盘点结果决定（U-5）。

#### 低效操作排除

| 潜在低效 | 排除措施 |
|---------|---------|
| 用 YAML 注释存放大段示例 → 解析成本与维护噪声 | 只留 schema 与 1 条注掉的占位形态 |

### 3.8 模块 8：`pyproject.toml`（D-5 运行时开关）

#### 职责

注册 `heavy` marker，使 `-m "not heavy"` 不产生 `PytestUnknownMarkWarning`（DESIGN §3.2 第 8 行）。

#### 接口签名

```toml
[tool.pytest.ini_options]
markers = ["heavy: 需真实外部环境，登记源为 tests/ci_exclusions.yaml（本标记仅为运行时开关）"]
```

#### 实施要点

- 只新增该段，不动 `[project]` / 依赖 / `[tool.hatch.build.targets.wheel]`。
- 不启用 `--strict-markers`（会改变既有用例的失败面，超出本批 D-5 范围）。

#### 低效操作排除

| 潜在低效 | 排除措施 |
|---------|---------|
| 为 marker 引入 pytest 插件 | 内置 ini 选项即可，零新增依赖 |

### 3.9 模块 9-10：`.github/dependabot.yml` 与 `README.md`（D-6）

#### 职责

依赖自动化（actions + pip，monthly 分组）与 CI 徽章单一真值（DESIGN §6.1）。

#### 接口签名

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

#### 实施要点

- 两个 ecosystem 均用 `groups: {<name>: {patterns: ["*"]}}`，monthly（DESIGN §6.1 选择理由：单维护者）。
- README：删除 L27 的静态徽章 `Tests-2699 passed`（I-4 单一真值），替换为指向本 workflow 的 CI 状态徽章（`.../actions/workflows/ci.yml/badge.svg?branch=main`）；其余徽章不动。
- 徽章 URL 只引用真实存在的 workflow 文件名 `ci.yml`（不新建 badge 服务）。

#### 低效操作排除

| 潜在低效 | 排除措施 |
|---------|---------|
| weekly 逐条依赖 PR 淹没单人维护 | monthly + 全量分组（1 个 actions PR + 1 个 python PR/月） |
| 徽章指向第三方服务 | 直接用 GitHub 原生 badge 端点，零外部依赖 |

### 3.10 模块 11：`.pre-commit-config.yaml` 接线（I-6）

#### 职责

让覆盖闭合守卫在本地与 CI 同判（DESIGN §8 I-6）。

#### 接口签名

```yaml
- id: ci-coverage
  name: CI test coverage closure guard
  entry: python scripts/spec/ci_coverage_check.py --check
  language: system
  pass_filenames: false
  files: ^(tests/test_.*\.py|tests/ci_exclusions\.yaml|\.github/workflows/ci\.yml)$
```

#### 实施要点

- 新增钩子放在「额外守卫」段（不属于 A0-1 六必需；`repo-stats`/`step-enforce` 实际位于六必需段），与 `private-config` / `code-agent-wiring` / `rework-graph` 并列，避免改变六必需钩子的既有语义声明。
- `pass_filenames: false`：守卫自行枚举 `git ls-files`，不依赖 staged 子集（否则「新增测试文件但未登记」在只改 test 文件时可能漏判——实际会命中 files 正则，但仍以全量枚举为准）。
- 与 spec-gates job 的两处 entry 保持**逐字符一致**，防止本地/CI 分别演化。

#### 低效操作排除

| 潜在低效 | 排除措施 |
|---------|---------|
| 每次 commit 都跑 `--collect-only`（秒级） | 仅在命中 `files` 正则时运行；改动无关路径不触发 |
| 本地与 CI 两套 entry 漂移 | 两处 entry 字符串一致，由 §9.3 对齐项检查 |

## 4. 接口实施

### 4.1 `dc_validator.check_links`

```python
TRACKED: set[str] | None = None   # 进程级一次载入：{normpath(p) for p in git ls-files}

def check_links(file, text, root=ROOT, tracked: set[str] | None = None):
    """M5/DC3：档 1 相对链接——(1) 可解析；(2) 目标在 git index 内。

    tracked=None：有 .git 时自动 `git ls-files` 载入一次（模块级缓存）；
                  sdist / 无 .git 场景置空集并打印一行 skip 提示。
    """
```

**签名一致性**: 与 DESIGN.md §4.1 一致 ✅（实现位置：[dc_validator.py](../../scripts/spec/dc_validator.py) L352 `check_links`）

**回退点**：删除 `tracked` 判定分支即可恢复 v1.0 语义；21 处链接改写不依赖本改动。

### 4.2 `vendor_source_sync.py` CLI

```
python scripts/spec/vendor_source_sync.py --check   # 0 一致 / 1 有差异
python scripts/spec/vendor_source_sync.py --write   # 重算校验和字段（files[]: bytes/sha256；license_files[]: 仅 sha256）
```

**签名一致性**: DESIGN §4 未单列本脚本签名，本文件按 DESIGN §3.2（`--write`/`--check`）与 §4.4（blob 语义）定义；**与 DESIGN §3.2/§4.4 一致 ✅**（属实施层补全，登记为 derived-requirement，见 §9.3）。

**回退点**：删文件；测试 helper 改为本地读取实现（需同步改 §3.1 的 import）。

### 4.3 `ci_coverage_check.py` CLI

```
python scripts/spec/ci_coverage_check.py [--check|--write|--selftest]
退出码：0 闭合；1 存在未登记差异 / schema 违规 / 非 git 工作树（fail-closed）
```

双向闭合：`L = git ls-files tests/test_*.py`、`R = ci_exclusions.yaml` 的 `path` 集，要求 `R ⊆ L` 且 `L \ R ⊆ C`（C = `--collect-only` 实际文件集）。

**签名一致性**: 与 DESIGN.md §4.2 一致 ✅（多出 `--selftest` 为内嵌自测，不改变判据面）

**回退点**：删文件 + 摘 `.pre-commit-config.yaml` 与 ci.yml 两处 entry。

### 4.4 `tests/test_vendor_auto_prover.py::_blob_bytes`

```python
def _blob_bytes(rel: str) -> bytes: ...
```

**签名一致性**: 测试内部 helper，非 DESIGN §4 契约；其判据（blob 原始字节）与 DESIGN §4.4 一致 ✅。

**回退点**：该 helper 与其调用点同文件，单文件 revert。

## 5. 兼容性

### 5.1 Python 版本兼容

| Python 版本 | 支持 | 说明 |
|------------|------|------|
| 3.11 | ✅ | `requires-python` 下限；本批只用 3.11 可用 stdlib |
| 3.12 / 3.13 | ✅ | CI 必需矩阵 |
| 3.14 | ⚠️ 实验 | `continue-on-error`，不入必需检查（DESIGN §3.4 / U-6） |
| 3.10 及以下 | ❌ | 不在 `requires-python` 内，不承诺 |

### 5.2 依赖兼容

| 依赖组合 | 兼容性 | 验证 |
|---------|--------|------|
| stdlib 脚本 + 无 `.git`（sdist 安装后运行） | ✅ | `check_links` 空集 skip；`vendor_source_sync`/`ci_coverage_check` 仅门禁侧调用，不进 wheel |
| PyYAML 6.0.3 + `yaml.safe_load` | ✅ | 本机实测版本；`ci_exclusions.yaml` 只用基础类型 |
| `setup-python@v7` + `cache: pip` + 现有 `.[dev]` 依赖 | ✅ | action 原生能力，无需额外 action |
| pytest 8.3.4 + `-m "not heavy"`（marker 已注册） | ✅ | `[tool.pytest.ini_options]` 注册后无 unknown marker 警告 |

### 5.3 向后兼容

- **行为变更（有意）**：tests job 从 45 文件枚举改为全量收集后，此前从未在 CI 跑的 104 个测试文件进入失败面——这是 D-5 的目的，风险由 RI-1 三分法消化；不提供「回退到枚举」的配置开关（避免双真值源）。
- **语义变更（有意）**：SOURCE.json 的 `bytes`/`sha256` 由「本地工作树」改为「git blob」；旧值经 `--write` 一次性重算（DESIGN §4.4）。工作树 CRLF 不参与、不清理（U-4：清理不作为提交内容）。
- **不变**：5 个 job 的 `name:`、触发器 `push`/`pull_request`、矩阵版本、`fetch-depth: 0`、`continue-on-error` 语义——分支保护的 7 个必需检查名因此保持有效。
- **门禁 hook id 不变**：既有 9 个钩子 id 与 entry 不改；只新增第 10 个（`ci-coverage`）。

## 6. 错误处理实施

### 6.1 错误场景与处理

| 错误场景（来自 DESIGN.md §7） | 异常类型 | 处理代码 | 测试 |
|------------------------------|---------|---------|------|
| 链接目标未入库 | 非异常（`CheckResult("dc3", …, "P2", …)`） | `dc_validator.check_links` tracked 分支 | `dc_validator.py --selftest` F34/F35 |
| SOURCE.json 与 blob 不符 | `pytest.fail`（`AssertionError`） | `tests/test_vendor_auto_prover.py::test_vendored_file_matches_sha256` + `vendor_source_sync --check` | 同文件参数化 27 例（先红 12 例，见 §8.2） |
| 测试文件新增但未进 CI | `SystemExit(1)` | `ci_coverage_check.main` → `closure_violations` 第 2 类 | `ci_coverage_check --selftest` C2 |
| 登记项指向已删文件 | `SystemExit(1)` | `closure_violations` 第 1 类（`R ⊄ L`） | `--selftest` C3 |
| 登记项缺 marker / 有 marker 未登记 | `SystemExit(1)` | `closure_violations` 第 3 类 | `--selftest` C4 |
| git 不可用（sdist 场景） | 无异常：`skip` + 一行提示 | `check_links` 空集分支；`_blob_bytes` 调 `pytest.skip` | F36（tracked skip）；`_blob_bytes` 的 skip 分支 |

原则落地：每条文案都在 DESIGN §7 的给定句式上补「下一步动作」（如「跑 `vendor_source_sync.py --write`」「删除该登记」），不做静默降级。

## 7. 不变式实施

| 不变式（来自 DESIGN.md §8） | 实施位置 | 验证方式 |
|---------------------------|---------|---------|
| I-1 入库真值 | `dc_validator.check_links` tracked 分支 | `--selftest` F34/F35 + detached worktree 复跑 0 违规 |
| I-2 可重现元数据 | `vendor_source_sync.blob_facts`（单一实现，测试复用） | `--check` 退出 0；测试 27 例全绿 |
| I-3 覆盖闭合 | `ci_coverage_check.closure_violations` | `--check` 退出 0 + `--selftest` 三类违规可判 |
| I-4 单一真值 | README 徽章替换（删静态 `Tests-2699`） | 人工核对 README 无「未经 CI 实测」的数字徽章 |
| I-5 红即阻断 | §10 Step 5 runbook（7 必需名 / `enforce_admins=true` / 3.14 不入集） | 分支保护 API 读回（`gh api .../branches/main/protection`）逐字段核对 |
| I-6 本地=CI | `.pre-commit-config.yaml` 的 `ci-coverage` 钩子 + spec-gates job 同 entry | 两处 entry 字符串一致；`pre-commit run ci-coverage` 与 job 内命令同判 |

## 8. 测试策略

### 8.1 单元测试

| 模块 | 测试文件 | 测试数 | 覆盖率目标 |
|------|---------|--------|----------|
| `check_links` tracked 判定 | `scripts/spec/dc_validator.py --selftest`（F34-F37） | 4 | 不设覆盖率门（D-8 显式不实施） |
| `closure_violations` 三类违规 | `scripts/spec/ci_coverage_check.py --selftest`（C1-C4） | 4 | 同上 |
| vendored blob 断言 | [tests/test_vendor_auto_prover.py](../../tests/test_vendor_auto_prover.py)（既有 7 个测试函数，其中 blob 断言参数化 27 + 许可文件参数化） | 既有 + 0 新增 | 同上 |

> 本批不新增 `tests/test_*.py` 文件：DESIGN §3.2 未列入新测试模块，新增会扩张 CI 覆盖面并触发新登记义务；validator 与守卫的自测走各自 `--selftest`（既有惯例：`grandfather_gate.py --selftest`、`dc_validator.py --selftest`）。

### 8.2 集成测试

1. **先红（B1 步骤 1-2）**：改断言前在本地 CRLF 工作树跑 `pytest tests/test_vendor_auto_prover.py -q` ⇒ 预期 12 failed / 15 passed（与 CI 12 条失败同名）；`vendor_source_sync --write` 后转 27 passed。
2. **先红（B1 步骤 3-4）**：加 tracked 判定后，在 **detached worktree（仅已提交文件）** 中对 hook 作用域（`spec/**` + `docs/PROGRESS.md` + `docs/CONSOLE.md`）跑 `dc_validator --check-links` ⇒ 预期 21 P2；改写 21 处后 0 违规。**口径说明**：本地工作树因 6 个目标文件恰在磁盘上，同一命令读数为 0，不可作为先红判据；无参 `--check-links` 扫全仓 md（含域外 docs 与未入库本地笔记），与本批无关，亦不可作为判据。
3. **先红（B2 步骤 8）**：`ci_coverage_check --check` ⇒ 预期 exit 1（104 文件未进 C）；ci.yml 改全量收集后再跑 ⇒ exit 0。
4. **端到端**：`pre-commit run --all-files`（10 钩子全过）→ push → CI 连续两次全绿 → 按 Step 5 开保护 → 用一次故意违反（临时改坏一个链接）的 PR 验证红即阻断，随后 revert。
5. **轮子面不回归**：`python -m pytest tests/test_packaging.py -q` 必须保持绿（本批不碰 `[tool.hatch.build.targets.wheel]`）。

### 8.3 属性测试（如适用）

对覆盖闭合做集合性质断言（`--selftest` 内实现，不引入 hypothesis）：

- `R ⊆ L` 且 `L \ R ⊆ C` ⇒ `closure_violations` 返回空（闭合方向）；
- 从 `L` 移除一个未登记文件 ⇒ 必报第 2 类（漏纳方向）；
- 向 `R` 加入一个不存在路径 ⇒ 必报第 1 类（死项方向）；
- `R` 与 `C` 的 marker 集合不一致 ⇒ 必报第 3 类（声明源与开关同向）。

## 9. 幻觉抑制审查（Step 6 Review）

### 9.1 依赖版本验证

- [x] 所有依赖版本已查询 PyPI 确认存在 —— 零新增三方依赖；`pytest 8.3.4` / `PyYAML 6.0.3` 本机实测，pin 未变
- [x] 无虚构的库或函数 —— 仅 stdlib + 既有 PyYAML；未引用任何未安装模块
- [x] 版本兼容性已验证 —— action 版本经 `gh api …/releases/latest` 查得（checkout `v7.0.1`、setup-python `v7.1.0`）
- [x] stdlib API 下限检查 —— 全部 API 在 3.11 可用（§2.2），未使用 3.12+ API

### 9.2 接口签名验证

- [x] 所有接口签名与 DESIGN.md §4 一致 —— §4.1 签名块逐字符一致（TRACKED 行尾注已补齐）；§4.2 CLI 一致；§4.3/§4.4 属实施层补全并已在 §4.2 显式登记
- [x] 所有签名可实现 —— `tracked` 默认参数向后兼容（既有 9 调用点零改动）；集合判定无类型矛盾

### 9.3 实施与设计对齐

- [x] 每个模块对应 DESIGN.md §3.2 的一个模块 —— §3.1↔第1行、§3.2↔第2行、§3.3/§3.4↔第3-4行、§3.5↔第5行、§3.6/§3.7↔第6-7行、§3.8↔第8行、§3.9↔第9-10行、§3.10↔第6行内嵌的 I-6 接线
- [x] 每个接口对应 DESIGN.md §4 的一个接口 —— §4.1↔§4.1、§4.3↔§4.2、§4.2↔§3.2+§4.4
- [x] 无设计未覆盖的实施 —— **derived-requirement 三项**：① `vendor_source_sync.py` 的 CLI 形态（DESIGN 只给 `--write`/`--check` 语义、未给签名）；② `ci_coverage_check --write` 的「不自动登记、仅校验 schema 并把 `version` 规范为 `1`」语义（DESIGN §4.2 只列 `[--check|--write]`、未定义写行为）；③ 两处 `--selftest`。均由本文件 §4.2/§4.3 显式声明，不构成新增设计面

### 9.4 低效操作排除

- [x] 无 O(n²) 可优化为 O(n log n) 的操作 —— blob 读取改 `--batch` 单进程；链接/覆盖判定改集合成员 O(1)
- [x] 无不必要的 I/O —— `git ls-files` 进程级一次；`SOURCE.json` 单读单写；`--collect-only` 单次
- [x] 无重复计算 —— blob 哈希/闭合判定各自单一实现，测试与脚本复用同一函数

> 本 §9 前四组为实施文档**自审**；独立异构复审已于本批执行（登记见 §9.5），复审订正后升版 v1.1 并转 `verified`。

### 9.5 独立复审登记（v1.0 → v1.1，2026-11-14）

独立上下文子代理证伪式复审，25 项逐项核对（行号/版本/计数/存在性/结构/内部一致性），结论 **PASS-with-fixes**：7 缺陷 + 4 观察，全部处置如下：

| 编号 | 缺陷（v1.0 声明 → 实测） | 订正 |
|------|------------------------|------|
| W-1 | 自测编号 F22-F25 → `run_selftest` 现有编号已用至 F33 | 顺延为 F34-F37 |
| W-2 | 「license_files[] 重写 bytes/sha256 两字段」→ license_files 条目仅有 sha256（无 bytes 键） | files[] 重写 bytes/sha256；license_files[] 仅 sha256 |
| W-3 | check_links「既有 12 个调用点」→ 全仓 1 处定义 + 9 处调用 | 12 → 9 |
| W-4 | 「既有 5 个测试函数」→ 实测 7 个（另两个不在 blob 断言范围） | 5 → 7 |
| W-5 | §1「5 个改文件」与 §2.3 表（改 7 / 新增 4）矛盾，漏计 dependabot 配置 | 改 7 / 新增 4 |
| W-6 | 「第 29-33 行两处断言」→ 函数体 3 处断言（L31 is_file / L32 st_size / L33 sha256） | 「第 32-33 行两处字节断言（L31 is_file 保留）」 |
| W-7 | 新钩子「与 repo-stats / step-enforce 并列」→ 二者实际位于 A0-1 六必需段 | 「与 private-config / code-agent-wiring / rework-graph 并列」 |

观察：O-1 枚举行号 L111-157 → L112-156（已订正）；O-2 §4.1 TRACKED 行缺尾注（已补齐，现与 DESIGN §4.1 逐字符一致）；O-3 §2.2/§2.3 内容形态与模板存在良性偏差（不改文）；O-4 上游 DESIGN §4.1 多写返回注解 `-> list[CheckResult]`（真实源码无）→ **已由 DESIGN v1.3 删除该注解，本项关闭**（见 §9.6）。

复审确认成立的关键实测：Python 3.13.5 / pytest 8.3.4 / PyYAML 6.0.3 / git 2.53.0.windows.2 / checkout v7.0.1 / setup-python v7.1.0（gh api 两次成功）；`git ls-files "tests/test_*.py"` = 149；README L27 恰为 `Tests-2699 passed` 静态徽章；pyproject 无既有 `[tool.pytest.ini_options]`；tests/test_packaging.py 存在；.gitattributes 含 vendor `-text`；pre-commit 现状 9 钩子且无 ci-coverage。

### 9.6 四文档一致性审计登记（v1.1 → v1.2，2026-11-14，P-111）

Step 8（文档一致性）+ Step 10（ADD）交叉审计，四文档逐项复算 + 命令实跑，本文件承载 3 项订正：

| 编号 | 缺陷（原文 → 实测） | 订正 |
|------|-------------------|------|
| A-2(P2) | Step 3/Step 4/§8.2-2 以无参 `dc_validator --check-links` 为「先红 21 / 后绿 0」判据 → 无参实跑 = **64 P2**（`clawsgo-*.md`/`dsh-*.md` 等未入库本地笔记 + 域外 `docs/*.md`），且改写 spec 链接后这些读数不变，判据**永不归零**；21/10/6 仅在 detached worktree 的 hook 作用域内成立 | 三处统一改为「detached worktree（仅已提交文件）+ hook 作用域（`spec/**` + `docs/{PROGRESS,CONSOLE}.md`）」，并显式声明本地工作树与无参命令不可作判据 |
| A-3(P3) | §3.6 `--selftest` 只列「闭合/死项/未进 CI 三类」→ 与 §8.1「C1-C4 四例」、§6.1「第 3 类 marker」矛盾 | 改为「C1 闭合 / C2 未进 CI / C3 死项 / C4 marker 不一致四类（4 个断言）」 |
| A-6(P3) | §9.3 的 derived-requirement 清单漏 `ci_coverage_check --write` 语义（§4.3 已定义、DESIGN §4.2 未定义） | 升为「三项」并逐项列明 |

观察 A-1（DESIGN §4.1 返回注解失真）本批由 DESIGN v1.3 订正，本文件 §9.5 O-4 随之关闭。CONFIRM（本轮独立复现）：21 处 / 10 文件 / 6 目标的文件级精确复算；DESIGN §3.2 十行 ↔ 本文件 §2.3 十一行；7 必需检查名；I-1..I-6 ↔ §7；DESIGN §7 六行 ↔ §6.1 六行。

## 10. 实施步骤

### Step 1: 建立 blob 事实源（B1 / D-1）

- 文件：`scripts/spec/vendor_source_sync.py`（新增）
- 内容：`blob_facts()` 用一次 `git cat-file --batch` 读取 27 条 + 许可条目；`diff_entries()` 比对 `bytes`/`sha256`/`file_count`；`--check` exit 1 + 差异清单，`--write` 只改校验和字段（files[] 为 bytes/sha256，license_files[] 仅 sha256）并保留缩进与键序
- 测试：`python scripts/spec/vendor_source_sync.py --check` ⇒ 先红（12 条差异，与 DESIGN §2.1.1 同名）；`--write` 后 ⇒ 0

### Step 2: 断言改锚 blob（B1 / D-1）

- 文件：[tests/test_vendor_auto_prover.py](../../tests/test_vendor_auto_prover.py)
- 内容：`_blob_bytes` 复用 `vendor_source_sync.blob_facts`；第 32-33 行两处断言改 blob；无 `.git` 走 `pytest.skip`
- 测试：`pytest tests/test_vendor_auto_prover.py -q` ⇒ 改前 12 failed → 改后 27 passed；本地 CRLF 工作树与 CI clean checkout 同判

### Step 3: 加 tracked 链接校验（B1 / D-2）

- 文件：[scripts/spec/dc_validator.py](../../scripts/spec/dc_validator.py)
- 内容：`TRACKED` 模块级缓存 + `check_links(..., tracked=None)` + 新 dc3 文案；`run_selftest` 加 F34-F37
- 测试：`python scripts/spec/dc_validator.py --selftest` 全 PASS；`--check-links` 在 detached worktree 的 hook 作用域内 ⇒ 先红 21 条 P2（本地工作树/无参全仓扫描不作判据，见 §8.2-2 口径说明）

### Step 4: 改写 21 处未入库链接（B1 / D-2）

- 文件：`spec/**` 10 文件 21 处（以 Step 3 输出为准）
- 内容：链接改行内代码引用，保留原路径文本；不动正文措辞
- 测试：detached worktree 的 hook 作用域内 `--check-links` ⇒ 0；本地全绿不算验收

### Step 5: 分支保护 runbook（B1 / D-3）

- 文件：无代码改动；执行留痕写入 `docs/PROGRESS.md` 的 P-109 行
- 内容：在 **CI 连续两次全绿后**执行——`Require a pull request before merging = true`、`required_approving_review_count = 0`、`enforce_admins = true`、必需检查 = 7 个具体名（`Packaging / wheel smoke`、`Extras import`、`Tests (3.11)`、`Tests (3.12)`、`Tests (3.13)`、`Roadmap coverage gates`、`Spec gates (pre-commit all-files)`）；`Tests (3.14)` 不入集
- 测试：`gh api repos/<owner>/<repo>/branches/main/protection` 读回逐字段核对；一次故意违规 PR 验证阻断后 revert

### Step 6: workflow 硬化（B2 / D-4）

- 文件：[.github/workflows/ci.yml](../../.github/workflows/ci.yml)
- 内容：`workflow_dispatch`、`permissions: contents: read`、`concurrency`（取消前序）、5 个 job 的 `timeout-minutes`、`cache: pip`、`checkout@v7` / `setup-python@v7`；**不改 job `name:`**
- 测试：一次 push 观察同分支连推是否取消前序 run；缓存命中日志；CI 两次绿

### Step 7: 登记表与 marker（B2 / D-5）

- 文件：`tests/ci_exclusions.yaml`（新增）、[pyproject.toml](../../pyproject.toml)
- 内容：空表 `version: 1` + 五字段注释契约；`[tool.pytest.ini_options] markers = ["heavy: …"]`
- 测试：`pytest tests -m "not heavy" --collect-only -q` 无 unknown marker 警告；空表可被 `yaml.safe_load` 解析

### Step 8: 覆盖闭合守卫与接线（B2 / D-5 + I-6）

- 文件：`scripts/spec/ci_coverage_check.py`（新增）、[.pre-commit-config.yaml](../../.pre-commit-config.yaml)、[.github/workflows/ci.yml](../../.github/workflows/ci.yml)
- 内容：`load_left/load_right/load_collected/closure_violations` + `--selftest`；tests job 改 `pytest tests -m "not heavy" -q`；spec-gates 加 `--selftest` 与 `--check`；pre-commit 加 `ci-coverage` 钩子（entry 与 job 逐字符一致）
- 测试：`--selftest` 4 例 PASS；`--check` 先红（104 未进 C）→ 全量收集后 0；`pre-commit run ci-coverage --all-files` 与 CI job 同判

### Step 9: 依赖自动化与徽章（B2 / D-6）

- 文件：`.github/dependabot.yml`（新增）、[README.md](../../README.md)
- 内容：两 ecosystem monthly 分组；删静态 `Tests-2699` 徽章，加 `ci.yml` 状态徽章
- 测试：Dependabot 首个分组 PR 出现（观察项）；徽章 URL 可解析且指向真实 workflow

### Step 10: 派生视图与门禁收口

- 文件：`docs/REPO_STATS.md`、`docs/CONSOLE.md`、`docs/PROGRESS.md`
- 内容：`python scripts/spec/repo_stats.py --write` 同步计数；`console_gen.py` 刷新；P-109 行记录实施读数
- 测试：`repo_stats.py --check`、`grandfather_gate.py`、`step_enforce.py`、`pre-commit run --all-files` 全绿；CI 连续两次绿后执行 Step 5

---

**Review 签字**: _________ 日期: _________
