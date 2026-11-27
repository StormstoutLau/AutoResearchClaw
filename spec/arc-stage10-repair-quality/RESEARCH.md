---
id: arc-stage10-repair-quality-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-27
depends: [arc-stage10-generation-budget-contract]
upstream: arc-master-roadmap
---

> v1.0（2026-11-27，P-213）：补 §6「P0 取证范围」并把状态由 draft 升为 verified；方案主体见 [DESIGN](DESIGN.md)。

# 调研（草案）：Stage 10 repair 层的可用性与错误闭环（B-36）

> **状态**：**仅立项登记**，DESIGN / IMPLEMENTATION / CHECKLIST 待实施时补齐。
> **触发**：运行 H（[postmortem §2.5](../../docs/arc-b-site-stage10-postmortem-20261126.md)）在五模块全部生成后，卡在 `data.py` 的**代码校验 + repair** 层。

## 1. 现场读数（运行 H，attempt 1）

```text
00:12:57 Code validation failed for data.py (attempt 1/5): Code validation: 1 error(s)
00:14:04 Repair attempt returned invalid Python for data.py, keeping original
00:14:04 Code validation failed for data.py (attempt 2/5): Code validation: 1 error(s)
00:15:03 Repair attempt returned invalid Python for data.py, keeping original
00:15:03 Repair aborted for data.py after 2 unusable response(s)
00:15:03 Code validation FAILED for data.py after 5 repair attempts: Code validation: 1 error(s)
00:15:03 CRITICAL validation issues remain after 5 repair attempts. Blocking stage.
```

三个可直接核对的事实：

1. **repair 请求只发了 2 次**就 `abort`，但日志同时写「after 5 repair attempts」——**计数口径自相矛盾**（循环变量 vs 中止阈值）。
2. **2 次 repair 全部返回非法 Python**，说明问题不在「改不对」，而在「返回的东西根本不可解析」。
3. 校验器只给出 `1 error(s)`，**没有把错误码/行号/片段写进 repair 提示的可见文本**（待 P0 取证确认）。

## 2. 代码面

| 位置 | 作用 | 可疑点 |
|---|---|---|
| [`_request_repair_response`](../../researchclaw/pipeline/stage_impls/_code_generation.py#L107-L122) | repair 调用与截断升级（8192→32768） | 只升级预算，不携带「上次返回为何被拒」 |
| [`_extract_valid_repair_files`](../../researchclaw/pipeline/stage_impls/_code_generation.py#L61-L97) | 从响应抽取合法文件 | 拒绝条件（围栏/语法）不回报给下一次请求 |
| [`_merge_repair_files`](../../researchclaw/pipeline/stage_impls/_code_generation.py#L98-L106) | 合并修复结果 | 无变更时是否重试未定义 |
| 校验循环（`_code_generation` repair 段） | attempt 计数与止损 | `attempt 1/5 → 2/5 → abort` 与「after 5」不一致 |
| `_hard_validate_and_repair`（CodeAgent） | 生成后硬校验 | 与 Stage 级 repair 的职责边界需确认 |

## 3. 假设（待 P0 取证）

| ID | 假设 | 判别方法 |
|---|---|---|
| H-1 | 校验器的错误描述未进入 repair prompt（或只有「1 error(s)」） | dump 实际 repair prompt 与 validator 输出对比 |
| H-2 | repair 响应格式不稳定（无围栏/多文件/带解释文字）被 `_extract_valid_repair_files` 拒绝 | dump 原始响应 + 抽取结果 |
| H-3 | repair 预算不足（复用 8192，未按错误规模升级） | 统计 repair completion 是否打满 |
| H-4 | repair prompt 未给足上下文（缺原文件全文/依赖签名） | 检查 prompt 组装的字符预算 |
| H-5 | 止损策略过激（2 次不可用即 abort，且不再换策略） | 对照日志与代码常量 |

## 4. 建议分级

| 级别 | 动作 | 验收（可测量） |
|---|---|---|
| P0 | 落 repair 取证：把每次 repair 的「错误码/行号/片段 + prompt 摘要 + 响应摘要 + 拒绝原因」写入 `steps.jsonl` 或 `repair_trace.jsonl` | 一次失败运行可完整重放 2 次 repair 的输入输出 |
| P1 | 错误闭环：validator 的结构化错误（code/line/snippet）必须进入下一次 repair 提示；被拒原因回传 | 同 fixture 下 repair 成功率提升；`invalid Python` 次数下降 |
| P2 | 计数与止损统一：`attempt x/N` 与最终判词同源；abort 前至少换一次策略（如整文件重写） | 日志自洽；有「换策略」记录 |
| P3 | 回归测试：构造 `data.py` 单错误 + 非法响应 fixture，断言「先重试换策略、再显式失败」 | 新增测试文件，红→绿 |

## 5. 非目标

- 不修改校验器的判据阈值（是否误杀另立项）。
- 不引入自动删除/自动降级模块。
- 不在本批处理蓝图/对齐分档（属 B-34 的后续小步）。

## 6. P0 取证范围（本批交付）

- **目标**：让下一次失败运行能完整回答「repair 收到了什么、返回了什么、为什么被拒」。
- **不改变行为**：repair 的提示、预算、止损阈值、校验规则全部不动。
- **落点**：`stage-10/repair_trace.jsonl`，append-only，摘要 only（与 `steps.jsonl` 同一纪律）。
- **事件**：`validation_failed` / `repair_request` / `repair_accepted` / `repair_rejected` / `repair_aborted` / `project_repair`。
- **字段**：`phase/file/attempt/max_attempts/reason/error_summary/errors[]`（severity/category/line/col/message≤300）+ `prompt_sha256/prompt_chars/response_sha256/response_chars` + `accepted/rejected/model/truncated`，另可带 `extra`（如 `invalid_returns`）。
- **可回答的 P0 问题**：H-1（错误描述是否进 prompt，可用 prompt 摘要与 errors 对照）、H-2（响应是否可解析、拒绝原因）、H-5（2 次即 abort 的计数）。
- **不回答**：H-3/H-4（预算与上下文是否足够）需在 P1 加长度分布统计。
