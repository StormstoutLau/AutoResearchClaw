---
id: arc-g0b-implementation-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g0b-implementation-DESIGN]
upstream: arc-g0b-implementation-DESIGN
---

# 实施记录：G0b 完整治理基座

> 基于 [DESIGN.md](DESIGN.md) v1.0。按 S-1 + T-1 + H-1 + 独立策略层执行。

## 1. 执行顺序

| # | 步骤 | 命令/动作 |
|---|---|---|
| S-1 | 迁移六个治理脚本 | `git mv scripts/<name>.py scripts/spec/<name>.py` |
| S-2 | 修 ROOT 与同目录 import | 编辑 5 个 ROOT；`sys.path` 保持不变 |
| S-3 | 建六个兼容壳 | `scripts/<name>.py` = runpy 转发 |
| S-4 | 新增策略层 | `scripts/spec/grandfather_gate.py` |
| S-5 | 新增 grandfather 清单 | `spec/grandfather.yaml`（空 entries） |
| S-6 | 新增三道门禁 | `scripts/spec/{m7_stats,repo_stats,blackbox_check}.py` |
| S-7 | 迁移 SPEC_PROCESS | `git mv SPEC_PROCESS.md spec/SPEC_PROCESS.md` + 链接重写 + 根指针 |
| S-8 | 更新钩子组成 | `.pre-commit-config.yaml` 9 道 |
| S-9 | 新增 CI job | `.github/workflows/ci.yml` → `spec-gates` |

## 2. 脚本迁移与 ROOT 修正

| 脚本 | 原 ROOT | 新 ROOT |
|---|---|---|
| `dc_validator.py` | `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` | 外层再包一层 `os.path.dirname(...)` |
| `roadmap_coverage_check.py` | 同上 | 同上 |
| `step_enforce.py` | `Path(__file__).resolve().parents[1]` | `parents[2]` |
| `console_gen.py` | `Path(__file__).resolve().parents[1]` | `parents[2]` |
| `rework_graph_check.py` | `Path(__file__).resolve().parent.parent` | `parents[2]` |
| `spec_map.py` | 无 | 不变 |

`console_gen.py` / `step_enforce.py` 的 `sys.path.insert(0, Path(__file__).resolve().parent)` **保持不变**：真身与 `spec_map` 同在 `scripts/spec/`。

## 3. 兼容壳

