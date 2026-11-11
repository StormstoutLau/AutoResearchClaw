---
id: arc-g3-readiness-RESEARCH
type: design
version: 1.3
status: verified
date: 2026-11-11
depends: [arc-g2-m5-offline-audit-IMPLEMENTATION, arc-master-roadmap]
upstream: arc-g2-m5-offline-audit-IMPLEMENTATION
---

# 调研：G3 生产脊柱开工 readiness 与切片

> **Feature**：P-069，G3（生产脊柱 + 证据血缘 + 循环护栏）开工前 readiness。
> **Spec 步骤**：T3 轻批（Layer-0：本文件 + session + PROGRESS 行；零生产代码/零门禁）。
> **结论先行**：G3 的前置 G1/G2 已满足，G2 的 M0–M5 与 P-068 复审缺陷已全部收口；H-4 已落地（`retrieval_degraded` 字段与测试在位），A3-5 不再记 `N/A`。G3 是一个 8+6+3+3 验收项的宽阶段，**不能单批施工**；建议先 P-071 做 G3 M0 设计冻结，再按 M1 ArtifactNode/血缘 → M2 循环护栏 → M3 claim 脊柱（14/17/22）→ M4 治理 → M5 retrieval/K5 切片推进。
>
> **修订**：v1.1（2026-11-11，P-070）**M0 待裁决事项补充调研**——Q-1..Q-9 逐项给出候选方案、外部证据与明确建议（§7），新增 15 条标准/官方文档/学术/工程实践锚点（§8）。核心结论：PARTIALLY_FORMALIZED **放行但标注**；ArtifactNode **大文件只存指针**；annotation **跟随封顶后状态**且由 Stage 14 生产；summary **JCS + 侧车摘要 + 事件链锚定**；循环检测 **签名+零新增+网络错误豁免**；RunMandate **run 启动即不可变**；K5 **未解析即阻断**；敏感产物 **只存指针**。
>
> **修订**：v1.2（2026-11-11，P-070）**建议已采纳为决策**——Q-1..Q-9 全部按 §7 建议定稿（状态见 §4 表），P-074 G3 M0 按此冻结；总纲升至 v1.3m。变更摘要见 §10。无代码/测试改动。
>
> **修订**：v1.3（2026-11-11，P-074）**编号顺延**——P-072（独立复核）与 P-073（O-1..O-6 深挖）占用后，G3 M0 = **P-074**，M1..M5 = **P-075..P-079**；内容与决策不变。

## 1. 问题与前置

G3 目标：让一条 claim 从生成到门禁到引用核验全程可追溯；让文献/综述循环能停下来（[总纲 §G3](../../arc-master-roadmap.md)）。

前置核对：

| 前置 | 状态 | 证据 |
|---|---|---|
| G1 运行时恢复 | 已收口（12/12） | 总纲 §G1 |
| G2 学术证据内核 | 已收口（M0–M5） | P-047..P-068；M5 复审缺陷 P-068 关闭 |
| H-4 `retrieval_degraded` | **已落地** | [`_literature.py`](../../researchclaw/pipeline/stage_impls/_literature.py) `retrieval_degraded`；`tests/test_retrieval_degraded.py` 在 CI 清单 |

因此 A3-5 从「N/A」转为可施工；A3-1 所需的 claim 门禁基础（Stage 9/20/23）已在 M4 交付。

## 2. 现状盘点（一手 grep/读码）

| G3 交付物 | 当前状态 | 缺口 |
|---|---|---|
| Stage 9/14/17/20/23 接入 `ClaimStatus`/`CitationLabel` | 9/20/23 已有 claim 门禁；`researchclaw` 内**无** `ClaimStatus`/`CitationLabel` 词表 | 14/17/22 未接；词表未引入 |
| `pipeline_summary.json` 程序派生 | [`runner.py`](../../researchclaw/pipeline/runner.py) `_build_pipeline_summary` 已程序生成并写盘 | 缺 A3-2「手改未重算 → 失败」一致性校验 |
| Stage 20 门禁 `status != FALSIFIED/FAILED` | 已由 M4 `run_stage20_gate` 实现 | 无 |
| Stage 23 `evidence[].digest` 可复算 | 当前只比 `status`/`deliverable` | A3-3 断网 digest 复算未实现 |
| `retrieval_degraded` 接门禁/论文标注 | 字段已存在 | 未接 Stage 20 与论文标注 |
| `ArtifactNode v1` | 无 | 全新（AN-1..6） |
| `stage_events.jsonl` + 循环检测 | 无 | 全新（FC-1..3） |
| Stage 22 导出侧 claim 接线 | 无 | A3-1 第三出口缺失 |
| `RunMandate` / `prompt_version` / `StageHandback` | 无 | A3-6/7/8 全新 |
| K5 `tb:`/`paper:` 引用门禁 | 无解析器 | A3-4 全新 |

