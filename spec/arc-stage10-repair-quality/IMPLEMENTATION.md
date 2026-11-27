---
id: arc-stage10-repair-quality-IMPLEMENTATION
type: design
version: 1.4
status: verified
date: 2026-11-27
depends: [arc-stage10-repair-quality-DESIGN]
upstream: arc-stage10-repair-quality-DESIGN
---

> v1.1（2026-11-27，P-213 续）：部署首跑发现 **CodeAgent 的 `_repair_critical_issues` 是第三个 repair 站点**（P0 初版只覆盖 `_code_generation`），已补两处事件与 2 例测试。
> v1.2（2026-11-27，P-214）：部署后在 B 站重跑 Stage 10（运行 I），把 7 行现场 trace 与三问答案写入 §6；C-12 现场关闭。
> v1.3（2026-11-27，P-216）：运行 I 终态（attempt 3 失败）与两处状态矛盾的修复写入 §7（`decision.json` 不再在失败态写 `proceed`；`validation_report.md` 改为实际 repair 次数）。
> v1.4（2026-11-27，P-220）：运行 J 暴露 `Deep repair fixed -14/3` 负计数，补 §8（按集合计数并报告剩余）。

# 实施记录：B-36 P0（repair 取证）

## 1. 改动

| 文件 | 改动 |
|---|---|
| [`researchclaw/pipeline/repair_trace.py`](../../researchclaw/pipeline/repair_trace.py)（新增） | `digest` / `record` / `load`；`TRACE_NAME="repair_trace.jsonl"`；`errors` 结构化；锁 + `fsync`；全部异常吞掉 |
| [`researchclaw/pipeline/stage_impls/_code_generation.py`](../../researchclaw/pipeline/stage_impls/_code_generation.py) | 导入 `_record_repair_trace`；per-file repair 五处事件（`validation_failed` / `repair_request` / `repair_accepted` / `repair_rejected` / `repair_aborted`）；项目级 repair 一处（`project_repair`） |
| [`researchclaw/pipeline/code_agent.py`](../../researchclaw/pipeline/code_agent.py) | v1.1：`_repair_critical_issues` 增 `attempt/max_attempts` 参数，记录 `agent_validation_failed`（带 `issues` 摘要）与 `agent_repair`（accepted/rejected + reason）；调用方传入循环计数 |
| `tests/test_repair_trace.py`（新增） | 10 例：摘要不落正文、错误结构化与截断、追加顺序、abort 计数、路径为文件不抛、坏行跳过、缺文件为空、必填字段齐全、**agent 校验/修复两事件**（v1.1） |

### 1.1 关键实现

```python
# repair_trace.py —— 只写摘要
payload = {
    "ts": ..., "stage": stage_dir.name, "phase": phase, "file": file,
    "attempt": attempt, "max_attempts": max_attempts, "reason": reason,
    "error_summary": error_summary, "errors": _summarize_errors(errors),
    "prompt_sha256": digest(prompt), "prompt_chars": len(prompt or ""),
    "response_sha256": digest(response), "response_chars": len(response or ""),
    "accepted": list(accepted), "rejected": list(rejected),
    "model": model, "truncated": truncated,
}
```

```python
# _code_generation.py —— 拒绝分支必留原因
elif _repaired.strip():
    invalid_returns += 1
    _record_repair_trace(stage_dir, phase="repair_rejected", file=fname,
                         reason="invalid_python", rejected=[fname])
else:
    invalid_returns += 1
    _record_repair_trace(stage_dir, phase="repair_rejected", file=fname,
                         reason="empty", rejected=[fname])
```

## 2. 行为对照

| 场景 | 之前 | 现在 |
|---|---|---|
| 校验失败 | 仅 `logger.info` + `validation_log` | 额外一行 `validation_failed`（含结构化 errors） |
| repair 请求 | 无记录 | `repair_request`（prompt/响应摘要、model、truncated） |
| 响应被拒 | 仅 WARNING 文案 | `repair_rejected` + `reason`（`invalid_python` / `empty`） |
| 2 次不可用中止 | 仅 ERROR 文案 | `repair_aborted` + `invalid_returns` |
| 项目级 repair | 仅 merged 日志 | `project_repair`（accepted/rejected 文件名集合） |
| repair 的提示/预算/阈值 | — | **完全未变** |

## 3. 验证

```bash
python -m pytest tests/test_repair_trace.py -q
# 10 passed

python -m pytest tests/test_repair_trace.py tests/test_codegen_truncation.py \
  tests/test_entrypoint_contract.py tests/test_codegen_evidence.py \
  tests/test_generation_budget_contract.py tests/test_module_extraction_fallback.py \
  tests/test_rc_stages.py -q
# 195 passed

python -m pytest tests/test_repair_trace.py tests/test_code_agent.py \
  tests/test_entrypoint_contract.py tests/test_module_extraction_fallback.py \
  tests/test_generation_budget_contract.py -q
# 110 passed
```

