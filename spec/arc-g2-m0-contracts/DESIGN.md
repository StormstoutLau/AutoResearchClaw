---
id: arc-g2-m0-contracts-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g2-m0-contracts-RESEARCH]
upstream: arc-g2-m0-contracts-RESEARCH
---

# 设计：G2 M0 契约 v1

> 基于 [RESEARCH.md](RESEARCH.md)。目标：7 份 JSON Schema + 正反 fixture + 兼容矩阵，全部可离线机械校验。

## 1. 交付结构

| 路径 | 职责 |
|---|---|
| `contracts/README.md` | 版本、兼容矩阵、破坏性变更政策、校验入口 |
| `contracts/v1/*.schema.json` | 7 份契约（2020-12，URN `$id`） |
| `contracts/v1/fixtures/<contract>/valid/*.json` | 每份 ≥1 正例 |
| `contracts/v1/fixtures/<contract>/invalid/*.json` | 每份 ≥1 反例（含 A2-1 指定反例） |
| `tests/test_contracts_v1.py` | schema 自检、fixture 全通过、红线定点复验 |
| `pyproject.toml`（dev） | `jsonschema>=4.20` |
| `.github/workflows/ci.yml` | 契约测试加入既有 tests 矩阵 |

文件名固定为 `c1_run_envelope` … `c7_derived_view`，`$id` 为 `urn:arc:contracts:v1:<name>`。

## 2. 七份契约

### 2.1 C1 `RunEnvelope`

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `run_id` | string | ✅ | 非空 |
| `attempt` | integer | ✅ | ≥1 |
| `inputs_digest` | string | ✅ | `^sha256:[0-9a-f]{64}$` |
| `artifact` | object | — | `digest` + `size`（≥0）均必填 |
| `exit_code` | integer | ✅ | 无枚举（由退出码契约解释） |
| `status` | string | ✅ | `running/succeeded/failed/timeout/cancelled` |
| `usage` | object | ✅ | 值为非负数；键由调用方扩展 |

**红线**：顶层 `additionalProperties: false` ⇒ 出现 `verdict` 即失败（产出方不自评）。

### 2.2 C2 `TaskContract`

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `task_id` / `task_desc` | string | ✅ | 非空 |
| `accept` | array | ✅ | ≥1 项；每项 `criteria`（非空）+ `criteria_hash`（sha256） |
| `golden` | object | ✅ | `ref`（非空）+ `checksum`（sha256） |
| `evidence_budget` | integer | ✅ | ≥0，单位为证据条数 |
| `sensitivity` | string | ✅ | `public/internal/private` |
| `readonly` | boolean | ✅ | 派发时固化 |

### 2.3 C3 `GateResult`

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `status` | string | ✅ | `pass/fail/warn/skip` |
| `code` | string | ✅ | 非空（判据 ID） |
| `evidence_refs` | array[string] | ✅ | 可为空（`skip` 场景） |
| `coverage` | number | ✅ | 0–1 |
| `pre_red_fixture` | string | ✅ | 非空；无变红反例即假防线 |

### 2.4 C4 `ClaimRecord`

以 R-03 §3.2 为 v1 冻结面。

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `claim_id` | string | ✅ | `^c-[0-9a-f]{8}$` |
| `claim_class` | string | ✅ | `A/B/C`（A2-1 反例：缺失即失败） |
| `claim_type` | string | ✅ | `exploratory/confirmatory` |
| `statement` | string | ✅ | 非空 |
| `formal_statement` | string \| null | ✅ | — |
| `formality` | object | ✅ | `status=formal/debt`；`debt ⇒ reason` 非空 |
| `assumptions` | array | ✅ | 每项 `statement` + `why` |
| `evidence` | array | ✅ | 每项为 C5（`$ref`） |
| `reasoning_chain` | array | ✅ | 每步 `step`≥1、`detail` 非空、`source_refs` ≥1 |
| `stats_protocol` | object \| null | ✅ | `estimator/sample/missing_policy/alpha/section_index` 五项齐全 |
| `results` | object \| null | — | `section_index`≥1 + `value` |
| `falsifier` | object | ✅ | `condition` + `test_ref` 两个键（语义由 AR-05 判） |
| `consensus` | object \| null | — | `models[]`、`agreement` 0–1、`used_as` 恒为 `filter` |
| `verification_depth` | string | ✅ | `stage1/stage2/stage3/stage3_5` |
| `status` | string | ✅ | 7 值（见 §2.8） |
| `policy_version` | integer | ✅ | ≥1 |

