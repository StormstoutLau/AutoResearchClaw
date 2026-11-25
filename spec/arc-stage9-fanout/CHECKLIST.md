---
id: arc-stage9-fanout-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-25
depends: [arc-stage9-fanout-IMPLEMENTATION, arc-stage9-fanout-DESIGN]
upstream: arc-master-roadmap
---

# 审查验收 Checklist：Stage 9 计划派生健壮化（P-177）

> **计数**：**31 项 = 文档 4 + 功能 10 + 接口 3 + 不变式 7 + 错误 4 + 测试与门禁 3**。
> **状态**：31/31 功能面通过；门禁全绿；CI round 1 = run `45624474598` 8/8（round 2 见 PR #53）。

## 1. 文档一致性

| 检查项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| D-1 RESEARCH 有现场读数 | RESEARCH v1.1 | O-1..O-12 可复核 | ✅ | [RESEARCH.md](RESEARCH.md) §1 |
| D-2 DESIGN 覆盖实现 | 四文档 | D-1..D-9 均有落点 | ✅ | D-1↔schema；D-2/D-3↔derive；D-4↔`_take_owned`；D-5↔抽取；D-6↔_synthesis；D-7↔exit_codes；D-8↔exp_plan；D-9↔rebuild |
| D-3 IMPLEMENTATION 锚点可达 | 四文档 | ≥10 个文件/行锚点 | ✅ | [IMPLEMENTATION.md](IMPLEMENTATION.md) §1（16 行） |
| D-4 术语一致 | 四文档 | shard / 派生 / 幂等 / 契约修复同义 | ✅ | 四文档一致 |

## 2. 功能验收

| 验收项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| F-1 H1 小节抽取 | DESIGN §2.1 | `# Sub-questions` + `SQ1..4` → 4 条 | ✅ | `test_sub_questions_from_sq_headings` |
| F-2 goal 跳过提示块 | DESIGN §2.1 | 不含 `Note (Stage 01` | ✅ | `test_goal_skips_blockquote_note` |
| F-3 CJK 假设抽取 | DESIGN §2.1 | `最终假设 1` + 下一标题 → 真实陈述 | ✅ | `test_hypotheses_from_chinese_markers` |
| F-4 语句无 Markdown 标记 | DESIGN §2.1 | 不以 `#` 开头 | ✅ | `test_no_markdown_markers_in_statements` |
| F-5 真实规模可校验 | DESIGN §2.2 | 4 根 + 6 gap + 2 假设 + 12 实验 → 0 违规 | ✅ | `test_realistic_scale_is_valid` |
| F-6 fanout 有界 | DESIGN §2.2 | fanout ≤ 8 | ✅ | 同 F-5 |
| F-7 depth 允许语义链 | DESIGN D-1 | `DEFAULT_MAX_DEPTH >= 4` | ✅ | `test_depth_default_allows_semantic_chain` |
| F-8 实验依赖假设 | DESIGN D-2 | 12 个实验全部依赖 hypothesis | ✅ | `test_experiments_rest_on_hypotheses` |
| F-9 幂等（三处） | DESIGN D-4 | 重跑节点数不变 | ✅ | `test_stage{7,8,9}_twice_is_stable` |
| F-10 重建产出合法计划 | DESIGN D-9 | 0 违规 + version 递增 | ✅ | `test_rebuild_produces_valid_plan` |

## 3. 接口验收

