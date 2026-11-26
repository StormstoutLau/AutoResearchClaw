---
id: arc-stage10-module-extraction-fallback-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-26
depends: [arc-stage10-module-extraction-fallback-DESIGN]
upstream: arc-stage10-module-extraction-fallback-DESIGN
---

# 实施记录：B-34（M1-a / M1-b + F-1..F-6）

## 1. 改动

| 文件 | 改动 |
|---|---|
| [`researchclaw/pipeline/code_agent.py`](../../researchclaw/pipeline/code_agent.py) | 顶部导入 `_close_unterminated_fence`；新增 `ModuleExtractionError`；`_extract_single_file_code` 入口闭合围栏（M1-a）；`_phase2_sequential_generate` 记录升级预算与升级后 `truncated`，失败时写 diag + `steps.jsonl` + `logger.error` 并抛异常（M1-b）；新增 `_record_module_failure` |
| [`researchclaw/pipeline/codegen_evidence.py`](../../researchclaw/pipeline/codegen_evidence.py) | `_METRIC_DEF_RE` 终止符收窄为空白/竖线/分号（F-3）；`_leaf_strings` 显式 `bool` 分支（F-4）；新增 `_strip_comments` 并在 `check_data_source` 使用（F-1/F-5）；新增 `_class_has_behavior`，`count_compute_units` 对 `*Config` 类加行为判定（F-2） |
| [`researchclaw/pipeline/step_journal.py`](../../researchclaw/pipeline/step_journal.py) | 新增模块级 logger；`code_version()` 版本回落改 `logger.debug` 并带原因（F-6） |
| `tests/test_module_extraction_fallback.py`（新增） | 24 例：M1-a 4、M1-b 2、F-1/F-5 5、F-2 4、F-3 6、F-4 2、F-6 1 |

### 1.1 关键实现（M1-b）

```python
resp = self._chat(sp.system, sp.user, max_tokens=8192)
budget = 8192
if getattr(resp, "truncated", False):
    resp = self._chat(sp.system, sp.user, max_tokens=32768)
    budget = 32768

truncated = bool(getattr(resp, "truncated", False))
code = self._extract_single_file_code(resp.content, file_name)
if truncated or not code:
    reason = "truncated" if truncated else "empty"
    self._codegen_diag.setdefault("module_failures", []).append({...})
    self._record_module_failure(...)      # steps.jsonl, status="failed"
    raise ModuleExtractionError(file_name=file_name, reason=reason)
```

