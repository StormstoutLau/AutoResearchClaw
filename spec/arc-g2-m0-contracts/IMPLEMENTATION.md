---
id: arc-g2-m0-contracts-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g2-m0-contracts-DESIGN]
upstream: arc-g2-m0-contracts-DESIGN
---

# 实施记录：G2 M0 契约 v1

## 1. 改动清单

| 文件 | 类型 | 内容 |
|---|---|---|
| `contracts/README.md` | 新增 | 版本 v1.0.0、兼容矩阵、破坏性变更政策、校验入口 |
| `contracts/v1/c1_run_envelope.schema.json` | 新增 | C1；顶层封闭，禁止 `verdict` |
| `contracts/v1/c2_task_contract.schema.json` | 新增 | C2；`accept[]` ≥1，golden 固化 |
| `contracts/v1/c3_gate_result.schema.json` | 新增 | C3；`pre_red_fixture` 必填 |
| `contracts/v1/c4_claim_record.schema.json` | 新增 | C4；R-03 §3.2 的 16 字段，`evidence[]` 复用 C5 |
| `contracts/v1/c5_evidence_ref.schema.json` | 新增 | C5；`snapshot ⇒ readonly=true` |
| `contracts/v1/c6_model_role.schema.json` | 新增 | C6；角色/后端/敏感度枚举 |
| `contracts/v1/c7_derived_view.schema.json` | 新增 | C7；真值源与 `check_cmd` |
| `contracts/v1/fixtures/**` | 新增 | 7 正例 + 8 反例（含 A2-1 指定反例） |
| `tests/test_contracts_v1.py` | 新增 | 8 个测试函数，参数化后 34 项 |
| `pyproject.toml` | 修改 | `dev` extra 增 `jsonschema>=4.20` |
| `.github/workflows/ci.yml` | 修改 | 契约测试加入 tests 矩阵的固定清单 |

## 2. 关键实现

- **离线 `$ref`**：C4 的 `evidence[]` 指向 `urn:arc:contracts:v1:evidence_ref`；测试用 `referencing.Registry` 预注册 7 份 schema，校验时不发起网络请求。
- **红线用 schema 表达**：
  - C1 顶层 `additionalProperties: false` ⇒ `verdict` 键直接失败；
  - C4 `required` 含 `claim_class`；`status` 为 7 值枚举；
  - C5 `allOf` 条件：`kind=snapshot` ⇒ `readonly` 必填且为 `true`；
  - C4 `claim_type=confirmatory` ⇒ `stats_protocol` 必须为非空对象。
- **状态词表**：C4 `status` 的 7 个 lowercase 值与 AP `CitationLabel` 6 值 + `speculation` 对齐；`policy_version` 必填（AP 当前为 2）。
- **测试归因**：反例不只断言「失败」，而是断言错误落在预期字段（`$.status`、`$.readonly`、`claim_class` 缺失消息、`verdict` 未声明消息）。

## 3. 测试结果

| 环境 | 命令 | 读数 |
|---|---|---|
| 3.13.5（全局） | `python -m pytest tests/test_contracts_v1.py -q` | **34 passed**（0.22s） |
| 3.11.15（`%TEMP%\arc-ap-py311`，`jsonschema 4.26` + `referencing 0.37`） | 同上 | **34 passed**（0.71s） |

测试结构：

| 测试 | 项数 | 覆盖 |
|---|---|---|
| `test_schema_set_is_frozen` | 1 | 7 份文件与 7 个 `$id` 一一对应 |
| `test_schema_is_valid` | 7 | `check_schema` |
| `test_each_contract_has_positive_and_negative_fixture` | 7 | 每份契约正/反例齐备 |
| `test_fixture_classification` | 15 | 正例全过、反例全败 |
| 红线定点 | 4 | `verdict` / `claim_class` / `status` / `snapshot.readonly` |

## 4. 与设计的偏差

| # | 偏差 | 原因 |
|---|---|---|
| D-1 | `contracts/v1` 未放入 wheel（`hatch` 只打包 `researchclaw`） | M0 只要求仓内契约与测试；运行时分发在 M1 之后另行决定 |
| D-2 | C4 未含 `producer_model` / `independent_checks` | 与 [DESIGN](DESIGN.md) §2.4 的映射一致：由 C1/C5 承担 |
| D-3 | `quote` 的「≤3 行」未写成 `pattern` | 语义判据归 AR-01（M1）；schema 只约束类型，避免误伤合法引文 |

## 5. 未执行

- AR-01..08 判据、`can_enter_deliverables` 等谓词（M1/G2 后续验收）；
- vendor 3.11 内核（M2）；
- `RunEnvelope` 与 ARC `run_state` 的机械对齐用例（U-1，M1 接线时）。
