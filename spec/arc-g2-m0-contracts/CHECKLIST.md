---
id: arc-g2-m0-contracts-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-11
depends: [arc-g2-m0-contracts-IMPLEMENTATION]
upstream: arc-g2-m0-contracts-IMPLEMENTATION
---

# 验收清单：G2 M0 契约 v1

## 1. M0 DoD（R-03 §5.2）

- [x] `C1–C7` 共 7 份 JSON Schema 落盘（`contracts/v1/`）
- [x] 每份 schema 有正例/反例 fixture（7 正 + 8 反）
- [x] `RunEnvelope` 反例：含 `verdict` ⇒ 校验失败
- [x] `ClaimRecord` 反例：缺 `claim_class` 或 `status` 不在 6+1 档 ⇒ 失败
- [x] 兼容矩阵写清 Python 3.11/3.12/3.13、MCP v2、Lean 可选（`contracts/README.md` §2）
- [x] 6 钩子可跑：G0b 交付的 6 必需钩子在 P-046 提交时全绿（本批未改钩子）

## 2. A2-1

- [x] 契约 JSON Schema + fixture 全通过（7 个 schema）
- [x] 负向：缺 `claim_class` 必须失败（`missing_claim_class.json` + 定点断言）
- [x] 反例只改一个变量，失败可归因
- [x] C4 `evidence[]` 通过 `$ref` 复用 C5，无字段复制

## 3. 不变式

- [x] 契约不表达「产出方自评」：C1 顶层封闭且禁止 `verdict`
- [x] 门禁必须有反例：C3 `pre_red_fixture` 必填
- [x] 证据无定位/摘要不得计为已验证：C5 `locator`/`digest` 必填
- [x] `ClaimRecord.status` 词表与 AP `CitationLabel` 对齐（lowercase + `speculation`）
- [x] `policy_version` 必填，防止跨策略比较
- [x] 跨文件引用离线解析，无网络依赖

## 4. 机检

- [x] `python -m pytest tests/test_contracts_v1.py -q` → 34 passed（3.13.5）
- [x] 同一命令在 3.11.15 venv → 34 passed
- [x] `jsonschema>=4.20` 进入 `dev` extra，CI tests 矩阵安装 `.[dev,server,mcp]`
- [x] `tests/test_contracts_v1.py` 加入 CI 固定清单
- [x] 9 道 pre-commit 门禁全绿；`roadmap_coverage_check.py` accept=106 missing=0

## 5. 未纳入本批

- [ ] AR-01..08 判据实现与 16 fixture（M1）
- [ ] 3.11 内核 vendor（M2）
- [ ] sidecar / Lean 可选（M3）
- [ ] `RunEnvelope` ↔ `run_state` 机械对齐（U-1）
