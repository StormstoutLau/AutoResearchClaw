---
id: arc-stage10-intra-stage-checkpoint-CHECKLIST
type: design
version: 1.1
status: accepted
date: 2026-11-26
depends: [arc-stage10-intra-stage-checkpoint-IMPLEMENTATION]
upstream: arc-stage10-intra-stage-checkpoint-IMPLEMENTATION
---

# 验收清单：B-33 M1

| ID | 断言 | 结果 |
|---|---|---|
| C-1 | 无 checkpoint 时 `read_checkpoint` 返回 `None` | ✅ `test_no_checkpoint_returns_none` |
| C-2 | 阶段完成后返回下一阶段 | ✅ `test_completed_stage_returns_next` |
| C-3 | `in_progress_stage` 优先于下一阶段（V-1） | ✅ `test_in_progress_stage_wins_over_next` |
| C-4 | `_write_stage_start` 保留 `last_completed_stage` 且写 `in_progress_*` | ✅ `test_preserves_last_completed` |
| C-5 | 阶段 DONE 后 `in_progress` 被清除 | ✅ `test_completion_clears_in_progress` |
| C-6 | 蓝图成功后 `architecture_spec.yaml` 已落盘（V-9） | ✅ `test_artifact_written_on_success` |
| C-7 | YAML 解析失败时原始文本仍落盘（V-9 负向面） | ✅ `test_artifact_written_even_when_yaml_is_bad` |
| C-8 | 蓝图截断重试以 `variant=retry` 记账（复合键口径） | ✅ `test_truncated_retry_is_tagged`（2 次调用） |
| C-9 | 账本只存摘要，不含蓝图/代码正文（V-7） | ✅ `test_journal_body_contains_no_spec_text`、`test_payload_has_no_code_body` |
| C-10 | `seq` 严格单调 | ✅ `test_seq_is_monotonic` |
| C-11 | 账本末尾坏行容忍、中间坏行抛错 | ✅ `test_torn_tail_is_tolerated`、`test_corrupt_middle_raises` |
| C-12 | `last_done` 忽略 `truncated`，variant 属身份的一部分 | ✅ `test_ignores_truncated`、`test_variant_is_part_of_identity` |
| C-13 | `should_skip` 全部匹配才命中 | ✅ `test_hit_when_everything_matches` |
| C-14 | 输入摘要变化即 miss（V-3） | ✅ `test_miss_on_input_change` |
| C-15 | `code_version` / `prompt_version` 变化即 miss（V-4） | ✅ `test_miss_on_code_version_change`、`test_miss_on_prompt_version_change` |
| C-16 | 产物被篡改或删除即 miss（V-5、V-6） | ✅ `test_miss_when_output_tampered`、`test_miss_when_output_deleted` |
| C-17 | 无 outputs 的步骤不复用 | ✅ `test_miss_when_no_outputs_recorded` |
| C-18 | `code_version` 形如 `<pkg>+<8 hex>`（D-8 单一算法） | ✅ `test_code_version_shape` |
| C-19 | 事件重建回填 `in_progress_stage`（D-9，复审 D-4） | ✅ `test_rebuild_checkpoint_marks_unfinished_stage`、`test_recover_from_events_resumes_interrupted_stage` |
| C-20 | 已完成阶段不被标记为在飞；重试以最后一次 `started` 为准 | ✅ `test_rebuild_checkpoint_no_in_progress_after_completion`、`test_rebuild_checkpoint_retry_uses_last_start` |
| C-21 | `code_version` 经 `importlib.resources` 可读生成器源码，文件缺失有兜底（D-5） | ✅ `test_code_version_reads_package_files`、`test_code_version_changes_when_generator_bytes_change`、`test_code_version_survives_missing_files` |
| C-22 | 更早的完成阶段不掩盖在飞阶段，完成后退回下一阶段 | ✅ `test_in_progress_wins_over_older_completed`、`test_in_progress_cleared_for_later_stage` |
| C-23 | 新测试全绿 | ✅ 55 passed（journal 22 + in-progress 9 + blueprint 6 + event_log 18） |
| C-24 | 相关回归无退化 | ✅ 63 passed（code_agent/entrypoint/truncation）+ 72 passed（runner/checkpoint） |
| C-25 | B 站部署后 `--resume` 落在 Stage 10 | ⏳ 待现场（未部署） |
| C-26 | `checkpoint.json` 写 `continuation_anchor`（`step_id` 复合键，非阶段名） | ⏳ 未实施（DESIGN v1.1 D-10） |
| C-27 | 阶段重试入口写 `abandoned_attempt` 摘要（attempt/时间/产物/最后 step_id） | ⏳ 未实施（DESIGN v1.1 D-11） |
| C-28 | 全仓不新增 `handoff.md`，断点真值仅 `steps.jsonl` | ✅ 设计层确认（DESIGN v1.1 D-12，实现未引入） |

## 算术

24 项本地断言 + 1 项现场待验 + 2 项设计已裁决待实施。通过 24（C-1..C-24）+ C-28 设计确认，待验证 1（C-25），待实施 2（C-26、C-27）。

## 边界

- L2（生成路径实际跳过）与 L3（LLM 响应缓存）不在本批，`should_skip` 暂无主线调用点。
- checkpoint 损坏且事件链中无任何 `stage.completed`（首个阶段即中断）时无法自动恢复，需人工 `--from-stage`。