| 验收项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| I-1 CLI 可用 | DESIGN D-9 | `plan rebuild --run-dir` 帮助可打印 | ✅ | `python -m researchclaw plan rebuild --help` |
| I-2 契约修复签名 | DESIGN D-8 | `ensure_methods(plan, *, llm, topic, hypotheses)` | ✅ | [exp_plan.py L81-L90](../../researchclaw/plan/exp_plan.py#L81-L90) |
| I-3 builder 签名不变 | DESIGN §2 | 四个公开 builder 参数不变 | ✅ | 计划套件 54 passed（既有调用零改动） |

## 4. 不变式

| 不变式 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| J-1 幂等 | DESIGN §3 | 同输入两次集合相同 | ✅ | F-9 |
| J-2 子节点 ≤ max_fanout | DESIGN §3 | 0 违规 | ✅ | F-5/F-6 |
| J-3 depth ≤ max_depth | DESIGN §3 | depth=3（≤4） | ✅ | F-5 |
| J-4 实验优先挂假设 | DESIGN §3 | 全部 experiment 依赖 hypothesis | ✅ | F-8 |
| J-5 外部依赖者受保护 | DESIGN §3 | `_take_owned` protected 集 | ✅ | [derive.py L203-L237](../../researchclaw/plan/derive.py#L203-L237) |
| J-6 无悬空依赖 | DESIGN §3 | 重跑后 V3 无违规 | ✅ | F-9（`validate_plan == []`） |
| J-7 确定性违规不重启 | DESIGN §3 | 分类 ≠ RETRYABLE | ✅ | `test_plan_violation_is_not_retryable`、`test_exp_plan_mismatch_is_not_retryable` |

## 5. 错误处理

| 场景 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| E-1 空 dict 仍 PAUSED | DESIGN §4 | `schema_deficient` 且不写 exp_plan | ✅ | `test_empty_dict_response_pauses`（5 passed） |
| E-2 exp_plan 缺键可修复 | DESIGN §4 | 一次重生成后含 methods | ✅ | `test_repair_fills_missing_methods` |
| E-3 已有方法不额外调用 | DESIGN §4 | llm.calls == 0 | ✅ | `test_existing_methods_skip_llm` |
| E-4 rebuild 违规不落盘 | DESIGN §4 | `persisted=False` 且旧计划保留 | ✅ | [rebuild.py L104-L106](../../researchclaw/plan/rebuild.py#L104-L106) |

## 6. 测试读数

| 项 | DoR | DoD | 状态 | 证据 |
|---|---|---|---|---|
| T-1 新用例 | CHECKLIST §2-§5 | 全绿 | ✅ | 15 passed |
| T-2 计划套件 | 新 + 既有 | 全绿 | ✅ | 54 passed |
| T-3 相关面 | plan/synthesis/exit_code | 全绿 | ✅ | 126 passed |

## 7. 诚实边界

1. 抽取是规则式，无法覆盖任意格式；失败时回退为「首行/主题」，计划质量下降但不静默。
2. 实验→假设是容量轮转，不是语义匹配。
3. `rebuild` 会丢弃人工新增的非派生节点（U-177-3）。
4. 全量 6 项环境态失败与历史一致（Windows shell hook / Keras 3 ×4 / bash 路径），与本批无关。

## 8. 门禁与 CI

| 门禁 | 读数 |
|---|---|
| `dc_validator` | 4 文件 / **0 违规** |
| `step-gate` | **5/5 pass**（research → design → implement → verify → finalize） |
| `verify-anchor` | **10 真实 / 0 硬性 / 0 软性** |
| `step_enforce` | `mode=batch pid=P-177 digest_bound=1` |
| `pre-commit` | **10/10 Passed** |
| 两轮 CI | round 1 = run `45624474598`（8/8）；round 2 = 本提交 |

## 9. 批次自审（ADD）

| 项 | 级别 | 内容 | 处置 |
|---|---|---|---|
| P3-1 | low | shard 语句含完整 goal，超长 goal 会撑大节点文本 | statement 由 `_trim(300)` 截断 |
| P3-2 | medium | 受保护节点与新派生同 key 时可能产生重复 | 仅出现在「先跑 Stage 9 再回退到 8」的罕见路径；登记 U-177-5 |
| P3-3 | low | `ensure_methods` 回退会生成合成方法名 | 已有 `logger` 告警；不静默通过验收 |
