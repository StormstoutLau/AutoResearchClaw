# P-072 对 P-069/P-070 G3 readiness 的独立复核（2026-11-11）

> **性质**：Layer-0 独立复核（T3，零代码/零门禁）。同 P-062/P-065/P-067 先例：不采信 [G3 readiness v1.2](../spec/arc-g3-readiness/RESEARCH.md) 结论，全部一手重验（grep/读码/机检/锚点抽查）。
> **对象**：P-069（readiness 调研）与 P-070（Q-1..Q-9 决策采纳）两批 T3 文档；对象含总纲 v1.3m 的 G3 决策闸门行。
> **编号说明**：本批占用 **P-072**；原计划 G3 M0 设计包由 P-071 顺延为 **P-073**（沿 P-054 让位先例）。

## 1. 一手复验（V 表）

| # | 报告声明 | 复验方式 | 结果 |
|---|---|---|---|
| V-1 | 前置：G1/G2 收口、H-4 已落地 | 读码：`_literature.py:385` 有 `retrieval_degraded`；`tests/test_retrieval_degraded.py` collect 2 项 | ✅ |
| V-2 | 「researchclaw 内无 ClaimStatus/CitationLabel 词表」 | 全仓 grep（排除 vendor）：`CitationLabel` 仅存在于 vendor 侧；`ClaimStatus/ArtifactNode/RunMandate/StageHandback` 在非 vendor 代码 0 命中 | ✅ 盘点准确（readiness 未提 vendor 内已有 CitationLabel 枚举，见 O-1） |
| V-3 | 「Stage 22 无 claim 接线」 | grep 无命中；M4 仅接 9/20/23 | ✅ |
| V-4 | 「pipeline_summary 已程序生成，缺 A3-2 校验」 | 读码 `runner.py:_build_pipeline_summary/_write_pipeline_summary`（普通 write_text，无 digest/重算） | ✅ |
| V-5 | 「K5 `tb:`/`paper:` 无解析器」 | grep `tb:`/`paper:` 无解析实现 | ✅ |
| V-6 | Q-1..Q-9 决策采纳与 §7 建议一致 | 逐条比对 §4 状态列与 §7 各小节结论（9/9 一致） | ✅ |
| V-7 | 总纲 v1.3m 决策闸门行 | `arc-master-roadmap.md` L398「P-070 已裁决」与 readiness v1.2 一致；修订行 v1.3m 在位 | ✅ |
| V-8 | DC 契约 | `spec/arc-g3-readiness/RESEARCH.md` 0 违规 | ✅ |
| V-9 | 切片编号一致性 | readiness 内 P-071..P-076 引用共 15 处，无 P-070 旧编号残留 | ✅ |
| V-10 | 机检 | pre-commit 9/9、coverage missing=0（P-069/P-070 暂存集复跑） | ✅ |
| V-11 | S-1..S-16 锚点抽查 | RFC 8785/SLSA/PROV-O/OpenLineage/DVC/Lean/PRISMA/OPA/MLflow/OWASP/Pandoc/Nix URL 与 P-070 检索记录一致（抽查 8/16） | ✅ 无幻觉 |
| V-12 | 编号让位 | P-070 占用补充调研批、M0 顺延 P-071 的订正在 PROGRESS 与 readiness 修订头均一致 | ✅ |

## 2. 复审发现

### 缺陷：无

P-069/P-070 的事实断言、决策采纳、编号与登记全部成立。

### 观察项（O 表）

| # | 内容 | 定级 |
|---|---|---|
| O-1 | readiness §2 称「`researchclaw` 内无 CitationLabel 词表」**不完全精确**：vendor 侧已有 `CitationLabel` 枚举与 `decide_citation_label` 判定链（`vendor/auto_prover/verdict/policy.py`）。G3 M3「Stage 14/17/22 接入 CitationLabel」应优先**复用 vendor 枚举**而非新建词表，避免双词表漂移 | 文档/设计输入 |
| O-2 | 总纲存在 **4 条既有 P2 断链**（`../spec/arc-cli-agent-wiring/` 等旧 §9 索引行，L788..L791），经 stash 验证在已提交 HEAD 上即存在，非本轮引入；`docs/` 与 `spec/` 路径在总纲根目录下应为 `spec/...`（无 `../`）。建议在 G3 M0 或专项小批顺带修复 | 文档卫生 |
| O-3 | Q-3（capped 记录 `cap_reason`）与现有 gate payload 尚无该字段；P-073 实现时需与 M5 `claim_gate.json` 契约协同升版 | 实现注意 |
| O-4 | Q-4 Stage 14 生产 annotation：需明确 Stage 14 输出（`experiment_summary.json`/VerifiedRegistry）与 `claim_id` 的映射来源，避免 LLM 生成 claim id 与 Stage 14 数据无法对齐 | 设计输入 |
| O-5 | Q-5 事件链锚定依赖 M2 `stage_events.jsonl` 先行；若 M1/M2 并行，`--check` 的事件链校验应特性开关或后置 | 排序注意 |
| O-6 | 切片表 M1/M2「可并行」与 P-073 M3 依赖 M1 的约束一致，但未写明 M2 的 FC-1..3 依赖 Stage 5/12 的 `plan_sig` 取数字段，M2 开工前需先冻结 | 设计输入 |

## 3. 结论

- **P-069/P-070 成立**：V-1..V-12 全过，现状盘点、决策采纳、编号与登记零幻觉。
- **无缺陷**；6 项观察均为设计输入/文档卫生级，全部可作为 **P-073 G3 M0 设计冻结**的强制输入（其中 O-1 的「复用 vendor CitationLabel」应写入 M0 决策）。
- 编号让位：本批占用 P-072，G3 M0 顺延 **P-073**。
