---
id: arc-g2-decisions-RESEARCH
type: design
version: 1.1
status: verified
date: 2026-11-10
depends: [arc-master-roadmap, arb-v2-decisions-research-design]
upstream: arc-master-roadmap
---

# 调研：G2 前置 Q1（证据内核形态）/ Q2（vendor 边界）裁决

> **Feature**：P-042，G2 开工前的两项决策闸门。
> **Spec 步骤**：T3 轻批（Layer-0：本文件 + session + PROGRESS 行 + 总纲 Q1/Q2 状态；零代码/零门禁）。
> **修订**：v1.1（2026-11-10，P-043）**U-1 关闭**——AP 已采用 **Apache-2.0**（`LICENSE` 官方全文、`NOTICE`、PEP 639 元数据 `License-Expression: Apache-2.0` / `License-File: LICENSE, NOTICE` 均已验证）；Q2 的 L-1 许可证闸门解除，并新增 §9 vendor 合规要求。
> **优先级声明**：本文件 **取代** [R-03 §1.3/§2.3/§7](../../arb-v2-decisions-research-design.md) 的「建议」为正式裁决；R-03 原文不改（追加式证据）。

## 1. 问题与判据

| 闸门 | 原文（总纲 §7） | 本文件要回答 |
|---|---|---|
| Q1 | Python 双轨（3.11 内核 + 3.12 子进程）还是统一 3.12 | 证据内核以什么形态交付：进程内子集 / 统一 3.12 / 降级上游 |
| Q2 | Lean 是否作为安装前置 | vendor 哪些、不 vendor 哪些；Lean 的边界与降级 |

**为什么必须现在裁决**：G2 的 A2-3 要求判定内核在 **3.11** 跑通并按 `pytest --collect-only` 冻结；A2-7 要求无 Lean 时深度封顶。形态未定，M2/M3 无法排期。

## 2. 本仓事实（T1，一手复验）

| # | 事实 | 证据 |
|---|---|---|
| F-1 | ARC 声明 `requires-python = ">=3.11"`；CI 必过矩阵 **3.11 / 3.12 / 3.13**，3.14 为实验性 | `pyproject.toml:5`；`.github/workflows/ci.yml:81-84` |
| F-2 | ARC 的 MCP 依赖为 `mcp>=2.1,<3`（可选 extra） | `pyproject.toml:18` |
| F-3 | Auto_Prover（AP）v3.7.0 声明 `requires-python = ">=3.12"`，依赖 `mcp>=1,<2` | `F:\Auto_Prover\pyproject.toml` |
| F-4 | **AP 内核代码在 3.11 语法下全量可解析**：94 个 `proof_pipeline/**/*.py`，`ast.parse(feature_version=(3,11))` **0 失败** | 本批实跑（3.11.15 解释器） |
| F-5 | AP 内核**无 3.12-only 构造**：`type X =` / `@override` / `itertools.batched` / `except*` 命中 **0** | 本批扫描 94 文件 |
| F-6 | 内核子集体量可控：`datatypes` 9 文件、`verdict` 3 文件、`sandbox` 4 文件；`sandbox/evaluator.py` 仅用 stdlib | 本批清点 + 读码 |
| F-7 | **AP 无项目许可证**（P-042 时）：无 `LICENSE`/`COPYING`/`NOTICE`，`pyproject.toml` 无 `license` 字段，README 无许可声明；远端 `github.com/StormstoutLau/Auto_Prover`。**2026-11-10 已解除**：AP 采用 Apache-2.0（LICENSE/NOTICE/PEP 639），见 §5.1 L-1 与 §8 | 本批穷举检索（P-042）；P-043 复核 LICENSE 哈希与元数据 |
| F-8 | ARC 现有 `hitl/claim_verifier.py` 的 `Claim` 只有 `text/claim_type/grounded/evidence:str/confidence`，**不是** G2 的 `ClaimRecord v1` | 读码 `claim_verifier.py:24-44` |
| F-9 | ARC 约 289 个 Python 文件；AP 内核 94 个；两侧规模都在「vendor 子集」可维护范围 | 本批清点 |

## 3. 外部锚点（T1/T2，已回原文）