`raise` 由 [`execute_stage`](../../researchclaw/pipeline/executor.py#L712-L720) 捕获并转为 `StageStatus.FAILED`（error=`str(exc)`）；`_call_with_retries` 不介入异常路径，故不会在同一阶段内重复生成（D-11）。

## 2. 社区/标准库证据映射

| 锚点 | 原文要点 | 本批如何映射 | 验证 |
|---|---|---|---|
| A-1 `tokenize` | 注释是独立 `COMMENT` token，字符串不被拆 | `_strip_comments` 按 token 列号截断整行 | ✅ 本机探针读数见 RESEARCH §1.2/§3 |
| A-2 `ast` | 方法体 `Return` vs `Pass` / `Expr(Constant)` | `_class_has_behavior` 逐语句判平凡 | ✅ 4 例（有方法计数、纯声明不计数、docstring-only 不计数、普通类计数） |
| A-3 `json_repair` | 修不了返回空串 | 提取空/截断 → 显式异常，不返回半成品 | ✅ M1-b 2 例 |
| A-4 `OutputFixingParser` | `max_retries=1` | 8192→32768 一次升级后即止 | ✅ `calls == [8192, 32768]` |
| A-5 P-178 本仓 | 兜底只覆盖两个提取器 | 第三个（单文件）补齐 | ✅ `test_unclosed_fence_is_extracted` |
| A-6 `logging` HOWTO | DEBUG 默认不可见 | 回落用 DEBUG，`caplog` 可取证 | ✅ `test_code_version_fallback_is_logged` |
| A-7 `execute_stage` | 异常 → FAILED | 不新增失败通道 | ✅ 代码路径审阅 + M1-b 单测（异常类型可导入、抛出） |

## 3. 行为对照

| 场景 | 之前 | 现在 |
|---|---|---|
| 完整回答漏闭合围栏 | 三个正则全不匹配 + `ast.parse` 失败 → `""` | 入口补围栏 → 正常提取 |
| 升级后仍 `truncated` | 继续下一个模块，数小时后出口失败 | `steps.jsonl` 记 `failed` + 立即 FAILED |
| 提取为空（对话式回复） | WARNING 后 `continue` | 同上，`reason="empty"`，不升级 |
| 数据源只出现在注释 | 视为已交付（假阴性） | 剔除注释后 WARN |
| 注释提到 `np.random` | `synthetic_data=true`（假阳性） | 不触发 |
| `*Config` 含真实 `compute` | 0 个计算单元 → 可被误判配置自检 | 计为计算 |
| 指标名含 `()` / `[]` | 在闭括号处截断 | 完整保留 |
| 版本不可用 | 静默 `0+…` | DEBUG 记录原因，返回值不变 |

## 4. 验证

```bash
# 红（实现前）
python -m pytest tests/test_module_extraction_fallback.py -q
# 9 failed, 15 passed

# 绿（实现后）
python -m pytest tests/test_module_extraction_fallback.py -q
# 24 passed

# 相关回归
python -m pytest tests/test_module_extraction_fallback.py tests/test_codegen_evidence.py \
  tests/test_evidence_gate_hardening.py tests/test_blueprint_yaml_repair.py \
  tests/test_code_agent.py tests/test_blueprint_persistence.py \
  tests/test_entrypoint_contract.py tests/test_codegen_truncation.py \
  tests/test_step_journal.py tests/test_checkpoint_in_progress.py \
  tests/test_simulated_guard.py -q
# 195 passed

python -m pytest tests/test_rc_executor.py tests/test_rc_stages.py \
  tests/test_rc_e2e_regression.py -q
# 302 passed
```

**红→绿记录（逐条）**：

```text
test_unclosed_fence_is_extracted                         assert '' == startswith('import numpy as np')
test_still_truncated_after_escalation_fails_fast         ImportError: ModuleExtractionError
test_empty_response_fails_without_escalation             ImportError: ModuleExtractionError
test_comment_only_mention_does_not_satisfy_source        assert [] (warnings)
test_comment_random_is_not_synthetic                     assert True is False
test_config_suffix_with_real_method_counts               assert 0 == 1
test_metric_name_is_kept_whole[auroc(delta)]             assert 'auroc(delta' == 'auroc(delta)'
test_metric_name_is_kept_whole[hit@k[5]]                 assert 'hit@k[5' == 'hit@k[5]'
test_code_version_fallback_is_logged                     assert 'code_version' in ''
```

15 例首跑即绿，其中 11 例是**负向面**（闭合围栏不变、对话回复仍拒绝、字符串仍命中、真实随机仍标合成、普通类仍计数、`auroc{0.5}` 与 `50%-winrate` 不回归、分隔符仍截断、bool 不遮蔽兄弟叶子、非 F-2 项不受影响），4 例是行为不变的显式化（F-4 两例 + M1-a 的闭合/无围栏两例）。

## 5. 边界与差异

- **M2 未实施**：模块 prompt 仍注入整份蓝图；DESIGN D-10 已说明理由，B-34 在总纲保持 `in-progress` 而非关闭。
- **抛异常后 `code_agent_log.json` 不落盘**：`generate()` 未返回，证据改为 `steps.jsonl` + stage error。
- **docstring 仍算数据源命中**：只剔注释 token（DESIGN §5）。
- **F-2 的语法级判据**：`return None` 之类也算行为；空壳方法会被计为计算单元。
- **未部署 B 站**：仅本地单测与回归；`ModuleExtractionError` 与流水线退出码分类（B-8）的交互未验。
- **未新增 prompt 资源 / 未改预算**：与用户约束一致。
