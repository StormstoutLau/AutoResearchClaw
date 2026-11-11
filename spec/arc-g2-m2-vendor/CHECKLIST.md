---
id: arc-g2-m2-vendor-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-11
depends: [arc-g2-m2-vendor-IMPLEMENTATION]
upstream: arc-g2-m2-vendor-IMPLEMENTATION
---

# 验收清单：G2 M2 判定内核 vendor

## 1. M2 DoD / A2-3

- [x] 3.11 内核子集 vendor 到 `researchclaw/vendor/auto_prover/`（27 文件闭包）
- [x] 65 项判定测试迁入 ARC，函数名与断言不变
- [x] ARC 3.11.15 按冻结 node ID 逐项执行 → 65 passed
- [x] 3.13.5 同一集合 → 65 passed（vendor 全量 99 passed）
- [x] ARC 侧冻结清单 `spec/arc-g2-m2-vendor/testset-arc-3.11.txt`
- [x] CI 固定清单接入 4 个测试文件

## 2. Vendor 合规（V-1..V-6）

- [x] V-1 `auto_prover/` 按文件 Apache-2.0；ARC 其余 MIT
- [x] V-2 `LICENSE`/`NOTICE` 随目录；wheel namelist 实测包含两路径
- [x] V-3 修改文件带 `# Modified by AutoResearchClaw on 2026-11-11: ...`
- [x] V-4 `NOTICE` 保留 `Copyright 2026 Aiming Lab`；`SOURCE.json` 记录 `bd95f02`
- [x] V-5 未复制 AP `spec/`/`docs/`
- [x] V-6 升级流程写入 README；`SOURCE.json` 含逐文件 sha256

## 3. 完整性

- [x] 27 个文件 size + sha256 与 `SOURCE.json` 一致
- [x] `LICENSE`/`NOTICE` sha256 一致
- [x] 排除模块（`kg_importer`/`kg_writeback`/`verdict_store`/Lean stages/`mcp_servers`/`atlas_bridge`）不存在
- [x] 目录内所有 `.py` 均被 `SOURCE.json` 的 `files` 或 `added` 覆盖
- [x] `kg/`、`stages/` 的最小 `__init__` 不导入 sidecar/Lean

## 4. 机检

- [x] `pytest tests/test_vendor_auto_prover.py ...` → 99 passed（3.13.5）
- [x] 同一命令 → 99 passed（3.11.15）
- [x] 冻结 65 node ID → 65 passed（3.11.15）
- [x] `python -m build --wheel` 成功；`LICENSE`/`NOTICE` 在包内
- [x] 9 道 pre-commit 门禁全绿；`roadmap_coverage_check.py` accept=106 missing=0

## 5. 未纳入本批

- [ ] 3.12 sidecar / JSON 契约（M3）
- [ ] Lean 可选 Tier-3（M3）
- [ ] AP 上游同步机制（U-2）
- [ ] `hitl/claim_verifier.py` 消费 `ClaimRecord`（后续迁移）
