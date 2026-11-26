# clawsgo-cleanroom-arc-reinforcement.md v0.4 异构独立审查报告（2026-11-26）

> **性质**：Layer-0 独立审查（T3，零代码/零门禁，全程只读）。审查基座（GLM-5.3-Flash）与被审文档撰写基座（DeepSeek-V4.1-Flash）异构；纪律同 P-039/P-041——**不采信文档自报结论**，全部以全文回读、T0 报告回源、代码锚点一手复验、跨文档一致性核对重验。
> **对象**：`clawsgo-cleanroom-arc-reinforcement.md` v0.4（本地草稿，被 `.gitignore` 的 `/clawsgo-*.md` 排除，不入库；本文引用一律用行内代码）。
> **辅助回源**：`D:\rea-main\reports\clawsgo-reverse-engineering.md`（用户提供，T0 级；只读其结论作对照，不复制实现）。

---

## 1. 审查方法与边界

| 手段 | 内容 |
|---|---|
| 全文回读 | 被审文档 745 行全文（§0–§12.10），含 v0.2/v0.3/v0.4 三层增补的叠加一致性 |
| T0 回源 | T0 报告关键节重读：§5.1–5.4（协议 v3/帧族/RPC 表/CORS）、§15.13–15.15（默认模型/无 Agent 工具/子智能体验证）、§6.1（loader）、§14.1–14.2（136/Lean/turns 内存表） |
| 代码锚点复验 | 对 §12.1 台账逐行回读所引源码；对存疑主张（I-3 消费点、`VALID_CATEGORIES`、`approval_timeout_hours`、`MCPServerRegistry`、`_run_task`、env allowlist 测试、事件类型数）全仓 grep 一手取证 |
| 跨文档一致性 | 总纲 §3.1/§3.2（106 计数、Q5/Q9、G1/G4/G6 状态、B-1..B-12）、PROGRESS P-171..P-182 行、八套编号（R0–R9/S0–S12/C-1..C-11/HC-1..HC-10/U-180/U-181/T0-1..8/N1–N5/M1–M6）无重号冲突 |

边界：本报告不修改被审文档、不运行管线、不产生代码变更；D 组修复由后续批次裁决。

---

## 2. 总体判定

**附条件维持 v0.4。**

三条主判断全部成立：① ClawsGO 1.1.4 是"云端控制面 + 薄本地执行代理"，durability 在云端（T0 回源吻合）；② ARC 的本地 `file-as-state + supervisor` 是差异化路线而非追赶；③ T0 只作判断校准、不进实现规格的边界设置恰当（含 T0-8 对报告内部口径不一的识别，回源属实）。

§12 统一治理的台账主结构（R0/R3 关闭、R5/R7 真新增、六项 partial 净缺口、W0–W3 波次、非补偿五步）成立；但发现 **6 个缺陷（D-1..D-6）**，其中 D-1、D-4 影响 C-7 裁决与 §3.5 对照结论的准确性，建议修后再提交。另登记 5 条观察（O-1..O-5）。

---

## 3. D 组缺陷（需修）

