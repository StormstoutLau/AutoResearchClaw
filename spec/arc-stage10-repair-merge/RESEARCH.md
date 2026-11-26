---
id: arc-stage10-repair-merge-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-26
depends: [arc-stage10-codegen-truncation]
upstream: arc-master-roadmap
---

# 调研：Stage 10 repair/review-fix 截断与部分文件覆盖（B-28）

> **问题**：B 站 Stage 10-12 复跑（B-11）在 Stage 10 失败，耗时 13006.59s。最终 `experiment/main.py` 4705B、第 130 行停在 `"cor`；沙箱 `agent_sandbox/_project_4/main.py` 9472B、294 行，日志写 `Exec-fix iter 1: code runs OK`。

## 1. 现场证据（B 站，2026-11-25T18:19Z）

| 事实 | 读数 |
|---|---|
| Stage 10 状态 | failed；3 次 stage attempt；13006.59s |
| 失败原因 | `generated entrypoint is not runnable: main.py has a syntax error: unterminated string literal (detected at line 130)` |
| 最终产物 | `stage-10/experiment/main.py` 4705B |
| 沙箱修复版 | `stage-10/agent_sandbox/_project_4/main.py` 9472B / 294 行 |
| 修复日志 | 连续 5 次 `Repair updated 1 file(s): main.py`；`data.py` 的 7 个 CRITICAL 一直未消 |
| 生成日志 | `No main.py generated, promoting first file`；sequential 只产出 `config.py`、`data.py` |
| Stage 12 | 未执行；`run-1.json` 是 14:14:37Z 旧产物 |

## 2. 代码路径（T1）

| 位置 | 行为 | 问题 |
|---|---|---|
| `researchclaw/pipeline/code_agent.py` L554–L563 | 无 `main.py` 时把第一个文件提升为 `main.py` | config-only 入口，后续被出口门拒绝 |
| `researchclaw/pipeline/stage_impls/_code_generation.py` repair 块 | `repaired = _extract_multi_file_blocks(...)`；`files = repaired`；整批写盘 | 部分响应会丢掉未返回文件；截断响应直接覆盖 |
| 同文件 review-fix 块 | 同上，且要求 `"main.py" in fixed_files` | 只修 `data.py` 的响应会被丢弃；截断 `main.py` 会覆盖 |
| 同文件出口门 | `_entrypoint_issues(main_code)` | 能检出，但此时好文件已被覆盖 |

## 3. 与 P-178 的边界

P-178 已覆盖：blueprint、单文件、single-shot 的 `truncated` 重试与围栏容错。**未覆盖** repair/review-fix 两类二次 LLM 调用；它们同样会返回截断内容，且用"替换整个 files"的方式落盘。

## 4. 结论

B-28 = "repair/review-fix 截断与部分覆盖"：修法是**合并而非替换、截断重试 32768、AST 校验后再落盘**，并补负向测试。
