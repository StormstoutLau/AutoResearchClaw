---
id: arc-stage10-blueprint-yaml-robust-IMPLEMENTATION
type: design
version: 2.0
status: verified
date: 2026-11-26
depends: [arc-stage10-blueprint-yaml-robust-DESIGN]
upstream: arc-stage10-blueprint-yaml-robust-DESIGN
---

# 实施记录：B-32 M1 + M2 + M3

> v1.1（2026-11-26，P-197）：补 §6 M2 四项门与折叠保护、§7 验证；§5 边界同步删去「M2 未做」。
> v2.0（2026-11-26，P-202）：补 §8 M3 硬化（F-1..F-4 + N-1）、§9 红→绿记录与回归读数。

## 1. 改动

| 文件 | 改动 |
|---|---|
| [`researchclaw/pipeline/code_agent.py`](../../researchclaw/pipeline/code_agent.py) | 新增模块级 `_TRAILING_COLON_ITEM`、`_fold_trailing_colon_items`、`_YAML_REPAIR_SUFFIX`；`_parse_blueprint` 在 sanitizer 前先跑折叠（D-1/D-2）；`_phase1_blueprint` 解析失败后调用一次 `_repair_blueprint_yaml`（D-5/D-6）；新增 `_repair_blueprint_yaml`、`_record_codegen_decision`（D-4/D-8）、`_codegen_diag`；`generate` 单发分支改为 `logger.warning` + 回退原因二分（D-7） |
| `tests/test_blueprint_yaml_repair.py`（新增） | 11 例：折叠 5 例（行尾冒号+续行、无续行、顶层 key 不动、嵌套序列不动、兄弟项截断）、真实现场片段解析、修复成功/失败、回退决策文件、结构无效原因、关闭归档时不写决策 |

### 1.1 折叠实现（核心 12 行）

```python
_TRAILING_COLON_ITEM = re.compile(r"^(?P<indent> *)-[ \t]+(?P<text>.*\S):[ \t]*$")
...
folded = [text + ":"]                     # regex consumed the colon
while j < len(lines):
    nxt_indent = len(lines[j]) - len(lines[j].lstrip(" "))
    if nxt_indent <= len(indent):
        break
    if lines[j].lstrip().startswith("- "):
        nested_sequence = True; break     # legitimate nested list, not prose
    folded.append(lines[j].strip()); j += 1
out.append(f'{indent}- "{escaped}"')
```

### 1.2 回退记录

```json
// stage-10/codegen_decision.json（D-4：不用 decision.json，避免被 _write_stage_meta 覆盖）
{
  "fallback": "single_shot",
  "reason": "blueprint_unparsable",
  "blueprint_chars": 57948,
  "yaml_repair_attempted": true,
  "at": "2026-11-26T08:22:00+00:00"
}
```

## 2. 社区源码级证据映射

| 锚点 | 原文要点 | 本批如何映射 | 验证 |
|---|---|---|---|
| S-1 `json_repair` README L116 | 先走标准库严格解析，失败才进修复器 | `_parse_blueprint` 保持「sanitized → 原文」两次严格解析，折叠只是**预处理**，不替代解析 | ✅ 原文已抓取（2026-11-26） |
| S-2 同上 L54-56 | `repair_json` 对「太烂」的输入返回空串 | `_repair_blueprint_yaml` 修复后仍解析失败即返回 `("", None)`，不伪造结构 | ✅ |
| S-3 LangChain `OutputFixingParser` | "Wrap a parser and try to fix parsing errors."；`max_retries=1` | 修复**只做 1 次**（`_YAML_REPAIR_SUFFIX` 窄提示，32768），失败即回退 | ✅ API 文档原文；源码行号未回（抓取为空，已降级） |
| S-4 本仓现场复现 | `ScannerError: could not find expected ':'` | 现场片段转为 `TestParseBlueprint::test_real_site_snippet_now_parses` | ✅ E1 可重放 |

