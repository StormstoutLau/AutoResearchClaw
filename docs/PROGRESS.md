# PROGRESS 待办登记

> 依据 SPEC_PROCESS 约定建立（每步完成后更新）。状态词表：`pending / in-progress / blocked / done`。
> 登记日期：2026-11-06
> 编号口径：P-001 起；每个批次必须有一条 `specwf-pNNN-*.jsonl` 决策流（五步：research → design → implement → verify → finalize）。
> 真值源：本表 = P 级任务；`docs/CONSOLE.md` 为纯派生视图，禁止手改。

| ID | 事项 | 依据 | 状态 | 优先级 | 验收标准 |
|---|---|---|---|---|---|
| P-001 | 安装 Spec_Workflow + Spec_Runner，接入 ARC 并启用门禁 | [spec/arc-spec-workflow-install/](../spec/arc-spec-workflow-install/) | done | P0 | 适用 pre-commit 门禁全绿；决策流 5/5 通过 step-gate |
| P-002 | 审查 ARC 总纲及 14 份关联文档的事实底座、引用可信度与路线可行性 | [spec/arc-roadmap-review/](../spec/arc-roadmap-review/) | done | P0 | 8 条代码事实逐条核验；106 条验收覆盖检查；P1/P2/P3 分级含证据；step-gate 5/5 通过 |
| P-003 | 按审查结论订正总纲至 v0.2（H-4 前提、C-9 与生效起点、A2-3 口径、钩子数） | [spec/arc-roadmap-fix/](../spec/arc-roadmap-fix/) | done | P0 | 106 计数不变；H-1..H-4 全部进 C-9；矛盾表述清零；四道钩子全绿 |
| P-004 | 落档总纲完备度审计，产出 12 项外部锚点与 7 项补全方案（未执行） | [spec/arc-roadmap-gaps/](../spec/arc-roadmap-gaps/) | done | P1 | 6 结构缺口 + 8 执行盲区有证据；12 锚点可核验；总纲与 106 计数不变；step-gate 5/5 |
| P-005 | 裁决落地：总纲 v0.4（D-1=A、D-2=C）+ D-3..D-7 + 覆盖率 CI 门禁 | [spec/arc-roadmap-verdict/](../spec/arc-roadmap-verdict/) | done | P0 | 106 计数不变；H-5 进 C-9；A2-4/5/6 谓词化；覆盖率脚本 CI 绿（missing=0）；step-gate 5/5 |
| P-006 | G-1 急救落地：Q18/Q19/Q20 裁决 + H-1..H-8 代码与 8 个测试 | [spec/arc-g1-hardening/](../spec/arc-g1-hardening/) | done | P0 | 28 个新测试全绿；既有回归 346 passed；Q19 回环默认生效；覆盖 missing=0；step-gate 5/5 |
| P-007 | B 站（集群节点 B）LLM 端点与 Claude Code 接入（preset×2 + CLI 菜单 + env 注入 + 思考模型兼容修复） | [spec/arc-b-station-endpoint/](../spec/arc-b-station-endpoint/) | done | P1 | 离线 18 测试全绿；live 双 wire 实测命中 B 站 1M；LLM 回归 105 passed；step-gate 5/5 |
| P-008 | B 站 live 覆盖扩展（health/JSON/系统提示/多轮/用量/preflight）+ Anthropic cache 计费修复 | [spec/arc-b-station-live/](../spec/arc-b-station-live/) | done | P2 | live 9 用例全绿；离线 19 passed；cache 输入计入 prompt；回归 43 passed；step-gate 5/5 |
| P-009 | 私有端点卫生：清私网地址、端点改配置/环境变量、新增泄漏扫描门禁 | [spec/arc-private-endpoint-hygiene/](../spec/arc-private-endpoint-hygiene/) | done | P1 | 全仓扫描 0 违规；live 未设端点即 skip；离线 21 passed；pre-commit 六钩子全绿 |
| P-010 | 历史提交脱敏：filter-repo 重写 323 提交并验证全历史 0 命中 | [spec/arc-history-scrub/](../spec/arc-history-scrub/) | done | P1 | 四 token 全历史 0 命中；旧对象不可达；当前树扫描 0、测试 21 passed；强推待授权 |
| P-011 | CLI 代码代理接线断裂调研：问题链追溯、13 项外部锚点、6 种社区接法与 4 条路线建议 | [spec/arc-cli-agent-wiring/](../spec/arc-cli-agent-wiring/) | done | P1 | F-1..F-9 可复现；锚点 13 项；R-1..R-4 含推荐；未改代码与总纲；step-gate 5/5 |
| P-012 | R-3 统一接缝落地：配置去重 + Stage 10/13 CLI 接线与回退 + Codex stdin + doctor/适应度函数 | [spec/arc-cli-agent-seam/](../spec/arc-cli-agent-seam/) | done | P1 | 16 新用例全绿；相关回归 171；真实 CLI E2E 4 文件；wiring check PASS；默认 llm 零变化 |
| P-013 | CLI 代理未决项收口：U-3 传输选型裁决、U-5 Stage 13 边界提示+审计、U-4 前移、U-6 新开 | [spec/arc-cli-agent-followups/](../spec/arc-cli-agent-followups/) | done | P2 | 边界测试 18 passed；相关回归 130；wiring check PASS；默认 llm 零变化 |
| P-014 | 信念修正与多步传播调研：回退链审计、7+5 缺口、13 项外部锚点、外部文档复用评估与 R-1..R-3 | [spec/arc-belief-revision-propagation/](../spec/arc-belief-revision-propagation/) | done | P1 | 场景 A/B 机制与 12 缺口可复现；锚点 13 项；复用边界明确；未改代码与总纲；step-gate 5/5 |
| P-015 | R-3 重型方案补充分析：Saga/Temporal/DAG/自动闭包影响面与可控性；R-3a/b/c 分层 | [spec/arc-r3-engine-impact/](../spec/arc-r3-engine-impact/) | done | P1 | 8 维影响矩阵；可控性判定；5 项引擎触发；未改代码；step-gate 5/5 |
| P-016 | 总纲 v0.6 状态同步：G-1 完成、G0b 未就绪、Q17 裁决、P-011..P-015 依据挂载、G3 候选增量 | [spec/arc-roadmap-v06/](../spec/arc-roadmap-v06/) | done | P0 | 106 计数不变；G-1/Q17/G0b 状态一致；覆盖率 missing=0；step-gate 5/5 |
| P-017 | G0b 治理基座调研：A0-1..A0-6 缺口、路径迁移、钩子组成、Q3、统计/黑盒/CI 方案 | [spec/arc-g0b-governance-base/](../spec/arc-g0b-governance-base/) | done | P0 | 实测 6 钩子全绿但组成不符；三方案对比；推荐迁移+根壳+6+2 钩子；未改代码；step-gate 5/5 |
| P-018 | 总纲 v0.7：纳入 G0b 调研结论（状态、交付物、A0-1 口径、Q3/Q11、§11） | [spec/arc-roadmap-v07/](../spec/arc-roadmap-v07/) | done | P0 | 106 计数不变；G0b 标调研完成待实施；Q3/Q11 写入 P-017 建议；step-gate 5/5 |
| P-019 | Q3 裁决调研：touch=migrate 与存量 grandfather 策略；A/B/C/D 对比与建议 B | [spec/arc-q3-grandfather-policy/](../spec/arc-q3-grandfather-policy/) | done | P0 | 当前 DC 0 违规、基线可空；建议 B 基线+棘轮、90 天、只豁免 DC1-DC3；未改代码；step-gate 5/5 |
| P-020 | P-019（Q3 grandfather）独立复核：机检重跑、锚点回源、设计审查；维持建议 B | T3：Layer-0 独立复核报告，零代码/零门禁；[arc-q3-grandfather-review-20261110.md](arc-q3-grandfather-review-20261110.md) | done | P0 | 主张基本成立；1 个设计缺口（F-1 I-3/I-4 冲突）；F-2..F-5 修正澄清；S-1..S-3 补充佐证；4 项实施前提；step-gate 5/5 |
| P-021 | G0b 完整治理基座实施：scripts/spec 迁移+根壳、grandfather 策略层、m7/repo/blackbox 钩子、CI spec-gates | [spec/arc-g0b-implementation/](../spec/arc-g0b-implementation/) | done | P0 | 九钩子全绿；grandfather selftest 11/11；A0-1..A0-6 全过；dc_validator 零改动；roadmap missing=0；step-gate 5/5 |
| P-022 | G1 前置调研：Q5 事件后端（纯文件 vs SQLite WAL）、Q9 事件保留期（30 天/永久）；10 项现状 + 16 锚点 + 判定矩阵 | [spec/arc-g1-readiness-research/](../spec/arc-g1-readiness-research/) | done | P0 | 建议 Q5=A（纯文件+supervisor）、Q9=A（热30/归档365/摘要永久）；发现 fsync/WS 丢事件/heartbeat 非原子三处缺陷；未改代码与总纲；step-gate 5/5 |
| P-023 | P-022（G1 前置调研）独立复核：三缺陷一手验证、F 表抽查、锚点回源、矩阵权重复算 | T3：Layer-0 独立复核报告，零代码/零门禁；[arc-g1-readiness-review-20261110.md](arc-g1-readiness-review-20261110.md) | done | P0 | 三缺陷属实；定级修正 2 处（fsync 限断电场景、WS 丢弃与 A1-2 无关）；Q5 建议降格为倾向 A（权重敏感性披露）、Q9 稳健维持；R-5 登记 step_enforce 分支不一致；step-gate 5/5 |
| P-024 | R-5 修复：step_enforce 两分支 feature 门槛对齐（`_resolve_declared` 补 `BATCH_BINDING_MIN_P` 谓词） | [spec/arc-step-enforce-branch-consistency/](../spec/arc-step-enforce-branch-consistency/) | done | P1 | 新增 8 用例全绿；混合批真实复现（P-022+P-023）exit 0；覆盖检查/session 校验未放宽；9 门禁全绿；step-gate 5/5 |
| P-025 | R-4 处置：Q5 决策方法从加权总分改为「硬约束→支配→敏感点→可逆性→kill criteria」；Q5/Q9 重推 | T3：Layer-0 方法学补全，仅文档；[spec/arc-q5-decision-method/RESEARCH.md](../spec/arc-q5-decision-method/RESEARCH.md) | done | P1 | 反转条件量化为线性不等式（默认 +6，B 偏重时 −4）；Q5 新理由不依赖权重；Q9 由硬约束淘汰 B/C（约束即结论）；G1 五项约束已登记；step-gate 5/5 |
| P-026 | Q5/Q9 裁决 + 总纲 v1.0：Q5=A（纯文件）、Q9=A（热30/归档365/摘要永久）；G1 拆 G1a/G1b | T3：Layer-0 总纲文档，零代码/零门禁；[arc-master-roadmap.md](../arc-master-roadmap.md) | done | P0 | 106 计数不变；Q5/Q9 标已裁决；A1 项 G1a/G1b 归属明确；roadmap missing=0；step-gate 5/5 |
| P-027 | G1a 事件内核：EventEnvelope/链哈希/fsync/滚动/配额/保留 + 租约 fencing + 原子 heartbeat + checkpoint 事件重建 | [spec/arc-g1a-event-core/](../spec/arc-g1a-event-core/) | done | P0 | 新增 24 用例；回归 106 passed；A1-1/4/5/6 全过；fsync 失败不重试；递归不重复收口；9 门禁全绿；step-gate 5/5 |
| P-028 | G1b 调研：进程守护/退出码契约、Run-Stage-Attempt 三层、SSE 补拉、outbox；10 锚点 | [spec/arc-g1b-supervisor-protocol/](../spec/arc-g1b-supervisor-protocol/) | done | P0 | 四子问题各 3 方案；退出码 0/75/65/77/78 与退避参数定案；attempt 与 _v{k} 分离；缺口用 stream.gap 显式；未改代码；step-gate 5/5 |
| P-030 | P-028（G1b 调研）独立复核：事实复验、锚点等级审查、契约×G1a 交互推演 | T3：Layer-0 独立复核报告，零代码/零门禁；[arc-g1b-review-20261110.md](arc-g1b-review-20261110.md) | done | P0 | 事实/锚点成立；X-10 数值降 T2；三缺口登记（R-1 非失败终态无退出码、R-2 租约所有权死锁、R-3 长任务无续期）为 P-029 强制输入；step-gate 5/5 |
