---
id: arc-g1-hardening-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-08
depends: [arc-g1-hardening-DESIGN]
upstream: arc-g1-hardening-DESIGN
---

# 实施记录：H-1..H-8 落地

## 1. 落点

| # | 改动 | 落点 |
|---|---|---|
| E-1 | `_build_run_payload` 统一 writer，主路径补 `returncode`/`mode` | `pipeline/stage_impls/_execution.py` |
| E-2 | stage 级重试 | `pipeline/executor.py::_call_with_retries` |
| E-3 | ClaimVerifier 接线 | `_review_publish.py::_write_claim_verification` + Stage 20/23 |
| E-4 | 检索降级标记 | `_literature.py::_write_retrieval_status` + Stage 4 |
| E-5 | 聚合层过滤 | `pipeline/_helpers.py::_collect_experiment_results` |
| E-6 | 子进程 env allowlist | `utils/env.py` + `sandbox.py`（2 处）+ `mcp/client.py` |
| E-7 | `safe_join` | `utils/paths.py` + `_execution.py::_write_project` |
| E-8 | API 默认收紧 | `config.py`（默认 + `validate_server_security`）+ `server/app.py` |

## 2. 验证

```bash
# V1 八个 H 项测试（28 用例）
python -m pytest tests/test_stage12_returncode.py tests/test_stage_retries.py \
  tests/test_claim_verifier_wiring.py tests/test_retrieval_degraded.py \
  tests/test_forged_execution_guards.py tests/test_env_allowlist.py \
  tests/test_safe_join.py tests/test_cors_default.py -q

# V2 既有回归子集
python -m pytest tests/test_packaging.py tests/test_run_state.py tests/test_frontend_mount.py \
  tests/test_simulated_guard.py tests/test_cost_tracker.py tests/test_docs_and_adapters.py \
  tests/test_rc_config.py tests/test_cli.py tests/test_fabrication_guards.py \
  tests/test_rc_executor.py tests/test_hitl_verifier.py -q

# V3 覆盖率与契约
python scripts/roadmap_coverage_check.py --check
python scripts/dc_validator.py spec/arc-g1-hardening/RESEARCH.md spec/arc-g1-hardening/DESIGN.md \
  spec/arc-g1-hardening/IMPLEMENTATION.md spec/arc-g1-hardening/CHECKLIST.md docs/PROGRESS.md docs/CONSOLE.md
```

## 3. 结果

- V1：**28 passed**。
- V2：**346 passed / 5 skipped**（跳过项为既有 async 插件缺失与平台相关用例）。
- V3：覆盖率 `accept=106 missing=0`；dc-validator 0 违规。
- 已知环境限制：本机 `mcp` SDK 缺 `MCPServer`，`tests/test_mcp*.py` 无法收集（既有问题，与本次改动无关）；`mcp/client.py` 的 env 改动已由 `test_env_allowlist` 的 builder 覆盖。

## 4. 未执行

- Q18 的 vendor/语料清单文件（G2/G5）。
- Q20 的 run 级预算账本与 `LLMClient.chat` 前置检查（G6）。
- A4-8 的全仓写入点替换（G4）。
