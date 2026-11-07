---
id: arc-roadmap-gaps-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-07
depends: [arc-master-roadmap, arc-runtime-backend-audit-20261107]
upstream: arc-master-roadmap
---

# 调研：总纲完备度与执行盲区

> **前序**：[总纲](../../arc-master-roadmap.md) v0.3；P-002 审查（`docs/arc-roadmap-review-20261106.md`）；P-004 前置备忘（[运行时后端审计](../../docs/arc-runtime-backend-audit-20261107.md)）。
> **本批目标**：把 2026-11-07 的完备度审计**落档为可核对清单**，并为每类缺口找到可引用的外部锚点；**不改总纲、不改代码**。
> **本文件即上一轮口头审计的落档件**（§2），§3–§5 为细化与外部取证。

## 1. 问题分解

| # | 问题 | 回答位置 |
|---|---|---|
| Q1 | 完备度能否用单一分数表达 | 否；拆为 8 维评分（§2.1） |
| Q2 | 哪些缺口会阻断开工或让判据失真 | 6 条结构性缺口（§2.2） |
| Q3 | 哪些盲区要到开工才暴露 | 8 条执行盲区（§2.3） |
| Q4 | 外部有哪些现成判据/格式可复用 | 12 项锚点（§4） |
| Q5 | 哪些可直接采用、哪些只借语义 | 采用矩阵（§5） |

## 2. 现状审计（落档）

### 2.1 八维评分

| 维度 | 评级 | 依据 |
|---|---|---|
| 目标与范围 | 良 | 四份来源全覆盖；K4/GQ 有显式降级 |
| 依赖与顺序 | 中 | §1 最短路径与 §6 串行要求矛盾；G2 出口依赖 G3 |
| 验收可判定性 | 中 | 106 条都有负向用例，但 0 条映射到测试；4 条依赖人工或特定平台 |
| 门禁覆盖 | 差 | 15 条未归属且未声明；I-1 无套件；H-5 生效点错位 |
| 交付物↔验收 | 差 | 10 条无交付物，2 条仅隐含 |
| 证据与外部依赖 | 中 | vendor 未 pin；Paper/Textbook 语料无路径与版本 |
| 治理与裁决 | 中 | 17 项 Q 中 4 项阻塞 G1/G2，无裁决人与期限 |
| 回滚与成本 | 弱 | 无逐阶段回滚；预算字段两套且默认不一致 |

### 2.2 结构性缺口

| # | 缺口 | 证据 | 为什么是缺口 |
|---|---|---|---|
| **P0-1** | H-5 交付在 G-1，却归入 C-7 且生效起点为 G3 | 总纲 §4 G-1 H-5；§5 C-7 行 | G-1 可在“伪造执行护栏”未生效时全绿，与其目标直接冲突 |
| **P0-2** | A2-4/A2-5/A2-6 在 G2 内不可判定 | §4 G2 验收表；对应 Stage 17/20/22 的行为由 G3 接线 | G2 出口断言依赖后一阶段产物；A2-7 属内核可判，不在此列 |
| **P0-3** | 106 条验收零测试映射 | `tests/` 108 个文件检索 `A1-1/AN-1/H-1/FC-1` 零命中；无 conformance harness | “验收”目前只是文档约定，无法在 CI 判红 |
| **P1-4** | 最短路径与依赖表矛盾 | §1「G0a → G-1 → G3」；§6「G0a → G-1 → G0b → G2 → G3」 | 未定义“G3 所需最小契约”，执行时无法判断 A1/A2 的最小集 |
| **P1-5** | 交付物与验收不对齐 | G1 缺 A1-6/9/10/11/12；G3 缺 A3-6/7/8；G5 缺 A5-8/9（共 10 条） | 实施者无明确构建目标；A3-7 同时是前置审计的 GAP-1，两份文档都提、都未列交付物 |
| **P1-6** | §5 覆盖声明不完整 | 脚本差集：另 15 条既无套件也未在声明中出现（`A1-6`、`A3-5`、`A5-1..4`、`A5-7..9`、`A6-5`、`A7-2/3/5/6/7`）；I-1 无套件 | 声明自称穷举，实际漏项；I-1 是五条不变量中唯一无判据的 |

### 2.3 执行盲区

