---
id: arc-a1-9-session-resume-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-a1-9-session-resume-RESEARCH]
upstream: arc-a1-9-session-resume-RESEARCH
---

# 设计：Stage 10/13 的会话续接与真值记录

## 1. 决策

| ID | 决策 |
|---|---|
| D-1 | 会话 id = `uuid5(namespace, "<run_dir.resolve()>:<stage>")`；同一 run 的同一 stage 跨 attempt 稳定 |
| D-2 | `attempt==1` 传 `--session-id <id>`；`attempt>1` 传 `--resume <id>` |
| D-3 | `--resume` 报 `No conversation found` 时**显式**新建会话，并记 `resumed=false`（禁止假装续接） |
| D-4 | attempt 的 `session_id`/`context_replayed` 取自 stage 自己写的 CLI 日志，不用策略推断；日志早于本次 attempt 开始时间则忽略 |
| D-5 | 只有 `SESSION_RESUME_BACKENDS`（当前 `{claude_code}`）拿到会话；`codex`/`llm` 保持无会话 |
| D-6 | Stage 13 的 `_try_agent_refine` / `_try_agent_repair` 返回完整 `CodeAgentResult`，调用方回填 `refinement_log.cli_agent.session` |

## 2. 数据流

```
create_code_agent(session_ctx=(run_dir, stage))
  ├─ SESSION_RESUME_BACKENDS 命中？
  │    ├─ 是 → session_id = stage_session_id(run_dir, stage)
  │    │        resume = next_attempt_number(run_dir, stage) > 1
  │    └─ 否 → 无会话
  └─ ClaudeCodeAgent._invoke()
       ├─ 正常 → last_session = {id, resumed, resume_requested}
       └─ --resume not found → 换 --session-id 重跑 → resumed=false

stage 日志（stage-10/cli_agent_log.json | stage-13/refinement_log.json）
  → runner._record_attempt() 读取 → attempts/stage-NN/attempt-k.json
       session_id=<真实 id>, context_replayed=not resumed
```

## 3. 验收映射

| 验收 | 落点 |
|---|---|
| A1-9 首跑固定 id、重试续接 | `test_claude_cmd_pins_then_resumes_session`、`test_factory_pins_first_attempt_and_resumes_the_second` |
| 会话不存在显式降级 | `test_missing_session_falls_back_to_a_fresh_one` |
| attempt 写真值 | `test_attempt_record_persists_the_real_provider_session` |
| 旧日志不冒充 | `test_session_telemetry_ignores_stale_stage_log` |
| UUID 合法且确定 | `test_stage_session_id_is_a_stable_uuid` |
| 白名单边界 | `test_session_resume_backend_whitelist` |

## 4. 回滚

删 `session_ctx` 参数与 `_invoke` 分支即可回到 P-036 行为；attempt 的 `session_id` 会自然回落到 `None`，无需迁移。

## 5. 与既有契约的关系

- **A1-9 与 A1-12 分工不变**：`session_id` 记「记得做过什么」（同机），`resume_note` 记「先查什么」（跨机）。
- **attempt 不迁移 Stage 状态**（P-029 D-4）不变；本批只补两个字段的来源。