**M5 遗留输入**：O-1（封顶后 annotation 渲染语义）与 O-2（`annotations.json` 生产者）直接决定 A3-1 的数值 claim 能否在 Stage 22 一致导出，必须在 G3 M0 裁决。

## 3. 建议切片

| 批次 | 内容 | 覆盖验收 | 理由 |
|---|---|---|---|
| **P-074 G3 M0** | 设计冻结：四文档 + 决策矩阵 + 切片 | — | 20 个验收 ID，先冻结范围 |
| P-075 M1 | `ArtifactNode v1` + `pipeline_summary` 一致性校验 | AN-1..6、A3-2、A3-3 | 血缘是 A3-1 的地基 |
| P-076 M2 | `stage_events.jsonl` + 循环检测 | FC-1..3 | 相对独立，先拿住「循环可停」 |
| P-077 M3 | Stage 14/17/22 claim 接线 | A3-1（三出口一致） | 依赖 ArtifactNode；工作量最大 |
| P-078 M4 | `RunMandate` / `prompt_version` / `StageHandback` | A3-6/7/8 | 治理面，独立切片 |
| P-079 M5 | `retrieval_degraded` 门禁 + K5 引用门禁 | A3-4、A3-5 | H-4 已落地；依赖知识层 |

> 切片顺序可按 M0 结论调整；M1/M2 可并行，M3 必须在 M1 之后。

## 4. M0 待裁决事项（v1.2 已采纳）

| # | 决策 | 采纳结论 | 状态 | 影响 |
|---|---|---|---|---|
| Q-1 | Stage 20 是否允许 `PARTIALLY_FORMALIZED` 通过 | 允许，但强制 `formalization_gap` 标注；仅阻断 `FALSIFIED/FAILED` | 已采纳 | A2/A3 出口一致性 |
| Q-2 | ArtifactNode 是否覆盖 Stage 12 大文件 | 只存指针（`content_hash + locator`），>1 MiB/二进制/敏感不入 blobs | 已采纳 | AN-1/AN-5、存储 |
| Q-3 | O-1 封顶后 annotation 语义 | annotation 跟随封顶后最终状态；capped 记录 `cap_reason`，`latex_verified` 不强制 | 已采纳 | A3-1 数值 claim |
| Q-4 | O-2 `annotations.json` 生产者 | Stage 14 生产；外部可覆盖并标 `source`；Stage 20 对 numeric 缺标注 fail-closed | 已采纳 | A3-1、A2-5 |
| Q-5 | `pipeline_summary` 防篡改口径 | RFC 8785 JCS + SHA-256 侧车 + `stage_events` 哈希链锚定；`--check` 重算 | 已采纳 | A3-2 |
| Q-6 | `stage_events` 位置与 `plan_sig` | run 根 `stage_events.jsonl`；一次 attempt 一条；签名+零新增+网络豁免 | 已采纳 | FC-1..3 |
| Q-7 | `RunMandate` / `StageHandback` / `prompt_version` | mandate 启动即不可变；handback schema 固定；prompt_version 内容哈希 | 已采纳 | A3-6/7/8 |
| Q-8 | K5 引用文法与失败定位 | `tb:`/`paper:` 显式文法；未解析即阻断并带 `{file,line,ref}` | 已采纳 | A3-4 |
| Q-9 | 敏感产物策略 | 只存指针；不入 blobs/导出/preview；日志只记类别 | 已采纳 | AN-6 |

## 5. 风险

