# DeepScientist 基准对标分析（2026-11-26）

> **性质**：Layer-0 调研（T3，零代码/零门禁变更）。本文只做架构对标与机制对比，不构成实施承诺。
> **对象**：[DeepScientist](https://github.com/StormstoutLau/DeepScientist) 当前 checkout（未记录 commit）。
> **方法**：读码锚点 + 架构文档一手阅读。未运行该项目，未做行为实验。
> **边界**：① 未在本地运行，未验证 `__DS_PROGRESS__` 协议在真实长任务下的表现；② 引用行号来自当前 checkout（未记录 commit）；③ 它的设计目标（本地优先、面向单研究者）与 ARC（多阶段、强门禁、现场 soak）不完全一致，结论是「借鉴机制」而非「移植方案」。

---

## 0. 结论摘要

| 维度 | DeepScientist | ARC 现状 | 借鉴结论 |
|---|---|---|---|
| 调度 | Prompt-led + Skill-led，无阶段调度器 | 23 阶段硬编排 + 门禁 | **不要移植**：它的文档明确以此为目标，放弃阶段会丢掉可审计性 |
| 状态载体 | 1 quest = 1 Git 仓库，持久状态在文件与 Git 里 | file-as-state | **可参考** Git 级持久化思路 |
| 对外工具面 | 3 个 MCP：`memory` / `artifact` / `bash_exec` | 工具注册表 + 沙箱 | **可参考** 最小 MCP 面 |
| 长任务 | 受管 shell 会话（可停止、可续看、持久化） | 子进程 + 30 分钟墙钟 | **强烈借鉴** 受管会话模式 |
| 进度报告 | **语义化进度标记**（`__DS_PROGRESS__`）+ `progress.json` | 时间心跳 + 日志 | **强烈借鉴** 语义化进度 |
| 续跑语义 | 显式续跑锚点 + 被放弃运行摘要 | `checkpoint.json` + 事件链 | **强烈借鉴** 续跑锚点 + 放弃摘要 |
| 产物契约 | 有类型、有校验、成功必须有证据 | file-as-state + 门禁 | **强烈借鉴** 证据强制 |
| 状态机 | `planned/ready/queued/running/success/failed/blocked/warning/passed/active/superseded` | `RUNNING/UNKNOWN/COMPLETED/FAILED/PAUSED` | **可借鉴** 更完整的状态机 |
| 持久化 | 1 quest = 1 Git 仓库，产物即提交 | file-as-state | **可参考** Git 级持久化思路 |

**结论**：三点高度可借鉴（语义化进度、续跑锚点+放弃摘要、证据强制），两点可部分借鉴（更完整状态机、Git 级持久化思路），一点不要照搬（Prompt-led 无硬阶段、超大单体 service、无阶段重试语义）。

---

## 1. 现状对标

### 1.1 B 站 Stage 10 现场痛点（B-31/B-32/B-33 的触发背景）

| 痛点 | ARC 现状 | DeepScientist 的对应机制 |
|---|---|---|
| **进度不可见** | 2 h 44 m 只有 22 行日志，08:43–09:45 62 分钟完全空白 | **语义化进度标记**：进程主动打印 `__DS_PROGRESS__ {json}`，monitor 解析并原子写入 `progress.json`，与日志级别/缓冲无关 |
| **重试从零重跑** | 09:45 失败后 `agent_runs/attempt_001` 被重建，`code_agent_log.json` 仍是旧版，80 分钟白跑 | **显式续跑锚点 + 放弃运行摘要**：`runtime_state.json` 有 `continuation_anchor`/`last_recovery_abandoned_run_id`/`last_recovery_summary`，重试时显式记录「放弃了什么、为什么」 |
| **成功判据过弱** | 运行 A 25 min / 2 文件 / 4.5 KB 蓝图也算 `exit_code=0` | **证据强制**：`success` 状态必须携带 `input_paths/log_paths/output_paths/evidence_paths` 或相关节点 |
| **阶段内无断点** | `checkpoint.json` 只在 DONE 后写，`read_checkpoint` 返回下一阶段 | **显式续跑锚点 + 文件级 Git**：`continuation_anchor` + 产物即提交 |
| **状态机过简** | 只有 `RUNNING/UNKNOWN/COMPLETED/FAILED/PAUSED` | **完整状态机**：`planned/ready/queued/running/success/failed/blocked/warning/passed/active/superseded` |

---

## 2. 六个可借鉴的核心机制

### M1 语义化进度标记（治「进度不可见」）

**实现**（`bash_exec/service.py` L26、`bash_exec/monitor.py` L400-409）：

```python
# 被监控进程打印
print("__DS_PROGRESS__ {\"step_id\": \"gen:config.py\", \"done\": 7, \"total\": 12}")

# monitor 解析
BASH_PROGRESS_PREFIX = "__DS_PROGRESS__"
progress = _parse_progress_marker(line)
if progress is not None:
    progress.setdefault("ts", timestamp)
    _atomic_write_json(progress_path, progress)
    update_meta(last_progress=progress, latest_seq=seq, ...)
```

**关键点**：与日志级别/缓冲/阻塞无关；进程主动声明进度；只存摘要。

---

### M2 显式续跑锚点 + 被放弃运行摘要（治「重试从零重跑」）

**实现**（`quest/service.py` L3349-3360）：

```python
"continuation_policy": ...,        # auto / wait_for_user_or_resume
"continuation_anchor": ...,        # 下一步从哪开始（如 "decision"）
"continuation_reason": ...,
"last_resume_source": ..., "last_resume_at": ...,
"last_recovery_abandoned_run_id": ...,   # 被放弃的那次运行
"last_recovery_summary": ...,            # 放弃了什么、为什么
"last_stage_fingerprint": ..., "same_fingerprint_auto_turn_count": 0,
```

写入走 `.ds/runtime_state.lock` 文件锁（L2934-2939），状态目录在 [layout.py](file:///D:/Github/DeepScientist-main/src/deepscientist/quest/layout.py#L17-L52) 里显式登记。

---

### M3 证据强制的产物契约（治「成功判据过弱」）

**实现**（`artifact/schemas.py`）：

```python
# L134-138
if kind == "science.computational_run" and status == "success" and not _has_any_path(
    payload, ("input_paths", "log_paths", "output_paths", "evidence_paths")):
    errors.append("Successful computational_run requires at least one input, log, output, or evidence path.")

# L127-131
if kind == "science.claim":
    claim_type = payload.get("claim_type")
    if claim_type == "computed" and not _has_any_path(payload, ("evidence_paths", "validation_paths", "output_paths", "log_paths")):
        errors.append("Computed science claim requires evidence_paths, validation_paths, output/log paths, or related_node_ids.")
```

---

### M4 更完整的状态机（可借鉴）

```python
SCIENCE_STATUSES = {
    "planned", "ready", "queued", "running", "success", "failed",
    "blocked", "warning", "passed", "active", "superseded"
}
```

比我们的 `RUNNING/UNKNOWN/COMPLETED/FAILED/PAUSED` 更细，可直接合入 B-31 的 `STALLED`。

---

### M5 Git 级持久化（可参考）

**它怎么做**：1 quest = 1 Git 仓库，产物即提交，`handoffs/` 存跨会话交接。

**对我们**：我们的 `steps.jsonl` 是摘要账本；Git 方案的好处是 diff/回滚/内容寻址免费。但它和我们的 file-as-state + 单写者租约冲突较大。

**建议**：不替换 `steps.jsonl`，但借用 `handoffs/` 思路——Stage 10 每次终止写 `stage-10/handoff.md`（当前到哪、产物清单、下一步建议），用于人工接管与续跑判断。

---

### M6 派生视图 + 指纹级停滞计数

**它怎么做**：`stage_views.py` 的 `QuestStageViewBuilder`（L125）从 artifacts/events **派生**阶段视图；`same_fingerprint_auto_turn_count` + `last_stage_fingerprint` 是「同一指纹连续多少轮」的停滞计数（与我们 `stage_events` 循环守卫同构，但粒度更细）。

**建议**：B-31 的「合成视图」直接照这个模式——`ops` 显示的一切都是派生，真值永远是产物 + 事件；并把我们的循环守卫从「阶段级」下沉到「步骤级指纹」。

---

## 3. 不建议照搬的三点

1. **Prompt-led + 无硬阶段**：它的文档明确以此为目标（[90_ARCHITECTURE.md L16](https://github.com/StormstoutLau/DeepScientist/blob/main/docs/en/90_ARCHITECTURE.md#L16)）。我们的强项恰恰是 23 阶段 + 门禁 + 证据链；放弃阶段调度会丢掉可审计性。
2. **超大单体 service**：`artifact/service.py` 786 KB、`quest/service.py` 378 KB。我们的 spec workflow 要求每批可审、可门禁，不能接受这种规模。
3. **没有阶段级重试语义**：它靠「运行循环 + 续跑锚点」，没有我们 `_call_with_retries` 那种「三次重试」概念。我们的重试策略应保留，只借它的「放弃摘要」记录。

---

## 4. 建议的最小动作集（按性价比排序）

| 优先级 | 动作 | 落到 | 工作量 |
|---|---|---|---|
| 1 | 引入 `__ARC_PROGRESS__ {json}` 行协议 + `stage-10/progress.json` | B-31 M1 | 小（解析器 + 各 phase 一行 print） |
| 2 | 阶段重试时写「放弃摘要」（`abandoned_attempt`），断点账本加 `continuation_anchor` | B-33 M1 | 小（1 个函数 + 2 字段） |
| 3 | 把「成功必须有证据」变成 Stage 10 的硬判据；`RunStatus` 补 `blocked/warning/superseded` | B-32 M2 | 中（约 3 处判定） |
| 4 | Stage 10 写 `session.log.jsonl`（seq+ts）供 `ops` tail | B-31 M2 | 小到中 |
| 4 | Stage 10 写 `session.log.jsonl`（seq+ts）供 `ops` tail | B-31 M2 | 小到中 |
| 5 | 终止时写 `stage-10/handoff.md` | B-33 / A1-9 | 小 |

---

## 5. 诚实声明

- **未运行 DeepScientist**：所有结论基于读码 + 文档，未在本地运行，未验证 `__DS_PROGRESS__` 协议在真实长任务下的表现。
- **行号基于当前 checkout**：未记录 commit，后续 checkout 可能行号漂移。
- **目标不一致**：它的设计目标（本地优先、面向单研究者）与 ARC（多阶段、强门禁、现场 soak）不完全一致，结论是「借鉴机制」而非「移植方案」。
- **超大单体风险**：`artifact/service.py` 786 KB、`quest/service.py` 378 KB，我们的 spec workflow 要求每批可审、可门禁，不能接受这种规模。

---

## 6. 待决裁决

| 项 | 我的建议 | 需你裁决 |
|---|---|---|
| 1. B-31 M1 是否包含 `__ARC_PROGRESS__` 行协议 | **是** | 确认 |
| 2. B-33 M1 是否加 `continuation_anchor` + `abandoned_attempt` | **是** | 确认 |
| 3. B-32 M2 是否把「成功必须有证据」列为硬判据 | **是** | 确认 |
| 4. B-31 M2 是否加 `session.log.jsonl` | **建议是** | 裁决 |
| 5. B-31/B-32/B-33 是否分三批还是合并 | **建议分批**（B-31 只读观测 / B-32 写产物门 / B-33 写状态） | 裁决 |

---

## 附录：关键文件与行号速查

| 文件 | 关键行 | 说明 |
|---|---|---|
| `bash_exec/service.py` | L24, L26, L400-409 | `__DS_PROGRESS__` 前缀 + 解析 + 原子写入 |
| `bash_exec/monitor.py` | L50-60 | `_parse_progress_marker` |
| `bash_exec/runtime.py` | L50-60 | 同处 |
| `quest/service.py` | L3349-3360 | 续跑锚点字段 |
| `quest/service.py` | L3358-3360 | `same_fingerprint_auto_turn_count` |
| `artifact/schemas.py` | L127-138 | 证据强制判据 |
| `layout.py` | L17-52 | 状态目录列表 |
| `bash_exec/service.py` | L1531-1552 | `issue_terminal_attach_token` |
| `stage_views.py` | L1257-1347 | `QuestStageViewBuilder` + `progress_eval` |
| `quest/layout.py` | L17-52 | 状态目录列表 |

---

*分析完成时间：2026-11-26。模型：GLM-5.3-Flash（异构复审视角）。*