| ID | 缺陷 | 一手证据 | 修法 |
|---|---|---|---|
| **D-1** | **C-7/U-181-1 对 `skills.VALID_CATEGORIES` 的影响面判断失准**：该常量实测**无任何消费者**——loader 不校验 category（`loader.py:82` 仅把 front-matter 键拷入 metadata，`schema.py:71` 的 `category` 属性默认 `"domain"` 无校验）、`registry.py:88-90` 只做字符串相等过滤、`matcher.py:121` 只打印、`pipeline_manifest.py` 与 tests 均不引用（全仓 grep：`skills` 域内仅 `schema.py:38` 定义；`memory/store.py:55` 的同名常量是另一模块的独立定义，与本议题无关）。**推论**：P-171 D-8 落 `skills/builtin/formal/` 不会被任何机制拦截；真正的问题是"死常量与目录漂移"（契约失真），不是阻塞。§12.5 敏感点 1 的触发条件（"出现 SKILL.md 而 VALID_CATEGORIES 未改"导致的风险）当前**无法机械发生** | `researchclaw/skills/schema.py#L38`、`loader.py:82-93`、`registry.py:88-90`、`matcher.py:121`、全仓 grep | C-7 裁决改为二选一：**(a)** 在 loader 增加 category 校验并同步加 `formal`（把死常量变成活契约）；**(b)** 删除/放宽常量，承认 category 为自由字符串。§12.5 敏感点 1、U-181-1、"§12.1 R6 ④"同步改写 |
| **D-2** | §12.1 R0 "事件白名单 **18 类**"过期：`runtime/event_log.py:37-45` 的 `EVENT_TYPES` 实测 **21 类**（run.\*4 + stage.\*4 + tool/llm 5 + approval.required 1 + effect.\*3 + budget_exhausted 1 + pipeline.summary 1 + event_log_truncated/rolled 2）。"18"是 P-040 当时前端对齐口径，其后新增 budget/pipeline.summary/event_log_\* 等类型 | `researchclaw/runtime/event_log.py#L37-L45` 一手计数 | 改为"21 类"或注明"P-040 时点 18，现行 21" |
| **D-3** | §12.1 R5 净剩余列引用"受 **C-6/C-10** 约束"——C-10 是 R9/A7-1/B-8 的审批冲突，与 R5 无关；"A7-1 前不动 Stage 12"属 **HC-8**（且 C-6 的裁决文字本身已含"A7-1 前不改 Stage 12"） | §12.2 HC-8、§12.3 C-6/C-10 对照 | 改为"受 C-6/HC-8 约束" |
| **D-4** | §3.5 修正表"多并发 单任务 → **有**：admission 槽 + 多 run 准入"以偏概全：`server/routes/pipeline.py:51/129/146` 的 server 路由**至今仍是全局单 `_run_task`**（`asyncio.Task | None` + 单 `create_task` + cancel）；admission/supervisor 是另一执行平面。v0.1 快照的该条结论对 server 路径**仍然成立**，不应整体标"已推翻" | `researchclaw/server/routes/pipeline.py#L51,L129,L146` 一手 grep | 该行改为"supervisor/admission 层已支持多 run 准入（P-172/P-173）；**server 路由仍为全局单任务 `_run_task`**" |
| **D-5** | §1.4 T0-6 与 §7 "应保持并**补测试**"已过期：`tests/test_env_allowlist.py` 与 `tests/test_boundary_coverage.py:832-841` 已存在；后者先注入 `AWS_SECRET_ACCESS_KEY` 哨兵、断言其不在 env，再断言 `extra = set(env) - SAFE_ENV_KEYS - overrides` 中只允许 `LC_*`——即"凭据不落子进程"的强断言 | `tests/test_boundary_coverage.py#L832-L841`、`tests/test_env_allowlist.py:8-23` | 改为"已有测试（test_env_allowlist / test_boundary_coverage::test_t10_env_is_closed_over_allowlist），保持" |
| **D-6** | 编号/标题漂移三处：§12.3 标题"(C-1..C-10)"但表含 **C-11**；§11.2 标题"五个可拆解机制"但表列 **M1–M6**（M6 标"辅助"）；§12 标题"(v0.3)"而正文已 v0.4 | 全文对照 | 三处标题同步（"C-1..C-11"、"M1–M6（M6 辅助）"、"(v0.3，§12.10 为 v0.4)"） |

---

## 4. O 组观察（建议，不阻塞）

| # | 内容 | 建议 |
|---|---|---|
| O-1 | §12.5 R1-R 的逃生口（"窗口不足则 A7-1 后立即补"）未反映到 §12.6 W2 触发条件（严格"B-11 验收通过"），两表粒度不一致：若 B-11 通过后 A7-1 立即启动，按 §12.6 字面 R1-R 将被推迟到 W3，与 §12.5 意图相悖 | §12.6 W2 触发改为"B-11 验收通过；若 A7-1 已先启动，R1-R 顺延至 A7-1 结束后立即执行" |
| O-2 | §12.1 R1 的 grep 表述"仅命中 artifact_node.py 与 outbox.py"漏了第三处：`evidence/sidecar.py:239` 也有 `inputs_digest`（Lean sidecar JSON 契约字段） | 补第三处，保持"runner 无消费点"结论不变 |
| O-3 | `approval_timeout_hours` 比"死配置"更强：**10 处 README 注释（`README.md` + 9 个语言版）**将其描述为"Gate stage timeout / 门控阶段超时"，另 3 处配置样例（`config.researchclaw.example.yaml`、`docs/integration-guide.md`、`experiments/arc_bench/config/base_config.yaml`）仅含字段、无误述——属**文档-代码漂移**（文档承诺了代码未实现的行为） | **已修（P-185）**：10 处注释统一改为"预留；尚未接线"（reserved / not wired）；字段本身的接线或删除仍待 C-10 |
| O-4 | PROGRESS P-182 行称"§9 标记 5 条已裁决"，实际明确标记"已裁决/已落地"的是 **4** 条（§9 第 1/2/5/6），第 3 条只是状态更新 | 措辞改"4 条已裁决 + 1 条状态更新"，或给 §9 第 3 条补标记 |
| O-5 | §12.10 引用"§8.7"指 §8 编号列表第 7 条，易与章节号混淆（§8 无 §8.7 小节） | 写作"§8 第 7 条" |

