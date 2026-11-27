---
id: arc-stage10-generation-budget-contract-CHECKLIST
type: design
version: 1.2
status: accepted
date: 2026-11-27
depends: [arc-stage10-generation-budget-contract-IMPLEMENTATION]
upstream: arc-stage10-generation-budget-contract-IMPLEMENTATION
---

> v1.1（2026-11-27，P-211）：C-28 由「待现场」转 ✅（运行 H 读数）；新增 C-29（配置解析缺陷）与 C-30（运行 H 的对照）。
> v1.2（2026-11-27，P-219）：M5 新增 C-31..C-33（模块级符号契约、一次定向修复、边界失败记账）。

# 验收清单：B-34 M4（思考预算分档 + 文件预算 + 符号契约）

| ID | 断言 | 结果 |
|---|---|---|
| C-1 | `thinking_policy=off` 时三类模块都不发任何思考字段（D-3） | ✅ `test_policy_off_sends_nothing` |
| C-2 | `tiered` 下 `config.py` 发 `reasoning_effort=low` | ✅ `test_mechanical_modules_get_low_effort[config.py]` |
| C-3 | `settings.py` 判为机械模块 | ✅ `test_mechanical_modules_get_low_effort[settings.py]` |
| C-4 | `schema.py` 判为机械模块 | ✅ `test_mechanical_modules_get_low_effort[schema.py]` |
| C-5 | `utils.py` 判为机械模块 | ✅ `test_mechanical_modules_get_low_effort[utils.py]` |
| C-6 | `io.py` 判为机械模块 | ✅ `test_mechanical_modules_get_low_effort[io.py]` |
| C-7 | `loader.py` 判为机械模块 | ✅ `test_mechanical_modules_get_low_effort[loader.py]` |
| C-8 | 设计模块（`methods.py` / `tau_kl_model.py`）不发字段（D-5） | ✅ `test_design_module_keeps_default_thinking` |
| C-9 | `thinking_core_max_tokens>0` 时设计模块发 `reasoning.max_tokens` | ✅ `test_design_module_can_be_bounded` |
| C-10 | 机械档 effort 可配置（`medium`） | ✅ `test_mechanical_effort_can_be_configured` |
| C-11 | 机械档 effort 置空即不发字段 | ✅ `test_mechanical_effort_can_be_empty` |
| C-12 | 顺序生成把分档送到 LLM，并把行预算写进 prompt | ✅ `test_tier_reaches_the_llm_and_prompt_has_budget` |
| C-13 | 设计模块的 `max_tokens` 上限送达 | ✅ `test_core_limit_reaches_design_module` |
| C-14 | 蓝图 `max_lines` 覆盖配置默认值（D-6） | ✅ `test_blueprint_value_wins` |
| C-15 | `max_lines` 非法值回落配置默认 | ✅ `test_invalid_value_falls_back` |
| C-16 | 行预算下限 40 | ✅ `test_floor_is_forty` |
| C-17 | 声明符号齐全 → 契约通过 | ✅ `test_declared_symbols_present_passes` |
| C-18 | 声明函数缺失 → `blueprint_symbols_missing`（含 `file:symbol`） | ✅ `test_missing_method_fails` |
| C-19 | 声明类缺失 → 同上 | ✅ `test_missing_class_fails` |
| C-20 | 文件缺失只由文件门报（D-7 不重复） | ✅ `test_absent_file_is_left_to_the_file_gate` |
| C-21 | 蓝图未声明符号 → 跳过（D-8） | ✅ `test_no_declarations_skips_the_gate` |
| C-22 | 文件不可解析 → 判失败而不是跳过（D-10） | ✅ `test_unparsable_file_fails_rather_than_passing` |
| C-23 | `evaluate_stage10_evidence` 汇总含符号失败 | ✅ `test_evaluate_reports_it` |
| C-24 | `extra_body` 合并进请求体（含嵌套 `chat_template_kwargs`） | ✅ `test_extra_body_is_merged_into_payload` |
| C-25 | 不传 `extra_body` 时请求体保持干净（D-2 负向面） | ✅ `test_no_extra_body_keeps_the_payload_clean` |
| C-26 | 相关回归无退化 | ✅ 182 passed（九文件）+ 78 passed（LLM 三文件） |
| C-27 | 有严格 TDD 红→绿记录 | ⚠️ **无**：实现先于测试；仅有兼容性红（4 例）与测试自身缺陷（1 例），见 IMPLEMENTATION §4 |
| C-28 | B 站配置 `thinking_policy=tiered` 后截断率下降 | ✅ 运行 H：首轮截断 4/4 → **1/5**；`data.py` 由「32 768 仍截断→失败」变为 **6 249 一次成功**（320 行）；`config.py` 2 542（39 s）。详见 [postmortem §2.5](../../docs/arc-b-site-stage10-postmortem-20261126.md) |
| C-29 | yaml 的四个新键能被 `_parse_code_agent_config` 解析（修复前 `policy` 回落 `off`） | ✅ `test_new_keys_are_parsed` / `test_defaults_survive_an_empty_block`；修复后线上复读 `policy=tiered core=2048` |
| C-30 | 运行 H 的失败点已不在生成/提取层 | ✅ attempt 1 在 `data.py` 代码校验 + repair 无效处失败（`CRITICAL validation issues remain after 5 repair attempts`） |
| C-31 | 模块生成后立即判定声明符号，缺失即在该模块报出 | ✅ `TestModuleSymbolContract::test_missing_helper_reports_absent_names` + 生成路径用例 |
| C-32 | 缺符号时只做一次定向修复，提示含声明名与缺失名；契约满足不额外调用 | ✅ `test_missing_symbol_is_repaired_once` / `test_satisfied_contract_costs_no_extra_call` |
| C-33 | 修复后仍缺 → 该模块边界 `ModuleExtractionError(reason=symbols_missing)`，账本留 `failed` 行 | ✅ `test_unrepaired_module_fails_at_its_own_boundary` |

## 算术

| 段 | 通过 | 待现场 |
|---|---|---|
| 思考分档 | 11（C-1..C-11、C-13） | 0 |
| 顺序接线 | 1（C-12） | 0 |
| 行预算 | 3（C-14..C-16） | 0 |
| 符号契约 | 7（C-17..C-23） | 0 |
| 客户端透传 | 2（C-24..C-25） | 0 |
| 回归 | 1（C-26） | 0 |
| 过程/现场 | 1（C-27 ⚠️） | 1（C-28） |
| **合计** | **27 项本地断言 + 1 过程项** | **0 项现场待验**（C-28/C-30 已由运行 H 关闭） |

## 边界

- 分档依赖文件名子串，算法写在 `utils.py` 会被降档。
- 符号契约只证明名字存在，空实现可通过。
- `max_lines` 只提示，不阻断。
- `tiered` 仅适用于接受这些字段的 endpoint（严格 provider 会 400）。
- 未做 C++（函数级分块）与 A'（65536 兜底），两者见 §F-7b.8。
- C-27 为 ⚠️：本批无严格 TDD 红态，已如实标注，不作「红→绿」宣称。