- **范围风险**：G3 验收项多且横跨文献、执行、写作、导出；M0 不冻结切片会单批过大。
- **A3-1 最重**：Stage 14/17/22 需同时接线，且 Stage 22 必须与 A2-4/5/6 谓词一致。
- **ArtifactNode 改造面广**：所有 DONE 阶段均需节点，需先定义入树/指针边界。
- **O-1/O-2 已裁决**：分别为 Q-3/Q-4；实现前仍需在 M0 落地 `cap_reason` 与 Stage 14 annotation 生产者。
- **A3-3 断网复算**：要求 digest 可从落盘证据独立重算，不能依赖运行期内存。

## 6. 结论

G3 可开工；先 **P-074 G3 M0 设计冻结**，按 Q-1..Q-9 定稿后再进入 M1。M5 遗留的 O-3/O-5/O-6 可在 M0/M1 顺带处理，O-4/O-7 存档。本文不改变总纲 106 计数。

## 7. M0 决策补充调研与采纳结论（P-070，v1.2）

> 本节对 Q-1..Q-9 逐项给出候选方案、外部证据与明确建议；**v1.2 已将全部建议采纳为 G3 M0 决策**（§4 表状态均为「已采纳」），P-074 设计冻结按此执行。证据等级：T1 = 标准/官方文档，T2 = 学术指南/论文；工程类比标注为「类比」，不冒充直接规范。

### 7.1 Q-1 Stage 20 是否允许 `PARTIALLY_FORMALIZED`

**决策（已采纳）：允许通过，但强制标注。**

- 证据：Lean 官方说明 `sorry` 展开为 `sorryAx`，完成证明不应使用；`#print axioms` 可列出常量传递依赖的全部公理（[S-7][S-8]）。这说明「部分形式化」是可度量、可展示的中间层，不是失败。
- 方案：Stage 20 阻断集仅 `{FALSIFIED, FAILED}`；`PARTIALLY_FORMALIZED` 放行，但 claim 必须带 `formalization_gap`（缺失公理/sorry 位置），导出侧渲染为「部分形式化」，不得显示 `FORMALLY_VERIFIED`。
- 取舍：全阻断会丢弃可用的部分结果；全放行会让 `sorry` 冒充完成证明。A2-7 已给出上限，Stage 20 只需消费该上限。

### 7.2 Q-2 ArtifactNode 是否覆盖 Stage 12 大文件

**决策（已采纳）：只存指针，不入 `blobs/`。**

- 证据：SLSA `ResourceDescriptor` 用 `uri + digest` 描述产物（[S-2]）；DVC 用小型 `.dvc` 占位文件记录 md5 与缓存位置，数据本身不进 Git（[S-6]）；PROV-O 用 `Entity/Activity` 表达生成关系（[S-4]）。
- 方案：`ArtifactNode` 固定 `content_hash + locator + type + producer + parent_ids`；超过阈值（建议 1 MiB）或二进制/敏感产物只存指针；`blobs/` 仅收小型文本；禁止 inline base64。
- 取舍：全量入树会让仓库膨胀且污染导出；全指针会让 AN-4 的旧 evidence 投影难以逐字段相等。折中是「小文本入树、大文件指针」。

### 7.3 Q-3 O-1 封顶后 annotation 语义

**决策（已采纳）：annotation 跟随封顶后的最终状态。**

- 规则：`requires_annotation` 只看最终 `status`；`numerically_verified` 必须有 annotation；被 AR-06/AR-05 封顶到 `latex_verified` 时不强制，但 gate 必须记录 `cap_reason`，导出侧显示「已封顶」。
- 证据：Lean 的公理层级与 `#print axioms` 表明「结论强度」应由最终可验证事实决定（[S-7][S-8]）；OPA 决策日志同时记录 policy revision、input 与结果，而非只记结论（[S-10]）。
- 取舍：按原始状态要求 annotation 会把已封顶 claim 误杀；完全不记录封顶原因会丢失审计信息。

### 7.4 Q-4 O-2 `annotations.json` 生产者

**决策（已采纳）：Stage 14 生产，外部可覆盖，Stage 20 fail-closed。**

- 方案：Stage 14 从数值验证结果生成 `{claim_id: {text, n, ci, metric, source: "stage14"}}`；允许外部 `annotations.external.json` 覆盖并标 `source`；Stage 20 对 `numerically_verified` 缺 annotation 继续阻断；禁止 LLM 自行编造。
- 证据：MLflow 用 tags/metadata 给 run 附加可检索上下文（[S-12]）；DVC 用占位文件承载元数据（[S-6]）。这是「元数据与产物分离」的成熟做法。
- 验收映射：A2-5、A3-1；当前 M5 的 `annotations.json` 无生产者，必须在本项关闭。

