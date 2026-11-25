---
id: arc-g7-concurrency-dual-plane-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-g7-concurrency-dual-plane-RESEARCH, arc-g1-readiness-research-DESIGN, arc-q5-decision-method-RESEARCH]
upstream: arc-master-roadmap
---

# 设计：G7 并发/双平面段（P-172）

> **范围**：A7-2 / A7-3 / A7-5 / A7-6 / A7-7 + 跨 run 归档 + 观测看板 + 并发准入。
> **非目标**：A7-1/A7-4 field run 验收；不新增调度器；不做跨机分布式锁；不做 LLM 语义限流。

## 1. 决策表

| ID | 决策 | 被拒替代 | 理由（证据） |
|---|---|---|---|
| D-1 | 准入集中在 `researchclaw/runtime/admission.py`，用 run 目录之外的 `slot_root` 存 registry JSON | 塞进 `Supervisor` 内联；用 SQLite/Redis | 可独立测试与复用；零新依赖（E4/E5）；supervisor 保持「只负责重启」 |
| D-2 | 容量二分：`normal_cap = max(0, max_attempts - reserved)`；`hitl_cap = max_attempts`；总在册 ≤ `max_attempts` | 抢占低优先级 run；全部 FIFO | E2 的非抢占式优先级；E3 的类别上限；HITL 最坏等一个 worker 退出 |
| D-3 | slot 在 **spawn 前同步预留**，worker 退出后立即释放；重启下一 attempt 重新申请 | 整个 supervisor 生命周期持槽 | A7-7 字面；退避睡眠不占容量 |
| D-4 | 槽满时记录 queue 行并**阻塞轮询**至 `queue_timeout_sec`；超时返回 CONFIG(78) + `queued=True`，不 spawn | 无限等待；返回 RETRYABLE(75) | 75 会触发 supervisor 重启风暴；78 非 retryable，交由上层重排 |
| D-5 | 预算前置拒绝用 `sum_cost_log(run_dir)`，在 `budget_usd>0` 且 `spent>=budget` 时抛 `BudgetRejected`，不 spawn | 复用进程内 tracker | resume 是新进程，tracker 从 0 开始；run 目录才是真值（E1 的准入语义） |
| D-6 | `max_inflight_llm_calls` 为**单 run 内**信号量；token 目录 `run_dir/.inflight`；0=不限 | 全局跨 run 限流 | 跨 run 公平已由 slot 承担；避免引入全局耦合（U-2） |
| D-7 | 双平面不改算法：A7-3 只增加并发/跨 run/只读三类证据，复用 `compare_claims` | 新写独立判定器 | E9 的方法论是差分测试；共用内核时只能证明重放一致，不能宣称 N-version |
| D-8 | 跨 run 归档 = 逐 run `EventLog.apply_retention` + `RUN_INDEX.jsonl`（append-only，锁保护）；索引可由 run 目录重建 | 合并所有 run 的事件到全局日志 | E5 的单写者/checkpoint；run 目录仍是唯一真值 |
| D-9 | 观测看板 = 纯函数 `build_ops_view(runs_root)` + CLI `researchclaw ops`；只读 | 改 dashboard 服务 | Runbook 需要一个 10 秒内可执行的入口；纯函数易测且无副作用 |
| D-10 | 配置字段进既有 `multi_project`，不新增顶层 section；默认值保持关闭/0 | 新建 `concurrency` section | 避免配置 schema 扩散与旧配置兼容风险（U-5） |

## 2. 数据模型（`admission.py`）

```json
// <slot_root>/registry.json
{
  "version": 1,
  "fencing": 7,
  "slots": [
    {"slot_id": "s7", "run_id": "rc-...", "owner": "host:123", "pid": 123,
     "slot_class": "normal", "acquired_at": "2026-11-25T...Z",
     "expires_at": "2026-11-25T...Z", "fencing": 7}
  ],
  "queue": [
    {"run_id": "rc-...", "slot_class": "normal", "priority": 1,
     "queued_at": "2026-11-25T...Z"}
  ]
}
```

- `fencing` 单调递增，只增不减；slot 删除后不复用编号。
- `slot_class ∈ {"normal", "hitl"}`；`priority` 仅用于看板排序（hitl=0，normal=1），**不参与**容量判定。
- `queue` 按 `run_id` 去重；成功拿槽时移除该 run 的队列行。

## 3. 算法

### 3.1 `SlotRegistry.acquire(run_id, slot_class, timeout, poll)`

