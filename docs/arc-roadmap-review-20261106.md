---
id: arc-roadmap-review-20261106
type: design
version: 0.1
status: draft
date: 2026-11-06
depends: [arc-master-roadmap]
upstream: arc-master-roadmap
---

# ARC 总纲及关联调研文档 · 审查报告

> **审查对象**：[arc-master-roadmap.md](../arc-master-roadmap.md)（v0.1，12 阶段 / 106 条验收）及其 14 份关联文档。
> **审查依据**：[SPEC_PROCESS.md](../SPEC_PROCESS.md) §Review 检查清单、RULE-1..6、ADD 四阶段与取证矩阵（E1–E5）。
> **审查性质**：独立 pass（非文档作者同一次写入），结论标注 `[已复核]`；单 Agent 单视角，RULE-4/5 局限见 §6。
> **本轮不改动任何被审文档**，只输出问题清单与修复建议。

---

## 0. 取证矩阵（RULE-6）

| 取证手段（等级） | 覆盖项 | 结果 |
|---|---|---|
| `git ls-tree` / `git log` / `git fsck`（E1） | 文档提交状态、历史清理完整性 | ✅ 零残留；15 份文档已不在任何 ref |
| `rg --no-ignore` 全仓符号检索（E1，可原样重放） | H-1..H-8 的 8 条代码事实 | ✅ 8/8 成立 |
| `python -c` 读取源 JSON 计数（E2，场景自选：源文件直读） | G5 的 2,487 / 1,824 / 20,235 | ✅ 三数与源文件完全一致 |
| 静态读码（E3，绑定 `7d0e70a`） | executor/config/runner/stage_impls 锚点行号 | ✅ 全部在范围内且语义匹配 |
| WebSearch/WebFetch（E4，扫描范围：26 条外部引用） | arXiv 编号、标准、开源项目 | **发现 6 项不匹配** |
| 脚本解析 front-matter（E2） | 14 份文档的 id / depends / upstream 闭合 | **发现 6 条断链** |
| 人工一致性比对（E4，扫描范围：§0–§11 全部交叉引用） | 阶段依赖、验收计数、C 套件覆盖 | **发现 6 项内部矛盾** |

---

## 1. Review 规则执行结论

| 规则 | 结论 | 说明 |
|---|---|---|
| **RULE-1 时序独立** | ✅ 满足 | 本次为独立 pass，非与正文同一次写入 |
| **RULE-2 统计溯源** | ⚠️ 部分 | 106 条验收计数可逐阶段复算一致；但 A2-3「65 项 verdict 测试」口径无法复现（见 P2-07） |
| **RULE-3 环境确定性** | ❌ 不满足 | A1-3 `kill -9`、A1-7 退出码 137 以 Linux 语义书写，Windows 开发机不可原样验收（见 P2-08） |
| **RULE-4 单 Agent 自查** | ⚠️ 声明 | 本报告为**单视角**审查；代码核验与外部核验由两个子任务分工，但同一基座 |
| **RULE-5 异质基座** | ❌ 未满足 | 未引入不同模型家族的对抗审查；本报告不构成最终合规结论 |
| **RULE-6 证据绑定** | ✅ 满足 | 见 §0；每条 P1/P2 均绑定 E1–E4 证据，无 E5 推测入结论 |

---

## 2. 发现清单

### P1 · 阻断（进入 G-1 前必须修）

