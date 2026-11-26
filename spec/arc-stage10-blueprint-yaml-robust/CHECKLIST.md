---
id: arc-stage10-blueprint-yaml-robust-CHECKLIST
type: design
version: 1.1
status: accepted
date: 2026-11-26
depends: [arc-stage10-blueprint-yaml-robust-IMPLEMENTATION]
upstream: arc-stage10-blueprint-yaml-robust-IMPLEMENTATION
---

# 验收清单：B-32 M1 + M2

| ID | 断言 | 结果 |
|---|---|---|
| C-1 | 现场失败片段（行尾冒号 + 两行续行）折叠后可被 `yaml.safe_load` 解析，且续行文本保留 | ✅ `test_real_site_snippet_now_parses` |
| C-2 | 折叠结果以 `- "` 开头，续行以空格连接，不丢行尾冒号 | ✅ `test_trailing_colon_item_is_folded_and_parses` |
| C-3 | 行尾冒号但无续行时也加引号 | ✅ `test_trailing_colon_without_continuation` |
| C-4 | 顶层 mapping key（`verification_criteria:`）不被折叠（D-2） | ✅ `test_top_level_mapping_key_is_untouched` |
| C-5 | 列表项后接更深缩进的嵌套序列不被折叠 | ✅ `test_nested_sequence_is_untouched` |
| C-6 | 同层兄弟项终止折叠 | ✅ `test_sibling_item_stops_folding` |
| C-7 | 修复重试成功：账本 `variant` 序列为 `first → yaml_repair`，磁盘蓝图被替换（D-5/D-6） | ✅ `test_repair_success_replaces_blueprint` |
| C-8 | 修复失败：保留首版蓝图、账本只有 `first`、`yaml_repair_attempted=True`（D-6） | ✅ `test_repair_failure_keeps_first_version` |
| C-9 | 不可解析时写 `codegen_decision.json`，含 `fallback/reason/blueprint_chars/yaml_repair_attempted/at`（D-4） | ✅ `test_unparsable_writes_decision_file` |
| C-10 | 结构无效（<2 `generation_order`）记为 `blueprint_structure_invalid` 且不触发修复（D-7） | ✅ `test_structure_invalid_reason` |
| C-11 | 关闭 `architecture_planning` 时不写决策文件 | ✅ `test_no_decision_when_planning_disabled` |
| C-12 | 相关回归无退化 | ✅ 69 passed（code_agent/blueprint_persistence/entrypoint/truncation） |
| C-13 | B 站 Stage 10 重跑后 `codegen_decision.json` 显示顺序生成已恢复 | ⏳ 待现场（未部署） |
| C-14 | 蓝图声明的有序文件全部交付 → 文件门通过 | ✅ `test_all_present` |
| C-15 | 缺 `monitor.py` → `blueprint_files_missing` 且指出文件名 | ✅ `test_missing_file_fails` |
| C-16 | `optional: true` 的文件缺失不报错（D-10） | ✅ `test_optional_file_may_be_missing` |
| C-17 | `files` 为 mapping 形态时按 key 取文件名 | ✅ `test_files_as_mapping` |
| C-18 | `METRIC_DEF` 名与蓝图指标一致 → 通过 | ✅ `test_match` |
| C-19 | 入口指标漂移（`window_f1` vs `auroc_delta`）→ `metric_mismatch`（D-11） | ✅ `test_mismatch` |
| C-20 | 入口不打印 `METRIC_DEF` → `metric_not_printed` | ✅ `test_missing_metric_def` |
| C-21 | 蓝图无指标声明时回落到 Stage 10 `metric_key` 比较 | ✅ `test_stage_metric_is_used_when_blueprint_has_none` |
| C-22 | 声明 `data.source` 未出现在产物 → WARN + `synthetic_data=True`（D-12） | ✅ `test_source_missing_with_synthetic_data` |
| C-23 | 配置自检交付（0 个非 Config 计算单元）→ `no_compute_unit`（D-13） | ✅ `test_config_only_fails`、`test_config_only_delivery_fails` |
| C-24 | 蓝图缺失时仍执行计算门，并给出 blueprint unavailable 警告 | ✅ `test_missing_blueprint_still_checks_compute` |
| C-25 | 报告落盘为 `codegen_evidence.json`，含 ok/failures/warnings/synthetic_data/at | ✅ `test_report_is_written` |
| C-26 | 单 token 列表项（`- interface:`）不被折叠（D-14） | ✅ `test_single_token_key_with_mapping_is_untouched` |
| C-27 | Stage 10 出口在真实 LLM 产出上按门失败 | ⏳ 单测级已验证，未跑真实模型 |
| C-28 | M2 相关回归无退化 | ✅ 121 passed（codegen 七文件）+ 302 passed（executor/stages/e2e） |

## 算术

M1 12 项 + M2 13 项本地断言 = 25 项通过（C-1..C-12、C-14..C-26、C-28）；待现场 2 项（C-13、C-27）。

## 边界

- 门只判失败、不补齐产物（D-9）；「`<metric>: <float>` 可解析」由 B-29 的 Stage 12 侧负责，本批未新增。
- C-27 只证明代码路径可达（单测），未在真实模型输出上跑过。
- 折叠单 token 规则是为保护 mapping 付出的代价：无空格散文不会修复。
- 文件门只比对 basename，不校验目录层级。