| # | 来源 | 关键原文/结论 | 等级 |
|---|---|---|---|
| S-1 | Scientific Python [SPEC 0](https://scientific-python.org/specs/spec-0000/) | 建议 Python 版本在**初始发布 3 年后**才可弃用 | T1 |
| S-2 | CPython [版本状态](https://devguide.python.org/versions/) | 3.11 = security，EOL **2027-10**；3.12 = security，EOL **2028-10** | T1 |
| S-3 | [PEP 698](https://peps.python.org/pep-0698/) | `typing.override` 为 **Python 3.12** 新特性（Final） | T1 |
| S-4 | CPython 文档 [itertools](https://docs.python.org/3/library/itertools.html#itertools.batched) | `batched()` **Added in version 3.12**；3.13 增 `strict` | T1 |
| S-5 | pip [Vendoring Policy](https://pip.pypa.io/en/stable/development/vendoring-policy/) | vendor 库**必须**：许可证允许并入 MIT 项目、随附 LICENSE、除移植外不得修改 | T1 |
| S-6 | Microsoft [Sidecar pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/sidecar) | 独立进程提供隔离与异构技术栈，生命周期与主应用绑定 | T1 |
| S-7 | W3C [PROV-O](https://www.w3.org/TR/prov-o/) | W3C Recommendation 2013-04-30；Entity/Activity/Agent 与派生关系 | T1 |
| S-8 | [JSON Schema 2020-12](https://json-schema.org/draft/2020-12) | 2022-06-16 发布；`$dynamicRef`、`prefixItems`、`unevaluated*` | T1 |
| S-9 | [Lean 安装](https://lean-lang.org/install/) | 推荐 VS Code 扩展或手动安装（elan/lake），**不经 pip** | T1 |
| S-10 | [Theorem Proving in Lean 4](https://lean-lang.org/theorem_proving_in_lean4/Interacting-with-Lean/) | `sorry` 是占位符；依赖它的求值会被中止，且始终产生 `declaration uses 'sorry'` 警告 | T1 |
| S-11 | Wadden et al. 2020, [SciFact](https://aclanthology.org/2020.emnlp-main.609/)（DOI [10.18653/v1/2020.emnlp-main.609](https://doi.org/10.18653/v1/2020.emnlp-main.609)） | 科学 claim 与 evidence/rationale 的显式配对是可操作抽象 | T1 |
| S-12 | ACM [Artifact Review and Badging v1.1](https://www.acm.org/publications/policies/artifact-review-and-badging-current) | 结果可信度应由可独立复核的 artifact 支撑，而非单一标签 | T1 |
| S-13 | Jia & Harman 2011, IEEE TSE 37(5):649-678（DOI [10.1109/TSE.2010.62](https://doi.org/10.1109/TSE.2010.62)） | 变异测试用于评估测试集「能否变红」，是判据有效性证据 | T1 |

## 4. Q1 裁决：B 双轨（3.11 内核 + 3.12 子进程）

### 4.1 五步非补偿程序（P-025）

**① 硬约束**（违反即淘汰，不参与打分）

| ID | 约束 | 来源 |
|---|---|---|
| H-1 | ARC 维持 `>=3.11` 承诺，CI 3.11 必过 | F-1 + S-1（3.11 仍在 3 年窗口内） |
| H-2 | 不修改 AP 的 `>=3.12` 与 `mcp>=1,<2` 声明 | F-3；避免维护分叉 |
| H-3 | Lean 不得成为 ARC 安装前置 | S-9（非 pip 分发）+ 总纲 A2-7 |
| H-4 | 不复制无许可证代码 | F-7 + S-5 |

**② 支配分析**

| 方案 | H-1 | H-2 | H-3 | H-4 | 结论 |
|---|---|---|---|---|---|
| **A 统一 3.12** | ❌ 破坏 3.11 用户 | ✅ | ✅ | ✅ | 淘汰 |
| **B 双轨** | ✅ | ✅ | ✅ | 需 Q2 gate | **唯一全过** |
| **C 降 AP 到 3.11** | ✅ | ❌ 改上游 + 重跑 126 测试文件 | ✅ | 需 Q2 gate | 淘汰 |

**③ 敏感点**：唯一可能推翻 B 的是 H-1 本身——若 ARC 在 2027-10（3.11 EOL）后主动放弃 3.11，A 才具备可行性；届时 B→A 只是删除进程边界，契约不变。

**④ 可逆性**：B 的进程边界以 JSON 契约为唯一接口；回退到 A 或前进到「同机双解释器」均不需改内核语义。**高**。

**⑤ Kill criteria**
- 3.11 内核子集在 G2 开工复跑时不能全绿（R-03 的 65 用例）→ 停，重新评估 A；
- 进程边界无法在不泄漏内部类型的前提下承载 `ClaimRecord` → 停，改单进程 + 3.12 requirement（即 A）；
- AP 许可证未解决 → M2 不启动（见 Q2）。

**裁决：Q1 = B**。3.11 进程内只放「纯判定内核」（datatypes 裁剪 + verdict/policy + sandbox/evaluator）；完整 AP（Lean / ATLAS / MCP / 检索）作为 3.12 子进程，JSON 契约通信。

## 5. Q2 裁决：B 最小 kernel vendor + 全量 AP sidecar + Lean 可选 Tier-3

### 5.1 硬约束

| ID | 约束 | 后果 |
|---|---|---|
| L-1 | **许可证**：AP 原无许可证（F-7，P-042 时）；**2026-11-10 已采用 Apache-2.0**（LICENSE + NOTICE + PEP 639 元数据），满足 pip 政策与并入 MIT 项目的条件（S-5） | **已解除**；vendor 时须按 §9 保留 Apache 声明与 NOTICE |
| L-2 | 内核必须可 3.11 运行（A2-3） | 排除全量 vendor |
| L-3 | 不得把 `mcp>=1,<2` 引入 ARC 主环境（F-2/F-3） | MCP/ATLAS 必须留在 sidecar |
| L-4 | Lean 不经 pip（S-9），`sorry` 必须影响深度（S-10） | Lean 只能作为可选外部插件 |

### 5.2 支配分析

| 方案 | L-1 | L-2 | L-3 | L-4 | 结论 |
|---|---|---|---|---|---|
| **A 全量 vendor** | ❌ | ❌ 3.12-only 路径 | ❌ 带 mcp | ❌ | 淘汰 |
| **B 最小 kernel vendor + sidecar + Lean Tier-3** | 通过（许可证已解除） | ✅ | ✅ | ✅ | **采纳** |
| **C 全 sidecar（零 vendor）** | 通过 | ❌ 3.11 离线判定不可用 | ✅ | ✅ | 淘汰（违 A2-3） |
| **D clean-room 重写 kernel** | ✅ 不复制代码 | ✅ | ✅ | ✅ | **许可证被撤销时的替代路径** |

**裁决：Q2 = B，原 L-1 许可证闸门已于 2026-11-10 解除**：

1. **已完成的先决动作**：AP 采用 **Apache-2.0**——仓库根新增 `LICENSE`（官方全文，SHA-256 与 apache.org 一致）与 `NOTICE`；`pyproject.toml` 使用 PEP 639 元数据（`license = "Apache-2.0"`、`license-files = ["LICENSE", "NOTICE"]`，`setuptools>=77`）；README 增许可证章节。实测 wheel 元数据含 `License-Expression: Apache-2.0` 与两条 `License-File`。
2. **原回退条件（D 路径）**：仅在「许可证缺失」时触发。当前不触发；若未来许可证被撤销或第三方审计发现不可再分发的代码，M2 立即暂停并转 **D（clean-room 重写最小 kernel）**——只依据公开设计语义重写，不复制 AP 源码与文档原文；sidecar 契约不变。
3. **Vendor 边界（B 的精确清单）**：
   - **进**：`datatypes`（裁剪到 ClaimRecord 所需：core/result/numerical/proof/hypothesis/translation）、`verdict/policy.py`、`verdict/evidence.py`、`sandbox/evaluator.py` + `limits.py`；
   - **不进**：`stages`、`kg`、`lean_meta`、`mcp_servers`、`atlas_bridge`、`proof_pipeline/stages/lean*`（3.12 / MCP / Lean 绑定）；
   - **同步方式**：固定 AP commit（Q18 L1），以 subtree 或 patch 记录差异；不跟 `main` 漂移。
4. **Lean = 可选 Tier-3**：不作为安装前置，不进基座镜像；`arb lean doctor` 自检；无 Lean / 编译失败 / 出现 `sorry` → `verification_depth` 上限 `PARTIALLY_FORMALIZED`（A2-7），论文与 UI 必须标注「未形式化」。
5. **证据契约**：`EvidenceRef` 按 PROV-O 的 Entity/Activity/Agent 映射（S-7）；`ClaimRecord` schema 用 JSON Schema 2020-12 版本化（S-8）；A2-2 的「判据能变红」以变异测试作为方法学依据（S-13）；发布标签的深度分级参照 ACM badging 的 artifact 复核思想（S-12）。

### 5.3 与 ARC 现状的衔接

- F-8：现有 `hitl/claim_verifier.py` 的 `Claim` 是**消费端轻量结构**，不承担 `ClaimRecord v1`；G2 引入内核后，它应改为消费 `ClaimRecord`（迁移，不并存两套真值）。
- F-9/F-6：vendor 子集约 16 个文件，规模与 ARC 现有模块相当，可读可审。

## 6. 给 G2 实施批的强制输入

| # | 输入 | 落点 |
|---|---|---|
| I-1 | ~~M0 先决：AP 许可证（或书面授权）；否则转 D~~ **已完成（2026-11-10，Apache-2.0）** | Q2 L-1 |
| I-2 | M2 vendor 前冻结 AP commit + 文件清单 + 每文件 sha256 | Q18 L1 |
| I-3 | A2-3 的 3.11 用例清单在 G2 开工时 `pytest --collect-only` 冻结 | A2-3 |
| I-4 | Sidecar JSON 契约含 `schema_version`/`policy_version`/`exit_code`/`degraded_reason` | Q1 B |
| I-5 | Lean 未启用时导出 `verification_depth=stage2` 与 `lean_unavailable_reason` | A2-7 |
| I-6 | 变异测试至少对 AR-01/AR-04/AR-07 各做一次「删判据→fixture 变红」 | A2-2 + S-13 |
| I-7 | **Vendor 合规四件套**：Apache `LICENSE` + `NOTICE` + 修改声明 + 来源 commit（§9） | Q2 L-1 + S-5 |
| I-8 | **第三方血统审计收口**：`atlas_*.py` 与 `lean4_cases` 结论落 `THIRD_PARTY_NOTICES.md`；未收口前不 vendor 这两项 | Q2 + §9 |

## 7. 未决

- ~~**U-1 AP 许可证**：判据 = 仓库根出现可并入 MIT 的 LICENSE；触发 = G2 M2；阻塞级。~~ **已关闭（2026-11-10，P-043）**：AP 采用 Apache-2.0，LICENSE/NOTICE/PEP 639 元数据均验证；后续合规要求见 §9。
- **U-2 3.11 内核复跑**：R-03 的 65 用例在本批未重跑（仅验语法与构造）；触发 = G2 开工首日；失败即 Q1 kill criteria。
- **U-3 sidecar 传输**：JSON 文件 vs 本地 HTTP；触发 = M3；倾向 = 先文件（零端口、易审计），需要长驻时再升 HTTP。
- **U-4 vendor 同步机制**：subtree vs patch 集；触发 = M2；倾向 = subtree + commit pin。

## 8. Vendor 合规要求（P-043 追加，G2 M2 强制输入）

### 8.1 目录结构

```
researchclaw/vendor/auto_prover/
  LICENSE                  # Apache-2.0 官方全文（不得删改）
  NOTICE                   # AP 的 NOTICE（不得删改，可追加）
  THIRD_PARTY_NOTICES.md   # 第三方审计结论（升级时复核）
  SOURCE.json              # 上游 URL、commit/tag、文件清单、逐文件 sha256
  datatypes/ verdict/ sandbox/
```

### 8.2 许可边界（必须写进 G2 DESIGN）

| # | 规则 | 依据 |
|---|---|---|
| V-1 | ARC 整体仍为 MIT；`researchclaw/vendor/auto_prover/` **按文件保持 Apache-2.0**，不得重许可为 MIT | Apache-2.0 §4；S-5 |
| V-2 | 发布物（sdist/wheel/zip）必须携带该目录的 `LICENSE` 与 `NOTICE`；ARC 自有 `NOTICE` 与 AP NOTICE **并存**，不得覆盖 | Apache-2.0 §4(a)(d) |
| V-3 | 任何修改过的文件，在文件头加 `# Modified by AutoResearchClaw on YYYY-MM-DD: <reason>` | Apache-2.0 §4(b) |
| V-4 | 版权主体沿用 `Aiming Lab`；`SOURCE.json` 必须记录版权声明与来源 commit | 与 AP `NOTICE` 一致 |
| V-5 | 只复制代码文件；**不得复制 AP 的 `spec/`/`docs/` 原文**（文档同受版权保护） | 版权法基本要求 |
| V-6 | 升级 vendor 时必须：更新 `SOURCE.json`、重算 sha256、重跑 3.11 内核用例、复核 `THIRD_PARTY_NOTICES.md` | Q18 L1 + A2-3 |

### 8.3 明确不 vendor 的内容

| 项 | 原因 |
|---|---|
| `atlas_bridge/vendor/atlas_*.py`（8 文件） | 第三方血统**未审计**（P-043 时仍为 pending） |
| `atlas_bridge/vendor/data/lean4_cases/` | 可能派生自 mathlib，**未审计** |
| `stages/`、`kg/`、`lean_meta/`、`mcp_servers/` | 3.12 / MCP / Lean 绑定，违 L-2/L-3/L-4 |
| `proof_pipeline/stages/lean*` | Lean 绑定，属 sidecar/Tier-3 |

### 8.4 审计闸门

- M2 开工前：`THIRD_PARTY_NOTICES.md` 中所有 **pending** 项必须有结论（确认自有或补许可证）；
- 若结论为「第三方且不可再分发」：该文件不进 vendor，必要时以 sidecar 调用替代；
- 若 AP 许可证被撤销：M2 暂停，按 Q2 第 2 条转 D。

## 9. 引用

1. 仓内：[R-03](../../arb-v2-decisions-research-design.md) §1-§2/§7、[总纲 §4 G2 / §7](../../arc-master-roadmap.md)、`hitl/claim_verifier.py`、`pyproject.toml`、`.github/workflows/ci.yml`。
2. 本地上游：`F:\Auto_Prover\pyproject.toml`、`proof_pipeline/{datatypes,verdict,sandbox}/`（HEAD `d06699d`）。
3. 外部：S-1..S-13（§3 表，URL/DOI 已逐条解析）。