---

## 5. S 组复验成立（一手证据，抽样）

| # | 主张 | 复验方式 | 结果 |
|---|---|---|---|
| S-1 | T0-2：设备 WS 协议 v3、帧族（hello/hello_ack/presence/reject + rpc/rpc_result + turn_stream/exit + pty/fs 票据） | 回源 T0 §5.1–5.2（`DEVICE_PROTOCOL_VERSION = 3`） | ✅ 吻合 |
| S-2 | T0-3/T0-6：云端可下发任意 loader 与宿主脚本；CORS 反射任意 Origin；`bypassPermissions` | 回源 T0 §5.3/§5.4/§6.1/§15.14 | ✅ 吻合 |
| S-3 | T0-4：turns 内存表、无队列/DAG、turn 状态不持久化（会话转写仍落盘）、重启接不上旧 turn | 回源 T0 §14.2/§15.14 判断 4 | ✅ 吻合 |
| S-4 | T0-5：默认本地模型 `clawsgo-1.5-lithium`（CLI 报 unrecognized_model）；本地 turn 无 Agent/Task 工具、`subagentModelId` 出现 0 次 | 回源 T0 §15.13/§15.14/§15.15（Bash×3、子会话 0） | ✅ 吻合 |
| S-5 | T0-8：报告开头"未登录/未触发模型调用/未读取令牌明文/不改二进制"与 §15.11–15.14 的真实抓包、真实令牌（未打印）、临时注入并 SHA-256 还原存在口径不一 | 回源 T0 开头声明 vs §15.11–15.14 方法修正段 | ✅ 属实，被审文档的引用方式（分节证据为准）恰当 |
| S-6 | R1 净剩余：I-3 的 `stage_id + inputs_digest` 在 runner 无消费点；`stage-XX/parts/*.json` 未实现 | 全仓 grep（`inputs_digest` 仅 artifact_node/sidecar/outbox；`parts` 零命中）+ `KernelSession` 零命中 | ✅ 成立（表述完整性见 O-2） |
| S-7 | R2 净剩余：外部 MCP 独立连接表无生产消费者；`sandbox_profile` 执行端消费被显式推迟 | `MCPServerRegistry` 全仓仅定义/导出/测试；`config.py:325-327` 注释原文 | ✅ 成立 |
| S-8 | R3 关闭：路由+预算+`model_policy` 接线在；`roles.subagent` 无生产调用方（仅 tests 与 ROLES 定义） | `client.py:445-461`、全仓 grep | ✅ 成立 |
| S-9 | R9 净剩余：`approval_timeout_hours` 无消费者 | 全仓仅 `config.py:158`（定义）与 `:1034`（解析） | ✅ 成立（另见 O-3） |
| S-10 | 跨文档一致：106 计数、Q5=Q9=A、G1 12/12、G4 10/10、G6 5/5、G3 17/17、G5 14/14、B-1..B-12、B-13..B-17 未登记；R6 "builtin 20 个"（8 domain + 8 experiment + 4 tooling）；`server/routes/events.py` 存在；八套编号无重号冲突 | 总纲 §3.1/§3.2、PROGRESS P-171..P-182、目录清点 | ✅ 全部一致 |

---

## 6. 处置建议

1. **修 D-1..D-6 后再提交**：均为文档级修改（约 10 处编辑），不触碰代码与门禁；D-1 需要同时对 C-7 做出真正裁决（二选一），这是 v0.4 遗留的唯一"裁决未闭合"项。
2. **O-1..O-5 可顺带**（同批小修，不单开批次）。
3. **不新增 R 项**：本审查未发现任何需要新增 R10+ 或改波次的证据；§12.10 的"无新增项"结论维持。
4. **登记建议**：D 组修复若执行，建议作为 P-184 小批（T3，仅文档）并在 session 中绑定本报告为输入锚点；若用户决定不修，本报告的 D 组即构成 v0.4 的已知偏差清单，随文档一并提交。

---

## 7. P-184 复核记录（2026-11-26）

> 本节记录对本报告自身的异构复核与修复执行结果；§1–§6 保留为 P-183 原始审查结论，不改写。

### 7.1 复核结论：D-1..D-6 全部维持