## 3. 行为对照

| 场景 | 之前 | 现在 |
|---|---|---|
| 列表项以 `:` 结尾 + 缩进续行 | 解析失败 → 静默单发 | 折叠为带引号标量 → 解析成功 → 走顺序生成 |
| 顶层 `verification_criteria:` | 正常 | 不变（D-2） |
| 解析失败 | 只记 INFO（默认不可见） | `logger.warning` + `codegen_decision.json` |
| 解析失败且结构太薄 | 同一句 INFO，无法区分 | `blueprint_structure_invalid` 单独记因 |
| 修复成功 | — | 覆盖 `architecture_spec.yaml`，账本 `variant=yaml_repair` |
| 关闭 `architecture_planning` | — | 不写决策文件（非故障） |

## 4. 验证

```bash
python -m pytest tests/test_blueprint_yaml_repair.py -q
# 11 passed

python -m pytest tests/test_code_agent.py tests/test_blueprint_persistence.py \
  tests/test_entrypoint_contract.py tests/test_codegen_truncation.py -q
# 69 passed
```

红→绿记录：`test_trailing_colon_item_is_folded_and_parses` 首跑失败（折叠丢掉了行尾冒号，得到 `"…different Monitor A…"`），修正 `folded = [text + ":"]` 后通过；其余 10 例首跑即绿。

## 5. 边界

- **自动补齐未做**（D-9）：门判失败后不尝试按缺失清单再生成；调研 §5.2 第 4 项的「先补齐」被显式拒绝，理由见 DESIGN D-9。
- **折叠是启发式**：单 token 的 `- key:` 已由 D-14 保护（不折叠），但若模型把散文写成无空格串则不会修复。
- **决策文件名偏离调研措辞**：调研 §5.1 写 `decision.json`，实现用 `codegen_decision.json`，原因是 `_write_stage_meta` 会在阶段末重写前者（调研 §2.4）。
- **一次额外 LLM 调用**：解析失败时多一次 32768 的调用（现场约占单阶段 17 次调用的 1/17）；未设开关，理由是静默降级代价更高。
- **未部署 B 站验证**：本轮只做本地实现与回归。

## 6. M2 实施（P-197）

