---
id: arc-stage10-generation-budget-contract-IMPLEMENTATION
type: design
version: 1.3
status: verified
date: 2026-11-27
depends: [arc-stage10-generation-budget-contract-DESIGN]
upstream: arc-stage10-generation-budget-contract-DESIGN
---

> v1.1（2026-11-27，P-211）：补 §6「配置解析缺陷与修复」与运行 H 读数；§1 的测试数由 25 更新为 27。
> v1.2（2026-11-27，P-219）：M5——符号契约前移到模块边界，补 §8 与 4 例测试（31 passed）。
> v1.3（2026-11-27，P-221）：M6——生成侧统一采用蓝图指标名，补 §9 与 3 例测试（34 passed）。

# 实施记录：B-34 M4

## 1. 改动

| 文件 | 改动 |
|---|---|
| [`researchclaw/llm/client.py`](../../researchclaw/llm/client.py) | `chat()` 增 `extra_body`（文档 + 参数）；`_call_with_retry` / `_raw_call` 逐层透传；`body.update(extra_body)` 在发送前最后合并；`extra_body` 为空时**不传第 6 个实参**（D-2） |
| [`researchclaw/config.py`](../../researchclaw/config.py) | `CodeAgentConfig` 增 `thinking_policy`（默认 `off`）、`thinking_mechanical_effort`（`low`）、`thinking_core_max_tokens`（0）、`file_max_lines`（300） |
| [`researchclaw/pipeline/code_agent.py`](../../researchclaw/pipeline/code_agent.py) | 新增 `_MECHANICAL_FILE_HINTS`；`_is_mechanical_module` / `_module_line_budget` / `_thinking_extra`；顺序生成拼接 BUDGET 提示并把 `extra_body` 透传到两次 `_chat`（首轮与 32768 升级）；`_chat` 增 `extra_body` |
| [`researchclaw/pipeline/codegen_evidence.py`](../../researchclaw/pipeline/codegen_evidence.py) | 新增 `_SYMBOL_KEYS` / `_declared_symbols` / `_defined_names` / `check_symbol_contract`；`evaluate_stage10_evidence` 在文件门后调用 |
| `tests/test_generation_budget_contract.py`（新增） | 27 例：分档 8、顺序接线 2、行预算 3、符号契约 7、配置解析 2、客户端透传 2、其余边界 3 |

### 1.1 关键实现

```python
# client.py —— 只在有内容时合并，且不改变空调用形态
if extra_body:
    body.update(extra_body)

if extra_body:
    resp = self._call_with_retry(m, messages, max_tok, temp, json_mode, extra_body)
else:
    resp = self._call_with_retry(m, messages, max_tok, temp, json_mode)
```

```python
# code_agent.py —— 分档与预算
policy = str(getattr(self._cfg, "thinking_policy", "off") or "off")
if policy != "tiered":
    return {}
if self._is_mechanical_module(file_name):
    return {"reasoning_effort": effort} if effort else {}
return {"reasoning": {"max_tokens": limit}} if limit > 0 else {}
```

```python
# codegen_evidence.py —— 符号契约
for file_name, symbol in declared:
    code = delivered.get(file_name)
    if code is None:            # 缺文件归文件门
        continue
    if symbol not in _defined_names(code):
        missing.append(f"{file_name}:{symbol}")
```

## 2. 行为对照

| 场景 | 之前 | 现在 |
|---|---|---|
| `thinking_policy=off`（默认） | 无相关字段 | 请求体**逐字节不变** |
| `tiered` + `config.py` | — | 发 `reasoning_effort=low`（可配） |
| `tiered` + `methods.py`，`core=0` | — | 不发字段（保留默认思考） |
| `tiered` + `methods.py`，`core=2048` | — | 发 `reasoning={"max_tokens":2048}` |
| 模块 prompt | 无规模约束 | 追加 `BUDGET: keep this file at or under N lines` |
| 蓝图声明 `classes: [X]` 但文件里没有 | 通过（只查文件存在） | `blueprint_symbols_missing: methods.py:X` |
| 蓝图声明符号但文件缺失 | `blueprint_files_missing` | 仍只报文件门（不重复） |

## 3. 验证