```
deadline ← monotonic() + max(0, timeout)
loop:
    slot ← try_acquire(run_id, slot_class)
    if slot: return slot
    if monotonic() >= deadline: raise AdmissionTimeout
    sleep(min(poll, remaining))
```

### 3.2 `try_acquire`

```
with exclusive_lock(root/"registry.lock", timeout=lock_timeout):
    state ← load()                      # 缺失/损坏 → 空状态（fail-open 到「无槽」而非放行）
    moment ← now()
    state.slots ← [s for s in state.slots if not stale(s, moment)]
        stale(s) := expired(s) or (s.host == this_host and not is_pid_alive(s.pid))
    held ← first slot with slot_id.run_id == run_id
    if held: touch expiry; save; return held        # 幂等：同 run 不占两槽
    hitl ← count(slot_class == "hitl")
    normal ← count(slot_class == "normal")
    total ← hitl + normal
    allowed ← total < max_attempts and (
        hitl if slot_class == "hitl" else normal < normal_cap)
    if not allowed:
        upsert queue row; save; return None
    state.fencing += 1
    slot ← {slot_id: "s"+fencing, run_id, owner, pid, slot_class,
            acquired_at, expires_at: moment+ttl, fencing}
    state.slots.append(slot); remove queue row for run_id; save
    return slot
```

**边界**：
- `max_attempts < 1` → 构造期 `ValueError`；`reserved` 钳位到 `[0, max_attempts]`。
- registry JSON 损坏 → 视为空状态并记录 `corrupt_registry`（宁可暂时放行也不永久锁死；下一次写修复）。
- 同 host 才用 PID 探活；跨 host（sshd/共享盘）只信 TTL，避免误杀活槽。

### 3.3 `release(slot)`

```
with lock:
    state ← load()
    removed ← [s for s in slots if s.slot_id == slot.slot_id and s.fencing == slot.fencing]
    if not removed: return False        # 已被接管/已释放，幂等
    state.slots ← others; save; return True
```
**不释放别人的槽**：`slot_id + fencing` 双条件，防 ABA。

### 3.4 `preflight_budget`

