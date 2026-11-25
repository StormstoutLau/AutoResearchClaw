# Auto Prover 分阶段接入决策记录

---
id: auto-prover-phased-integration-decision
type: design
version: 1.0
status: decided
date: 2026-11-25
depends: [arc-g2-decisions, failure-guards-design, arc-g7-drift-guard-DESIGN]
upstream: arc-master-roadmap
---

> **决策**：Auto Prover（AP）不再作为「整体跟随上游」的依赖接入；改为 **冻结内核 + skill 化复用架构与逻辑 + 三阶段递进**。
> **一句话**：G2 已交付的 27 文件判定内核与 Lean sidecar 继续作为**执行底座**；AP 仍在演进的部分（Lean/ATLAS/MCP/检索/证明回路）以 **ARC SKILL.md 技能**承载其**架构与逻辑**，不随上游代码膨胀。
> **本记录性质**：Layer-0 决策落档（T3，零代码/零门禁变更）；不改变 G2 已交付物与既有裁决（Q1=B 双轨、Q2=B 最小 vendor + sidecar + Lean 可选）。

---

## 1. 现状（一手事实）

### 1.1 仓内已有（T1：源码/实测）

| 事实 | 证据 |
|---|---|
| AP 内核已 vendor：27 文件、上游 `bd95f02` / v3.7.0、Apache-2.0，含 LICENSE/NOTICE/SOURCE.json（逐文件 sha256） | [vendor/auto_prover/README.md](../../researchclaw/vendor/auto_prover/README.md) |
| vendor 面 = datatypes 9 + verdict 3 + sandbox 4 + semantic_verdict + model_gateway + kg 3 + stages 5 + verdict_recheck | 同上 §1 |
| 明确**不 vendor**：`stages/` 的 Lean/ATLAS 部分、`kg` 导入写回、`mcp_servers`、`atlas_bridge`、`lean4_cases`、AP 的 spec/docs | 同上 §1（P-043 §8.3、V-5） |
| Lean 走 **sidecar**：文件型 JSON 契约、每请求一进程、硬超时、`taskkill /T` 兜底、窄校验；退出码 0/65/75/78 | [evidence/sidecar.py L36-L74](../../researchclaw/evidence/sidecar.py#L36-L74) |
| G2 已收口 M0–M5（契约 / AR 判据 / 内核 vendor / sidecar+Lean / Stage 9/20/23 接线 / 离线审计） | [arc-master-roadmap.md v1.3j/v1.3k](../arc-master-roadmap.md) |
| 双平面一致性：`compare_claims` 为 Stage 23 与离线审计的**唯一比对实现**；`E23_CLAIM_DRIFT` | [evidence/claim_policy.py](../../researchclaw/evidence/claim_policy.py)、[evidence/offline_audit.py](../../researchclaw/evidence/offline_audit.py) |
| ARC 已有 **skills 子系统**：agentskills.io `SKILL.md`、`load_skill_from_skillmd` / `load_skills_from_directory`、registry/matcher/schema；内置分类 `writing/domain/experiment/tooling` | [skills/loader.py L18-L111](../../researchclaw/skills/loader.py#L18-L111)、[skills/schema.py L37-L57](../../researchclaw/skills/schema.py#L37-L57) |
| 内置技能以目录 + `SKILL.md` frontmatter 组织（name/description/metadata.category/trigger-keywords/applicable-stages/references） | [builtin/experiment/hypothesis-formulation/SKILL.md](../../researchclaw/skills/builtin/experiment/hypothesis-formulation/SKILL.md) |
| 漂移护栏已落地（FA-1..FA-3），Stage 15 PAUSE 语义复用既有状态机 | [guards/drift.py](../../researchclaw/guards/drift.py)、[spec/arc-g7-drift-guard/DESIGN.md](../../spec/arc-g7-drift-guard/DESIGN.md) |

### 1.2 上游 AP 仍在演进（T1：GitHub API，2026-11-25 实测）

| 项 | 读数 |
|---|---|
| 仓库 | `StormstoutLau/Auto_Prover`，Apache-2.0，stars 0，open issues 0 |
| 最近推送 | **2026-11-25**（本决策当日仍在提交）；仓库体积 9,242 KB |
| `proof_pipeline/` 顶层 | **30 项**：`atlas_bridge`、`lean_meta`、`lean4_project`、`mcp_servers`、`proof_graph`、`context_compression`、`heuristic_calibration`、`mathematica_bridge/support`、`pipeline/pipeline_support`、`d6_evidence`、`t12_input`、`case_sanitizer`、`metrics`… |
| 与 vendor 面比对 | vendor 仅 8 个子路径（27 文件）；**上游还有 20+ 模块未纳入**，且仍在变动 |

**结论**：全量跟随上游 = 无限追更；必须冻结边界、只复用**架构与逻辑**。

### 1.3 社区可复用面（T1/T2，已回原文）

| # | 项目 | 许可 / 反馈 | 可复用点 | 不采用 |
|---|---|---|---|---|
| C-1 | [cameronfreer/lean4-skills](https://github.com/cameronfreer/lean4-skills) | MIT，**500★**，2026-11-08 活跃 | 12 个工作流（draft/formalize/autoformalize/prove/autoprove/disprove/checkpoint/review/refactor/golf/learn/diagnose）；共享证明环 **Plan → Work → Checkpoint → Review → Replan → Continue/Stop**；`autoprove` 的**显式停止预算**；host-agnostic `SKILL.md` 组织；与 MCP 的可选组合 | 不整包引入其 12 条命令面；不采用其 Claude Code 插件钩子 |
| C-2 | [oOo0oOo/lean-lsp-mcp](https://github.com/oOo0oOo/lean-lsp-mcp) | MIT，**565★**，2026-11-03 活跃 | Lean LSP MCP：live goal 检查、mathlib 搜索、比全量 build 快得多的反馈回路 | 本阶段不强制依赖；仅作 S2 可选桥 |
| C-3 | [lean-dojo/LeanDojo](https://github.com/lean-dojo/LeanDojo) | MIT，**855★**，NeurIPS 2023 oral | 程序化与 Lean 环境交互、前提标注、数据抽取；benchmark（98,734 定理） | 不引入其 GPU 训练栈 |
| C-4 | [lean-dojo/ReProver](https://github.com/lean-dojo/ReProver) | MIT，**340★** | 检索增强前提选择（premise selection）的工程形态 | 不训练模型 |
| C-5 | [deepseek-ai/DeepSeek-Prover-V2](https://github.com/deepseek-ai/DeepSeek-Prover-V2) | 开源权重，**1332★**；MiniF2F-test 88.9% | 子目标分解式 RL 证明范式；作模型后端候选 | 不作默认依赖（体积/算力） |
| C-6 | [lean-dojo/LeanCopilot](https://github.com/lean-dojo/LeanCopilot) | MIT，**1350★** | 编辑器内 tactic 建议 + 前提检索的交互形态 | 不接其 VS Code 侧 |
| C-7 | [VeryMath/AI4Math-Lean-Agents](https://github.com/VeryMath/AI4Math-Lean-Agents) | MIT，9★，2026-11-03 | 「formalization / proof repair / machine-checked math」skills 与工作流的同类组织方式 | 星标低，仅作形态参考 |
| C-8 | [AxiomMath/axle-mcp-server](https://github.com/AxiomMath/axle-mcp-server) | MIT，38★ | Lean 基础设施的 MCP 形态（对照我们 sidecar 的 JSON 契约） | 不接第三方基础设施 |

学术侧（T1，arXiv abs 原文）：LeanDojo/ReProver（2306.15626，NeurIPS 2023 oral）、DeepSeek-Prover-V2（2504.21801，88.9% MiniF2F-test）、Kimina-Prover（2504.11354，80.7% pass@8192，开源 1.5B/7B 蒸馏）、Goedel-Prover（2502.07640，57.6% pass@32 SFT 起）、Pythagoras-Prover（2606.12594，4B 86.1% pass@32 超 671B 的 82.4%，32B 93.0% 开源 SOTA）。

> 降级记录：`mcp_english-search` 连续 HTTP 522；改用 GitHub API + arXiv abs 直取，以上读数均为一手。

---

## 2. 问题

1. **追更成本**：AP 上游当日仍在提交，`proof_pipeline/` 有 30 个顶层模块，vendor 面只有 8 个；每扩大一次 vendor 面就要重跑冻结用例、重做许可与 sha256。
2. **依赖体重**：Lean/ATLAS/MCP/mathematica 桥与 ARC 主环境冲突（Q1/Q2 已裁决：3.11 内核 + 3.12 sidecar，Lean 不得为安装前置）。
3. **复用诉求错位**：我们真正需要的是 AP 的**判定架构与证明逻辑**（判定出口唯一、证据分层、深度封顶、失败分类），不是它的全部实现。
4. **已有承接点**：ARC 的 `SKILL.md` 技能系统已能承载「工作流 + 契约 + 触发条件」，且内置技能已用 `references` 字段记录改编来源。

---

## 3. 决策

| 编号 | 决策 | 被拒绝的替代方案 | 拒绝理由 / 代价 |
|---|---|---|---|
| **D-1** | **冻结 vendor 边界**：维持 27 文件内核，不因上游新增模块而扩面；仅在「内核判定语义变更」或「安全修复」时按 README §3 重取并重跑 65 项 | ① 跟随上游全量 vendor；② 完全移除 vendor 改纯 sidecar | ① 追更无底、许可与 sha 维护成本线性增长；② 3.11 判定内核是 A2-3 的验收对象，移除即违约。代价：新能力只能经 skill/sidecar 表达 |
| **D-2** | **以 skill 为接入主通道**：把 AP 的架构与逻辑写成 ARC `SKILL.md` 技能（工作流、判定顺序、预算与停止条件、失败分类），执行仍调用既有 sidecar；复用「架构/逻辑」，不复用「代码体积」 | ① 继续在 `researchclaw/evidence/` 内联证明逻辑；② 把 lean4-skills 整包 vendor | ① 内联会成为第二个判定实现，与 `verdict` 唯一出口冲突；② 500★ 仓库含 12 命令 + 钩子 + 子 agent，体量与宿主耦合都超需求。代价：skill 文本需人工维护与版本化 |
| **D-3** | **三阶段递进**（S1 技能骨架 → S2 工具桥 → S3 自动证明回路），每阶段独立验收、可单独回退 | 一次性交付完整证明能力 | 单批无法同时覆盖技能、工具、预算与双平面；失败无法归因。代价：见效慢一阶段 |
| **D-4** | **社区复用按「形态参考 + 许可合规」**：工作流与共享证明环参考 C-1；LSP 反馈回路参考 C-2；前提检索参考 C-3/C-4；模型后端仅登记候选（C-5/C-6） | 直接依赖任一社区包为运行时 | 每个包都带自己的运行时假设（MCP 版本、Lean 版本、GPU），会把 ARC 安装面撑破。代价：需自行实现薄适配 |
| **D-5** | **许可与合规沿用 G2 V-1..V-6**：新增 vendor 一律带 LICENSE/NOTICE/`SOURCE.json`/修改声明；skill 文本若改编自 C-1/C-7 须在 frontmatter `metadata.references` 注明来源与许可 | 只在 NOTICE 里笼统致谢 | 无法逐文件追溯，等于放弃合规审计。代价：每次改编多一行元数据 |
| **D-6** | **失败语义统一**：证明失败必须落到既有 `FAILED/partially/formally_verified` 与 `E20_CLAIM_CONTRACT`/`E23_CLAIM_DRIFT`，禁止 skill 自造状态；预算与停止条件显式化（对齐 C-1 `autoprove` 的 explicit stop budgets） | skill 内自定义「差不多证明成功」 | 会重演 G3 M3 的 D-1（示例标记误阻断）类问题；也违反「不产出假结果」总纲红线。代价：skill 需多写状态映射表 |
| **D-7** | **Lean 仍非安装前置**：无 Lean 时深度封顶（沿用 A2-7 与 sidecar 现有行为）；技能必须声明 `requires: lean_optional` | 把 Lean 作为 S1 前置 | 违反 Q2 裁决与总纲 A2-7（Lean 非 pip 分发）。代价：无 Lean 环境职能做形式化草稿与静态审阅 |
| **D-8** | **技能落位**：新增 `researchclaw/skills/builtin/formal/`（与 domain/experiment/tooling 并列），首批 1 个技能 `lean4-formal-verification`；不新增顶层包 | 放进 `tooling/` 复用现有分类 | `tooling` 语义是工具用法，形式化验证是独立能力面；混放会削弱 matcher 的触发精度。代价：需在 `VALID_CATEGORIES` 增加 `formal` |

---

## 4. 阶段计划

### S1｜技能骨架（本决策后可立即开工）

| 项 | 内容 |
|---|---|
| 交付物 | `researchclaw/skills/builtin/formal/lean4-formal-verification/SKILL.md`；`VALID_CATEGORIES` 增 `formal`；技能契约节（状态映射、预算、停止条件、失败分类） |
| 复用 | AP 判定架构（判定出口唯一、深度封顶）+ C-1 共享证明环与工作流命名 |
| 验收 | 技能可被 `load_skills_from_directory` 加载；frontmatter 字段齐全（name/description/category/trigger-keywords/applicable-stages/references）；状态映射覆盖 `formally_verified/partially/FAILED` 三态；无 Lean 时有显式降级说明 |
| 依赖 | 无新三方依赖；不装 Lean |
| 回退 | 删除该目录与 `formal` 分类即可，零运行时影响 |

### S2｜工具桥（可选，按需）

| 项 | 内容 |
|---|---|
| 交付物 | skill 内声明可选 MCP 桥（C-2 lean-lsp-mcp）的**接入契约**（不打包、不默认注册）；sidecar 增加「LSP 优先、build 回退」的可选路径说明 |
| 复用 | C-2 的 live goal / mathlib 搜索形态 |
| 验收 | 未注册 MCP 时行为与 S1 完全一致；注册后仅影响反馈速度，不改变判定结果；两次路径判定一致 |
| 依赖 | Lean 环境（显式 opt-in） |
| 回退 | 移除 MCP 声明即回到 S1 |

### S3｜自动证明回路（最后）

| 项 | 内容 |
|---|---|
| 交付物 | `prove/autoprove` 型工作流的预算与停止条件实现（对齐 C-1 显式预算）；与 Stage 15 漂移护栏、Stage 20/23 claim 双平面联动；子目标分解的记录格式 |
| 复用 | C-1 的 Replan 语义；C-5 的子目标分解范式（仅范式，不引模型） |
| 验收 | 超预算/无进展时必须显式停止并落状态，不得静默继续；同一 claim 双平面一致；PAUSE 复用既有 `StageStatus` |
| 依赖 | S1 + S2 完成 |
| 回退 | 关闭 autoprove，仅保留交互式 prove 工作流 |

---

## 5. 未决项

- **U-1 首批技能粒度**：单技能 `lean4-formal-verification` 还是拆 `draft/prove/review` 三技能。判据：matcher 触发精度 + 技能体积；倾向单技能 + 内部分节（对齐 C-1「一个核心 skill + 多命令」的组织），触发条件：S1 设计时。证据等级 E1。
- **U-2 S2 是否引入 MCP**：ARC 当前无 MCP 客户端，Q10（MCP 协议版本对齐）仍未裁决。判据：`lean-lsp-mcp` 的 MCP 版本与 ARC 目标版本兼容矩阵；倾向 S2 只写契约不接客户端，触发条件：Q10 裁决后。
- **U-3 模型后端**：是否接入 C-5/C-6 作为 tactic/证明生成后端。判据：体积、许可、离线可用性、G6 预算治理；倾向仅登记候选，触发条件：G6 预算参数实测后。
- **U-4 与 AP 上游的关系**：是否向上游贡献技能（反向输出）。判据：上游是否接受 skill 层抽象；倾向先在本仓稳定，触发条件：S1 验收后。

---

## 6. 风险与红线

| 风险 | 触发信号 | 处置 |
|---|---|---|
| skill 与 sidecar 判定口径分歧 | 同一输入两路给出不同状态 | `compare_claims` 仍为唯一比对实现；skill 只描述流程不含判定逻辑 |
| 追更诱惑 | 上游新增模块被要求「顺手 vendor」 | D-1 冻结边界；扩大 vendor 必须新开批次并重做 V-1..V-6 |
| 技能文本腐化 | SKILL.md 引用不存在的 stage/状态 | S1 验收含字段与状态枚举机械校验 |
| 合规遗漏 | 改编段落无 references | D-5 强制 frontmatter 标注 |
| Lean 缺失导致静默降级 | 无 Lean 仍报 `formally_verified` | D-7 + sidecar 既有深度封顶；负向测试必红 |

---

## 7. 参考

1. 本仓：[vendor/auto_prover/README.md](../../researchclaw/vendor/auto_prover/README.md)、[spec/arc-g2-decisions/RESEARCH.md](../../spec/arc-g2-decisions/RESEARCH.md)、[evidence/sidecar.py](../../researchclaw/evidence/sidecar.py)、[skills/loader.py](../../researchclaw/skills/loader.py)。
2. 上游：`StormstoutLau/Auto_Prover`（Apache-2.0，2026-11-25 仍在推送，`proof_pipeline/` 30 个顶层模块）。
3. [cameronfreer/lean4-skills](https://github.com/cameronfreer/lean4-skills)（MIT，500★）：12 工作流 + 共享证明环 + 显式停止预算。
4. [oOo0oOo/lean-lsp-mcp](https://github.com/oOo0oOo/lean-lsp-mcp)（MIT，565★）：Lean LSP MCP。
5. [lean-dojo/LeanDojo](https://github.com/lean-dojo/LeanDojo)（MIT，855★）、[ReProver](https://github.com/lean-dojo/ReProver)（MIT，340★）、[LeanCopilot](https://github.com/lean-dojo/LeanCopilot)（MIT，1350★）。
6. [deepseek-ai/DeepSeek-Prover-V2](https://github.com/deepseek-ai/DeepSeek-Prover-V2)（1332★）。
7. arXiv：2306.15626（LeanDojo/ReProver，NeurIPS 2023 oral）、2504.21801（DeepSeek-Prover-V2，88.9% MiniF2F-test）、2504.11354（Kimina-Prover，80.7% pass@8192）、2502.07640（Goedel-Prover，57.6% pass@32 SFT）、2606.12594（Pythagoras-Prover，4B 86.1% / 32B 93.0%）。
8. [VeryMath/AI4Math-Lean-Agents](https://github.com/VeryMath/AI4Math-Lean-Agents)（MIT，9★）、[AxiomMath/axle-mcp-server](https://github.com/AxiomMath/axle-mcp-server)（MIT，38★）。
