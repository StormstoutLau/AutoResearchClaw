---
id: arc-science-workbench-reuse-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-19
depends: [arc-master-roadmap, arc-g1a-event-core]
upstream: null
---

# 调研：Claude Science / OpenAI4S / Open Science 的科研组件吸收与复用

> **Feature**：P-140。分析三系科研工作台的产品能力、社区逆向作品的可复用性，并映射到 AutoResearchClaw 现有组件。
> **Spec 步骤**：Step 1-2（调研批）。
> **结论先行**：最值得吸收的不是「再做一个桌面应用」，而是三类**可嵌入现有 23 阶段流水线**的组件：① 证据/动作账本（ARC 已有 `runtime/event_log.py` 链哈希与 `evidence/`，可扩展）；② pipeline-as-skill（把成功的研究路径固化为可复用技能）；③ Plan/Execute/Review 合同（执行前的计划、风险与预期产物，复用 HITL 门禁）。Code-as-Action 持久内核与算力编排价值高但成本大，列 P2。社区逆向作品中，MIT/Apache 的 OpenAI4S、OpenScience、SciForge 可做**思路与接口级复用**；无许可证的 `cscience` 与基于泄漏源码的 KAIROS **不得复用代码**。

## 1. 产品能力矩阵

| 产品 | 定位 | 关键组件 | 许可证/状态 |
|---|---|---|---|
| **Claude Science**（Anthropic，2026-06-30） | 科学家 AI 工作台 | 60+ 精选 skills/connectors（基因组、单细胞、蛋白、结构、化学）；图表/手稿与代码同源；可审计产物；本机/集群/GPU 算力；会话常驻内存；**pipeline 可保存为可复用 skill**；MCP 连接器；macOS/Linux beta | 闭源商业产品 |
| **Claude for Life Sciences**（更早） | 生命科学连接层 | Benchling、10x Genomics、PubMed、BioRender、Medidata、ClinicalTrials.gov 等 MCP 连接器；引用与权限继承 | 闭源商业产品 |
| **OpenAI4S**（北大—元空，MIT） | 开源复刻 Claude Science | 双行动面：JSON 工具调用负责编排/权限/审批/元数据，Python/R 持久内核负责计算；**Action Ledger**；版本化产物与 provenance；24–30+ skills；BYOC 算力；多模型 provider；只读 Notebook；会话分享 | MIT，668★，Python |
| **OpenScience**（aipoch，Apache-2.0） | 本地优先科研工作台 | 371 skills；37+ 科学数据库；MCP 工具/连接器；Python/R 执行；可追溯产物；算力管理；多会话；基准报告 | Apache-2.0，5.5k★，TypeScript |
| **Open Science Desktop**（ai4s-research） | 计划-执行-复核工作台 | 执行前显式 Plan（来源/步骤/预期产物/风险动作）；本地执行；输出回链代码/数据/引用；Tauri + MCP + skills | NOASSERTION，2.1k★ |
| **SciForge**（AGI4Sci，Apache-2.0） | 研究原生工作台 | 五层架构；**Evidence-DAG** 审计 sidecar；决策记录合同；Scientific Model Router；多角色协作（reviewer/approver、IM 通道） | Apache-2.0，84★，TypeScript |
| **K-Dense BYOK**（MIT） | 桌面 co-scientist | BYOK、多模型、桌面工作台 | MIT，1.4k★ |
| **PaperQA2**（Apache-2.0） | 文献层 | 高精度 RAG、文内引用、撤稿检查 | Apache-2.0 |

**共性抽象**：科研工作台 = 技能/连接器 + 代码执行 + 证据/产物 + 计划/审批 + 模型路由 + 算力。

## 2. 社区逆向作品与许可证风险

| 项目 | 许可证 | 与本仓关系 | 复用判断 |
|---|---|---|---|
| PKU-YuanGroup/OpenAI4S | MIT | 明确「复刻 Claude Science」；双行动面、Action Ledger、持久内核 | **高**：可做思路/接口/局部代码复用，保留版权与许可声明 |
| aipoch/open-science | Apache-2.0 | 371 skills、37 DB、MCP、本地优先 | **高**：技能目录与连接器模式可复用 |
| AGI4Sci/SciForge | Apache-2.0 | Evidence-DAG、决策合同、模型路由 | **高**：治理层最贴近本仓 spec 体系 |
| K-Dense-AI/k-dense-byok | MIT | 桌面 co-scientist、BYOK | 中：UX 与 BYOK 模式 |
| qzzqzzb/OpenClaudeScience | MIT | Claude Science 开源化 | 中：工作台交互 |
| Haleclipse/cscience | **无许可证** | Claude Science Rebuild | **禁止代码复用**；仅可观察产品思路 |
| Jyx0208/claude-science-api-bridge | MIT | 第三方 API 接入 | 低：provider 桥接思路 |
| exon-research/genomi | Apache-2.0 | DNA 专家 agent | 低：领域专用 |
| 「KAIROS / Claude Code leak」逆向 | 基于泄漏源码 | 记忆架构分析 | **禁止**：法律风险高，仅可作反面案例 |