| ID | 问题 | 证据 | 影响 |
|---|---|---|---|
| **P1-01** | [arc-master-roadmap.md](../arc-master-roadmap.md#L296) 第 296 行称「`retrieval_degraded` 标记（**H-4 已落地**，G3 接入门禁）」，但第 165 行将 H-4 列为 G-1 待做项，且 §0.3 R1 明确 G-1 尚未执行 | E3 @`7d0e70a` L165 vs L296；`rg retrieval_degraded` 全仓 0 命中 | G3 的 A3-5 以「H-4 已落地」为前提，实际该字段不存在；进入 G3 会得到恒假验收 |
| **P1-02** | §5 跨阶段一致性套件**未覆盖 H-1..H-4**：C-3 只列 A3-x/AN-x，C-4 只列 A4-x + H-6..H-8，C-7 只列 H-5 | E3 @`7d0e70a` L528–L537 | G-1 的「数据正确性」四项无回归闸门；G-1 出口只能靠一次性人工验收，违反 §5「每阶段结束 C 套件全绿」 |

### P2 · 应修（对应阶段开工前）

| ID | 问题 | 证据 | 影响阶段 |
|---|---|---|---|
| **P2-01** | 依赖 ID 断裂：`academic-reasoning-base-fusion.md` **无 `id` 字段**，但被 3 份文档的 `depends/upstream` 引用；`orchestration-capability-matrix.md` 引用 `clawsgo-research-orchestration-landscape`，实际 id 为 `clawsgo-orchestration-landscape` | E2 脚本解析：6 条 UNRESOLVED | 全局可追溯性 |
| **P2-02** | arXiv 2609.00006 被用于「校准四层拆解」，但论文实际提出 **7 个 canonical subsystems**；且文档 F17 自述仅检索到标题与摘要片段 | E4 WebFetch arxiv.org/abs/2609.00006 | G1、G4 |
| **P2-03** | PROV-O 字段名写作 `generatedBy`，正式名为 **`wasGeneratedBy`** | E3 [roadmap L279](../arc-master-roadmap.md#L279) vs w3.org/TR/prov-o | G2、G5 |
| **P2-04** | MCP 2026-07-28 被称「MCP v2」；规范不自称 v2（v2 是 SDK 叫法），且该版**移除了 Streamable HTTP 的 `Last-Event-ID` 与消息重投递** | E4 modelcontextprotocol.io/specification/2026-07-28/changelog | G4（G1 用 WHATWG，不受影响） |
| **P2-05** | 「E2B / Daytona / Firecracker 三档隔离」是类别错误：Firecracker 是 VMM 组件（E2B 基于它），Daytona 默认 runc 容器 | E4 e2b.dev/security、firecracker 文档 | G4（A4-2 隔离强度被高估） |
| **P2-06** | Kosmos「逐句引用到代码/文献」被列为可直接借鉴点，但论文只说生成带引用的报告；§11 已承认无量化结论，§9.3 未同步标注 `[推断]` | E4 arxiv.org/abs/2511.02824 + 文档内部不一致 | G3、G7 |
| **P2-07** | A2-3「既有 65 项 verdict 测试」无法复现：含 `verdict` 的 4 个测试文件共 **77** 个 `def test_`，筛选口径未说明 | E1 `rg -c "def test_"` | G2 |
| **P2-08** | A1-3 用 `kill -9`、A4-3 用退出码 137 表述，均为 Linux 语义；本机 Python 3.13.5 / Windows，无法原样重放 | E1 环境 + E3 文档 | G1、G4 |
| **P2-09** | ClawsGO（逆向对象）与 ClawGo（clawgo.com 商业运行时）混用，§9.2 直接以 ClawGo 四象限作为 G1/G4 参照，未说明二者是否同一实体 | E4 clawgo.com vs 逆向报告命名 | G1、G4 |
| **P2-10** | 「From Copilots to Colleagues」L1–L5 作 ARC 自评标尺，但该文为个人站点自出版、自述 99% 由 AI 生成，非同行评审 | E4 victorchen96.github.io | G0a |

### P3 · 提示

| ID | 问题 | 证据 |
|---|---|---|
| **P3-01** | §7 标题写「尚未裁决的 10 项」，表内实为 Q1–Q16 共 **16** 项 | [L568](../arc-master-roadmap.md#L568) |
| **P3-02** | §10 称「3 道钩子即可」，G0a 实际安装 **4** 道激活钩子（dc/step/console/rework），Q11 也写 3 道 | [L653](../arc-master-roadmap.md#L653) vs §4 G0a |
| **P3-03** | C-3 漏 A3-5、C-4 漏 A1-8（CORS）、C-5 漏 A0a-4 | [L532–L534](../arc-master-roadmap.md#L532-L534) |
| **P3-04** | §11 依据表只列 8 份，另 7 份关联文档未标注「并入」去向 | [L666–L677](../arc-master-roadmap.md#L666-L677) |
| **P3-05** | A2-3 写「Python 3.11 跑通」，本机为 3.13.5；CI 矩阵含 3.11 但本地无 3.11 验证记录 | E1 |
| **P3-06** | `docs/` 下 6 份设计文档的 `type: design` 与根目录 3 份同类文档一致，但 `depends` 使用 id 而非路径，dc-validator 只校验字段存在、不校验可解析，断链长期不可见 | E2 |

---

## 3. 已核验为真（不需返工）

| 断言 | 结论 | 证据 |
|---|---|---|
| H-1 Stage 12 `run-1.json` 未写 `returncode` | ✅ 成立 | [_execution.py L575-L597](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/pipeline/stage_impls/_execution.py#L575-L597) 载荷无该键 |
| H-2 `max_retries` 有定义无消费 | ✅ 成立 | [contracts.py L21-L26](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/pipeline/contracts.py#L21-L26) 定义；`executor.py` 仅用 `contract.output_files/input_files` |
| H-3 `ClaimVerifier` 无生产调用 | ✅ 成立 | [claim_verifier.py L68-L109](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/hitl/claim_verifier.py#L68-L109)；仅 `tests/test_hitl_verifier.py` 引用 |
| H-4 `retrieval_degraded` 不存在 | ✅ 成立 | 全仓 0 命中 |
| H-5..H-8 安全三项 | ✅ 成立 | [sandbox.py L324](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/experiment/sandbox.py#L324) `{**os.environ}`；[client.py L69](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/mcp/client.py#L69) `dict(os.environ)`；[_execution.py L1140-L1144](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/pipeline/stage_impls/_execution.py#L1140-L1144) 无围栏；[config.py L748](file:///d:/AutoResearchClaw-main/AutoResearchClaw-main/researchclaw/config.py#L748) `("*",)` |
| G5 三组数字 | ✅ 与源一致 | `Paper_Organized_v2_report.json` → 2,487；`knowledge_graph.json` → 1,824 / 20,235 |
| 106 条验收计数 | ✅ 复算一致 | 4+8+6+12+7+17+10+14+5+15+4+4 = 106 |
| 13 个外部锚点主体 | ✅ 真实存在 | arXiv 2511.02824 / 2505.13400 / 2603.14312 / 2608.30661 / 2505.19955 等标题均匹配 |
| `execute_stage` / 快照 / `problem_tree` / `exp_plan` | ✅ 行号与语义匹配 | executor L613、runner L1264、_topic L176、_experiment_design L593 |

---

## 4. 工程路线可行性复核

| 维度 | 结论 | 依据 |
|---|---|---|
| **关键路径** | ✅ 合理 | `G0a → G-1 → G3` 确实能独立支撑「不产出假结果」；G1/G2 可并行，G4/G5/G8a 可并行 |
| **前置完整性** | ⚠️ 有缺口 | G-1 不依赖未裁决项，可开工；G0b 依赖 Q3/Q11，G4 依赖 Q10，G5 依赖 Q4/Q6/Q7，G7 依赖 Q13，G8a 依赖 Q15 —— §7 规则「未裁决不得进入」意味着这些阶段目前均不可启动 |
| **验收可机械判定** | ⚠️ 部分 | 106 条中约 90 条可机械判红；A2-3（65 项）、A4-3（137）、A7-1（72h）、A7-5（30 分钟）等 6–8 条依赖人工或长跑，需单独定义口径 |
| **平台可移植性** | ❌ 缺口 | `kill -9`、SIGKILL/137、`/tmp` 路径语义在 Windows 上不成立；CI 三平台矩阵未在验收项中体现 |
| **成本/资源** | ⚠️ 未估 | G7 的 72h soak + N 并发、G5 的 2,487 条导入、G1 的 kill -9 故障注入均未给资源上限；仅 G7 有 `max_concurrent_attempts` 概念 |
| **回滚与止损** | ✅ 明确 | I-1..I-5 全局不变量 + 每阶段硬出口 + 「只能做三件事」的最短路径，止损设计成立 |
| **洁净室边界** | ✅ 明确 | §8 红线（不抓私有 API、不逆向二进制、不复制资产）与 ClawsGO 反模式使用方式一致 |

---

## 5. 结论

1. **事实底座可信**：8 条代码事实 8/8 成立，Paper/Textbook 三组数字与源文件完全一致，106 条计数复算无误，13 个外部锚点主体真实。总纲不是凭空生成的路线图。
2. **存在 1 个逻辑硬伤**（P1-01「H-4 已落地」）与 **1 个门禁缺口**（P1-02 C 套件未覆盖 H-1..H-4），必须在 G-1 开工前修正；否则 G3 的 A3-5 会以不存在的字段为前提通过或恒假。
3. **10 项 P2 不影响路线方向，但影响阶段准入**：其中 P2-01（依赖断链）、P2-04（MCP 版本语义）、P2-05（隔离档位）会直接改变 G4 的设计输入，应在 G4 的 RESEARCH 文档中先行更正。
4. **可行性结论**：`G0a → G-1` 可以立即推进（G0a 已完成，G-1 无未裁决前置）；`G0b` 之后各阶段受 Q3/Q10/Q15 等未裁决项阻塞，符合 §7 规则，不需要额外干预。
5. **审查局限**（RULE-4/5）：本报告为单基座、单视角审查，未做异构模型对抗复审；外部引用核验为「存在性 + 标题匹配」级别，未逐篇读全文验证因果结论；代码证据绑定 `7d0e70a`，重构后行号会腐烂。

---

## 6. 建议的最小修复顺序

1. 修 P1-01：把 L296 改为「H-4 待落地（G-1），G3 接入门禁」，或在 G-1 CHECKLIST 中显式标注依赖。
2. 修 P1-02：在 C-3 增补 H-1/H-2，在 C-4 增补 H-3/H-4 与 A1-8，在 C-5 增补 A0a-4。
3. 修 P2-01：给 `academic-reasoning-base-fusion.md` 补 `id`，把 `clawsgo-research-orchestration-landscape` 改为 `clawsgo-orchestration-landscape`。
4. 其余 P2 在对应阶段的 `RESEARCH.md` 中作为「已识别偏差」登记，不阻塞 G-1。
