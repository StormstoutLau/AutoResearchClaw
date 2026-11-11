---
id: arc-g2-m1-ar-checks-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-11
depends: [arc-g2-m0-contracts, arb-v2-decisions, arc-master-roadmap]
upstream: arc-g2-m0-contracts
---

# 调研：G2 M1 学术八条机械化（AR-01..08）

> **Feature**：P-048，G2 里程碑 M1。
> **Spec 步骤**：T1 完整管线（Layer-1：新增 `researchclaw/evidence/`、`tests/` 与 fixture）。
> **结论先行**：8 条判据可全部落为**无 IO 纯函数**，严重度严格按 R-03 §3.4 的三档 `downgrade/warn/fail`；16 个 fixture（每判据 1 正 1 反）与 8 条「删判据即变红」的变异自检可机械执行。R-03 中 AR-05 的 `claim_type ∈ {model, method}` 与 `ClaimRecord v1` 的 `exploratory/confirmatory` 枚举**冲突**，v1 下按 A/B 类触发（见 §3 F-2）。

## 1. 问题与边界

R-03 §5.2 把 M1 定义为「八条机械化（AR-01..08）+ ClaimRecord」，DoD 为 **16 fixture + 8 条 pre-red 全绿**（[R-03 §5.2](../../arb-v2-decisions-research-design.md)），总纲对应验收为 **A2-2**（[总纲 §4 G2](../../arc-master-roadmap.md)）。本批回答：

1. 每条判据的机械输入、判定条件与严重度如何落到代码；
2. R-03 内部矛盾（AR-05 的 `claim_type`）如何在 v1 契约下解释；
3. 「pre-red / 变异」如何证明判据不是空实现；
4. 哪些语义明确**不可机械化**，必须留给 Review/用户裁决。

**不在本批**：状态改写与发布谓词（A2-4..A2-6）、vendor 内核（M2）、sidecar/Lean（M3）。

## 2. 本仓一手事实（F）

| # | 事实 | 证据 |
|---|---|---|
| F-1 | R-03 §3.3 逐条给出 AR-01..08 的判据与违反处置：AR-01/02 降级、AR-03/04/08 fail、AR-05/06 封顶、AR-07 fail/warn | [R-03 §3.3](../../arb-v2-decisions-research-design.md) |
| F-2 | **源冲突**：AR-05 写 `claim_type ∈ {model, method}`，但 R-03 §3.2 与 M0 的 C4 v1 把 `claim_type` 冻结为 `exploratory/confirmatory`，不含 `model/method` | R-03 §3.2/§3.3；[C4 schema](../../contracts/v1/c4_claim_record.schema.json) |
| F-3 | C4/C5 已在**结构层**强制部分 AR-08（`snapshot ⇒ readonly`、`digest` 必填）；AR-08 仍需运行时检查：内存态记录、`inline_copy` 长度、以及 schema 之外的跨仓声明 | M0 实施；本批读码 |
| F-4 | M0 契约位于 `contracts/v1/`，fixture 位于 `contracts/v1/fixtures/`；仓库 `tests/` 为扁平文件，无 `tests/fixtures/` 目录 | 本批清点 |
| F-5 | `researchclaw/hitl/claim_verifier.py::Claim` 只有 6 字段，是文本事实核查，不是 C4；复用会混淆两套语义 | `researchclaw/hitl/claim_verifier.py:24-43` |
| F-6 | A2-2 要求：16 fixture 全绿；**删掉任一判据 → 对应 fixture 变红**；判据空实现必须失败 | [总纲 §4 G2](../../arc-master-roadmap.md) |
| F-7 | `jsonschema>=4.20` 已在 dev extra（P-047），测试可把正例回验到 C4 schema | `pyproject.toml` |
| F-8 | `researchclaw` 下无 `g2`/`evidence` 模块；新增包不会与现有模块重名 | 本批清点 |

## 3. 源冲突的裁定

AR-05 的触发条件在 R-03 中写为「`claim_type ∈ {model, method}` 或 A/B 类」。v1 的 `claim_type` 没有 `model/method`，若照字面实现会产生永远不触发的死分支。裁定：

- **以 A/B 类为唯一机械触发**；`model/method` 视为原框架的「主张种类」描述，不是 v1 字段。
- 该裁定不缩小覆盖面：R-03 原文本身就是「或 A/B 类」的并集，A/B 已覆盖需要反例的断言。
- 在 [DESIGN](DESIGN.md) §3 记录该解释，并在 [IMPLEMENTATION](IMPLEMENTATION.md) 的偏差表登记。

