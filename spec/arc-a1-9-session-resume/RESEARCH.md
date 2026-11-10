---
id: arc-a1-9-session-resume-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-10
depends: [arc-g1-residual-analysis-RESEARCH, arc-g1b-supervisor-protocol-DESIGN]
upstream: arc-g1-residual-analysis-RESEARCH
---

# 调研：A1-9 attempt 级会话续接的接线条件

> **Feature**：P-037，把已实测的 CLI 会话能力接进 Stage 10/13 与 attempt 记录。
> **Spec 步骤**：Step 1-2（T1：改 `researchclaw/` 与 `tests/`）

## 1. 缺口（开工前代码事实）

| 项 | 现状（P-036 时） |
|---|---|
| 白名单 | `SESSION_RESUME_BACKENDS = frozenset()`，`session_resume_supported(None)` 恒 False |
| 命令构造 | `ClaudeCodeAgent._build_cmd` 无 `--session-id` / `--resume` |
| 调用点 | Stage 10 `_try_cli_code_agent`、Stage 13 `create_code_agent` 均不传会话上下文 |
| attempt 记录 | `session_id=None`、`context_replayed=True` 硬编码 |
| 测试 | `test_session_resume_is_explicitly_unsupported` 固化「无 backend 支持」 |

## 2. 能力证据（本轮新增）

| 事实 | 证据 | 等级 |
|---|---|---|
| `claude --session-id <uuid>` 首跑创建会话，`--resume <uuid>` 续接 | 本批在主控站 / A 站 NEX / B 站 GTR-Pro 三端实测（同文件行数增长、语义回忆正确） | T1 |
| 会话不存在时 `--resume` **hard fail**：exit 1 + `No conversation found with session ID: <id>` | 本批主控站实测（bogus uuid，未触发模型调用） | T1 |
| 会话库是机器本地状态（`~/.claude/projects/*.jsonl`） | P-035 §3 本地取证 | T1 |
| C 站 seaviv 未测 | 用户明确「不要动」 | — |

**推论**：P-035 §6.3 担心的「静默从零开始」在该 CLI 上不会发生；可以用退出码 + 错误标记做机械判定，并显式降级。

## 3. 方案对比

| 方案 | 评价 |
|---|---|
| **A `--session-id` 首跑 + `--resume` 重试 + 不存在时显式新建** | 语义清晰、可证伪；attempt 记录能区分续接/重放 |
| B 只写 `session_id` 不真的续接 | 记录造假，正是 U-2 要避免的 |
| C 换代到常驻 ACP 通道 | 与 Stage 10/13 的 CLI 子进程模型冲突，超出本批 |

**裁决 A**。

## 4. 边界

- 跨机续接**不支持**：换机后 session id 找不到 → 走显式降级 + `resume_note`（P-035 U-2）。
- PIVOT/REFINE 重跑同一 stage 时 `attempt>1`，会续接上一轮会话；语义上是「继续之前的讨论」。本批**不**额外区分「重试」与「重跑」，登记为观察项。
- Stage 12 的 collider/biology/stat agent 走 sandbox 路径，不经 `create_code_agent`，不在本批范围。

## 5. 未决

- **U-1 续接成功的 provider 侧证明**：当前以「`--resume` 未报 not found 且 rc=0」判定；`--output-format text` 无 session 字段，若 CLI 因其他原因静默新建则无法识别。触发 = 需要更强证据时；倾向 = 改 `--output-format json` 解析 session 字段。
- **U-2 PIVOT 重跑是否应改用新会话**：判据 = 出现「旧会话污染新实验」的实际案例；触发 = G2 回退链上线后。

## 6. 引用

1. 本地：`claude --help`（`--session-id`、`-r/--resume`、`--fork-session`）。
2. 本地实测：bogus uuid `--resume` → exit 1 + `No conversation found with session ID`。
3. 仓内：[P-035](../arc-g1-residual-analysis/RESEARCH.md) §3/§6、[P-028 DESIGN §4](../arc-g1b-supervisor-protocol/DESIGN.md)。
