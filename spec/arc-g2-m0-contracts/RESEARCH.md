---
id: arc-g2-m0-contracts-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-master-roadmap, arc-g2-decisions, arc-g2-py311-env]
upstream: arc-g2-decisions
---

# 调研：G2 M0 契约冻结（C1–C7）

> **Feature**：P-047，G2 里程碑 M0（契约 v1 + Spec 引导）。
> **Spec 步骤**：T1 完整管线（Layer-1：新增 `contracts/`、`tests/`、CI 列表与 `pyproject.toml` 依赖）。
> **结论先行**：M0 的实际缺口只有 **7 份 JSON Schema + 正反 fixture + 兼容矩阵**；「6 钩子可跑」已由 G0b（P-021）交付并在 P-046 复跑全绿。Schema 采用 **2020-12**，`$id` 用 **URN** 离线解析，校验依赖 **`jsonschema`（dev extra）**，C1/C4 的版本红线用 `additionalProperties: false` 与必填字段机械锁定。

## 1. 问题与边界

R-03 把 M0 定义为「契约 v1 + Spec 引导（S0）」，DoD 为 **7 契约 schema + 6 钩子可跑**（[R-03 §5.2](../../arb-v2-decisions-research-design.md)）。需要回答四件事：

1. 「6 钩子」是否仍需本批交付，还是已由既有治理基座满足；
2. 7 份契约的字段以哪份材料为真值源（R-02 §6.3 的抽象清单 vs R-03 §3.2 的 `ClaimRecord v1`）；
3. JSON Schema 的方言、`$id` 与校验依赖怎么选，才能在 3.11/3.12/3.13 离线可复现；
4. 契约「冻结」的机械口径是什么——哪些字段/枚举/红线必须由 schema 拒绝，哪些留给 M1 的 AR 判据。

**不在本批**：AR-01..08 实现（M1）、vendor 内核（M2）、sidecar/Lean（M3）、谓词 `can_enter_deliverables` 等（G2 后续验收）。

## 2. 本仓一手事实（F）

| # | 事实 | 证据 |
|---|---|---|
| F-1 | R-02 §6.3 定义 7 个跨层契约：C1 `RunEnvelope`、C2 `TaskContract`、C3 `GateResult`、C4 `ClaimRecord`、C5 `EvidenceRef`、C6 `ModelRole`、C7 `DerivedView`，并给出各自核心字段 | [R-02 §6.3](../../academic-reasoning-base-fusion.md) |
| F-2 | R-03 §3.2 把 C4 具体化为 `ClaimRecord v1`：16 个顶层字段（`claim_id`…`policy_version`），`status` 7 值、`verification_depth` 4 值、`claim_class` A/B/C | [R-03 §3.2](../../arb-v2-decisions-research-design.md) |
| F-3 | AP 的 `CitationLabel` 是 **6 个 lowercase 字符串值**（`formally_verified`…`failed`），`CURRENT_POLICY_VERSION = 2`；C4 的 `status` 在其上追加 `speculation` | `F:\Auto_Prover\proof_pipeline\datatypes\core.py:23-34` |
| F-4 | ARC 当前**没有** `contracts/` 目录，也**没有**任何 `jsonschema` 依赖或用法 | 本批穷举检索 |
| F-5 | ARC CI 的 tests job 安装 `.[dev,server,mcp]`，并运行一份**固定**的契约测试文件清单；新增测试文件必须显式加入该清单才会在 CI 执行 | [ci.yml](../../.github/workflows/ci.yml) |
| F-6 | G0b 已交付 **6 必需钩子 + 3 守卫**（DC validator、m7、repo-stats、step-enforce、console-gen、blackbox、private-config、code-agent-wiring、rework-graph），P-046 提交时全绿 | P-021、P-046 提交日志 |
| F-7 | A2-1 的负向口径是「**缺 `claim_class` 必须失败**」；A2-1 还要求 7 个 schema 的 fixture 全通过 | [总纲 §4 G2](../../arc-master-roadmap.md) |
| F-8 | G2 的 3.11 前置已由 P-046 关闭：65 项 node ID 冻结，3.11/3.13 双环境 65 passed | [P-045 调研](../arc-g2-py311-env/RESEARCH.md) |
| F-9 | ARC 的 `hitl/claim_verifier.py::Claim` 只有 6 个字段（`text/claim_type/source_line/grounded/evidence/confidence`），**不是** C4；本批不改造它 | `researchclaw/hitl/claim_verifier.py:24-43` |

## 3. 外部锚点（S）

