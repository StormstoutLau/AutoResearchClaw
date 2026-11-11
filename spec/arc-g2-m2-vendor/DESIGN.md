---
id: arc-g2-m2-vendor-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g2-m2-vendor-RESEARCH]
upstream: arc-g2-m2-vendor-RESEARCH
---

# 设计：G2 M2 判定内核 vendor

> 基于 [RESEARCH.md](RESEARCH.md)。目标：65 项在 ARC 3.11 全绿，许可四件套完整，vendor 可逐字节核验。

## 1. 目录与边界

```
researchclaw/vendor/
  __init__.py                        # ARC 包标记（MIT）
  auto_prover/                       # 以下全部 Apache-2.0
    LICENSE  NOTICE                  # AP 原文，逐字节
    README.md  THIRD_PARTY_NOTICES.md  SOURCE.json
    __init__.py                      # 新增包标记
    datatypes/    9 文件
    verdict/      3 文件
    sandbox/      4 文件
    semantic_verdict.py
    model_gateway.py
    kg/           i2_extractor / unified_cases / verdict_writer + __init__
    stages/       stage2_numerical + 4 个数值辅助 + __init__
    scripts/      verdict_recheck.py
```

**纳入判据**：65 项冻结测试的 import 闭包（含运行时相对导入）。**排除**：`kg_importer`/`kg_writeback`/`verdict_store`、`stage0/1/1.5/3/3.5`、`mcp_servers`、`atlas_bridge`、`lean4_cases`、AP 的 `spec/`/`docs/`。

## 2. 许可边界（V-1..V-6 对照）

| 规则 | 本批落实 |
|---|---|
| V-1 按文件保持 Apache-2.0 | `auto_prover/` 下所有 `.py` 与 `LICENSE`/`NOTICE` 均为 Apache-2.0；ARC 其余仍 MIT；`vendor/__init__.py` 为 MIT 包标记 |
| V-2 分发携带 LICENSE/NOTICE | 两文件随包目录；CI packaging job 断言 wheel 中存在这两个路径 |
| V-3 修改声明 | `kg/__init__.py`、`stages/__init__.py` 头部带 `# Modified by AutoResearchClaw on 2026-11-11: ...`；新增 `__init__.py` 带 SPDX 标记 |
| V-4 版权主体与来源 commit | `NOTICE` 原文保留 `Copyright 2026 Aiming Lab`；`SOURCE.json` 记录 `bd95f02` 与逐文件 sha256 |
| V-5 只复制代码 | 未复制 AP `spec/`/`docs/`；README/THIRD_PARTY_NOTICES 为 ARC 自写 |
| V-6 升级流程 | README §3；升级须更新 `SOURCE.json`、重算 sha256、重跑 65 项与完整性测试 |

## 3. 迁移策略

- **保留包内相对导入**：`datatypes`、`verdict`、`sandbox`、`kg`、`stages` 与 `semantic_verdict.py`、`model_gateway.py` 同处 `auto_prover` 下，`from ..datatypes import ...` 等无需改写。
- **测试改写**：3 份测试只替换顶层导入前缀 `proof_pipeline.` → `researchclaw.vendor.auto_prover.`；`test_vendor_d110_verdict_recheck.py` 的脚本路径改为 `<repo>/researchclaw/vendor/auto_prover/scripts/verdict_recheck.py`。
- **包 `__init__` 替换**：`kg/` 与 `stages/` 使用最小 `__init__`，只导出空包，防止 `kg_importer`/Lean 阶段被导入。
- **测试重命名**：`test_vendor_<原名>`，便于与 ARC 自有测试区分；测试函数名与断言不变。

## 4. `SOURCE.json` 契约

| 字段 | 内容 |
|---|---|
| `upstream` | name/url/version=3.7.0/commit=`bd95f02`/commit_subject/license/copyright |
| `vendored_at` / `batch` | `2026-11-11` / `P-049 / G2 M2` |
| `files[]` | 27 项：`path`、`source`、`bytes`、`sha256` |
| `license_files[]` | `LICENSE`、`NOTICE` 的 sha256 |
| `added[]` / `modifications[]` | 新增包标记与两处最小 `__init__` 替换 |
| `excluded[]` | 明确不 vendor 的路径（审计面） |
| `verification` | 65 项与执行命令 |

生成方式：复制后用脚本比对上游字节并计算 sha256；**任何不一致即中止**（本批实际执行）。

## 5. 完整性测试

`tests/test_vendor_auto_prover.py`：

1. `upstream` 固定值（版本 3.7.0、commit `bd95f02`、Apache-2.0）；
2. 27 个文件的 size + sha256 与 `SOURCE.json` 一致；
3. `LICENSE`/`NOTICE` sha256 一致，文本包含 Apache 2.0 与 Aiming Lab；
4. `added`/`modifications` 均有对应文件，修改文件带修改声明；
5. 排除清单中的模块不存在；
6. 目录内所有 `.py` 均被 `SOURCE.json` 覆盖（无未登记文件）。

## 6. A2-3 验收

- **主集**：3 份 vendor 测试 → 65 项（23 + 3 + 39）。
- **冻结**：`spec/arc-g2-m2-vendor/testset-arc-3.11.txt` 由 `--collect-only -q` 生成，含解释器/依赖版本与 AP→ARC 文件映射。
- **执行**：按 node ID 逐项跑（不是按文件名），3.11.15 与 3.13.5 双环境。
- **回归**：CI 固定清单新增 4 个测试文件；packaging job 新增两个许可路径断言。

## 7. 风险

| 风险 | 缓解 |
|---|---|
| 上游文件被修改但 sha256 未更新 | 完整性测试逐文件比对；`kg/stages` 修改显式登记 |
| Windows/Linux 换行转换导致 sha256 漂移 | `.gitattributes` 对 `researchclaw/vendor/auto_prover/**` 设 `-text`，checkout 不做 EOL 转换 |
| 新 `__init__` 意外拉入 sidecar | 完整性测试断言 `kg_importer` 等不存在；65 项在 3.11 实跑 |
| wheel 漏带 LICENSE/NOTICE | CI packaging job 断言路径存在 |
| 测试重命名导致冻结集失配 | `SOURCE.json` 与 `testset-arc-3.11.txt` 记录映射与计数 |