## 4. 边界

- **已部署 B 站**（P-214，运行 I）：工作树快照 42 751 487 B，两端 SHA-256 `a5340cfa…19c5` 一致；旧代码 `AutoResearchClaw-main.prev-p210`、旧 Stage 10 `stage-10.bak-p213` 保留。
- 不记录 token 用量与成本；不记录全文。
- trace 不参与跳过/复用逻辑（与 B-33 L2/L3 无耦合）。
- 项目级 repair 的 `rejected` 是「未出现在修复响应中的文件」，不等于「修复失败」。
- 若 `record` 因磁盘/权限失败则静默丢弃，不阻断阶段。

## 5. 下一步（B-36 P1 输入）

用新 trace 回答：`errors[]` 是否与 prompt 中的 `issues_text` 一致、被拒响应的长度/围栏形态分布、
`attempt` 与最终判词是否同源。这三项决定 P1 的错误闭环设计。

## 6. 现场取证（运行 I，P-214）

**部署**：见 §4；配置未变（沿用 p210 的 `thinking_policy: tiered`）。tmux `p213-stage10`，日志 `~/arc-runs/g7-baseline/p213-stage10.log`。

**时间线（CST）**：

| 时刻 | 事件 | 读数 |
|---|---|---|
| 00:31:09 | 运行 I 启动 | — |
| 00:41:08 | 蓝图完成（8 192→32 768） | 63 135 B / 4 files；`steps.jsonl` seq 1；`code_version=0.5.0+16dc7ee1` |
| 00:54:17 → 01:11:20 | CodeAgent 硬校验 5 次（19/9/10/10/10 个 CRITICAL）+ 4 次 repair | 每次 `Repair updated 2 file(s)`（data.py + main.py）仍未清零；01:11:20 `Max repair attempts reached` |
| 01:12:35 | Phase 2 完成 | 2 465.3 s / 13 次 LLM / 1 次沙箱 / score 1.00 |
| 01:15:58 | 专用入口生成成功 | 4 294 字符，首次即过 |
| 01:15:58 | `data.py` 校验失败 attempt 1/5 | `syntax / line 46 / col 20 / '(' was never closed` |
| 01:17:01 | 第 1 次 repair 被拒 | 响应 3 189 字符、`truncated=true` |
| 01:17:51 | 第 2 次 repair 接受 | 响应 1 620 字符、`truncated=false` |
| 01:17:51 | 12 处 UnboundLocalError 风险自动修复 | models 1 / methods 7 / main 4 |
| 01:25:03 | 项目级 repair 完成 | 8 192 截断→32 768；合并 4 文件、保留 `config.py`；`experiment_config.py` 因未知文件名被忽略；`fixed 0/1` |
| 01:25:12 → 01:29:50 | 对齐门连否 2 次后通过 | 第 2 次重生成后 `Code aligned` |
| 01:34:12 → 01:39:07 | 入口生成：第 1 次语法错误 → 第 2 次成功（4 519 字符） | — |
| 01:39:07 | **证据门失败**：`blueprint_symbols_missing` | `data.py` 缺 7 个声明符号；磁盘 `data.py` 仅 1 422 B；executor 进入 attempt 2 重试 |

**`repair_trace.jsonl`（7 行，摘要 only）**：

| # | phase | file | attempt | 关键字段 |
|---|---|---|---|---|
| 1 | `validation_failed` | data.py | 1/5 | `errors: syntax / 46 / 20 / "'(' was never closed"` |
| 2 | `repair_request` | data.py | 1/5 | prompt 51 111 chars；response 3 189；`truncated=true` |
| 3 | `repair_rejected` | data.py | 1/5 | `reason=invalid_python`（旧码；本地已改为优先 `truncated`） |
| 4 | `validation_failed` | data.py | 2/5 | 同 #1 |
| 5 | `repair_request` | data.py | 2/5 | prompt 同 sha `b5656f37…`；response 1 620；`truncated=false` |
| 6 | `repair_accepted` | data.py | 2/5 | `accepted=["data.py"]` |
| 7 | `project_repair` | — | — | prompt 52 812；response 51 142；accepted 4 / rejected `config.py`；`reason=merged` |

**三问的现场回答**：

1. **错误是否进 prompt**：是。`validation_failed.errors` 带 `syntax/line/col/message`，`issues_text` 由 `format_issues_for_llm(errors_only)` 组装进 `code_repair` 提示。但两次 repair 的 prompt sha **完全相同** ⇒ 首次被拒的原因没有回传；第二次成功只是同一请求的重新采样。
2. **响应为何被拒**：第 1 次 `truncated=true`（3 189 字符）。per-file repair 走 `_chat_with_prompt` 且不传 `max_tokens`/`extra_body` ⇒ 引擎默认 8 192 输出 + 默认思考档，思考挤占预算（与 B-34 同源）；项目级 repair 有 8 192→32 768 升级（日志 `retrying with 32768`），per-file 没有。
3. **计数口径**：per-file 的 `attempt x/5`/abort 用 `invalid_returns`（连续不可解析次数，本次 1 次后被接受，未 abort）；项目级 `fixed 0/1` 统计关键词过滤后的 **warning 文本**，不是文件数；trace 的 `accepted/rejected` 是**文件级**。三者不同源。且该 1 个 critical（`config.py` 文件名遮蔽 stdlib）**无法靠内容重写修复**——模型返回改名后的 `experiment_config.py`，被 `unknown file` 规则忽略。

