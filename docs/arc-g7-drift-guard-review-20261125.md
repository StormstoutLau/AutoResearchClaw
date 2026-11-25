# P-167（G7 漂移护栏）异构独立复审报告

---
id: arc-g7-drift-guard-review-20261125
type: review
version: 1.0
status: final
date: 2026-11-25
reviewer: GLM-5.3-Flash
implementer: DeepSeek-V4.1-Flash
target: PR #47（spec/p167-g7-drift-guard，head 01a34c7，含 P-167+P-168）
---

> **复审性质**：异构基座独立复审（RULE-5）+ RULE-6 单向权限（只标记不修复）+ RULE-1 独立 pass。登记批随 PR #47 同分支提交（P-163 先例：批次 + 其复审同 PR）。
> **取证纪律**：探针落 `%TEMP%\arc-rv167\`（机检 + 边界探针），**零仓库变异**；结论绑定 E1-E4。

## 1. 结论（诚实结果列）

**P-167 三条主线一手成立、FA-1..FA-3 经边界探针全成立、计数零幻觉；0 P1 / 0 P2 / 0 P3，登记 4 项观察（O-168-1..4，已追加至观察项登记表）。零发现按 RULE-6(c) 降级重扫（阈值边界注入控制 + CJK/环境变量/scope 边角），仍为零。**

| 主张 | 复审判定 | 证据 |
|---|---|---|
| 15 用例全过（12 单测 + 3 集成） | ✅ 复跑 `test_drift_guard + test_rc_executor` 222 passed | E1 |
| FA-1 无关分析 → PAUSED | ✅ 探针 PR-12b（lexical rq_cos=0.0 → pause）+ PR-12 StageResult 字段逐项正确 | E2 |
| FA-2 正常分析 → DONE | ✅ T04 复跑 | E1 |
| FA-3 批准 PIVOT → exempt | ✅ T05 复跑 + PR-7（approved=false → 不豁免）+ PR-8（错 schema → 未批准） | E1/E2 |
| 词面后端 ≥0.20 绝不 PAUSE（J-5） | ✅ 注入后端边界精确控制：0.35→warn、0.34→pause；unsupported 0.40→warn（不 >） | E2 |
| `unsupported=None` 不 PAUSE（J-2） | ✅ PR-4（cos=0.10 + None → warn） | E2 |
| `embed_fn` 失败不崩、降级 warn | ✅ PR-5（rq_cos_unavailable） | E2 |
| 环境变量越界钳位 | ✅ PR-9（1.5 / -0.2 → 默认 0.45） | E2 |
| 报告总写入 + backend/thresholds 记录 | ✅ PR-12 + T10 | E1/E2 |
| digest 绑定 | ✅ 4/4 OK；session 5 步链完整 | E1 |
| CHECKLIST 算术 | ✅ 4+9+5+7+4+3=32；26 通过列和 26 → 32=32+0+0（逐行核对） | E1 |
| diff 面 vs 意图 | ✅ 14 files / +1500 / -14，恰为 guards+接线+15 测试+registry+四文档+session+3 派生视图 | E1 |
| 观察项登记 17 项 | ✅ 15 普通行 + 2 加粗 high 行（O-165-3/O-165-6）= 17 | E1 |
| 三轮 CI + PR 态 | ✅ 45465677366 / 45466275642 / 45466889199 全 success；PR47 OPEN/MERGEABLE | E1 |
| 引用真实性 | ✅ E1-E12 全部在本会话回原文（arXiv abs / 官方文档直取，含 MLR-Bench "80%" 原句、2601.03315 六失败模式、OpenAI tripwire 机制） | E1 |

## 2. T 表：一手复验

| # | 复验项 | 读数 | 等级 |
|---|---|---|---|
| T-1 | 触及面复跑 | drift+executor **222 passed**；stages/runner/claim **132 passed**（合计 354） | E1 |
| T-2 | 关键代码读 | `_apply_drift_guard` 双调用点（L1176 agent 路径 / L1422 标准路径）；PAUSE 返回 `StageStatus.PAUSED` + `E_DRIFT_DETECTED` + `decision="refine"`；runner 既有 PAUSED 不推进语义复用 | E3 |
| T-3 | digest 绑定 + session | 4/4 OK（CHECKLIST 175cb203…、DESIGN 928fa253…、IMPL 124c6446…、RESEARCH 9c472890…）；5 步链 | E1 |
| T-4 | CHECKLIST 算术 | 逐行核对 32=32+0+0 | E1 |
| T-5 | diff 面 | 14 files / +1500 / -14，无越界文件 | E1 |
| T-6 | 登记表一致性 | 17 行（O-161×5 + O-163×6 + O-165×6）；high 标记 2 项；全 open | E1 |
| T-7 | CI ×3 + PR | 三 run 全 success（2m23s/2m29s/2m28s）；OPEN/MERGEABLE | E1 |
| T-8 | 改动引入面 | 新增 guards 模块无 subprocess/socket/network；`_analysis.py` 仅插入调用 | E1/E3 |
| T-9 | 消费者零破坏 | 无参调用与既有 Stage 15 测试全过（222 内含） | E1 |
| T-10 | 引用抽查 | MLR-Bench 80%、2601.03315 六失败模式、OpenAI tripwire 原文回读一致 | E1 |

## 3. 探针明细（E2，12 项）

| # | 场景 | 结果 |
|---|---|---|
| PR-1 | 注入后端 cos=0.35（= rq_pause） | warn（0.35 不 < 0.35），边界严格 |
| PR-2 | cos=0.34 | pause |
| PR-3 | unsupported=0.40（= 阈值） | warn（不 > 0.40） |
| PR-4 | unsupported=None + cos=0.10 | warn，绝不 PAUSE（J-2） |
| PR-5 | embed_fn 抛异常 | warn + rq_cos_unavailable，backend=injected |
| PR-6 | lexical 完全无关文本 | rq_cos=0.0 → pause（FA-1 同路径）；0.20 边界由注入后端结构性覆盖 |
| PR-7 | approved=false + PIVOT | pause（不豁免） |
| PR-8 | scope 文件错 schema | 视为未批准（None） |
| PR-9 | env 越界 1.5 / -0.2 | 钳位回默认 0.45 |
| PR-10 | extract_conclusion 无标题 | 末 400 字符回退 |
| PR-11 | CJK p_only | **0.0**（见 O-168-3） |
| PR-12 | pass/pause 双态 | 报告总写入；PAUSE StageResult 字段逐项正确 |

## 4. O 表：观察项（已同步追加至 docs/observations-registry.md）

| # | 观察 | 证据 | 建议 |
|---|---|---|---|
| O-168-1 | **agent-mode requirements 路径的漂移接线无测试覆盖**（3 个集成用例只走 `_execute_research_decision`）；代码读确认 L1176-1193 接线正确 | E3 | 下次触碰 Stage 15 时补 1 个 agent 路径用例 |
| O-168-2 | agent 路径 drift PAUSE 时早退于 `requirements_verdict.json` 写出（L1192 早于 L1195），verdict 仅存于 decision_structured.json | E3 | 可接受；如下游依赖 verdict 文件需调整顺序 |
| O-168-3 | p_only 分句要求 `。！？` 后有空白；无空格的中文文本整段成单句 → `p_only_ratio` 恒 0（D-4 已声明"非英文覆盖有限"，本探针具体化） | E2 PR-11 | 后续按标点直接切分（去空白要求） |
| O-168-4 | `_read_prior` 捕获全部异常返回空串 → 接线错误会静默降级为 insufficient_inputs WARN | E3 | 收窄 except 或加一次性告警 |

### 4.3 盲区扫描范围声明（RULE-6c/E4）

- 扫描面：32 项 CHECKLIST 断言、15 新测试、drift.py 全部分支（判定 7 步顺序、边界严格性、异常路径）、Stage 15 双路径接线、scope 契约三态（approved/false/坏文件）、env 钳位、报告落盘、派生视图。
- 零发现处置：首轮机检+代码读+6 探针零缺陷 → 换角度（注入后端精确边界、CJK、env 越界、scope 三态、双路径）重扫 6 项 → 仍零 → 记合规并声明范围。
- 未覆盖：真实 LLM 语义后端（本批无）、HITL scope producer（未接线，DESIGN 已声明）、护栏 B/C。

## 5. 与 P-161/P-163/P-165 复审口径对照

| 项 | P-161 | P-163 | P-165 | 本复审（P-168） |
|---|---|---|---|---|
| 缺陷 | D-1/D-2 P2 + D-3 P3 | D-1 P2 + D-2 P3 | 0 | **0** |
| 观察 | 5 | 6 | 6 | 4（已入登记表） |
| 探针自身错误披露 | T-3 | PR-7 撤销 | PR-7 撤销 | 无 |
| 单向权限 | 未改实现 | 未改实现 | 未改实现 | 未改实现 |

## 6. 复审登记门禁（本批执行读数）

- dc（grandfather_gate）：`grandfathered=0 expired=0 violations=0`
- step-gate：`specwf-p168-g7-drift-guard-review` 5/5
- verify-anchor：见登记后输出
- step-enforce：`mode=session-progress pid=P-168`
- pre-commit：10/10 Passed

## 7. 处置建议

1. **P-167 验收通过**：FA-1..FA-3 正式成立，PR #47 可进入合并决策。
2. **O-168-1 优先**：agent-mode 漂移接线补测，随下次 Stage 15 触碰批次。
3. **O-168-2/3/4**：登记在案；O-168-3 承接时只需改 `_SENTENCE_RE` 并补 CJK 用例。
4. **边界维持**：本复审零代码变更（登记行/报告/session 除外）。
