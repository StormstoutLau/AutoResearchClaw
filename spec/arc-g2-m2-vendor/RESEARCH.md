---
id: arc-g2-m2-vendor-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g2-decisions, arc-g2-py311-env, arc-g2-m1-ar-checks]
upstream: arc-g2-decisions
---

# 调研：G2 M2 判定内核 vendor

> **Feature**：P-049，G2 里程碑 M2。
> **Spec 步骤**：T1 完整管线（Layer-1：新增 `researchclaw/vendor/`、`tests/` 与 CI 断言）。
> **结论先行**：最小内核的**真实边界**不是 R-03 的三包 16 文件，而是 **65 项冻结测试的依赖闭包 27 文件**——额外需要 `semantic_verdict`、`model_gateway`、`kg` 3 个模块、`stages` 5 个数值模块与 `scripts/verdict_recheck.py`。闭包只依赖 stdlib + numpy；D173 的 venv 启动器修复随 `bd95f02` 一并进入；ARC 3.11 下按冻结清单 **65 passed**。

## 1. 问题与边界

R-03 §5.2 的 M2 DoD 是「3.11 内核子集 vendor（policy/sandbox/ledger）→ 65 项判定测试迁入 ARC 并绿」；总纲对应验收是 **A2-3**（[总纲 §4 G2](../../arc-master-roadmap.md)）。合规要求由 P-043 §8 冻结（[P-042 §8](../arc-g2-decisions/RESEARCH.md)）：`LICENSE` + `NOTICE` + 修改声明 + `SOURCE.json`，vendor 目录按文件保持 Apache-2.0。本批要回答：

1. 65 项测试的**完整依赖闭包**是什么，是否仍在「最小内核」边界内；
2. 如何在不改上游语义的前提下迁入 ARC（包路径、相对导入、脚本路径）；
3. 如何证明 vendor 未被篡改、许可未被覆盖；
4. A2-3 如何在 ARC 3.11 下复跑并留痕。

**不在本批**：sidecar（M3）、Lean（Tier-3）、AP 的 `stages/lean*`、`mcp_servers`、`kg` 导入/写回、ATLAS。

## 2. 本仓与上游一手事实（F）

| # | 事实 | 证据 |
|---|---|---|
| F-1 | M2 DoD = 65 项判定测试迁入 ARC 并绿；测试集已在 G2 开工时冻结 | [R-03 §5.2](../../arb-v2-decisions-research-design.md)；[testset-3.11.txt](../arc-g2-py311-env/testset-3.11.txt) |
| F-2 | 冻结集拆分：`test_d110_verdict_policy` 23 + `test_d110_verdict_recheck` 3 + `test_semantic_verdict` 39 = **65** | 冻结清单按文件分组 |
| F-3 | 只复制 datatypes/verdict/sandbox 三包时，65 项中 **4 项失败**：2 项缺 `proof_pipeline.kg`，2 项缺 `proof_pipeline.stages` | 本批探针（临时目录，65 → 61 passed/4 failed） |
| F-4 | 补齐闭包后 65 项全绿；闭包共 **27 个内核文件**：datatypes 9、verdict 3、sandbox 4、semantic_verdict 1、model_gateway 1、kg 3、stages 5、scripts 1 | 本批探针 + `SOURCE.json` |
| F-5 | 闭包的外部依赖只有 **stdlib + numpy**；不含 Lean、MCP、httpx、fastapi、pydantic | 逐文件 import 扫描 |
| F-6 | AP 的 `kg/__init__.py` 会导入 `kg_importer`/`kg_writeback`，`stages/__init__.py` 会导入 Lean/ATLAS 阶段；直接复制会把 sidecar 拉进 3.11 内核 | AP 源码读码 |
| F-7 | `test_d110_verdict_recheck.py` 通过文件路径加载 `scripts/verdict_recheck.py`（stdlib 脚本），不是包导入 | 测试读码 |
| F-8 | `test_semantic_verdict` 的 2 项集成用例使用 `NumericalVerifier.__new__` + mock gateway，不触真实 LLM/Lean | 测试读码 |
| F-9 | AP 在 `bd95f02` 已含 D173（`sys._base_executable` + `PYTHONPATH`）；vendor 该 commit 即满足 I-9 | AP 提交；[P-045](../arc-g2-py311-env/RESEARCH.md) |
| F-10 | ARC 已有 numpy 运行时依赖；`researchclaw/vendor/` 为新增命名空间，与 M0/M1 无冲突 | `pyproject.toml`；本批清点 |

