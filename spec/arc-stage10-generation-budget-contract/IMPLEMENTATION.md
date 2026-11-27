---
id: arc-stage10-generation-budget-contract-IMPLEMENTATION
type: design
version: 1.1
status: verified
date: 2026-11-27
depends: [arc-stage10-generation-budget-contract-DESIGN]
upstream: arc-stage10-generation-budget-contract-DESIGN
---

> v1.1（2026-11-27，P-211）：补 §6「配置解析缺陷与修复」与运行 H 读数；§1 的测试数由 25 更新为 27。

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
