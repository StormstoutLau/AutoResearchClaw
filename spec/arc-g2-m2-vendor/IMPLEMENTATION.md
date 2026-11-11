---
id: arc-g2-m2-vendor-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g2-m2-vendor-DESIGN]
upstream: arc-g2-m2-vendor-DESIGN
---

# 实施记录：G2 M2 判定内核 vendor

## 1. 改动清单

| 文件 | 类型 | 内容 |
|---|---|---|
| `researchclaw/vendor/__init__.py` | 新增 | ARC 包标记（MIT） |
| `researchclaw/vendor/auto_prover/` | 新增 | 27 个内核文件（Apache-2.0）+ `LICENSE`/`NOTICE` |
| `researchclaw/vendor/auto_prover/README.md` | 新增 | 边界、合规、升级与校验 |
| `researchclaw/vendor/auto_prover/THIRD_PARTY_NOTICES.md` | 新增 | 血统结论与运行时依赖 |
| `researchclaw/vendor/auto_prover/SOURCE.json` | 新增 | commit、逐文件 sha256、新增/修改/排除清单 |
| `researchclaw/vendor/auto_prover/__init__.py` | 新增 | 包标记（Apache-2.0） |
| `researchclaw/vendor/auto_prover/{kg,stages}/__init__.py` | 替换 | 最小包标记，避免导入 sidecar/Lean |
| `tests/test_vendor_d110_verdict_policy.py` | 新增 | 23 项（迁入） |
| `tests/test_vendor_d110_verdict_recheck.py` | 新增 | 3 项（迁入） |
| `tests/test_vendor_semantic_verdict.py` | 新增 | 39 项（迁入） |
| `tests/test_vendor_auto_prover.py` | 新增 | 34 项完整性/许可断言 |
| `spec/arc-g2-m2-vendor/testset-arc-3.11.txt` | 新增 | ARC 侧 65 项冻结 node ID |
| `.gitattributes` | 新增 | `researchclaw/vendor/auto_prover/** -text`，禁止 EOL 转换，保证 sha256 跨平台 |
| `.github/workflows/ci.yml` | 修改 | 4 个测试入清单；wheel 断言 LICENSE/NOTICE |

## 2. 关键实现

- **零改写相对导入**：`datatypes/verdict/sandbox/kg/stages` 与两个顶层模块同处 `auto_prover/`，原 `from ..datatypes import` 等不变。
- **测试只需换前缀**：`proof_pipeline.` → `researchclaw.vendor.auto_prover.`；recheck 的脚本路径指向 vendor 目录。
- **包 `__init__` 最小化**：上游 `kg/__init__.py` 会导入 `kg_importer`/`kg_writeback`，`stages/__init__.py` 会导入 Lean/ATLAS 阶段；替换为空包后，3.11 内核不触 sidecar。
- **逐字节校验**：复制后用脚本比对上游字节；27 个文件全部一致才写入 `SOURCE.json`。
- **D173 随行**：vendor 的 `sandbox/evaluator.py` 已含 `sys._base_executable` + `PYTHONPATH` 修复（I-9）。

## 3. 测试结果

| 环境 | 命令 | 读数 |
|---|---|---|
| 3.13.5 | `pytest tests/test_vendor_auto_prover.py tests/test_vendor_d110_verdict_policy.py tests/test_vendor_d110_verdict_recheck.py tests/test_vendor_semantic_verdict.py -q` | **99 passed**（65 + 34） |
| 3.11.15 | 同上 | **99 passed** |
| 3.11.15 | 按 `testset-arc-3.11.txt` 的 65 个 node ID 逐项执行 | **65 passed**（0.58s） |
| wheel | `python -m build --wheel` + 检查 namelist | `researchclaw-0.5.0`；`vendor/auto_prover/LICENSE` 与 `NOTICE` 均在包内 |

65 项分布：23（policy）+ 3（recheck）+ 39（semantic），与 AP 冻结清单逐文件计数一致。

## 4. 与设计的偏差

| # | 偏差 | 原因 |
|---|---|---|
| D-1 | vendor 由 16 文件扩为 **27 文件** | 65 项测试的完整依赖闭包；只 vendor 三包会 61/65（[RESEARCH](RESEARCH.md) §3） |
| D-2 | `kg/__init__.py`、`stages/__init__.py` 为替换而非原文 | 原 `__init__` 会拉入 sidecar/Lean；已在 `SOURCE.json` 登记并加修改声明 |
| D-3 | 测试文件重命名为 `test_vendor_*` | 与 ARC 自有测试区分；函数名与断言不变 |
| D-4 | `researchclaw/vendor/__init__.py` 为 MIT | 仅 ARC 包标记，不含 vendor 代码；目录内代码仍 Apache-2.0 |

## 5. 未执行

- sidecar / Lean（M3）；
- 上游 vendor 同步机制（U-2，手工复制 + sha256 暂用）；
- `hitl/claim_verifier.py` 改为消费 `ClaimRecord`（P-042 F-8 的后续迁移，不属 M2 DoD）。
