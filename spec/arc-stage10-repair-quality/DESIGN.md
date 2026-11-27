---
id: arc-stage10-repair-quality-DESIGN
type: design
version: 1.2
status: verified
date: 2026-11-27
depends: [arc-stage10-repair-quality-RESEARCH]
upstream: arc-stage10-repair-quality-RESEARCH
---

# 设计：repair 取证（B-36 P0）

> v1.1（2026-11-27，P-214）：`repair_rejected.reason` 增 `truncated`（优先于 `invalid_python`）；`repair_request.extra` 增 `issues_text_sha256/chars`，使「错误文本是否进 prompt」可直接对照。
> v1.2（2026-11-27，P-216）：运行 I 终态暴露两处状态矛盾，补 D-8（报告写实际 repair 次数）与 D-9（失败态不写 `proceed`）。
> 本文件只覆盖 **P0 取证**；P1..P3（错误闭环、计数统一、fixture 回归）仍为 draft，见 RESEARCH §4。

## 1. 决策

| ID | 决策 | 被拒替代 | 理由 |
|---|---|---|---|
| D-1 | 新建独立模块 `pipeline/repair_trace.py`，不塞进 `step_journal.py` | 复用 `steps.jsonl` | `steps.jsonl` 语义是「步骤完成/失败」，repair 是步骤内事件；混写会破坏 I-1/I-3 的 skip 语义 |
| D-2 | 只存 **sha256 + 长度 + 诊断摘要**，不存 prompt/代码正文 | 存全文便于排查 | 与 `steps.jsonl` 同一纪律；正文可能含私有代码，且会让 stage 产物膨胀 |
| D-3 | 事件六种：`validation_failed` / `repair_request` / `repair_accepted` / `repair_rejected` / `repair_aborted` / `project_repair` | 只记 request/response | 六种能把「校验失败 → 请求 → 被拒 → 中止」串成一条链；`project_repair` 覆盖第二条修复路径 |
| D-4 | `errors[]` 保留 severity/category/line/col + message≤300 | 只存 `summary()` | 运行 H 的 `1 error(s)` 无法定位；结构化字段是 P1 闭环的输入 |
| D-5 | 全部 best-effort：`record()` 捕获所有异常并返回 `None` | 失败即抛 | 取证不得把「已经失败的阶段」再弄崩 |
| D-6 | append + `fsync` + 文件锁 | 无锁 append | 与 `steps.jsonl` 同款并发安全；单进程也避免撕裂行 |
| D-7 | 不改 repair 的提示、预算、止损阈值 | 顺手优化 | P0 只取证；行为变更需 P1/P2 的单独验收 |
| D-8 | 报告计数 = **实际执行**的 repair 次数（含逐文件明细），每文件上限只作附注 | 沿用 `max_repair` | 提前 abort（2 次不可用响应）时报告写「after 5 repairs」，与日志的 `invalid_returns` 自相矛盾；计数必须同源 |
| D-9 | `decision.json` 的 `decision` 在非 DONE 状态不得为默认 `proceed`：默认值改写为 `status.value`，显式 decision（`abort`/`resume`/`degraded`）原样保留 | 直接删 `decision` 字段 | `StageResult.decision` 默认 `proceed`，失败阶段因此写出 `{"status":"failed","decision":"proceed"}`；删字段会破坏 schema 与既有 `resume` 断言 |

## 2. 接口

```python
# researchclaw/pipeline/repair_trace.py
TRACE_NAME = "repair_trace.jsonl"

digest(text: str) -> str
record(
    stage_dir, *, phase, file="", attempt=0, max_attempts=0, reason="",
    error_summary="", errors=(), prompt="", response="",
    accepted=(), rejected=(), model="", truncated=None,
    extra=None, ts=None,
) -> dict | None
load(stage_dir) -> list[dict]
```

记录示例：

```json
{"ts":"2026-11-27T00:12:57+00:00","stage":"stage-10","phase":"validation_failed",
 "file":"data.py","attempt":1,"max_attempts":5,"reason":"",
 "error_summary":"1 error(s)","errors":[{"severity":"error","category":"syntax",
 "line":219,"col":8,"message":"…"}],
 "prompt_sha256":"sha256:…","prompt_chars":18422,
 "response_sha256":"sha256:…","response_chars":5210,
 "accepted":[],"rejected":[],"model":"halogen-qwen3.8-flash-next","truncated":false}
```

## 3. 调用点

| 位置 | 事件 | 说明 |
|---|---|---|
| [`_code_generation.py` L1311-1326](../../researchclaw/pipeline/stage_impls/_code_generation.py#L1311-L1326) | `validation_failed` | 每轮校验失败，带 `errors` |
| 同文件 per-file repair | `repair_request` | 带 prompt 摘要、响应摘要、model、truncated；`extra.issues_text_sha256/chars` |
| 同文件接受分支 | `repair_accepted` | `accepted=[file]` |
| 同文件拒绝分支 | `repair_rejected` | `reason` ∈ {`truncated`, `invalid_python`, `empty`}（`truncated` 优先） |
| 同文件 `invalid_returns>=2` | `repair_aborted` | `extra.invalid_returns` |
| 项目级 repair（`_request_repair_response` 之后） | `project_repair` | `accepted/rejected` 文件名集合 + `reason=merged|no_valid_file` |

## 4. 非目标与边界

- D-9 只改 `decision.json` 的**呈现**，不改 `StageResult.decision` 的运行时语义（runner 仍读内存对象）；rollback 决策只在 RESEARCH_DECISION 的 DONE 分支生效。
- CodeAgent 的 `Max repair attempts reached` / `fixed x/y` 仍是独立口径，统一留 B-36 P2。
- 不记录 LLM token 用量（`LLMResponse` 有 total_tokens，但 P0 聚焦「为什么被拒」）。
- 不推断「错误是否真的写进 prompt」——P0 只留 prompt 与 `issues_text` 的 digest，P1 用两者的 sha256 逐次对照。
- 不保证 trace 文件一定存在（record 失败静默）；但一旦写成功，行内字段齐全。
- 与 B-33 L2/L3 无耦合：trace 不参与 `should_skip`。