### 7.5 Q-5 `pipeline_summary` 防篡改口径

**决策（已采纳）：JCS 规范化 + SHA-256 侧车 + 事件链锚定。**

- 方案：按 RFC 8785 JCS 生成 canonical JSON（[S-1]）；同目录写 `pipeline_summary.sha256`；摘要同时写入 `stage_events.jsonl` 的哈希链（复用 G1a）。`--check` 从 stage 结果/产物重算并与侧车、事件链双向核对；手改 JSON 不重算即失败。
- 证据：SLSA/in-toto 用 subject digest 绑定产物（[S-2][S-3]）；Nix 用内容哈希验证可复现性（[S-15]）。
- 取舍：只把 digest 放在同一 JSON 内可被一起篡改；侧车 + 事件链提供外部锚点。

### 7.6 Q-6 `stage_events` 位置与 `plan_sig`

**决策（已采纳）：run 根 `stage_events.jsonl`，一次 attempt 一条事件。**

- 方案：事件 `{ts, stage, attempt, plan_sig, new_rows, network_error, status}`；`plan_sig = sha256(JCS({stage, queries, filters, sources}))`；`new_rows` 取去重后的新增记录数（PRISMA 的 duplicate removal 口径，[S-9]）；连续 3 次同签名 + `new_rows=0` + 无网络错误 → `PAUSED`；网络错误置 `degraded=true` 且不计入循环。
- 证据：OpenLineage 事件模型以 run/job/dataset + facets 描述执行与产物（[S-5]）；PRISMA 明确区分「识别记录 / 去重 / 筛选」（[S-9]）。
- 验收映射：FC-1..3。

### 7.7 Q-7 RunMandate / StageHandback / prompt_version

**决策（已采纳）：RunMandate 启动即不可变，prompt_version 内容哈希。**

- 方案：`RunMandate {policy_version, scope, strength, requester}` 写入 `run_meta.json`；配置变更只影响新 run，不改变已接受 run；`StageHandback {reason, evidence, requested_scope}` 交回路由，禁止静默扩 scope；`prompt_version = sha256(JCS({system, user_template, model_role, prompt_bank_version}))`，每次 LLM 请求记录。
- 证据：OPA bundle 以 tag + descriptor SHA 固定版本，变更需重新下载/激活（[S-10]）；MLflow Prompt Registry 强调不可变版本与别名（[S-11]）；MLflow Tracking 用 tags 记录上下文（[S-12]）。
- 验收映射：A3-6/7/8。

### 7.8 Q-8 K5 `tb:`/`paper:` 引用门禁

**决策（已采纳）：显式文法 + 未解析即阻断 + 定位。**

- 方案：文法 `^(tb|paper):[A-Za-z0-9][A-Za-z0-9._-]*$`；`tb:` 解析到知识库节点，`paper:` 解析到文献 key；失败返回 `E_K5_UNRESOLVED_REF` 并携带 `{file, line, ref}`；默认严格，不提供静默降级开关。
- 证据：Pandoc 的交叉引用/内部链接在标识符不一致时会失效，官方手册要求标识符与引用一致（[S-14]）；LaTeX 未定义引用会产生 warning 而非静默通过（工程常识，未单列来源）。
- 验收映射：A3-4。

### 7.9 Q-9 敏感产物策略

**决策（已采纳）：只存指针，绝不入 blobs/导出/preview。**

- 方案：`sensitive=true` 节点只保留 `content_hash + locator + type`；不写 `blobs/`、不导出、不生成 preview；日志只记类别不记值；新增审计事件 `artifact.sensitive_skipped`；inline base64 一律阻断。
- 证据：OWASP Logging Cheat Sheet 明确禁止记录访问令牌、PII、密钥、支付数据等（[S-13]）；OWASP DevSecOps 指南要求「记录类别而非值」（[S-16]）。
- 验收映射：AN-6。

## 8. 信息源（S 表）

