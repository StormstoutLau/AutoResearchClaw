---
id: arc-g7-concurrency-dual-plane-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-25
depends: [arc-g7-concurrency-dual-plane-DESIGN, arc-g7-concurrency-dual-plane-RESEARCH]
upstream: arc-master-roadmap
---

# 实施：G7 并发/双平面段（P-172）

> **批次**：T1（Layer-1 运行时模块 + 配置 + 接线 + 测试）。
> **口径**：本文件只写实际落地的锚点与读数；算法与不变式的权威在 [DESIGN.md](DESIGN.md)。

## 1. 交付面与源码锚点

| 交付 | 文件 | 符号/行 | 关键行为 |
|---|---|---|---|
| attempt 槽注册表 | [admission.py](../../researchclaw/runtime/admission.py) | `SlotRegistry` [L104](../../researchclaw/runtime/admission.py#L104) | 文件型跨进程 registry，`exclusive_lock` 唯一写入口 |
| 非阻塞申请 | 同上 | `try_acquire` [L209](../../researchclaw/runtime/admission.py#L209) | 清 stale → 幂等 → 容量判定 → fencing+1 |
| 阻塞申请 | 同上 | `acquire` [L272](../../researchclaw/runtime/admission.py#L272) | 轮询至 `timeout`，超时抛 `AdmissionTimeout` |
| 释放 | 同上 | `release` [L302](../../researchclaw/runtime/admission.py#L302) | `slot_id + fencing` 双条件，防 ABA |
| 看板快照 | 同上 | `snapshot` [L321](../../researchclaw/runtime/admission.py#L321) | 在册/按类/队列/fencing |
| 预算前置拒绝 | 同上 | `preflight_budget` [L343](../../researchclaw/runtime/admission.py#L343) | `sum_cost_log` → `spent >= budget` 抛 `BudgetRejected` |
| spawn 前准入 | [supervisor.py](../../researchclaw/runtime/supervisor.py) | `_admit` [L122](../../researchclaw/runtime/supervisor.py#L122) | 预算 → 槽 → `admission_granted` 日志 |
| spawn/释放配对 | 同上 | `run()` [L150-L190](../../researchclaw/runtime/supervisor.py#L150-L190) | `try/finally` 释放；`worker_started` 供恢复耗时统计 |
| queued 结果 | 同上 | `SupervisorResult.queued` [L56](../../researchclaw/runtime/supervisor.py#L56) | 槽满超时返回 CONFIG(78) 且 `queued=True` |
| inflight 限流 | [inflight.py](../../researchclaw/llm/inflight.py) | `InflightLimiter` [L43](../../researchclaw/llm/inflight.py#L43)、`slot` [L109](../../researchclaw/llm/inflight.py#L109) | token 文件 + 锁 + pid/expiry 清理 |
| LLM 接线 | [client.py](../../researchclaw/llm/client.py) | `_inflight_guard` [L408](../../researchclaw/llm/client.py#L408) | 仅 `max_inflight_llm_calls>0` 且有 run_dir 时生效 |
| 配置 | [config.py](../../researchclaw/config.py) | `MultiProjectConfig` [L799-L812](../../researchclaw/config.py#L799-L812)、解析 [L1702-L1721](../../researchclaw/config.py#L1702-L1721) | 默认关闭/0；非法值钳位 |
| 跨 run 看板 | [ops.py](../../researchclaw/runtime/ops.py) | `build_ops_view` [L158](../../researchclaw/runtime/ops.py#L158) | 只读纯函数；坏行跳过 |
| 跨 run 归档 | 同上 | `sweep_runs` [L195](../../researchclaw/runtime/ops.py#L195) | 逐 run `apply_retention` + `RUN_INDEX.jsonl` |
| CLI 看板 | [cli.py](../../researchclaw/cli.py) | `cmd_ops` [L536](../../researchclaw/cli.py#L536) | `researchclaw ops --runs-root ... [--json]` |
| CLI 准入开关 | 同上 | `cmd_supervisor` [L485-L533](../../researchclaw/cli.py#L485-L533) | `multi_project.enabled` + `--hitl-priority` |
| Runbook | [runbook-g7.md](../../docs/runbook-g7.md) | §1-§6 | 分诊/判定/恢复/验证/回退/演练 |

## 2. TDD 红 → 绿

1. **红**：先提交 5 个测试文件（`test_admission.py` / `test_inflight.py` / `test_ops.py` / `test_concurrency_isolation.py` + `test_supervisor.py` 追加），pytest collection 报 `ModuleNotFoundError: researchclaw.runtime.admission|ops` 与 `researchclaw.llm.inflight`，4 个文件收集失败。
2. **绿**：实现三个模块 + 四个接线点；首轮 38 项中 1 项期望错误——测试假设释放后复用 `slot_id=s1`，实际按设计 fencing 单调生成 `s2`；按 DESIGN §2「slot 编号不复用」修正测试断言（不是实现）。
3. **回归**：相关面 215 passed；全量 3945 passed / 6 环境态失败 / 108 skipped（失败同 P-167/P-171：Windows shell hook、Keras 3、bash 路径，均与本批无关）。

## 3. 关键实现点（与 DESIGN 对应）

- **容量二分**（DESIGN §3.2）：`normal_capacity = max_attempts - hitl_priority_slots`；normal 判定 `normal < normal_capacity`，hitl 判定 `hitl < max_attempts` 且 `total < max_attempts`。实现 [admission.py L240-L253](../../researchclaw/runtime/admission.py#L240-L253)。
- **stale 判定**（J-4）：先看 `expires_at`，再按 owner host 决定是否 PID 探活；跨 host 只信 TTL，避免误杀。实现 [L181-L193](../../researchclaw/runtime/admission.py#L181-L193)。
- **幂等**（J-3）：同 `run_id` 已在册时只续期并返回原槽，不新增计数。实现 [L222-L231](../../researchclaw/runtime/admission.py#L222-L231)。
- **预算边界**（J-6）：`budget<=0` 关闭；`spent >= budget` 即拒绝，与 `CostTracker.check_budget` 的「等于即耗尽」一致。
- **释放配对**（J-2）：`try: spawn … finally: release`；spawn 抛异常也会释放。
- **inflight**（J-7）：token 内含 `pid/host/expires_at`；申请与清理都在 `inflight.lock` 内完成。
- **看板只读**（J-8）：`build_ops_view` 只调用自写的 JSONL/gzip 读取器，不实例化 `EventLog`（后者会重建/截断 torn tail）。
- **归档不删 run**（D-8）：`sweep_runs` 只对已滚动段做 gzip/删除；active 日志不动。

## 4. 验收读数（本机）

| 项 | 命令 | 读数 |
|---|---|---|
| 新增面 | `pytest tests/test_admission.py tests/test_inflight.py tests/test_ops.py tests/test_concurrency_isolation.py tests/test_supervisor.py -q` | **38 passed**（后续 +1 坏行用例 = 39） |
| 相关回归 | `pytest tests/test_rc_config.py tests/test_rc_llm.py tests/test_reviewer_llm.py tests/test_event_log.py tests/test_event_log_roll_recovery.py tests/test_offline_audit.py tests/test_stage_claim_hooks.py tests/test_soak_driver.py tests/test_soak_verifier.py tests/test_cli.py tests/test_rc_cli.py -q` | **215 passed** |
| 全量 | `pytest -q` | **3945 passed / 6 failed / 108 skipped**（6 = 环境态） |
| 配置探针 | `RCConfig.from_dict` + `build_parser` | `max_attempts=3`、`reserved` 6→3 钳位、`queue_timeout_sec` -5→0.0；`ops` 子命令与 `--hitl-priority` 可解析 |
| 恢复演练 | 合成 worker：首次 75 且留 stale lease，二次收敛 | supervisor `exit=0 restarts=1 elapsed=0.34s`；`verify ok/converged`；`recovery_seconds=0.08s`；`ops last_stage=4 status=completed` |

## 5. 未做 / 边界

- **A7-1 / A7-4**：72h field run 与正式回放验收未做；本批只交工具链与合成演练，不虚报。
- **A7-5 的独立新人盲测**：未做（无人可派），Runbook §6 已声明为合成演练 + 作者执行；登记 U-172-1。
- **LLM 语义 inflight**：只做调用数限流，不做 token 级/费用级滑动窗口。
- **跨机并发**：registry 只对共享同一 `slot_root` 的进程有效；跨 host 的 PID 探活退化为 TTL。
- **裸 `researchclaw run` 绕过准入**：本批只在 `researchclaw supervisor` 的 spawn 边界实现准入；直接 `run` 的并发不受 `max_concurrent_attempts` 约束。生产无人值守入口是 supervisor（[cli.py L479](../../researchclaw/cli.py#L479)），登记 U-172-2 待后续在 run 入口复用同一 registry（需避免 supervisor→worker 双占槽）。
- **观察项 O-165-3 / O-165-6**：本批不触碰 `experiments/arc_bench/orchestration/`，不承接。
- **配置示例**：未改 `config.researchclaw.example.yaml`；字段有默认值，旧配置无需迁移。