六个壳逐字同构，只替换目标名：

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""兼容壳：转发到 scripts/spec/<name>.py（P-021 T-1）。真身唯一。"""
import os
import runpy
import sys

_TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spec", "<name>.py")
sys.path.insert(0, os.path.dirname(_TARGET))
sys.argv[0] = _TARGET
runpy.run_path(_TARGET, run_name="__main__")
```

## 4. `grandfather_gate.py`

### 4.1 结构

| 函数 | 职责 |
|---|---|
| `load_policy(path)` | 解析 YAML，校验 schema，返回 `(cfg, errors)` |
| `validate(cfg, root, md_files)` | 逐条校验 path 存在/重复/作用域、check_ids、日期上限、renewals |
| `filter_results(results, cfg)` | 按 `(file, check_id)` 与 `expires` 过滤 |
| `main(argv)` | 组装：files → `dc_validator.run_checks` → filter → 输出 → exit |

### 4.2 退出码

| 码 | 含义 |
|---|---|
| 0 | 无违规（含全部被合法豁免） |
| 1 | 存在违规（含过期豁免） |
| 2 | 策略文件非法 / 文件缺失 / 工具错误 |

### 4.3 关键实现约束

- 不 import 第三方 YAML 库以外的依赖；使用仓内已依赖的 `yaml`。
- 日期比较用 `datetime.date`，`today` 由 `date.today()` 取（确定性边界：同一天内稳定）。
- `--selftest` 内置 5 条 fixture（空清单/合法/过期/越界/非法 check_id），不依赖工作树。

## 5. SPEC_PROCESS 迁移的链接处理

| 原目标 | 新写法 |
|---|---|
| `docs/M7_EVIDENCE_LOG.md` | `../docs/M7_EVIDENCE_LOG.md` |
| `docs/ASSERTION_EVIDENCE_FRAMEWORK.md` | `../docs/ASSERTION_EVIDENCE_FRAMEWORK.md` |
| `spec/templates/*` | `templates/*` |
| `adr/ADR-0007...` / `adr/ADR-0008...` / `adr/ADR-0009...` | 文本前缀 `源项目·`（ARC 无 `adr/` 目录） |
| `spec/academic-writing-workflow/*` | 文本前缀 `源项目·` |
| `spec/stage-tooling-contract/*` | 文本前缀 `源项目·` |
| `spec/project-console/RESEARCH.md` | 文本前缀 `源项目·` |
| `docs/discoveries/` | 文本前缀 `源项目·` |

## 6. 负向用例（固化 A0-2..A0-5 + Q3-F4）

以临时目录 + `tempfile` 构造，不写入工作树：

| 用例 | 构造 | 期望 |
|---|---|---|
| T-1 | 新 `.md` 删除 `status:`，无豁免 | `grandfather_gate` exit 1（dc1） |
| T-2 | session 缺 `verify` 直接 finalize | `step-gate --expect ...` exit 1 |
| T-3 | verify 后改正文 | `step_enforce` digest 不匹配 → exit 1 |
| T-4 | 手改 `docs/CONSOLE.md` | `console_gen --check` exit 1 |
| T-5 | 作用域外文件 + 空 entries | `grandfathered=0`，exit 0，条目不被消耗 |
| T-6 | 过期 entry | 缺字段文件仍红，`expired=1` |
| T-7 | 非法 check_ids（含 `dc4`） | exit 2 |

T-2/T-3/T-4 复用既有机制，本轮以脚本化断言记录结果；T-1/T-5/T-6/T-7 由 `grandfather_gate --selftest` 覆盖。

## 7. 结果

### 7.1 交付物

| 交付物 | 状态 | 备注 |
|---|---|---|
| `spec/SPEC_PROCESS.md` | 完成 | v1.7.1 正文；28 链接重写（6 条路径重写 + 22 条 `源项目·` 档 2 标注） |
| 根 `SPEC_PROCESS.md` | 完成 | 指针，无规则内容 |
| `scripts/spec/` 10 个脚本 | 完成 | 6 迁移 + 4 新增 |
| 6 个根兼容壳 | 完成 | runpy 转发，零逻辑 |
| `spec/grandfather.yaml` | 完成 | `entries: []`、cutoff 2026-11-10、90 天（E3） |
| `.pre-commit-config.yaml` | 完成 | 6 必需 + 3 额外守卫 |
| CI `spec-gates` job | 完成 | 与 3.11–3.13 矩阵并行 |

### 7.2 `dc_validator` 改动面

与迁移前对比仅 3 处：ROOT 上移一级、ROOT 注释更新、文件首 BOM 去除。**检查逻辑（M2-M6）零改动**，I-1..I-6 保持。

### 7.3 负向用例

| 用例 | 命令 | 结果 |
|---|---|---|
| T-1 缺 `status` 无豁免 | `grandfather_gate --selftest` F1 | PASS（exit 1） |
| T-2 缺 verify 的 4 步 session | 隔离 repo `step-gate --expect` 5 步 | PASS（exit 1） |
| T-3 verify 后改正文 | 隔离 repo `step_enforce --base HEAD` | PASS（exit 1，digest 不匹配） |
| T-4 手改 CONSOLE | `console_gen --check` | PASS（exit 1）；重生成后 exit 0 |
| T-5/T-6/T-7 | `--selftest` F4a/F3/F5 | PASS |
| 全 selftest | `grandfather_gate --selftest` | **11/11 PASS** |

隔离夹具（T-2/T-3）建在系统临时目录的独立 git 仓库中：P-200 批 + 5/5 session + `--doc-digest` 生成的 digest；验证后销毁，不触碰工作树。

### 7.4 门禁结果

| 门禁 | 结果 |
|---|---|
| `pre-commit run --all-files` | **9/9 Passed**（dc/m7/repo/step/console/blackbox + private/code-agent/rework） |
| `step_enforce --base HEAD` | exit 0 |
| `console_gen --check` | 一致 |
| `roadmap_coverage_check --check` | accept=106 suite=70 declared=37 missing=0 |
| `repo_stats --check` | 一致（280/84158/118/41789/21） |
| `m7_stats` | samples=0，结构有效 |
| `blackbox_check` | module=ok(0.2s)，console=skip（未安装） |
| `step-gate` P-021 | 5/5 pass |
| 既有 pytest 子集 | 无测试引用被迁移脚本路径，零回归 |

### 7.5 计划偏差

| # | 计划 | 实际 | 原因 |
|---|---|---|---|
| D-1 | `adr/` 链接重写为 `../adr/` | 改标 `源项目·` | 双重根因：① ARC 无 `adr/` 目录（RESEARCH G-3），`../adr/` 会指向仓库外；② 迁移前根 `SPEC_PROCESS.md` 不在 dc-validator hook 作用域（旧正则 `^(spec/.*\.md|docs/(PROGRESS|CONSOLE)\.md)$`），断链从未显形，迁移后才首次受 DC3 审查——P-017 制定时低估了这一点 |
| D-2 | blackbox 两条命令都强制 | 控制台脚本条件执行 | 本机 `shutil.which("researchclaw")` = None（RESEARCH G-8）。覆盖实为**双层**：CI packaging（wheel 安装后 `researchclaw --help`）+ CI spec-gates（`pip install -e ".[dev]"` 会生成 console script，blackbox 的 console 断言在 CI 中**实际执行**而非 skip）——本地宽松、CI 严格，方向正确 |
| D-3 | 无 | `grandfather_gate` 无参默认按 DC 作用域取文件 | 初版 `gather_md_files()` 误扫全仓（`.claude/`、`external/` 等 126 条伪违规）。修正后经等价性验证：全仓 229 个 `.md` 中 89 个在作用域，`_in_dc_scope` 与 hook 正则逐文件 diff = none |
| D-4 | DESIGN 称条目 path 不得落在作用域外 → exit 2 | 一致 | 与 F-4「作用域外不消耗条目」不矛盾：后者指未登记时 |
| D-5 | RESEARCH §6.2 原稿「源缺失 exit 1」 | DESIGN §5.2 与实现均 exit 2 | 独立复核（本节 D-1..D-4 同轮）发现的文档失谐；fail-closed 口径以 DESIGN/实现为准，RESEARCH 已订正并标注 |
