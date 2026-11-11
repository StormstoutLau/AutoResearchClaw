# Contracts v1（G2 M0）

> 状态：**frozen**（2026-11-11，P-047）｜版本：**v1.0.0**｜方言：JSON Schema 2020-12
> 真值源：[R-02 §6.3](../academic-reasoning-base-fusion.md)（七契约字段清单）与 [R-03 §3.2](../arb-v2-decisions-research-design.md)（`ClaimRecord v1`）。

## 1. 契约清单

| # | 文件 | `$id` | 核心约束 |
|---|---|---|---|
| C1 | `v1/c1_run_envelope.schema.json` | `urn:arc:contracts:v1:run_envelope` | 顶层封闭；**禁止 `verdict`** |
| C2 | `v1/c2_task_contract.schema.json` | `urn:arc:contracts:v1:task_contract` | `accept[]` ≥1；判据与 golden 派发时固化 |
| C3 | `v1/c3_gate_result.schema.json` | `urn:arc:contracts:v1:gate_result` | `pre_red_fixture` 必填 |
| C4 | `v1/c4_claim_record.schema.json` | `urn:arc:contracts:v1:claim_record` | `claim_class` 必填；`status` 7 值；`evidence[]` 复用 C5 |
| C5 | `v1/c5_evidence_ref.schema.json` | `urn:arc:contracts:v1:evidence_ref` | `kind=snapshot ⇒ readonly=true` |
| C6 | `v1/c6_model_role.schema.json` | `urn:arc:contracts:v1:model_role` | `role/backend/sensitivity` 枚举 |
| C7 | `v1/c7_derived_view.schema.json` | `urn:arc:contracts:v1:derived_view` | `source_of_truth[]` ≥1；`check_cmd` 必填 |

`claim_record.status` 的 7 个值 = AP `CitationLabel` 的 6 个小写值 + `speculation`；`policy_version` 必填（当前 AP 为 `2`）。

## 2. 兼容矩阵

| 维度 | v1 兼容范围 | 说明 |
|---|---|---|
| Python | 3.11 / 3.12 / 3.13 | 契约本身无运行时依赖；校验仅在测试面使用 `jsonschema` |
| MCP | v2（仅宿主） | 契约不涉及 MCP 传输；sidecar（M3）经 JSON 复用 |
| Lean | 可选 Tier-3 | 无 Lean 时 `ClaimRecord.verification_depth=stage2`，契约不要求形式化 |
| 校验器 | `jsonschema>=4.20`（dev extra） | 通过 `referencing.Registry` 离线解析跨文件 `$ref` |

## 3. 版本与破坏性变更

- 目录 `contracts/v1/` 与 `$id` 中的 `v1` 同源；版本号遵循 SemVer 2.0.0。
- **minor**：新增可选字段、扩展现有枚举的取值（若消费方全部按字符串处理）。
- **major**：改必填、改类型、删除字段、收紧枚举。做法是新建 `contracts/v2/`，v1 保留只读。
- 任何契约变更必须同步 `fixtures/` 与 `tests/test_contracts_v1.py`，并更新本文件的版本号。

## 4. 校验

```powershell
python -m pytest tests/test_contracts_v1.py -q
```

测试覆盖：

1. 7 份 schema 存在且通过 `check_schema`；
2. 每份契约至少有 1 个 `valid/` 与 1 个 `invalid/` fixture；
3. 全部 `valid/` 通过、全部 `invalid/` 失败；
4. 红线定点复验：C1 `verdict`、C4 缺 `claim_class`、C4 非法 `status`、C5 `snapshot` 未声明 `readonly`。

## 5. 非目标

- AR-01..08 的语义判据（M1）不在此实现；契约只约束**形态**。
- `producer_model` / `independent_checks` 不在 C4 顶层：前者由 C1 承载，后者由 C5 的 `independent` 承载。