## 4. 外部锚点（S）

| # | 来源 | 关键读数 | 等级 |
|---|---|---|---|
| S-1 | [pytest · Monkeypatching](https://docs.pytest.org/en/stable/how-to/monkeypatch.html) | `monkeypatch.setitem` 可在用例内替换判据表项，用于「删判据即变红」 | T1 官方文档 |
| S-2 | [Python `re`](https://docs.python.org/3/library/re.html) | 引用标记与禁用短语的匹配语义；`re.IGNORECASE` 用于英文短语 | T1 官方文档 |
| S-3 | [JSON Schema 2020-12 Validation](https://json-schema.org/draft/2020-12/json-schema-validation) | M0 已冻结的结构面；M1 只叠加语义判据 | T1 标准 |
| S-4 | [pytest · Parametrize](https://docs.pytest.org/en/stable/how-to/parametrize.html) | 16 fixture 与 8 条变异按参数化展开，失败可归因到判据 ID | T1 官方文档 |

## 5. 方案对比

判据：

- **M-1**：每条判据是纯函数（无 IO、无全局状态），可单独调用；
- **M-2**：严重度与 R-03 §3.4 三档一一对应，不新增第四档；
- **M-3**：16 fixture + 8 变异可机械执行，且失败能定位到判据 ID；
- **M-4**：不改变 M0 契约；不引入运行时依赖。

| 决策点 | 方案 | M-1 | M-2 | M-3 | M-4 | 结论 |
|---|---|---|---|---|---|---|
| 代码形态 | **单模块 + 判据注册表** | ✅ | ✅ | ✅ | ✅ | **采纳** |
| 代码形态 | 8 个独立类/插件 | ✅ | ✅ | ⚠️ | ✅ | 淘汰：过度抽象 |
| 输出 | **`Finding(code, severity, message, field, cap)`** | ✅ | ✅ | ✅ | ✅ | **采纳** |
| 输出 | 只返回 bool | ✅ | ❌ | ⚠️ | ✅ | 淘汰：丢失严重度与定位 |
| 状态改写 | 本批**不写回** `status` | ✅ | ✅ | ✅ | ✅ | 采纳；A2-4..A2-6 再落谓词 |
| 状态改写 | 检查即改 `status` | ⚠️ | ✅ | ⚠️ | ✅ | 淘汰：混合判定与呈现 |
| fixture 位置 | **`tests/fixtures/g2/ar/`** | ✅ | ✅ | ✅ | ✅ | **采纳**；与契约 fixture 分离 |
| fixture 位置 | 复用 `contracts/v1/fixtures/` | ✅ | ✅ | ⚠️ | ✅ | 淘汰：契约 fixture 只验证形态 |
| 变异方式 | **monkeypatch 判据表项为空实现** | ✅ | ✅ | ✅ | ✅ | **采纳**（S-1） |
| 变异方式 | 复制文件后手删代码 | ✅ | ✅ | ❌ | ✅ | 淘汰：不可重复、不可并行 |

## 6. 未决（四元块）

| # | 判据 | 触发条件 | 当前倾向 | 证据等级 |
|---|---|---|---|---|
| U-1 | AR-03 的引用标记词法是否要扩展到 `(e-001)`、脚注等形态 | 首个真实论文片段的标记统计 | 先冻结 `[e-xxxx]`；若真实片段命中率 <80%，扩词法并升 v1.1 | E3（设计判断） |
| U-2 | AR-05/06 的「状态封顶」是否由检查层直接改 `status` | A2-4..A2-6 谓词实现时 | 由谓词层统一消费 `cap`，检查层保持只读 | E2（本批设计） |
| U-3 | AR-02 的「同一条 claim 不得混写」是否可机械识别 | 出现真实混写样本时 | 当前判为不可机械化，留 Review | E3（R-03 §3.5） |

## 7. 引用

1. 仓内：[R-02](../../academic-reasoning-base-fusion.md)、[R-03](../../arb-v2-decisions-research-design.md)、[总纲 G2](../../arc-master-roadmap.md)、[M0 契约](../../contracts/README.md)、`researchclaw/hitl/claim_verifier.py`。
2. 外部：S-1..S-4（§4 表，URL 已解析）。
