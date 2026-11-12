---
id: arc-g3-m2-stage-events-DESIGN
type: design
version: 1.1
status: verified
date: 2026-11-12
depends: [arc-g3-m2-stage-events-RESEARCH]
upstream: arc-g3-m2-stage-events-RESEARCH
---

# 设计：G3 M2 stage_events 循环护栏与 summary 事件链（P-078）

> 基于 [RESEARCH.md](RESEARCH.md)。冻结 M0 [DESIGN §4/§5/§10](../arc-g3-m0-design/DESIGN.md) 的两组接口，并修复 P-077 登记的 **D-2**（事件链尾锚可被覆盖）与 **O-4**（坏行语义不一致）。
> **修订 v1.1（2026-11-12，P-080）**：§3.1 由「单写者假设」升级为**跨进程互斥写**（`runtime/filelock.py`，修复 P-079 O-3）；§3.3 `window < 1` 显式拒绝（O-2）；§3.4 尾部**连续**坏行容忍，其前仍 fail-closed（O-1）。字段与判定语义不变。

## 1. 架构总览

```text
Stage 4 DONE ─┐
              ├─> runtime/stage_events.py ──> run_dir/stage_events.jsonl（一行一轮）
Stage 5 DONE ─┘         │
                        └─ evaluate_loop() → continue / warn / pause(E_LOOP_DETECTED)
runner 顶层执行结束
   └─ _write_pipeline_summary() ──> pipeline_summary.json + .sha256
   └─ append_summary_event()（仅 owns=True）──> events.jsonl:pipeline.summary
verify_summary(require_event=True)
   └─ 读 events.jsonl（含归档段）→ 段划分 → 锚点结构/身份/末锚三关
```

## 2. 模块与接口（本批新增/变更）

| 模块 | 接口 | 变更 |
|---|---|---|
| `researchclaw/runtime/stage_events.py` | `StageEvent`、`plan_signature()`、`collect_progress()`、`append_stage_event()`、`load_stage_events()`、`evaluate_loop()`、`record_stage_progress()` | 新增 |
| `researchclaw/evidence/summary_check.py` | `append_summary_event(run_dir, summary, event_log)`、`verify_summary(run_dir, *, require_event)` | 修改：锚点 payload 增 `generated`；`require_event` 三关（D-2） |
| `researchclaw/runtime/event_log.py` | `EVENT_TYPES` | 增 `pipeline.summary` |
| `researchclaw/pipeline/runner.py` | `execute_pipeline` | Stage 4/5 DONE 后评估循环；顶层 summary 写后锚定 |
| `frontend-legacy/src/services/api.js` | `EVENT_TYPES` 常量 | 同步新增类型（R-2 对齐测试） |

## 3. `stage_events.jsonl`

### 3.1 落盘

`run_dir/stage_events.jsonl`，append-only，一行一轮，`seq` 从 1 单调递增。**v1.1**：写入在 `run_dir/.locks/stage_events.lock` 的排他锁内完成，`seq` 与（缺省时）`attempt` 均锁内计算。

```json
{"seq":1,"ts":"2026-11-12T10:00:00Z","stage":4,"stage_name":"LITERATURE_COLLECT",
 "attempt":1,"plan_sig":"sha256:…","new_rows":42,"row_ids_digest":"sha256:…",
 "network_error":false,"status":"done"}
```

### 3.2 取数（全部来自既有产物）

`plan_sig = sha256(JCS(payload))`，payload：

| stage | payload | 来源 |
|---|---|---|
| 4 | `{stage:4, queries: sorted, year_min, sources: sorted ids, filters}` | `stage-03/queries.json`、`stage-03/sources.json`、`stage-03/search_plan.yaml` |
| 5 | `{stage:5, queries: sorted, year_min, sources: sorted ids, filters:{quality_threshold, min_shortlist, prefilter}}` | 同上 + `config.research.quality_threshold`（派生需求 **DR-2**） |

- `new_rows`：Stage 4 = `stage-04/candidates.jsonl` 非空行数；Stage 5 = `stage-05/shortlist.jsonl` 非空行数（M0 冻结口径）。
- `row_ids_digest`：`sha256(JCS(sorted(ids)))`，id 取 `id → paper_id → doi → title` 首个非空值（派生需求 **DR-1**）。
- `network_error`：`stage-04/retrieval_status.json.retrieval_degraded`（Stage 5 沿用上游，因为筛选本身不访问网络）。
- `attempt`：该 stage 历史事件数 + 1（不耦合 `runtime/attempt.py` 的独立计数）。