| # | 来源 | 等级 | 用于 |
|---|---|---|---|
| S-1 | [RFC 8785 JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.pdf) | T1 标准 | Q-5 |
| S-2 | [SLSA Provenance](https://slsa.dev/spec/v1.1-rc1/provenance) | T1 官方 | Q-2/Q-5 |
| S-3 | [in-toto and SLSA](https://slsa.dev/blog/2023/05/in-toto-and-slsa) | T1 官方 | Q-5 |
| S-4 | [W3C PROV-O](https://www.w3.org/TR/prov-o/) | T1 标准 | Q-2 |
| S-5 | [OpenLineage Object Model](https://openlineage.io/docs/next/spec/object-model/) | T1 官方 | Q-6 |
| S-6 | [DVC `.dvc` Files](https://doc.dvc.org/user-guide/project-structure/dvc-files) | T1 官方 | Q-2/Q-4 |
| S-7 | [Lean Axioms](https://leanprover.github.io/doc/reference/latest/Axioms/) | T1 官方 | Q-1/Q-3 |
| S-8 | [Lean: Printing Axioms](https://lean-lang.org/doc/reference/4.21.0/Interacting-with-Lean/) | T1 官方 | Q-1/Q-3 |
| S-9 | [PRISMA 2020 statement](https://www.bmj.com/content/372/bmj.n71) | T2 学术指南 | Q-6 |
| S-10 | [OPA Bundles](https://www.openpolicyagent.org/docs/v0.60.0/management-bundles/) | T1 官方 | Q-3/Q-7 |
| S-11 | [MLflow Prompt Registry](https://www.mlflow.org/docs/latest/genai/prompt-registry/) | T1 官方 | Q-7 |
| S-12 | [MLflow Tracking API](https://www.mlflow.org/docs/latest/ml/tracking/tracking-api) | T1 官方 | Q-4/Q-7 |
| S-13 | [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) | T1 官方 | Q-9 |
| S-14 | [Pandoc User's Guide](https://pandoc.org/MANUAL.html) | T1 官方 | Q-8 |
| S-15 | [A Decade of Software Reproducibility in the Nix Package Ecosystem](https://arxiv.org/html/2501.15919v2) | T2 论文 | Q-5 |
| S-16 | [OWASP DevSecOps: Logging and Monitoring](https://owasp.github.io/DevSecOpsGuideline/2-Process/2-7-Operate/2-7-2-Logging-and-Monitoring/) | T1 官方 | Q-9 |

> **社区问答说明**：本轮检索以标准、官方文档、学术指南为主；社区问答未提供强于上述来源的证据，故未单列。工程实践由 DVC/MLflow/OWASP 官方文档承载。

## 9. v1.3 结论

- Q-1..Q-9 **已全部采纳为 G3 M0 决策**（§4 状态均为「已采纳」），P-074 设计冻结直接按 §7 执行；其中 Q-3/Q-4/Q-7 属工程判断，已在文档中标明依据类型。
- 最高风险仍是 A3-1：它依赖 Q-1/Q-3/Q-4 的裁决与 ArtifactNode；M0 先锁这三项，再排 M3。
- 本文只做调研与决策记录，不改变总纲 106 计数；实现与验收留给 P-074..P-079。

## 10. 变更摘要（v1.3）

| 变更 | 内容 |
|---|---|
| 决策采纳 | Q-1..Q-9 从「建议」升为「已采纳决策」，§4 表新增「状态」列 |
| 关键定稿 | PARTIALLY 放行但标注；大文件指针；annotation 跟随封顶状态；Stage 14 生产 annotation；JCS+侧车+事件链；签名+零新增+网络豁免；RunMandate 不可变；K5 未解析即阻断；敏感产物只存指针 |
| 编号 | P-070 为补充调研批；G3 M0 = **P-074**，M1..M5 = **P-075..P-079**（P-072/P-073 为复核/深挖批） |
| 总纲 | 升至 **v1.3m**，G3 决策闸门由「待裁决」改为「已裁决」 |
| 编号顺延（v1.3） | P-072/P-073 占用后，M0..M5 由 P-071..P-076 顺延为 **P-074..P-079** |
| 代码/测试 | 无变更（T3 Layer-0） |
| 验收影响 | A3-1/A3-2/A3-4/A3-6/7/8、AN-1/5/6、FC-1..3 的设计口径已锁定 |
