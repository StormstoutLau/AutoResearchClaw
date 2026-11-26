---
id: arc-stage10-entrypoint-contract-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-26
depends: [arc-stage10-entrypoint-contract-DESIGN]
upstream: arc-stage10-entrypoint-contract-DESIGN
---

# 实施记录：B-29 入口契约与专用 main.py 生成

## 1. 改动

| 文件 | 改动 |
|---|---|
| `researchclaw/pipeline/entrypoint_contract.py`（新增） | `entrypoint_issues`、`summarize_modules`、`build_entrypoint_prompt`、`ENTRYPOINT_MAX_TOKENS=32768` |
| `researchclaw/pipeline/code_agent.py` | 删除"promoting first file"；新增 `_generate_entrypoint_file`（2 次、截断重试、契约校验） |
| `researchclaw/pipeline/stage_impls/_code_generation.py` | 改为复用共享 `_entrypoint_issues`；新增 `_is_parseable`、`_generate_entrypoint`、`_ensure_entrypoint`；repair 拒绝不合契约 `main.py`；校验前与出口门前各调用一次 `_ensure_entrypoint` |
| `tests/test_entrypoint_contract.py`（新增） | 15 个用例：契约判定、模块摘要、缺失/不合规再生成、已合规零调用、生成失败保持原样、repair 拒绝、CodeAgent 不提升+重试 |
| `tests/test_codegen_truncation.py` | 将 B-28 用例中的 `main.py` 改为合规样例（适配新契约） |

## 2. 行为变化

| 场景 | 之前 | 之后 |
|---|---|---|
| 无 `main.py` | 首个文件被重命名为 `main.py` | 保留原文件，专用生成 `main.py` |
| `main.py` 截断但可解析 | 通过 AST 过滤，4h 后出口门失败 | repair 阶段拒绝；校验前再生成 |
| 生成失败 | 只有出口门报错 | `_ensure_entrypoint` 两次失败后记录明确原因，出口门照旧拒绝 |
| 已合规 `main.py` | 无检查 | 零额外 LLM 调用 |

## 3. 验证

```bash
python -m pytest tests/test_entrypoint_contract.py tests/test_codegen_truncation.py -q
# 28 passed

python -m pytest tests/test_code_agent.py tests/test_universal_codegen_integration.py \
  tests/test_codegen_truncation.py tests/test_entrypoint_contract.py -q
# 73 passed

python -m pytest tests/test_rc_executor.py tests/test_stage12_returncode.py \
  tests/test_opencode_bridge.py -q
# 264 passed
```

## 4. 边界

- 本地全绿；**B 站 Stage 10-12 复跑尚在进行**，B-11 与 B-29 均待现场验收。
- `config.py` 遮蔽 stdlib 的告警仍未处理（`from config import Config` 本身可用，不阻塞）。
- 未改阶段重试与退出码分类（B-8）。