### 3.3 判定

```text
窗口 = 同 stage 事件中剔除 network_error=true 后的最近 3 条（含刚写入的一条）
若 窗口满 3 且 plan_sig 全同 且 row_ids_digest 全同 → PAUSED（E_LOOP_DETECTED）
若 窗口满 2 且同上                              → WARN（仅日志，不改变状态）
否则                                            → continue
```

- 任一有进展（`row_ids_digest` 变化）→ 窗口内不再全同 → 复位。
- `network_error=true` 的轮次整轮豁免（FC-3）；豁免不重置也不计数。
- Stage 5 的 gate 拒绝（`BLOCKED_APPROVAL` / `PAUSED`）不写事件 → 天然豁免「有意二次筛选」。
- **v1.1**：`window < 1` 抛 `ValueError`（否则 `consecutive >= window` 恒真，每轮必 pause）。

### 3.4 读侧语义（O-4 闭合）

- 空行跳过；
- **尾部连续**损坏行（torn tail，含多行半写）容忍并丢弃——与 `EventLog.read_all` 的崩溃恢复语义一致（v1.1，P-079 O-1）；
- 末尾最后一个可解析行**之前**的任何坏行 → 抛 `StageEventError`（fail-closed，对齐 `nodes.jsonl`）。

## 4. `pipeline.summary` 事件锚（D-2 修复）

### 4.1 写入

- 仅在 `_runtime_begin` 返回 `owns=True` 的**顶层执行**写锚，位置在 `_write_pipeline_summary` 之后、`run.completed/run.failed` 之前。
- payload 保持 M0 冻结字段：`{digest, generated}`。
- 嵌套执行（PIVOT/REFINE 递归）不写锚 → 每段执行**至多一个锚点**。
- `ARC_EVENTS_DISABLED=1` 时无事件日志 → 不写锚（审计需显式声明该前提）。

### 4.2 验证（`require_event=True` 三关）

1. **结构**：锚 `payload` 为对象、`digest` 为字符串、`payload_sha256` 与 `payload` 重算一致；否则 `E_SUMMARY_TAMPERED`。
2. **身份**：按 `run.started` 划分执行段；**同一段出现 ≥2 个锚点即判红**（`E_SUMMARY_TAMPERED`，`field=events.jsonl:duplicate_anchor`）。
3. **末锚**：最后一段的锚 `digest` 必须等于当前 summary 重算 digest；否则 `E_SUMMARY_TAMPERED`。
4. 无任何锚 → `E_SUMMARY_EVENT_MISSING`。