**复用纪律**：MIT/Apache 代码可复用但必须保留 NOTICE/版权；NOASSERTION/无许可证只做行为观察；闭源产品只做能力对标，不复制 UI/资产/文案；泄漏源码一律不接触。

## 3. 与本仓的组件映射

| 外部组件 | 本仓现有接缝 | 差距 | 吸收优先级 |
|---|---|---|---|
| Action Ledger / Evidence-DAG | `researchclaw/runtime/event_log.py`（事件链哈希）、`researchclaw/evidence/`（artifact_node、claim_spine、offline_audit、sidecar） | 缺「动作级」记录与可视时间线；证据与执行动作未统一 | **P0** |
| pipeline-as-skill | `researchclaw/skills/builtin`（20 个 SKILL.md）、`researchclaw/pipeline/stages.py`（23 阶段） | 技能是静态文件，不能把一次成功路径固化为技能 | **P0** |
| Plan/Execute/Review | `researchclaw/hitl/`、`researchclaw/copilot/`、`researchclaw/dashboard/` | 有门禁与反馈，但缺执行前「计划 + 风险 + 预期产物」合同 | **P1** |
| Scientific Model Router | `researchclaw/llm/`、`researchclaw/agents/` | 有模型配置，缺按能力/成本/延迟路由与可追溯选择 | **P1** |
| 技能/连接器目录 | `researchclaw/tools/registry.yaml`（6 个工具）、`researchclaw/domains/profiles`（10+ 域） | 技能与连接器数量少；缺 UniProt/PDB/ChEMBL/PubMed 等科学连接器 | **P1** |
| 代码即行动 / 持久内核 | `researchclaw/pipeline/code_agent.py`、`executor.py`、`experiment/` | 以脚本/阶段执行为主，缺常驻 Python/R 内核与 host RPC | **P2** |
| 算力编排 | `resource_planning` 阶段、`runtime/` | 缺本机/集群/GPU 适配与成本预算 | **P2** |
| 只读 Notebook / 审计视图 | `dashboard/`、`evidence/` | 缺产物版本时间线与只读审计视图 | **P1** |

## 4. 吸收建议（供后续实施批）

### P0

1. **统一证据/动作账本**：在现有事件链上增加 `action` 记录（工具、参数、环境、随机种子、输入/输出产物哈希、审批人），复用 `verify_chain` 做离线校验；证据 DAG 与事件流双向可查。
2. **pipeline-as-skill**：定义 `SkillManifest`（阶段子图、配置、依赖、连接器、验收读点、版本），支持「一次成功运行 → 固化为技能 → 下次复用」；技能加载器复用现有 `skills` 机制。

### P1

3. **Plan/Execute/Review 合同**：在 Stage 9（实验设计门禁）前产出计划产物：来源、步骤、预期产物、风险动作、回退；HITL 审批后再执行。
4. **Scientific Model Router**：按任务类型/上下文长度/成本/延迟选择模型与工具；选择理由写入账本。
5. **技能/连接器扩展**：优先补 UniProt、PDB、ChEMBL、PubMed、arXiv 五个连接器；技能目录按领域分层。
6. **产物时间线**：dashboard 增加只读时间线，按 artifact 版本回链代码、数据、引用与审批。

### P2

7. **Code-as-Action 持久内核**：Python/R 常驻内核 + host RPC；需沙箱、资源配额与安全边界，单独立项。
8. **算力编排**：本机/集群/GPU 适配、预算与排队；需与 runtime/supervisor 协同。

## 5. 不吸收清单

- 闭源 Claude Science 的 UI、文案、资产、协议实现。
- 无许可证 `cscience` 的任何代码。
- 基于泄漏源码的 KAIROS 逆向实现。
- 桌面应用壳（Tauri/Electron）本身：本仓是 CLI/服务端优先，桌面壳不是当前瓶颈。

## 6. 未决项

| ID | 内容 | 判据 | 当前倾向 | 证据等级 |
|---|---|---|---|---|
| U-1 | 证据账本是否复用 G1a 事件流还是新建存储 | 写入频率、查询模式 | 复用事件流，新增 action 类型 | E1 |
| U-2 | pipeline-as-skill 的版本粒度 | 阶段子图 vs 整条流水线 | 阶段子图 + 配置快照 | E1 |
| U-3 | 模型路由是否引入外部配置 | 模型数量与变更频率 | 先静态能力表，后动态 | E1 |
| U-4 | 持久内核的安全边界 | 沙箱/配额/审计 | 单独立项，不在 P0/P1 夹带 | E1 |

## 7. 诚实边界

- 外部产品能力来自公开页面与仓库元数据，未做逆向或私有接口验证。
- star 数与许可证为 2026-11-19 的 GitHub API 读数，会变化。
- 本批不实施任何代码；P0/P1 仅为后续批次候选，需单独立项与验收。
- 社区作品的「可复用」仅指许可证允许的代码/接口，不代表质量或安全性背书。
