---
id: arc-stage10-module-extraction-fallback-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-26
depends: [arc-stage10-module-extraction-fallback-IMPLEMENTATION]
upstream: arc-stage10-module-extraction-fallback-IMPLEMENTATION
---

# 验收清单：B-34（M1-a / M1-b + F-1..F-6）

| ID | 断言 | 结果 |
|---|---|---|
| C-1 | 完整回答漏闭合围栏时可提取（M1-a 正例） | ✅ `test_unclosed_fence_is_extracted` |
| C-2 | 已闭合围栏的提取结果不变（M1-a 负向面） | ✅ `test_closed_fence_is_unchanged` |
| C-3 | 无围栏但语法合法的原文仍被接受 | ✅ `test_unfenced_valid_python_is_still_accepted` |
| C-4 | 对话式回复仍被拒绝（不因补围栏而放宽） | ✅ `test_conversational_reply_is_still_rejected` |
| C-5 | 升级后仍截断 → `ModuleExtractionError`、`steps.jsonl` 记 `failed`、第二个模块不再请求（M1-b / D-2/D-3/D-4） | ✅ `test_still_truncated_after_escalation_fails_fast`（`calls == [8192, 32768]`） |
| C-6 | 空响应不升级预算即失败，账本 `truncated=false` | ✅ `test_empty_response_fails_without_escalation` |
| C-7 | 数据源只出现在注释不满足门（F-1 假阴性关闭） | ✅ `test_comment_only_mention_does_not_satisfy_source` |
| C-8 | 字符串常量中的数据源仍算命中（F-1 负向面） | ✅ `test_string_literal_still_satisfies_source` |
| C-9 | 注释提到 `np.random` 不再标合成（F-5 假阳性关闭） | ✅ `test_comment_random_is_not_synthetic` |
| C-10 | 真实 `np.random` 仍标合成（F-5 负向面） | ✅ `test_real_random_is_synthetic` |
| C-11 | 不可 tokenize 的文件保持原文（fail-open / D-5） | ✅ `test_unparsable_file_falls_back_to_raw_text` |
| C-12 | `*Config` 含真实方法计入计算单元（F-2） | ✅ `test_config_suffix_with_real_method_counts` |
| C-13 | 纯声明配置仍不计（F-2 负向面） | ✅ `test_declarative_config_still_excluded` |
| C-14 | 仅 docstring 的方法仍视为无行为 | ✅ `test_docstring_only_method_still_excluded` |
| C-15 | 普通类仍计 1 个计算单元（不回归） | ✅ `test_regular_class_still_counts` |
| C-16 | `auroc(delta)` 完整保留（F-3） | ✅ `test_metric_name_is_kept_whole[auroc(delta)-auroc(delta)]` |
| C-17 | `hit@k[5]` 完整保留（F-3） | ✅ `test_metric_name_is_kept_whole[hit@k[5]-hit@k[5]]` |
| C-18 | `auroc{0.5}` 完整保留（本已正确，防回归） | ✅ `test_metric_name_is_kept_whole[auroc{0.5}-auroc{0.5}]` |
| C-19 | `50%-winrate` 不回归（P-202 成果） | ✅ `test_metric_name_is_kept_whole[50%-winrate-50%-winrate]` |
| C-20 | 普通指标名不回归 | ✅ `test_metric_name_is_kept_whole[auroc_delta-auroc_delta]` |
| C-21 | 竖线分隔符仍终止捕获（D-7 负向面） | ✅ `test_separator_still_stops_the_capture` |
| C-22 | `bool` 叶子显式忽略（F-4 / D-8） | ✅ `test_bool_leaf_is_ignored_explicitly` |
| C-23 | `bool` 不遮蔽兄弟叶子（F-4 负向面） | ✅ `test_bool_does_not_hide_sibling_leaves` |
| C-24 | 版本回落可观测且返回 `0+…`（F-6 / D-9） | ✅ `test_code_version_fallback_is_logged` |
| C-25 | 相关回归无退化 | ✅ 195 passed（11 文件）+ 302 passed（executor/stages/e2e） |
| C-26 | 有真实红→绿记录（逐条读数见 IMPLEMENTATION §4） | ✅ 红 9 failed / 15 passed → 绿 24 passed |
| C-27 | B 站 Stage 10 重跑时缺模块在模块处即失败而非四小时后 | ⏳ 待现场（未部署） |

## 算术

| 段 | 通过 | 待现场 |
|---|---|---|
| M1-a | 4（C-1..C-4） | 0 |
| M1-b | 2（C-5..C-6） | 0 |
| F-1/F-5 | 5（C-7..C-11） | 0 |
| F-2 | 4（C-12..C-15） | 0 |
| F-3 | 6（C-16..C-21） | 0 |
| F-4 | 2（C-22..C-23） | 0 |
| F-6 | 1（C-24） | 0 |
| 回归/过程 | 2（C-25..C-26） | 0 |
| **合计** | **26 项本地断言** | **1 项现场待验** |

## 边界

- 只覆盖顺序生成路径；单发 / tree search / review 的失败语义未改。
- 抛异常后 `code_agent_log.json` 不落盘，证据改由 `steps.jsonl` 与 stage error 承担。
- docstring 里的数据源仍算命中（只剔注释 token）。
- F-2 是语法级判据：空壳方法（`return None`）也会被计为计算单元。
- F-3 保留括号：散文里的闭括号可能让指标名 mismatch（显式失败，不猜截断）。
- M2（prompt 瘦身）未做；生成预算未提高。
- C-27 只证明代码路径可达（单测），未在真实模型输出与 B 站上跑过。