```bash
python -m pytest tests/test_generation_budget_contract.py -q
# 25 passed

python -m pytest tests/test_generation_budget_contract.py tests/test_codegen_evidence.py \
  tests/test_evidence_gate_hardening.py tests/test_module_extraction_fallback.py \
  tests/test_code_agent.py tests/test_blueprint_yaml_repair.py \
  tests/test_entrypoint_contract.py tests/test_codegen_truncation.py \
  tests/test_step_journal.py -q
# 182 passed

python -m pytest tests/test_rc_llm.py tests/test_reviewer_llm.py \
  tests/test_generation_budget_contract.py -q
# 78 passed
```

## 4. 红→绿记录（诚实）

本批**没有**严格 TDD 红态：实现先于测试。观测到的真实失败有两类，均保留在过程里：

1. **兼容性红**：首次把 `extra_body` 始终作为第 6 位置参数传入后，既有
   `test_rc_llm.py` 的 `fake_raw_call` / `fake_call_with_retry`（6 参数）报
   `takes 6 positional arguments but 7 were given`，2 例失败；`test_module_extraction_fallback.py`
   的 `fake_chat` 报 `unexpected keyword argument 'extra_body'`，2 例失败。
   → 改为「有内容才传」后全部转绿（这正是 D-2 的来源）。
2. **测试自身缺陷**：`test_tier_reaches_the_llm_and_prompt_has_budget` 首跑
   `ValueError: too many values to unpack`——蓝图无 `main.py` 触发专用入口生成，
   实际 3 次调用；改为取 `calls[0]/calls[1]` 后通过。

未观察到实现逻辑（分档/契约）本身的失败，故不作为红→绿证据宣称；CHECKLIST 中标注 C-24。

## 5. 边界

- 未在 B 站部署/重跑（M4 的现场收益待验证）。
- 未做 C++（函数级分块）与 A'（65536 兜底）。
- 符号契约只证明名字存在，不证明实现正确。
- `max_lines` 只提示，不阻断。
- `tiered` 的字段下发依赖 endpoint 支持（halogen 已实测；严格 provider 会 400）。

## 6. 部署首验发现的配置缺陷与修复（P-211）

