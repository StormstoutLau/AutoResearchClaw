---
id: runbook-g7
type: design
version: 1.0
status: active
date: 2026-11-25
depends: [arc-g7-concurrency-dual-plane-DESIGN, arc-g7-soak-RESEARCH, arc-g7-orchestration-RESEARCH]
upstream: arc-master-roadmap
---

# G7 长跑恢复 Runbook

> **用途**：无人值守 run 卡住、异常退出、预算耗尽、事件链异常、双平面漂移时的**单页恢复流程**。
> **目标**：按本文档在 **30 分钟内**完成一次恢复并给出可复核的验证输出。
> **纪律**：不删事件、不改 fencing、不手改 claims；先取证再动手。

## 1. 5 分钟分诊（只读）

在仓库根目录执行：

```bash
python -m researchclaw ops --runs-root artifacts
```

读数含义：

| 字段 | 含义 | 异常信号 |
|---|---|---|
| `restarts` | `supervisor.jsonl` 的 `restart_scheduled` 或 `soak_session.jsonl` 的 `restart_injected` 次数 | 持续增长 = 重启风暴，先修根因 |
| `recovery_seconds` | 每次注入重启到下次 `worker_started` 的秒数 | 远大于正常启动时间 = 依赖/网络/锁 |
| `failure_stages` | 失败阶段分布 | 集中在一个 stage = 该阶段数据/环境问题 |
| `last_stage` / `status` | `checkpoint.json` 真值 | `unknown` = 没有可恢复检查点 |
| `events` | 可解析事件行数 | 0 = 事件日志缺失，按 §5 升级 |

补充取证：

```bash
tail -n 20 artifacts/<run>/supervisor.jsonl
python -m researchclaw soak verify --output artifacts/<run>
```

## 2. 判定表

| 症状 | 判定 | 动作 |
|---|---|---|
| checkpoint 长时间不前进，进程还在 | worker 卡在某个 stage（LLM/实验/工具） | 记录 stage；按 §3.1 让 supervisor 重启 |
| 进程已死，`lease.json` 仍在 | 崩溃留下 stale 租约 | **不要手删**；supervisor 会在 spawn 前回收（`is_expired` 或 pid 死） |
| `lease.json` 的 pid 活着但 checkpoint 不动 | 可能是另一个活 worker | 先 `ops` 确认没有第二个 run；不要强抢 |
| 反复退出 75 | retryable 失败（数据/临时错误） | 看 `supervisor.jsonl` 的 `rc`；`--max-restarts` 用尽后修根因 |
| `admission_budget_rejected` | 预算已耗尽 | 核对 `cost_log.jsonl` 求和；提高 `model_policy.run_budget_usd` 或终止 |
| `admission_timeout`（退出 78，`queued=true`） | attempt 槽已满 | 等正在跑的 run 结束；HITL 用 `--hitl-priority` 走保留槽 |
| `soak verify` 报 `chain:*` | 事件链断/被改 | 保留现场，按 §5 升级；不要继续写 |
| `soak verify` 报 `retention_limited` | 最旧归档段被回收 | 若是有意归档，记录后接受；否则检查 `apply_retention` 参数 |
| `python -m researchclaw audit --run-dir <run>` 退出 1 | 双平面 status/deliverable 漂移 | 对比 `stage-20/claims.jsonl` 与 `stage-20/claim_gate.json`；不要手改 |
| HITL 已写 `response.json` 但 run 不动 | worker 已死或等待超时 | 见 §3.2 |

## 3. 恢复步骤

### 3.1 普通恢复（推荐入口）

```bash
python -m researchclaw supervisor --output artifacts/<run> --config config.yaml
```

- supervisor **不持有 run 租约**；它只在 worker 可证死亡/过期时清理 stale lease，然后重启。
- 只有退出码 75 会重启；0/65/77/78/85 都停止。
- 若配置了 `multi_project.enabled`，supervisor 在 **spawn 前**申请 attempt 槽；槽满时不会起进程。

### 3.2 HITL 唤醒

```bash
python -m researchclaw supervisor --output artifacts/<run> --config config.yaml --hitl-priority
```

- `--hitl-priority` 使用为人工保留的槽位，不会被批量 run 饿死。
- 人工响应仍走文件 IPC：`artifacts/<run>/hitl/waiting.json` → 写 `response.json`。
- 若 `waiting.json` 存在但无 worker，直接按 §3.1 重启。

### 3.3 预算拒绝

```bash
python - <<'PY'
from pathlib import Path
from researchclaw.cost_tracker import sum_cost_log
print(sum_cost_log(Path("artifacts/<run>")))
PY
```

- 若 `spent >= run_budget_usd`：提高预算或终止；不要绕过（`pre_call_budget_check` 仍会拦）。
- 预算拒绝发生在 spawn 前，不会留下半启动进程。

### 3.4 并发槽位检查

```bash
cat .researchclaw/slots/registry.json
```

- `slots` 里的 pid 死/过期会被下一次申请自动回收；**不要手删 `registry.json`**（会丢 fencing 单调性）。
- 排队中的 run 在 `queue` 里；槽释放后按调用方重试顺序进入（本仓不做跨进程抢占）。

## 4. 验证（必须全过才宣布恢复）

```bash
python -m researchclaw soak verify --output artifacts/<run>
python -m researchclaw audit --run-dir artifacts/<run>
python -m researchclaw ops --runs-root artifacts
```

通过标准：

1. `soak verify`：`ok=True`、`converged=True`、无 `chain:*` / `seq_gaps` / `run_id_mismatch`。
2. `audit`：退出码 0（双平面一致）。
3. `ops`：该 run 的 `status` 与 `last_stage` 与 `checkpoint.json` 一致，`restarts` 不再增长。

## 5. 回退与升级

- **回退点**：停 supervisor 即可；run 目录、事件链、租约都保留原样。
- **禁止**：删除 `events*.jsonl`、手改 `lease.json` 的 `fencing`、手改 `stage-20/claims.jsonl`。
- **升级取证包**（30 分钟内无法定位时）：`supervisor.jsonl`、`events_summary.json`、`cost_log.jsonl`、`stage-20/claim_gate.json`、`ops --json` 输出。
- 事件链/双平面问题不在 runbook 内修复，转 P 批次处理。

## 6. 演练记录（A7-5）

| 项 | 值 |
|---|---|
| 日期 | 2026-11-25 |
| 执行人 | 作者（非独立新人；见下方限制） |
| 场景 | 合成 run：worker 第一次写 checkpoint 后以 75 退出并留下 stale lease，第二次恢复并收敛 |
| 步骤 | 严格按 §1 分诊 → §3.1 启动 supervisor → §4 三项验证 |
| 耗时 | supervisor 全程 **0.34s**；`recovery_seconds=0.08s`（远低于 30 分钟门槛） |
| 结果 | `soak verify` ok/converged（`last_seq=4`）、`audit` exit 0、`ops` 读数与 checkpoint 一致（`last_stage=4`、`status=completed`） |
| 限制 | 合成 worker（本机无真实 LLM 凭据）；恢复代码路径与生产一致（Supervisor/spawn/restart/stale lease）。**未做**独立新人盲测，已登记为 U-172-1，A7-5 记「部分」而非完全通过 |