**条件约束**：`claim_type=confirmatory ⇒ stats_protocol` 必须为非空对象。

### 2.5 C5 `EvidenceRef`

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `evidence_id` | string | ✅ | 非空 |
| `source_layer` | string | ✅ | `T1/T2/T3/T4` |
| `tier` | string | ✅ | `E1–E5` |
| `kind` | string | ✅ | `pointer/snapshot` |
| `source_id` | string | ✅ | 非空 |
| `locator` | string | ✅ | 非空（缺定位不得标已验证） |
| `quote` | string | — | ≤3 行由 AR-01 校验，schema 只约束类型 |
| `digest` | string | ✅ | sha256 |
| `independent` | boolean | ✅ | 是否独立来源 |
| `readonly` | boolean | — | `kind=snapshot ⇒ 必须为 true` |
| `replay_cmd` | string \| null | — | 可重放命令 |

### 2.6 C6 `ModelRole`

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `role` | string | ✅ | `orchestrator/reasoner/tactician/aux` |
| `backend` | string | ✅ | `local/egress` |
| `sensitivity` | string | ✅ | `public/internal/private` |
| `model_id` | string | ✅ | 非空 |
| `budget` | object | ✅ | `max_tokens`（≥0）+ `max_usd`（≥0） |

「`local` 硬拒出网」属运行时策略（M3 验收），schema 不表达。

### 2.7 C7 `DerivedView`

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `source_of_truth` | array[string] | ✅ | ≥1，非空项 |
| `generated_by` | string | ✅ | 非空（生成器路径） |
| `check_cmd` | string | ✅ | 非空（手改检测命令） |

### 2.8 状态词表

`status` 7 值 = AP `CitationLabel` 6 值 + `speculation`：

`formally_verified / partially_formalized / numerically_verified / latex_verified / falsified / failed / speculation`

大小写以 **lowercase 字符串** 为契约值；文档中的 `FALSIFIED` 等大写写法是概念名，不进入 JSON。

## 3. 跨文件引用与校验

- C4 的 `evidence[]` 用 `$ref: "urn:arc:contracts:v1:evidence_ref"` 指向 C5，避免字段复制。
- 测试用 `referencing.Registry` 预注册 7 份 schema，再交给 `Draft202012Validator`；**不发生网络请求**。
- 错误定位：对反例断言 `error.json_path` 命中预期字段（如 `$.claim_class`、`$.verdict`），不只断言「失败」。

## 4. 版本与兼容矩阵

见 [contracts/README.md](../../contracts/README.md)：

- 版本 `v1.0.0`；目录 `contracts/v1/` 与 `$id` 同时带 `v1`。
- 新增**可选**字段 → minor；改必填/枚举/类型/删除字段 → major（新建 `contracts/v2/`，v1 保留只读）。
- 兼容面：Python 3.11/3.12/3.13；MCP v2（仅宿主）；Lean 可选 Tier-3（不影响契约）。

## 5. fixture 矩阵

| 契约 | 正例 | 反例（必须失败的原因） |
|---|---|---|
| C1 | `minimal.json` | `with_verdict.json`（`verdict` 未声明） |
| C2 | `minimal.json` | `empty_accept.json`（`accept` 空数组） |
| C3 | `pass.json` | `fail_without_pre_red.json`（缺 `pre_red_fixture`） |
| C4 | `minimal.json` | `missing_claim_class.json`；`bad_status.json` |
| C5 | `pointer.json` | `snapshot_without_readonly.json` |
| C6 | `orchestrator.json` | `bad_backend.json`（`local-only` 不在枚举） |
| C7 | `console.json` | `missing_check_cmd.json` |

正例覆盖跨文件 `$ref`（C4 内联一条 C5）；反例只改一个变量，保证失败可归因。

## 6. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 顶层封闭导致 M1 加字段即破坏 | 版本政策：加可选字段走 minor；schema 目录与 `$id` 同步升级 |
| `jsonschema` 版本行为差异 | 在 dev extra 固定 `>=4.20`；CI 三版本矩阵执行同一测试 |
| fixture 与 schema 同步漂移 | 测试按目录枚举，缺正/反例即失败（不是按硬编码文件名） |
| 契约与 AP 真值源分叉 | C4 状态词表直接对齐 `CitationLabel`；`policy_version` 必填 |