> **能力边界（诚实声明）**：以上只检测「结构不一致」与「单行追加」。能写 `events.jsonl` 的攻击者若伪造完整执行段（`run.started` + 锚 + 终态）仍可绕过；真正的完备性需跨信任域外部锚（[RESEARCH U-1](RESEARCH.md#64-未决项登记四元块)）。本批**不声称防篡改**，只声称「把单行追加伪造的成本抬到多事件一致伪造」。

## 5. runner 接线

| 位置 | 动作 | 失败策略 |
|---|---|---|
| Stage 4/5 且 `DONE`（`results.append` 之前） | `record_stage_progress()` → 写事件 → 评估 | 异常仅 warning；不改变 stage 结果 |
| 判定 `pause` | 用 `StageResult(status=PAUSED, error="E_LOOP_DETECTED", decision="loop_detected")` 覆盖 DONE | 不写 checkpoint、不注册节点、不写 KB；走既有 PAUSED 停机分支 |
| 判定 `warn` | 日志 + stdout 提示，继续 | — |
| summary 写后、`_runtime_end` 前 | `_emit_summary_anchor()`（仅 `owns`） | 异常仅 warning |

## 6. 错误码（沿用 M0 §9，不新增）

| 错误 | 触发 |
|---|---|
| `E_SUMMARY_TAMPERED` | 锚结构坏 / 同段重复锚 / 末锚不匹配 |
| `E_SUMMARY_EVENT_MISSING` | 无锚点 |
| `E_LOOP_DETECTED` | 连续 3 轮同签名同结果集 |

## 7. 关键决策与被拒绝的替代方案

| # | 决策 | 被拒绝方案 | 拒绝理由 | 代价 |
|---|---|---|---|---|
| D-1 | 一次顶层执行一个锚点 + 同段重复即判红 | (a) 所有锚 digest 必须等于当前 digest；(b) 全局首锚为准；(c) 锚 payload 加 `summary_seq` | (a) 递归/续跑会产生合法旧锚 → 误报；(b) 续跑后首锚必然过期 → 误报；(c) 需改 M0 冻结 payload，收益仅等价于同段去重 | 复刻一个「完整执行段」仍可绕过（已登记 U-1） |
| D-2 | 保留 `new_rows=行数` 冻结语义，另加 `row_ids_digest` | 只按行数判定 / 按跨轮 delta 判定 | 只按行数：「同计划同结果」永不触发（真实空转）；delta 需新增历史语料真值源 | 多一个字段；id 依赖上游稳定性 |
| D-3 | Stage 5 签名取 stage-03 计划 + config 阈值 | 以 `screen_meta.json` 为唯一来源（M0 §5.2 原文） | DONE 路径无该产物（R-4），会导致每轮签名缺失 | 与 M0 文字不一致 → 登记 DR-2 与 U-2 |
| D-4 | 评估点在 `results.append` 之前，PAUSED 覆盖 DONE | 在 checkpoint 之后评估 | 会先记「阶段完成」再暂停，续跑语义矛盾 | PAUSED 轮不写 checkpoint（符合既有 PAUSED 语义） |
| D-5 | `attempt` 取本 stage 事件数 + 1 | 复用 `runtime/attempt.py` 计数 | 两套计数顺序耦合，`_record_attempt` 在 DONE 后才递增 | 两个计数可能不一致（均为诊断字段，不承重） |

## 8. 派生需求登记（Step 8）

| ID | 派生需求 | 来源 | 上游追溯 |
|---|---|---|---|
| DR-1 | `row_ids_digest` 字段与 id 取键顺序 | RESEARCH S-4（去重后新增口径） | FC-1 意图 |
| DR-2 | Stage 5 签名来源退化为 stage-03 计划 + `quality_threshold` | RESEARCH R-4（产物缺口） | M0 §5.2 的偏移，登记 U-2 |
| DR-3 | 中间坏行 fail-closed、仅末行容忍 | RESEARCH R-1 + P-077 O-4 | O-4 闭合 |
| DR-4 | 2 次 WARN / 3 次 PAUSE | failure-guards C.2 | FC-1 |

## 9. 不变式

- I-1 `stage_events.jsonl` 只追加，不重写；`seq` 单调。
- I-2 循环判定是**纯函数**（事件列表 → 动作），不读写除事件文件外的状态。
- I-3 护栏失败不影响 run：任何异常只 warning。
- I-4 不新增错误码、不改 C4 schema、不动 `pipeline_summary` 字段集。
- I-5 事件锚与侧车同域，**不承诺**抗一致重写。

## 10. 验收映射

| 批次 | 验收 ID | 落盘 |
|---|---|---|
| M2 P-078 | FC-1 | `stage_events.jsonl` + PAUSED/E_LOOP_DETECTED |
| M2 P-078 | FC-2 | 有进展轮次不触发（`row_ids_digest` 变化） |
| M2 P-078 | FC-3 | `network_error=true` 豁免 |
| M2 P-078 | A3-2 | `pipeline_summary.json` + `.sha256` + `events.jsonl:pipeline.summary` 三向 |

## 11. 非目标 / 边界

- **职责外**：签名树头、外部公证、多机 gossip（G7）；多进程文件锁（P-079 与 D-1 同批裁决）。
- **能力边界**：无密钥 → 不能防「一致重写」；只能检测结构不一致。
- 不改 Stage 4/5 的业务产物与判定；不新增 Stage。

## 12. 拒绝的低效操作

| 操作 | 为何不做 |
|---|---|
| 每轮重算全量 `events.jsonl` 链 | 只读锚点行即可；链完整性是 `verify_chain` 的职责 |
| 在 `stage_events` 里存全量 id 列表 | 用 digest 即可，避免文件膨胀 |
| 为循环护栏起后台线程/定时器 | 判定是同步纯函数，无异步需求 |