## 3. 边界裁定

**最小内核 = 65 项测试的依赖闭包**，而不是「三个包」的字面清单。理由：

- R-03 的 M2 DoD 以 65 项为验收真值源；只 vendor 三包会使 4 项集成用例不可运行，M2 不成立；
- 新增的 8 个模块均为纯判定/数值代码，无 Lean/MCP/网络依赖，仍在 Q2「最小 vendor + 3.11 进程内」边界内；
- 反向排除 `kg_importer`/`kg_writeback`/`verdict_store`、`stage0/1/3/3.5`、`mcp_servers`、`atlas_bridge`，避免把 sidecar 拉进内核。

该裁定写入 [DESIGN](DESIGN.md) §1；P-043 §8.1 的目录结构由本批扩展为 `kg/ stages/ scripts/` 三个子目录，许可边界不变。

## 4. 外部锚点（S）

| # | 来源 | 关键读数 | 等级 |
|---|---|---|---|
| S-1 | [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) | §4(a) 分发须附许可证；§4(b) 修改文件须带显著修改声明；§4(d) 须保留 NOTICE | T1 标准 |
| S-2 | [Python · The import system](https://docs.python.org/3/reference/import.html) | 包内相对导入按包层级解析；保持 `datatypes`/`verdict`/`sandbox` 同级即可零改动复用 | T1 官方文档 |
| S-3 | [pytest · `--collect-only`](https://docs.pytest.org/en/stable/how-to/usage.html) | node ID 可直接作为验收选择器，避免按文件名模糊计数 | T1 官方文档 |
| S-4 | [hatchling · Build configuration](https://hatch.pypa.io/latest/config/build/) | wheel 默认包含包目录内的非 Python 文件；`LICENSE`/`NOTICE` 可随包分发 | T1 官方文档 |

## 5. 方案对比

判据（非补偿）：

- **V-1**：65 项在 ARC 3.11 全绿；
- **V-2**：许可四件套完整，vendor 文件可逐字节核验；
- **V-3**：不把 Lean/MCP/sidecar 拉进 3.11 内核；
- **V-4**：迁移不改变测试语义（同一断言、同一 fixture）。

| 方案 | V-1 | V-2 | V-3 | V-4 | 结论 |
|---|---|---|---|---|---|
| **A. vendor 依赖闭包（27 文件）** | ✅ | ✅ | ✅ | ✅ | **采纳** |
| B. 只 vendor datatypes/verdict/sandbox | ❌ 61/65 | ✅ | ✅ | ✅ | 淘汰：M2 DoD 不成立 |
| C. 完整 vendor `proof_pipeline` | ✅ | ✅ | ❌ 拉入 Lean/MCP | ✅ | 淘汰：违 Q2 边界 |
| D. 保留 AP 为 sidecar，ARC 只跑 61 项 | ❌ | ✅ | ✅ | ❌ 改变验收集 | 淘汰：A2-3 失真 |
| E. 改写 4 项集成用例以去掉 kg/stages | ✅ | ✅ | ✅ | ❌ | 淘汰：冻结集不可改 |

## 6. 未决（四元块）

| # | 判据 | 触发条件 | 当前倾向 | 证据等级 |
|---|---|---|---|---|
| U-1 | `semantic_verdict`/`stages` 闭包是否需要长期留在 3.11 内核 | M3 sidecar 接线后，若这些模块仅在 sidecar 使用 | 暂留：65 项验收依赖；M3 时重评并可能迁出 | E2（本批） |
| U-2 | vendor 同步机制（手工复制 vs subtree） | 上游第二次修改被 vendor 的文件 | 当前手工复制 + `SOURCE.json` sha256；累计 ≥3 次后评估 subtree | E3（设计判断） |
| U-3 | wheel 内 `LICENSE`/`NOTICE` 的路径是否需再加根级副本 | 发布审阅要求根级许可清单 | 先保持 vendor 目录内；CI packaging job 断言其存在 | E1（CI 配置） |

## 7. 引用

1. 仓内：[R-03](../../arb-v2-decisions-research-design.md)、[总纲 G2](../../arc-master-roadmap.md)、[P-042 §8](../arc-g2-decisions/RESEARCH.md)、[P-046 冻结清单](../arc-g2-py311-env/testset-3.11.txt)、`researchclaw/vendor/auto_prover/SOURCE.json`。
2. 外部：S-1..S-4（§4 表，URL 已解析）。