| 文件 | 改动 |
|---|---|
| [`researchclaw/pipeline/codegen_evidence.py`](../../researchclaw/pipeline/codegen_evidence.py)（新增） | `EvidenceFailure` / `EvidenceReport`；`load_blueprint`；`check_declared_files`（D-10）；`check_metric_consistency` + `normalize_metric`（D-11）；`check_data_source`（D-12）；`count_compute_units` / `check_compute_presence`（D-13）；`evaluate_stage10_evidence` 汇总；`write_evidence_report` 经 `safe_join` 写 `codegen_evidence.json` |
| [`researchclaw/pipeline/stage_impls/_code_generation.py`](../../researchclaw/pipeline/stage_impls/_code_generation.py#L2067-L2097) | 入口契约检查之后、DONE 之前调用四项门；失败 → `FAILED`（error 列出门 code），成功 → artifacts 追加 `codegen_evidence.json`；WARN 逐条 `logger.warning` |
| [`researchclaw/pipeline/code_agent.py`](../../researchclaw/pipeline/code_agent.py#L87-L98) | 折叠增加 D-14 保护：`text` 不含空白即视为 mapping key，原样保留 |
| `tests/test_codegen_evidence.py`（新增） | 17 例：文件门 4（全齐/缺失/optional/mapping 形态）、指标门 4、数据源 2、计算门 2、汇总 5（全绿/配置自检失败/无蓝图仍算计算门/回落 stage metric/报告落盘） |
| `tests/test_blueprint_yaml_repair.py`（修改） | 新增 1 例：单 token key + 嵌套 mapping 不被折叠；兄弟项用例改为散文 |

### 6.1 与调研 §5.2 的差异（诚实清单）

- 第 4 项「缺失时先尝试按缺失清单补齐生成」**未实现**（D-9），改为直接 FAILED。
- 第 6 项数据源门保留 WARN + `synthetic_data`，但未写回 `decision.json`（该文件被 `_write_stage_meta` 重写），改写在 `codegen_evidence.json`。
- 第 7 项「成功必须有证据」五项中，前三项（`METRIC_DEF`、`<metric>: <float>`、文件集合）由既有 B-29 契约 + 本批文件门覆盖；后两项（指标一致、非配置计算）由 D-11/D-13 覆盖。「`<metric>: <float>` 可解析」本批未新增检查（属 B-29 的 Stage 12 侧），已在 CHECKLIST 中标注未覆盖。

## 7. M2 验证

```bash
python -m pytest tests/test_codegen_evidence.py -q
# 17 passed

python -m pytest tests/test_blueprint_yaml_repair.py -q
# 12 passed

python -m pytest tests/test_codegen_evidence.py tests/test_blueprint_yaml_repair.py \
  tests/test_code_agent.py tests/test_blueprint_persistence.py \
  tests/test_entrypoint_contract.py tests/test_codegen_truncation.py \
  tests/test_simulated_guard.py -q
# 121 passed

python -m pytest tests/test_rc_executor.py tests/test_rc_stages.py \
  tests/test_rc_e2e_regression.py -q
# 302 passed
```

红→绿记录（M2）：`test_source_missing_with_synthetic_data` 首跑失败——`_find_data_sources` 只认 `data_source`，不认 `data.source`，返回空列表；补 `_SOURCE_KEYS`（`source/sources/provider`）后转绿。`test_sibling_item_stops_folding` 因 D-14 新规则（单 token 不折叠）失败，改用散文用例后转绿；同时新增 mapping 保护用例。

## 8. M3 硬化（P-202，关闭 §5.1 五项边界）

| 文件 | 改动 |
|---|---|
| [`researchclaw/pipeline/codegen_evidence.py`](../../researchclaw/pipeline/codegen_evidence.py#L29-L44) | `_METRIC_DEF_RE` 放宽为「到空白或 `\|`、`,`、`)`、`]` 为止」+ `_metric_from_text` 统一 `rstrip(".,;:'\"")`；`entrypoint_metric_name` 改为 **AST 优先**（遍历 `print` 的 `Constant` 实参），回落逐行扫描并无条件跳过 `#` 注释行（D-17）；新增 `_leaf_strings` 递归取叶子（深度上限 `_MAX_SOURCE_DEPTH=4`），`_collect_sources` / `_find_data_sources` 改走叶子、不再 `str(容器)`（D-18）；新增 `collect_delivered(files, delivered_dir)`，磁盘 `*.py` 覆盖内存映射（D-21）；`evaluate_stage10_evidence` 增 `delivered_dir` 关键字并对合并后的交付集跑四项门 |
| [`researchclaw/pipeline/code_agent.py`](../../researchclaw/pipeline/code_agent.py#L63-L137) | 新增 `_MAPPING_CONTINUATION_RE`；`_fold_trailing_colon_items` 增两条守卫——文本已含 `": "` 不折叠、续行形如 `k: v` 视为 mapping 且整项不折叠（D-19）；`_repair_blueprint_yaml` 无围栏时对齐到首个顶层 `files:` 行（D-20） |
| [`researchclaw/pipeline/stage_impls/_code_generation.py`](../../researchclaw/pipeline/stage_impls/_code_generation.py#L2070-L2079) | 证据门调用改传 `delivered_dir=exp_dir`，以磁盘产物为准（D-21） |
| `tests/test_evidence_gate_hardening.py`（新增） | 19 例：F-1 六例（注释、docstring、`50%-winrate`、注释行回落、无指标、一致性门不被注释劫持）、F-2 四例（列表 dict、嵌套 dict、真缺失仍 WARN、警告文本不含 repr）、F-3 四例（多词 key、值以冒号结尾、散文仍折、折叠后解析为字符串）、F-4 两例（无围栏对齐、围栏路径不变）、N-1 三例（磁盘优先、无 `delivered_dir` 回落映射、磁盘覆盖陈旧映射） |

### 8.1 与 §5.1 的对应

| 边界 | 关闭点 | 用例 |
|---|---|---|
| F-1 | `entrypoint_metric_name` 的 AST 主路径 + 注释行回落 | `TestF1MetricExtraction`（6） |
| F-2 | `_leaf_strings` + `_collect_sources` | `TestF2DataSourceLeaves`（4） |
| F-3 | `": "` 守卫 + `_MAPPING_CONTINUATION_RE` | `TestF3FoldingGuards`（4） |
| F-4 | `_repair_blueprint_yaml` 的 `^files:` 对齐 | `TestF4UnfencedRepair`（2） |
| N-1 | `collect_delivered` + `delivered_dir` | `TestN1DeliveredFromDisk`（3） |

### 8.2 未关闭的相邻风险（诚实登记）

- **合成入口的指标名不可静态提取**：`synthesize_entrypoint` 产出的 `print("METRIC_DEF: " + METRIC + ...)` 是拼接表达式，AST 取不到 `Constant`、回落扫描也取不到名字，因此证据门会判 `metric_not_printed`。这是 M2 起就存在的行为，P-202 未改变；因 B-30 兜底只在专用生成两次失败后触发，现场优先级低，登记不修。
- **散文里带 `k: v` 形态的续行**会被 F-3 的新守卫判为 mapping 而不折叠 → 解析失败 → 走回落。这是保护结构的代价，与 D-14 同类。

## 9. M3 验证

```bash
# 红（实现前，19 例中 12 失败）
python -m pytest tests/test_evidence_gate_hardening.py -q
# 12 failed, 7 passed
#   test_comment_is_not_mistaken_for_the_metric      assert 'old_metric' == 'auroc_delta'
#   test_docstring_is_not_mistaken_for_the_metric    assert 'stale_name' == 'auroc_delta'
#   test_name_with_percent_and_colon_is_kept_whole   assert '50' == '50%-winrate'
#   test_fallback_skips_comment_lines                assert 'old_metric' == 'window_f1'
#   test_comment_cannot_hijack_consistency_gate      [EvidenceFailure('metric_mismatch', ...)]
#   test_sources_from_list_of_dicts                  ['declared da...nerated code'] != []
#   test_no_repr_artefact_in_warning_text            "'provider'" 出现在告警里
#   test_multiword_key_with_mapping_is_not_folded    ['  - "some k...ue order: 1"'] != 原文
#   test_mapping_value_ending_with_colon_is_not_folded ['  - "name: foo bar:"'] != 原文
#   test_unfenced_repair_is_realigned_to_files_key   assert None is not None
#   test_disk_main_py_is_used_when_absent_from_the_mapping  TypeError: delivered_dir
#   test_disk_wins_over_stale_mapping                TypeError: delivered_dir

# 绿（实现后）
python -m pytest tests/test_evidence_gate_hardening.py -q
# 19 passed

python -m pytest tests/test_codegen_evidence.py tests/test_blueprint_yaml_repair.py \
  tests/test_code_agent.py tests/test_blueprint_persistence.py \
  tests/test_entrypoint_contract.py tests/test_codegen_truncation.py \
  tests/test_simulated_guard.py -q
# 121 passed

python -m pytest tests/test_rc_executor.py tests/test_rc_stages.py \
  tests/test_simulated_guard.py -q
# 317 passed
```

**过程记录**：首轮实现后仍有 1 例失败（`test_fallback_skips_comment_lines` 期望 `window_f1`，实得 `window_f1"`）——回落扫描捕获了字符串的收尾引号；把 `_metric_from_text` 的 `rstrip` 扩到引号后转绿。这是第二批红→绿，已计入 §9 的最终读数。