**缺陷**：yaml 写入 `experiment.code_agent.thinking_policy: tiered` 后，线上复读仍为 `off`。
根因：[`_parse_code_agent_config`](../../researchclaw/config.py#L1603-L1623) 逐字段构造 `CodeAgentConfig`，
新增的四个键没有对应赋值，被**静默丢弃**（`validate` 仍通过，因为未知键不报错）。

**修复**：补四个字段 + 两个单测：

```python
thinking_policy=str(data.get("thinking_policy") or "off"),
thinking_mechanical_effort=str(data.get("thinking_mechanical_effort", "low") or ""),
thinking_core_max_tokens=_safe_int(data.get("thinking_core_max_tokens"), 0),
file_max_lines=_safe_int(data.get("file_max_lines"), 300),
```

**红→绿（真实）**：新增的 `test_new_keys_are_parsed` 在修复前会得到 `policy == "off"`；
修复后 27 passed，线上复读 `policy=tiered effort=low core=2048 lines=300`。
这是本批**唯一可重放的行为型红→绿**，CHECKLIST C-29 记录。

## 7. 运行 H 的现场读数（C-28）

| 模块 | 档位 | 首轮 completion | 结果 |
|---|---|---|---|
| `config.py` | `reasoning_effort=low` | 2 542（39 s） | 217 行，无截断 |
| `data.py` | `reasoning.max_tokens=2048` | 6 249（92 s） | 320 行，**运行 F 在此失败** |
| `models.py` | 同上 | 6 018 | 295 行 / 4 类 |
| `monitors.py` | 同上 | 8 192 → 10 387 | 唯一升级，第二次成功 |
| `main.py` | 同上 | 5 489 | 无截断 |

首轮截断由 4/4 降到 **1/5**；Phase 2 共 2 211 s / 13 次调用。Stage 10 仍在 attempt 1
失败，但失败点已移到「`data.py` 校验 1 个错误 + repair 连续返回非法 Python」，
不再是生成/提取层（CHECKLIST C-30）。

## 8. M5：符号契约前移到模块边界（P-219）

**动机（现场）**：运行 I attempt 1 与运行 J attempt 1 都以出口证据门
`blueprint_symbols_missing` 结束，分别在 **68 min** 与 **61 min** 之后才报出
`data.py` 7 个、`data.py` 7 + `main.py` 6 个缺失符号；期间已完成 5 模块生成、
5 轮硬校验、入口生成、项目级 repair 与对齐门。

**改动**：

| 文件 | 改动 |
|---|---|
| [`codegen_evidence.py`](../../researchclaw/pipeline/codegen_evidence.py) | 新增 `declared_symbols(blueprint, file_name)` 与 `missing_symbols(blueprint, file_name, code)`（与出口门共用 `_declared_symbols` / `_defined_names`） |
| [`code_agent.py`](../../researchclaw/pipeline/code_agent.py) | 每个模块抽取成功后立即比对声明符号；缺失则用 `SYMBOL CONTRACT` 提示做**一次**定向修复（预算随原模块，截断则升级 32 768）；仍缺失则记 `generate_file(failed, reason=symbols_missing)` 并抛 `ModuleExtractionError` |

**行为对照**：

| 场景 | 之前 | 现在 |
|---|---|---|
| 模块缺声明符号 | 继续生成，61–68 min 后出口门失败 | 该模块生成后立即发现（分钟级） |
| 缺符号但可补 | 无机会 | 一次定向修复，提示列出需补的名字 |
| 修复后仍缺 | 阶段末失败 | 该模块边界失败，账本留 `failed` 行 |

**测试**：`TestModuleSymbolContract` 4 例（`missing_symbols` 判定、契约满足不额外调用、缺失后一次修复成功、修复无效在模块边界抛错并记账）；`tests/test_generation_budget_contract.py` **31 passed**，相关五文件 81 passed。

**边界**：只在 `_phase2_sequential_generate`（顺序生成）启用；单发回退路径仍由出口门判定（`generate_project` 无逐模块边界）；符号仍按 `ast.walk` 的类/函数名匹配，模块级常量不算「已定义」。

## 9. M6：生成侧统一采用蓝图指标名（P-221）

**动机（现场）**：运行 J attempt 2 的出口门报 `metric_mismatch: blueprint metric 'early_detection_roc_auc' != METRIC_DEF 'primary_metric'`。入口生成用的是 `config.experiment.metric_key`（默认 `primary_metric`），而出口门校验的是蓝图 `metric`。

**改动**：

| 文件 | 改动 |
|---|---|
| [`codegen_evidence.py`](../../researchclaw/pipeline/codegen_evidence.py) | 新增公开 `blueprint_metric(blueprint)` 与 `resolve_metric(stage_dir, fallback)`（读 `architecture_spec.yaml`，失败回落） |
| [`code_agent.py`](../../researchclaw/pipeline/code_agent.py) | 蓝图解析成功后把 `metric` 切换为蓝图声明值，后续模块 prompt 与专用入口生成同源 |
| [`_code_generation.py`](../../researchclaw/pipeline/stage_impls/_code_generation.py) | 两处 `_ensure_entrypoint` 调用前先 `resolve_metric(stage_dir, metric)` |

**行为对照**：

| 场景 | 之前 | 现在 |
|---|---|---|
| 蓝图声明 `early_detection_roc_auc` | 入口按 `primary_metric` 生成 → 出口 `metric_mismatch` | 入口按蓝图名生成，出口一致 |
| 蓝图无 `metric` | 用配置值 | 仍用配置值（行为不变） |
| 蓝图不可解析 | 用配置值 | 用配置值（`resolve_metric` 捕获异常） |

**测试**：`TestBlueprintMetricPropagation` 3 例（`resolve_metric` 优先蓝图 / 无蓝图回落 / 专用入口 prompt 使用蓝图指标名）；`tests/test_generation_budget_contract.py` **34 passed**，相关四文件 142 passed。

**边界**：只影响生成与入口提示；不改出口门判据；`metric_key` 仍是 Stage 12–14 的解析键（若蓝图指标与配置键不同，Stage 12 的取值需与之一致，属后续批次）。