| # | 来源 | 关键读数 | 等级 |
|---|---|---|---|
| S-1 | [JSON Schema 2020-12 Core](https://json-schema.org/draft/2020-12/json-schema-core) | 定义 `$schema`/`$id`/`$ref`/`$defs` 与 applicator 语义；`additionalProperties: false` 拒绝未声明成员 | T1 标准 |
| S-2 | [JSON Schema 2020-12 Validation](https://json-schema.org/draft/2020-12/json-schema-validation) | `required`/`enum`/`pattern`/`const`/`if-then` 的规范语义 | T1 标准 |
| S-3 | [python-jsonschema · Referencing](https://python-jsonschema.readthedocs.io/en/stable/referencing/) | 4.x 通过 `referencing.Registry` 注入跨文件 `$ref`，避免网络解析 | T1 官方文档 |
| S-4 | [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html) | 破坏性变更升 major；新增可选字段升 minor | T1 标准 |
| S-5 | [jsonschema 4.23 changelog / API](https://python-jsonschema.readthedocs.io/en/stable/) | `Draft202012Validator`、`check_schema` 可用；`referencing` 自 4.18 起为默认后端 | T1 官方文档 |

## 4. 方案对比

判据（非补偿）：

- **D-1**：7 份契约可在**离线**环境完成结构与红线校验；
- **D-2**：A2-1 的两个负向（缺 `claim_class`、fixture 全通过）可机械复现；
- **D-3**：不引入运行时依赖，不改变 `researchclaw` 包的导入面；
- **D-4**：3.11/3.12/3.13 行为一致，且 CI 可执行。

| 决策点 | 方案 | D-1 | D-2 | D-3 | D-4 | 结论 |
|---|---|---|---|---|---|---|
| 方言 | **2020-12** | ✅ | ✅ | ✅ | ✅ | **采纳**（S-1/S-2） |
| 方言 | 2019-09 | ✅ | ✅ | ✅ | ✅ | 淘汰：无收益，生态默认已是 2020-12 |
| 方言 | 自研 DSL | ✅ | ⚠️ | ✅ | ⚠️ | 淘汰：重造校验语义 |
| 校验器 | **`jsonschema>=4.20`（dev extra）** | ✅ | ✅ | ✅（仅测试面） | ✅ | **采纳**（S-3/S-5） |
| 校验器 | stdlib 子集实现 | ✅ | ⚠️ | ✅ | ✅ | 淘汰：`if/then`/`$ref` 需自造，易与标准分叉 |
| 校验器 | 不校验，只存 schema | ❌ | ❌ | ✅ | — | 淘汰：A2-1 不成立 |
| `$id` | **URN**（`urn:arc:contracts:v1:*`） | ✅ | ✅ | ✅ | ✅ | **采纳**：无网络解析副作用 |
| `$id` | `https://arc.local/...` | ✅ | ✅ | ✅ | ✅ | 淘汰：保留假域名易误解 |
| 严格度 | **顶层 `additionalProperties: false` + 红线必填** | ✅ | ✅ | ✅ | ✅ | **采纳**：契约冻结的可机械面 |
| 严格度 | 允许扩展字段 | ✅ | ⚠️ | ✅ | ✅ | 淘汰：C1 的 `verdict` 红线会被放行 |

**裁决**：2020-12 + URN + `jsonschema`（dev）+ 顶层封闭。C4 通过 `$ref` 复用 C5，不复制字段定义。

## 5. 契约真值源与字段裁定

| 契约 | 真值源 | 本批裁定 |
|---|---|---|
| C1 `RunEnvelope` | R-02 §6.3 | 顶层封闭；**禁止 `verdict`**（产出方不自评）；`status` 冻结为 `running/succeeded/failed/timeout/cancelled` |
| C2 `TaskContract` | R-02 §6.3 | `accept[]` 至少 1 条，每条带 `criteria_hash`；`golden.checksum` 用 sha256；`evidence_budget` 定为非负整数（条数） |
| C3 `GateResult` | R-02 §6.3 | `status` 四值；`pre_red_fixture` 必填（无变红反例即假防线） |
| C4 `ClaimRecord` | R-03 §3.2 | 以 R-03 为 v1 定义；`claim_class` 必填（A2-1）；`status` 7 值；`confirmatory ⇒ stats_protocol` 非空 |
| C5 `EvidenceRef` | R-02 §6.3 + R-03 AR-08 | `kind=snapshot ⇒ readonly=true`；`kind=pointer` 必须带 `digest` |
| C6 `ModelRole` | R-02 §6.3 | `backend=local` 的「硬拒出网」是运行时策略，schema 只冻结枚举 |
| C7 `DerivedView` | R-02 §6.3 | `source_of_truth[]` 至少 1 条；`check_cmd` 必填 |

**C4 字段映射**（R-02 抽象 → R-03 v1）：`claim` → `statement`；`evidence_refs[]` → `evidence[]`（C5 内联引用）；`producer_model` 与 `independent_checks` 不在 v1 顶层，分别由 C1（产出方）/ C5（`independent`）承担。此映射写入 [DESIGN](DESIGN.md) §2.4，避免两处口径漂移。

## 6. 未决（四元块）

| # | 判据 | 触发条件 | 当前倾向 | 证据等级 |
|---|---|---|---|---|
| U-1 | C1 的 `status` 与 ARC `run_state` 词表可一一映射，且有 1 条机械对齐用例 | M1 接线 `RunEnvelope` 时 | 先冻结 5 值；若 `run_state` 出现第 6 值，升 v1.1（minor） | E2（本批读码） |
| U-2 | `ClaimRecord` 的 `producer_model`/`independent_checks` 是否需要回到顶层 | G3 血缘实现需要按 claim 追溯模型时 | 保持 v1 顶层精简；由 C1/C5 承担 | E3（设计判断） |
| U-3 | 契约测试是否进入 3.11/3.12/3.13 全矩阵，而非仅单个 CI job | 首次出现 schema 方言/库版本差异 | 本批只加进既有 tests 矩阵清单（已覆盖 3.11–3.13） | E1（CI 配置） |

## 7. 引用

1. 仓内：[R-02](../../academic-reasoning-base-fusion.md)、[R-03](../../arb-v2-decisions-research-design.md)、[总纲 G2](../../arc-master-roadmap.md)、[P-042](../arc-g2-decisions/RESEARCH.md)、[P-045](../arc-g2-py311-env/RESEARCH.md)、`researchclaw/hitl/claim_verifier.py`、`pyproject.toml`、`.github/workflows/ci.yml`。
2. 外部：S-1..S-5（§3 表，URL 已解析）。
