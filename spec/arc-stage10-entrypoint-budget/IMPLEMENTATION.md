---
id: arc-stage10-entrypoint-budget-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-26
depends: [arc-stage10-entrypoint-budget-DESIGN]
upstream: arc-stage10-entrypoint-budget-DESIGN
---

# 实施记录：B-30 入口生成预算、约束与兜底

## 1. 改动

| 文件 | 改动 |
|---|---|
| `researchclaw/pipeline/entrypoint_contract.py` | 新增 `ENTRYPOINT_RETRY_MAX_TOKENS=65536`、`MAX_ENTRYPOINT_LINES=150`；提示增加“≤150 行 / 只调用不重写”，`exp_plan` 摘要 3000→1200；新增 `_ENTRY_CALLABLES` 与 `synthesize_entrypoint` |
| `researchclaw/pipeline/stage_impls/_code_generation.py` | `_generate_entrypoint` 第二次尝试升到 65536；`_ensure_entrypoint` 在生成失败后调用 `synthesize_entrypoint`；repair 循环新增 `invalid_returns`，连续 2 次不可用即停止并写 validation_log |
| `researchclaw/pipeline/code_agent.py` | `_generate_entrypoint_file` 同步预算升级 |
| `tests/test_entrypoint_contract.py` | 新增 9 例：兜底驱动、候选优先级、无候选返回 None、跳过 main/语法错误、预算升级 32768→65536、提示含 ≤150 行与“Do NOT re-implement” |

## 2. 行为对照

| 场景 | B-29 | B-30 |
|---|---|---|
| 首次生成截断 | 同额度重试 32768 | 升级 65536 |
| 模型写 500+ 行 | 仍会截断 | 提示限制 ≤150 行，且第二次预算更高 |
| 两次都失败 | 阶段末尾失败 | 生成薄驱动调用现有 `run/train` |
| 无入口函数可调 | — | 显式记录并保持失败（不造假） |
| repair 连续返回垃圾 | 耗满 5 次 | 2 次即止损 |

## 3. 验证

```bash
python -m pytest tests/test_entrypoint_contract.py tests/test_codegen_truncation.py -q
# 35 passed

python -m pytest tests/test_code_agent.py tests/test_universal_codegen_integration.py \
  tests/test_codegen_truncation.py tests/test_entrypoint_contract.py -q
# 80 passed

python -m pytest tests/test_stage12_returncode.py -q
# 3 passed
```

## 4. 边界

- 本地全绿；**B 站 Stage 10-12 复跑待验收**。
- 兜底只保证“可执行 + 有指标行”，不保证指标语义正确；若入口函数崩溃，Stage 12 会如实失败。
- repair 止损只针对“不可解析响应”，重复语义错误仍按原 5 次上限。