**判定**：C-12 现场关闭（5/6 类事件；`repair_aborted` 未触发属正常路径）。运行 I 的代码不含 agent 站点与 `reason=truncated` 细化，二者由 C-13 单测覆盖，现场验证留到下一次部署。

**额外读数**：attempt 1 最终被 **B-34 M4 的符号契约门**拦下——`blueprint_symbols_missing` 一次列出 `data.py` 缺失的 7 个符号，失败耗时 68 min；对齐重生成把 `data.py` 写成 1 422 B 薄壳（语法合法）是直接原因，属 P1/P2 的新输入。attempt 2 由 executor 自动重试，共用同一 trace 文件。

## 7. 终态与本轮修复（P-216）

**运行 I 终态（attempt 3）**：03:16:24 蓝图 39 221 B / 4 files；Phase 2 模块体量 config 213 / data 413 / models 431 / methods 409 行（蓝图 `max_lines=None`，全部超过默认 300 行预算）；硬校验耗尽 → 入口第 2 次成功（4 616 字符）；`data.py` 校验失败 `syntax / line 55 / col 21`；per-file repair #1 响应 3 003 字符 `truncated=true` → 非法 Python，#2 响应 3 108 字符 `truncated=true` → 抽取为空 → `repair_aborted`（`invalid_returns=2`）→ **Stage 10 FAILED，12 541.6 s，exit_code=75**；`repair_trace.jsonl` 累计 15 行（prompt 同为 49 714 字符、sha 相同）。

**本轮修复（用户点名的两处状态矛盾）**：

| 缺陷 | 现场读数 | 修复 |
|---|---|---|
| `decision.json` 自相矛盾 | `{"status": "failed", "decision": "proceed", "next_stage": 10}` | `_write_stage_meta`：非 DONE 且 decision 为默认 `proceed` 时改写为 `result.status.value`（如 `failed`）；显式 decision（`abort` / `resume` / `degraded`）原样保留 |
| `validation_report.md` 计数错误 | 实际 2 次 repair + abort，报告却写 `after 5 repairs` | 新增 `_blocked_validation_report`：统计**实际执行**的 repair 次数（`repair_counts`），标题写 `after N repair attempt(s) (limit 5/file)` 并逐文件列出；同源的日志行 `Code validation FAILED for %s after %d ...` 与 `CRITICAL ... remain after %d` 一并改为实际值 |

**测试**：`tests/test_codegen_truncation.py::TestBlockedReportCounts` 3 例（实际次数字面量、跨文件求和、零次）；`tests/test_rc_executor.py` 2 例（失败态不再写 `proceed`、显式 `abort` 保留）。相关回归 357 passed（六文件）。

**仍存的同源问题（未在本批修）**：CodeAgent 的 `Max repair attempts reached` 与 `fixed x/y` 仍各有独立口径（属 P2「计数与止损统一」）；`validation_report.md` 的 PASSED/FAILED 分支仍用跨文件累计 `attempt`（语义正确，但与 BLOCKED 分支的措辞不统一）。

## 8. `Deep repair fixed -14/3` 负计数（P-220）

**现场**：运行 J attempt 2 的日志写 `Stage 10: Deep repair fixed -14/3 critical issues`，`code_complexity.json` 同样记录负数。修复后 critical 从 3 条变成 17 条（模型重写文件触发了新的检查项），而计数器用「修复前条数 − 修复后条数」求差。

**修法**：

| 改动 | 说明 |
|---|---|
| 抽出 `_DEEP_CRITICAL_KEYWORDS` 常量 | 原先同一份关键词表在「修复前/修复后」各写一遍，易漂移 |
| 新增 `_critical_deep(warnings)` / `_deep_repair_counts(before, after)` | 纯函数；`fixed = max(0, 修复前 − 剩余)`，`remaining` 单独返回 |
| 日志与 `code_complexity.json` | 改为 `fixed %d of %d (%d remain)`，不再出现负数 |

**测试**：`TestDeepRepairCounts` 3 例（正常收敛、增加时钳到 0 且余量正确、非 critical 警告不计）；`tests/test_codegen_truncation.py` 20 passed，`test_rc_stages.py` 84 passed。

**边界**：只改计数呈现；repair 行为、阈值与关键词集合未变（`copy-paste` 仍按小写匹配，与既有门一致）。
