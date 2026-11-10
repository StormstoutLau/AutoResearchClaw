---
id: arc-a1-9-session-resume-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-a1-9-session-resume-DESIGN]
upstream: arc-a1-9-session-resume-DESIGN
---

# 实施记录：Stage 10/13 会话续接

## 1. 改动

| 文件 | 变更 |
|---|---|
| `researchclaw/runtime/attempt.py` | 白名单登记 `claude_code`；新增 `session_scope()`、`stage_session_id()`、`read_session_telemetry()`；`stage_session_id` 改按 run 目录派生 |
| `researchclaw/experiment/code_agent.py` | `CodeAgentResult.session_info`；`_CliAgentBase` 增 `session_id`/`resume_session`/`last_session`；`ClaudeCodeAgent._invoke()` 负责续接与 not-found 降级；`create_code_agent(..., session_ctx=(run_dir, stage))` |
| `researchclaw/pipeline/stage_impls/_code_generation.py` | `_try_cli_code_agent` 增 `run_dir` 与会话上下文；`cli_agent_log.json` 增 `generated`/`session` |
| `researchclaw/pipeline/stage_impls/_execution.py` | Stage 13 传会话上下文；`_try_agent_refine`/`_try_agent_repair` 返回完整 `CodeAgentResult`；`refinement_log.cli_agent.session` 回填 |
| `researchclaw/pipeline/runner.py` | `_record_attempt` 从 stage 日志读 `(session_id, resumed)`，写 `session_id` 与 `context_replayed` |
| `tests/test_g1b_runtime.py` | 新增 6 个用例（id/遥测/命令/工厂/降级/attempt 真值） |
| `tests/test_g1_closeout.py` | 白名单断言改为「claude_code 支持、未登记 backend 不支持」 |
| `tests/test_cli_agent_wiring.py` | 适配 `run_dir` 参数与 helper 返回类型 |

## 2. 关键实测

| # | 探针 | 结果 |
|---|---|---|
| E1 | `claude --resume <不存在的 uuid> -p "say ok"` | exit 1，stderr=`No conversation found with session ID: …`，未触发模型调用 |
| E2 | 三端 `--session-id` → `--resume`（P-035 已做） | 同文件行数 12→21，语义回忆正确 |

E1 直接决定 D-3：该 CLI 不会「静默从零开始」，因此 not-found 可以被显式识别并降级。

## 3. 验证

| # | 检查 | 结果 |
|---|---|---|
| V1 | `pytest tests/test_g1b_runtime.py tests/test_g1_closeout.py` | **22 passed** |
| V2 | `pytest`（code_agent / wiring / stage_retries / repair / events） | **91 passed** |
| V3 | 全量 `pytest tests --ignore=test_mcp*.py` | **3106 passed, 100 skipped, 7 failed**（均为环境性：Keras 3 ×4、Windows bash 路径、shell hook、server 默认值；与本批文件无关） |
| V4 | 旧用例 `test_session_resume_is_explicitly_unsupported` | 按新能力改写为白名单断言，非删除 |
| V5 | `session_id` 可被 `--session-id` 接受 | 用例内 `uuid.UUID(sid)` 校验 |

## 4. 鸿沟（诚实声明）

- **U-1 部分关闭**：会话不存在可机械识别；但 `--output-format text` 无 session 字段，「因其他原因静默新建」仍无法机械识别。建议后续改 JSON 输出再彻底关闭。
- **U-2 未解**：PIVOT/REFINE 重跑同一 stage 会续接旧会话；本批不区分「重试」与「重跑」。
- **C 站 seaviv 未测**（用户要求不动）；跨机续接按 P-035 U-2 明确不支持。
- Stage 12 的 collider/biology/stat sandbox 路径不在本批范围。
