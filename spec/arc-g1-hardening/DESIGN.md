---
id: arc-g1-hardening-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-08
depends: [arc-g1-hardening-RESEARCH]
upstream: arc-g1-hardening-RESEARCH
---

# 设计：H-1..H-8 的最小改动面

## 1. 不变量

1. **测试先行**：8 个测试文件与实现同批提交，负向用例必须能变红。
2. **单一 writer**：`run-1.json` 只经 `_build_run_payload` 生成。
3. **只改必要路径**：H-7 只替换 `_write_project`，不扩散到全仓（A4-8 归 G4）。
4. **失败关闭**：CORS 通配符、非回环无 token 均直接 `ValueError`。

## 2. 改动面

| 文件 | 改动 |
|---|---|
| `researchclaw/utils/env.py`（新） | `build_subprocess_env` allowlist |
| `researchclaw/utils/paths.py`（新） | `safe_join` |
| `pipeline/stage_impls/_execution.py` | `_build_run_payload`；主路径/agent 路径共用；`_write_project` 用 `safe_join` |
| `pipeline/executor.py` | `_call_with_retries` 消费 `contract.max_retries` |
| `pipeline/_helpers.py` | 聚合过滤 `status=failed` / `returncode≠0`；`excluded_runs` |
| `pipeline/stage_impls/_literature.py` | `_write_retrieval_status` + Stage 4 调用 |
| `pipeline/stage_impls/_review_publish.py` | `_write_claim_verification` + Stage 20/23 调用 |
| `experiment/sandbox.py` | 2 处 env 改用 allowlist |
| `mcp/client.py` | env 改用 allowlist |
| `config.py` | `ServerConfig` 回环默认 + 显式 origins；`validate_server_security` |
| `server/app.py` | 启动校验；`allow_credentials` 跟随 token |

## 3. 测试面

8 个文件：`test_stage12_returncode` / `test_stage_retries` / `test_claim_verifier_wiring` / `test_retrieval_degraded` / `test_forged_execution_guards` / `test_env_allowlist` / `test_safe_join` / `test_cors_default`。

## 4. 回滚

单提交 `git revert`；无数据迁移；配置默认值变更需在发布说明中标注（`host` 与 `cors_origins`）。