| 项 | 复核方式 | 结果 |
|---|---|---|
| D-1 | 全仓 grep `VALID_CATEGORIES`；读 `loader.py:60-98`、`registry.py:88-90`、`matcher.py:121`、`pipeline_manifest.py`（只 import `STAGE_NAME_TO_NUMBER`）、`skills/__init__.py`（只导出 Skill/Registry） | ✅ 维持：常量无消费者；`formal` 目录可被 loader 接受；C-7 应定性为契约漂移而非运行时冲突 |
| D-2 | `python -c "from researchclaw.runtime.event_log import EVENT_TYPES; print(len(EVENT_TYPES))"` → **21**；`tests/test_event_stream.py::test_frontend_event_types_match_runtime` 断言前端集合 **==** `EVENT_TYPES` | ✅ 维持："18"过期 |
| D-3 | 读 §12.2 HC-8、§12.3 C-6/C-10 | ✅ 维持：R5 应引 C-6/HC-8，C-10 属 R9 |
| D-4 | 读 `server/routes/pipeline.py:49-52,61-68,129,141-146`；`server/app.py:123-127` 确认 router 已挂载 | ✅ 维持：server 路由仍是全局单 `_run_task`；admission 是另一平面 |
| D-5 | 读 `test_boundary_coverage.py:832-841`、`test_env_allowlist.py:8-23` | ✅ 维持："补测试"过期（见 7.2 引文修正） |
| D-6 | 对照 §11.2/§12.3/§12 标题与表内容 | ✅ 维持：三处标题漂移 |

### 7.2 对本报告的两处引文修正

| 项 | 原表述 | 复核后 |
|---|---|---|
| O-3 | "8 处 README/config 样例" | 实为 **10 处 README 注释**（`README.md` + 9 语言版）误述为门控超时；另 3 处配置样例仅含字段、无误述 |
| D-5 | "断言 `set(env) - SAFE_ENV_KEYS - overrides == set()`" | 实际断言为：注入 `AWS_SECRET_ACCESS_KEY` 哨兵并断言不在 env；`extra = set(env) - SAFE_ENV_KEYS - overrides` 中只允许 `LC_*`（`assert all(key.startswith("LC_") ...)`），不是严格空集 |

### 7.3 本报告漏检、P-184 补充的缺陷

| ID | 内容 | 证据 | 处置 |
|---|---|---|---|
| **D-7** | 被审文档 §11.2 M2 与 §11.3 "技能"行仍称 ARC "无 `SKILL.md` 契约 / 无统一契约"，与事实冲突：`skills/schema.py` 定义 agentskills.io 字段，`skills/loader.py` 解析 `SKILL.md`，`skills/builtin/` 有 20 个 SKILL.md；§12.1 已正确记为"部分已存在"，属 v0.2 正文与 v0.3 台账的内部不一致 | `skills/loader.py:60-98`、`skills/builtin/**/SKILL.md`（20 个）、§12.1 R6 行 | P-184 已改为"已有 SKILL.md 契约与 20 个内置技能；缺信任分层/归属账本/按需加载验证" |

### 7.4 修复执行结果

| 项 | 状态 |
|---|---|
| D-1 | 已修：R6 行、C-7、HC-7、§12.5 支配/敏感点、§12.6 W0、U-181-1 全部改为"契约漂移、非阻塞；R6 二选一（推荐激活校验并纳入 formal）" |
| D-2 | 已修：§12.1 R0 改为"现行 21 类（P-040 时点 18）" |
| D-3 | 已修：R5 改引 C-6/HC-8 |
| D-4 | 已修：§3.5 多并发行改为"supervisor/admission 支持多 run；server 路由仍单 `_run_task`" |
| D-5 | 已修：T0-6 与 §7 改为"已有测试，保持" |
| D-6 | 已修：§12.3 → C-1..C-11；§11.2 → M1–M6（M6 辅助）；§12 → v0.3 起 + §12.10 v0.4 |
| D-7 | 已修：§11.2 M2、§11.3 技能行 |
| O-1 | 已修：§12.6 W2 触发条件补 A7-1 逃生口 |
| O-2 | 已修：§12.1 R1 grep 补 `evidence/sidecar.py:239` |
| O-3 | **已修（P-185）**：10 处 README 注释（root + 9 语言）统一改为"预留；尚未接线"；C-10 已记录准确计数。字段本身的接线或删除仍待 C-10 |
| O-4 | 已修：P-182 行改为"4 条已裁决 + 1 条状态更新" |
| O-5 | 已修：§12.10 引用改为"§8 第 7 条" |

> 边界：P-184 只改文档（被审文档为 gitignore 本地草稿 + 本报告 + PROGRESS），零代码、零门禁变更；未新增 R 项。