```
if budget_usd <= 0: return {"ok": True}
spent, tokens, lines ← sum_cost_log(run_dir)
if spent >= budget_usd: raise BudgetRejected(spent, budget_usd)
return {"ok": True, "spent_usd": spent, "budget_usd": budget_usd}
```
浮点直接用 `>=`（与 `CostTracker.check_budget` 的「等于即耗尽」一致，[cost_tracker.py L262-L270](../../researchclaw/cost_tracker.py#L262-L270)）。

## 4. supervisor 接线

`Supervisor.__init__` 新增可选参数（默认 None/0，行为不变）：

```python
admission: SlotRegistry | None = None
slot_class: str = "normal"
run_budget_usd: float = 0.0
admission_timeout: float = 0.0
```

`run()` 的每次 attempt：

```
if admission is not None:
    preflight_budget(run_dir, run_budget_usd)         # 失败 → log + return CONFIG
    try:
        slot ← admission.acquire(run_id, slot_class, timeout=admission_timeout)
    except AdmissionTimeout:
        log("admission_timeout"); return SupervisorResult(CONFIG, queued=True)
    log("admission_granted", slot_id, fencing)
try:
    rc ← spawn().wait()
finally:
    if slot: admission.release(slot)
```

- `queued=True` 是新字段，默认 False，既有调用方零影响。
- 预算拒绝与超时都返回 **CONFIG(78)**：非 retryable → supervisor 不会自旋重启。
- 日志只写 `supervisor.jsonl`，不写 `events.jsonl`（沿用 R-2「supervisor 不持租约、不写事件」）。

## 5. inflight LLM 限流（`llm/inflight.py`）

```
token_root = run_dir/".inflight"
slot(timeout):
    with exclusive_lock(token_root/"inflight.lock"):
        prune expired or dead-pid tokens
        if count < limit: create token-<pid>-<uuid>.json; return token
    loop until timeout: re-check; sleep(poll)
```
- 上下文管理器在 `finally` 删除自己的 token；进程崩溃由 pid/expiry 清理。
- `limit <= 0` → `nullcontext`（零开销）。
- 接线点：`LLMClient.chat` 的 `_call_with_retry` 外层（[client.py L356-L358](../../researchclaw/llm/client.py#L356-L358)），仅当 `max_inflight_llm_calls>0` 且 tracker 有 `run_dir`。

## 6. 跨 run 归档与看板（`runtime/ops.py`）

### 6.1 `build_ops_view(runs_root) -> dict`

只读；逐 run 汇总：

| 字段 | 来源 | 算法 |
|---|---|---|
| `restarts` | `supervisor.jsonl` / `soak_session.jsonl` | 计数 `restart_scheduled` + `restart_injected` |
| `recovery_seconds` | `soak_session.jsonl` | 对每个 `restart_injected` 取其后的首个 `worker_started`，`ts` 差 |
| `failure_stages` | `stage_events.jsonl`，回退 `events*.jsonl` | `status in {"failed","error"}` 或 `type=="stage.failed"` 按 stage 计数 |
| `last_stage` / `status` | `checkpoint.json` | 直读 |
| `events` | 分段事件文件 | 行数（只统计可解析行） |

排序：`run_id` 字典序；totals 求和。任何单 run 解析失败只降级该 run 的字段，不让整张看板失败。

### 6.2 `sweep_runs(runs_root, retention_days=30, archive_days=365, now=None)`

```
for run_dir in sorted(runs_root):
    log ← EventLog(run_dir, run_id, fsync=False)
    result ← log.apply_retention(retention_days, archive_days, now)
    row ← {ts, run_id, last_seq, count, chain_tail, archived, deleted}
    append row to runs_root/"RUN_INDEX.jsonl" under exclusive_lock
```
- **不删除 run 目录**；`deleted` 只可能是已 gzip 且超 `archive_days` 的分段。
- 索引是派生视图：删除索引不影响回放（能否回放由 `soak verify` / `verify_chain` 判定）。

## 7. 配置（`config.py`）

```yaml
multi_project:
  enabled: false            # 既有
  max_concurrent: 2         # 既有（项目级）
  max_concurrent_attempts: 2   # 新增：attempt 槽上限
  hitl_priority_slots: 1       # 新增：为 HITL 保留的槽数（0..max_concurrent_attempts）
  max_inflight_llm_calls: 0     # 新增：单 run 内并发 LLM 调用上限，0=不限
  slot_root: ".researchclaw/slots"
  queue_timeout_sec: 0.0       # 0 = 不等待，立即返回 queued
```

解析函数 `_parse_multi_project_config` 做类型转换与非负钳位；非法值回退默认（不抛异常，保持旧配置可加载）。

## 8. 不变式

| ID | 不变式 | 可机械验证 |
|---|---|---|
| J-1 | 启用 admission 时，无槽绝不 spawn | spawn 回调断言 registry 中存在本 run 槽 |
| J-2 | 任何退出路径（含 spawn 异常）都释放槽 | `try/finally` + 二次 release 返回 False |
| J-3 | 同一 `run_id` 不占两个槽 | 再次 acquire 返回同一 slot_id/fencing |
| J-4 | 活槽不被夺；死/过期槽可回收 | 伪造过期与伪造死 pid 两用例 |
| J-5 | normal 不吞 HITL 保留容量 | 1 normal 运行时 normal 入队、hitl 立刻拿槽 |
| J-6 | 预算拒绝发生在 spawn 前 | spawn 未被调用 + `BudgetRejected`/CONFIG |
| J-7 | inflight 并发数 ≤ limit | 3 线程共享 limit=2，峰值 ≤2 |
| J-8 | ops 视图只读 | 视图前后 run 目录哈希不变 |
| J-9 | 双平面同输入同状态；审计不写 run | 两平面 status 相等 + 审计前后哈希不变 |
| J-10 | 跨 run 零写入 | 并发两 run 后对方目录哈希不变 |

## 9. 错误语义

| 场景 | 行为 |
|---|---|
| registry 文件不存在 | 视为空 registry，首次 acquire 创建 |
| registry JSON 损坏 | 视为空 registry，记录 `corrupt_registry`，继续（可用性优先） |
| registry 锁超时 | `AdmissionTimeout`（调用方按 queued 处理） |
| 同 run 并发 acquire | 第二个拿到同一 slot（幂等），不重复计数 |
| slot 过期但 pid 活着 | **不回收**（活进程可能仍在跑）；仅 TTL 到期 + pid 死/跨 host 才回收 |
| 预算恰好等于上限 | 拒绝（`>=`） |
| inflight token 残留 | 下个 acquire 时按 pid/expiry 清理 |
| ops 单个 run 事件坏行 | 跳过坏行继续；不中断全局视图 |
| 归档时 active 日志 | `apply_retention` 不移动 active（既有语义） |

## 10. 回退点

- 删除三个新模块 + 还原 `supervisor.py`/`client.py`/`cli.py`/`config.py` 四个接线点即可完全回到 P-171 状态；新配置字段有默认值，不回退配置也不影响旧行为。
- Runbook 是纯文档，无运行时依赖。