| # | 盲区 | 证据 | 后果 |
|---|---|---|---|
| B-1 | 72h soak 无运行载体 | [ci.yml](../../.github/workflows/ci.yml) 三 job 均 `ubuntu-latest`，无 `timeout-minutes`、无自托管 runner；GitHub 默认单 job 上限 360 分钟 | A7-1 无法在 CI 执行 |
| B-2 | 故障注入只在 POSIX 可演练 | A1-3/A7-1 依赖 `kill -9` | 本地 Windows 无法验证，只能依赖 CI |
| B-3 | API 未认证暴露 | [config.py](../../researchclaw/config.py) `host=0.0.0.0`、`auth_token=""`、`cors_origins=("*",)` | A1-8 只测 CORS；绑定全网卡时接口默认无认证 |
| B-4 | 状态模型重构无迁移方案 | A1-11 要求 Run/Stage/Attempt；`rg StageAttempt` 全仓零命中；现有 `stages.py` 只有 `Stage/StageStatus` | 存量 `checkpoint.json` 与 run 目录的兼容、回滚未定义 |
| B-5 | vendor 供应链未固定 | §4 G2 仅写“vendor 到 ARC”，无仓库、commit、许可证 | `datatypes/verdict/sandbox` 不可复现，洁净室审查无对象 |
| B-6 | 语料无来源规格 | A5-2/A5-3 依赖 2,487 / 1,824 / 20,235，但无路径、版本、校验和 | 换机器即无法复算 |
| B-7 | 4 个 Q 阻塞开工且无裁决人 | Q1/Q2（G2）、Q5/Q9（G1）；§7 规则“未裁决不得进入” | 将以默认值静默开工 |
| B-8 | 预算字段两套且语义不一 | `hitl.config.cost_budget_usd` 默认 0（不限）；`cli_agent.max_budget_usd` 默认 5.0；CostGuard 为阶段检查而非逐调用前置拒绝 | A6-3“先拒绝后调用”无统一账本与阈值 |

## 3. 细化：缺口到验收项的映射

| 缺口 | 直接影响的验收 ID | 可机判性 | 处置类型 |
|---|---|---|---|
| P0-1 | H-5、C-7 | 可（退出码断言） | 门禁归属调整 |
| P0-2 | A2-4、A2-5、A2-6 | 可（需管线） | 生效起点调整 |
| P0-3 | 全部 106 条 | 可（需 harness） | 新增执行矩阵 |
| P1-4 | A1-*、A2-* | 不可直接判 | 定义最小子集或删句 |
| P1-5 | 10 条验收 | 可（对照表） | 补交付物 |
| P1-6 | 15 条 + I-1 | 可（脚本对账） | 补声明 |
| B-1/B-2 | A1-3、A7-1 | 需环境 | 运行载体与故障注入 |
| B-3 | A1-8 周边 | 可 | 安全项补登 |
| B-4 | A1-11 | 需设计 | 迁移方案 |
| B-5/B-6 | A5-2、A5-3、A2-1 | 可（哈希） | 供应链/数据清单 |
| B-7 | Q1/Q2/Q5/Q9 | 不可机判 | 裁决机制 |
| B-8 | A6-3 | 可 | 统一预算字段 |

## 4. 外部锚点（12 项，均已核验）

| # | 锚点 | 结论要点 | 对应缺口 | 来源 |
|---|---|---|---|---|
| X-1 | OWASP API Security Top 10 2023 · API2 Broken Authentication | 认证机制实现不当是最普遍的 API 风险；“默认无认证 + 绑定全网卡”属该类 | B-3 | <https://owasp.org/API-Security/editions/2023/en/0xa2-broken-authentication/> |
| X-2 | SLSA v1.0 Build track / Provenance | 依赖件应有机器生成的 provenance，可追溯到源与构建；L1 只要求“存在可验证的来源” | B-5 | <https://slsa.dev/spec/v1.0/levels> |
| X-3 | OpenTelemetry GenAI semantic conventions | 每次模型调用应有 `gen_ai.*` span（operation/provider/model/usage），可直接承载 prompt/response 追踪 | P1-5（A3-7）、前序 GAP-1 | <https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/> |
| X-4 | ACM Artifact Review and Badging v1.1 | “结果未被独立复现即未确立”；产物需可执行、可验证并附证据 | P0-1（H-5 的证据等级） | <https://www.acm.org/publications/policies/artifact-review-and-badging-current> |
| X-5 | ISO/IEC/IEEE 29148:2018 · requirements traceability | 需求须向上追溯到来源、向下分配到设计与测试；RTM 是标准工件 | P0-3、P1-5 | <https://www.iso.org/obp/ui/fr/#!iso:std:72089> |
| X-6 | METR《Measuring AI Ability to Complete Long Tasks》 | 以“人类完成时长”表达能力边界；长跑验收应对应任务跨度而非墙钟 | B-1 | <https://arxiv.org/abs/2503.14499> |
| X-7 | OpenAI MLE-bench | 75 个 Kaggle 任务 + 隔离环境 + 人类基线，是可复现的工程能力评测范式 | P0-2（实验阶段判据） | <https://arxiv.org/abs/2410.07095> |
| X-8 | AgentChaos（programmatic fault injection） | 在 LLM API 层做非侵入式故障注入，可系统验证 agent 的恢复与降级 | B-1、B-2 | <https://arxiv.org/abs/2608.06790> |
| X-9 | Temporal · Activity idempotency | 活动是 at-least-once，必须幂等；幂等键使重复可被下游丢弃 | B-4、A1-10 | <https://docs.temporal.io/activity-definition> |
| X-10 | Croissant 1.1 | 数据集元数据（来源、结构、许可）应机器可读、可复算 | B-6 | <https://docs.mlcommons.org/croissant/docs/croissant-spec-1.1.html> |
| X-11 | FrugalGPT | 级联/预算控制可在保持精度的同时大幅降本；成本应先于调用约束 | B-8 | <https://arxiv.org/abs/2305.05176> |
| X-12 | GitHub Actions 官方 cheat sheet | job `timeout-minutes` 默认 360 分钟 | B-1 | <https://github.github.io/actions-cheat-sheet/actions-cheat-sheet.pdf> |

### 4.1 核验方式

- arXiv 编号逐条以 WebSearch 命中标题与摘要（X-6、X-7、X-8、X-11）。
- 标准/官方文档以官方域名为准（X-1 `owasp.org`、X-2 `slsa.dev`、X-3 `opentelemetry.io`、X-4 `acm.org`、X-9 `docs.temporal.io`、X-10 `docs.mlcommons.org`）。
- 不引用二手博客作为判据；搜索结果中的第三方解读仅用于交叉确认，不进入本表。

## 5. 采用矩阵

| 锚点 | 采用 | 只借语义 | 拒绝 | 理由 |
|---|---|---|---|---|
| X-1 | 作为 G-1 安全核对表 | | | 成本低，直接对应默认配置风险 |
| X-2 | | ✓（pin + provenance 文件） | 全量 SLSA 等级 | ARC 非发布型供应链，L1 足够 |
| X-3 | | ✓（属性命名与 span 结构） | 引入完整 OTel SDK | 先落 JSONL，字段对齐即可 |
| X-4 | 作为 H-5 证据标准 | | | 与“可独立复现”目标一致 |
| X-5 | RTM 结构 | | 全量 29148 流程 | 只需“ID → 测试 → 证据”三列 |
| X-6 | | ✓（任务跨度视角） | 作为 ARC 验收指标 | 该指标测模型能力，不测系统可靠性 |
| X-7 | | ✓（隔离 + 人类基线 + 可复现） | 引入 75 个 Kaggle 任务 | 成本与许可不可控 |
| X-8 | 故障注入方法 | | 直接依赖其实现 | 可用 pytest + 故障代理自建 |
| X-9 | 幂等键与 attempt 语义 | | 引入 Temporal 运行时 | 总纲已明确第一版不引入 |
| X-10 | 最小数据清单 | | 全量 JSON-LD | 先记 name/version/hash/license 四字段 |
| X-11 | 预算上限与前置拒绝 | | 模型级联路由 | 级联属 G6（P2），当前只需预算护栏 |
| X-12 | 作为 B-1 的事实依据 | | | 只用于说明 6h 上限 |

## 6. 复现命令

```bash
# 1) 验收项 vs C 套件差集（含区间展开）
python -c "import io,re;t=io.open('arc-master-roadmap.md',encoding='utf-8').read();s4=t.split('## 4.')[1].split('## 5.')[0];s5=t.split('## 5.')[1].split('## 6.')[0]
def ex(s):
 p=r'\b((?:A0a|A0|A1|A2|A3|A4|A5|A6|A7|A8a|A8b|AN|FC|FA|GQ|OB|H))-(\d+)(?:\s*\.\.\s*(?:[A-Za-z0-9]+-)?(\d+))?';o=set()
 for m in re.finditer(p,s):
  a=int(m.group(2));b=m.group(3);o.update('%s-%d'%(m.group(1),i) for i in range(a,int(b)+1)) if b else o.add('%s-%d'%(m.group(1),a))
 return o
print(sorted(ex(s4)-ex(s5)))"

# 2) 验收 ID 是否有测试映射（应输出空，除会话文件外）
rg -n "\b(A1-1|A3-7|AN-1|H-1|FC-1)\b" -g "!*.md"

# 3) 预算与状态模型事实
rg -n "cost_budget_usd|max_budget_usd" researchclaw
rg -n "StageAttempt|RunMandate|StageHandback|prompt_version" researchclaw
```

## 7. 边界与未决

- 本批**不修改**总纲正文，也不修改代码；P0-1/P0-2/P1-4 属路线级判据变更，需单独裁决。
- 12 项锚点只做“是否适用”的判断，不替代各阶段 `RESEARCH.md` 的取证。
- 未覆盖：G5 语料的实际路径盘点（需访问 Paper/Textbook 仓）、OB 系列的三框架版本矩阵。
