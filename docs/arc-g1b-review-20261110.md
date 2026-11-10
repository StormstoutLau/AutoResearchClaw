# G1b 调研独立复核（P-028 复核）

> **日期**：2026-11-10
> **复核对象**：[spec/arc-g1b-supervisor-protocol/](../spec/arc-g1b-supervisor-protocol/)（P-028，G1b 调研批）
> **复核方法**：①事实表独立复验（CLI/路由/数据类一手重查）；②锚点回源状态与等级审查；③设计契约的逻辑一致性审查（退出码/租约/attempt/SSE/outbox 与 G1a 的交互）。
> **复核人声明**：本报告为独立会话产出；读码为本机独立进行。

---

## 1. 总体结论

P-028 的**事实底座与锚点成立**，四子问题的方案选择合理；但设计契约存在 **2 个实施前必须解决的缺口（R-2 租约所有权冲突、R-3 长任务租约过期无续期）**、**1 个未定义映射（R-1 非失败终态）**、**2 项需修正/澄清（C-2 两层退避、C-3 X-10 等级）**。七项验收的方案框架不受影响，实施批（P-029）**必须先吸收 R-1..R-3**。

---

## 2. 机检与事实表复验

| # | 复验 | 结果 |
|---|---|---|
| F-1 | CLI 无 `supervisor`/`worker` | ✅ 独立 grep 0 命中 |
| F-2 | 重试为进程内循环 | ✅ `executor.py:613-630` |
| F-3 | `StageResult` 无 attempt/session_id | ✅ 独立确认；`_helpers.py` 的 6 处 `attempt` 命中全部位于 LLM 调用重试函数（L770-805），不在数据类 |
| F-5 | `stage-NN_v{k}` 先例 | ✅ `runner.py:1365-1397` |
| F-6 | 路由无 `/events` | ✅ 独立 grep 0 命中 |
| F-8 | `EventLog.read_after` 存在 | ✅（G1a 已测） |
| F-9 | 退出码未分类 | ✅ `runner.py` FAILED 分支直接 `break` |

机检：`pre-commit run --all-files` 9/9、`step-gate` 5/5、`console --check` 一致、`step_enforce --base HEAD` exit 0 —— 全部独立重跑通过。

---

## 3. 锚点等级审查

10 项锚点全部一手命中。**一处等级需修正**：

- **C-3（X-10）**：RESEARCH 标「T1 书/官方」，但「重试占流量约 10% 即停」这一**具体数值**出自二手博客转述（dreaming.press），Google SRE 官方章节原文只讲 load shedding 未给该数。应改为：**重试预算思想 = T1（书）；10% 数值 = T2（二手转述，未回原文）**。不影响「设预算」的结论，影响的是数值引用的等级。

---

## 4. 设计契约审查（核心发现）

### R-1（实施前必须定义）：非失败终态没有退出码映射

`StageStatus` 九态中，`BLOCKED_APPROVAL`（审批门）、`PAUSED`、`REJECTED` 是**正常暂停**而非失败。DESIGN §2 的退出码表只覆盖成功/可重试/三类失败——worker 遇到审批门时以什么码退出？

- 若 `0`：supervisor 误判「完成」，run 结束，审批后无人续跑；
- 若 `75`：无限重启，直到重试预算耗尽。

**必须新增语义**（建议：专用退出码如 `85 = PAUSED_NORMAL`，supervisor 收到后**停止但不写 run.failed**，等待人工 `approve` 后重新 `supervisor --resume`）。P-029 开工前落档。

### R-2（实施前必须解决）：supervisor 与 worker 的租约所有权冲突

DESIGN §3 伪代码第一步是 `acquire lease(run)`——但 G1a 的 `runner._runtime_begin` 在 **worker 进程内**也会 `acquire`，而 supervisor 与 worker 的 `owner`（host:pid）**必然不同** → worker 启动即 `LeaseBusy`，**自愈流程结构性死锁**。

修正方向（二选一，P-029 落档）：
- (a) supervisor **不持有** run 租约，只监督进程；租约仍由 worker 持有；
- (b) supervisor 获取租约后把 `owner`/`fencing` 通过环境变量传给 worker，worker 以继承身份续期。

倾向 (a)（改动最小，且租约语义 = 「谁在写事件」）。

### R-3（实施前必须解决）：长任务下租约过期无续期 → 双写风险

G1a 的租约只在 `_runtime_begin` 获取一次，`TTL=600s`，**运行中无续期**。超过 10 分钟的 Stage（实验执行常态）期间租约过期，第二个 worker 可合法接管（fencing+1）→ 双写。单机手动场景风险低，但 G1b 的 supervisor 语境把「多进程并存」变成常态。

**G1b 必须补**：runner 内后台线程周期 `renew`（如 TTL/3 间隔）；续期失败（`LeaseLost`）→ worker 自停并写 `run.failed{lease_lost}`。此为 G1a 遗漏，登记为 G1b 实施项。

### C-2（需写明）：两层退避的职责边界

复核新发现：LLM 调用层已有 `2**(attempt+1)` 指数退避（`_helpers.py:802`，**无 jitter**）。G1b 的 supervisor 退避（进程级）与该退避（调用级）不冲突，但 DESIGN 应写明：**调用级退避管 API 限流，进程级退避管崩溃恢复**，且 G1b 实施时给 LLM 层退避补 full jitter（X-3 的直接适用点）。

### C-4（澄清）：A1-2 负向用例中「gap 检测」的定义

`stream.gap` 是对「请求范围超出保留窗口」的显式通知，**不是日志缺口**。A1-2 负向用例应表述为：「客户端请求已归档删除的 seq → 必须收到 `stream.gap` 且不得静默跳号」；日志本身的缺口由 `verify_chain` 的 seq 连续性覆盖。建议 P-029 CHECKLIST 引用时采用此表述。

### C-5（确认）：outbox 与 K-1 自洽

「启动时扫描全量事件构建 queued−done 集合」在 10²–10³ 事件/run 下可行，与 P-025 K-1（>10⁵ 触发重审）一致。✓

---

## 5. 复核结论

| # | 结论 | 类型 |
|---|---|---|
| C-1 | 事实表 F-1..F-9 全部属实（含 F-3 的 6 处命中归属澄清） | 确认 |
| C-2 | 新发现：LLM 层已有无 jitter 的指数退避；两层退避职责需在 DESIGN 写明 | 补充 |
| C-3 | X-10 的 10% 数值为二手转述，等级降 T2 | 等级修正 |
| C-4 | A1-2 负向用例的 gap 语义需按本报告 §4-C-4 表述 | 澄清 |
| C-5 | outbox 与 K-1 自洽 | 确认 |
| **C-6** | **R-1 非失败终态无退出码映射——实施前必须定义** | **缺口** |
| **C-7** | **R-2 supervisor/worker 租约所有权冲突——结构性死锁，实施前必须解决** | **缺口** |
| **C-8** | **R-3 长任务租约无续期（G1a 遗漏）——G1b 必须补续期线程** | **缺口** |

**裁决输入不受影响**（四子问题的方案选择维持），但 P-029 开工前必须先吸收 R-1..R-3 + C-2..C-4。P-028 文档保持原样（复核不修改被复核对象）。

---

## 6. 复核清单

- [x] 机检独立重跑（9/9）
- [x] 事实表复验（7 项一手确认，含 F-3 命中归属澄清）
- [x] 锚点 10 项回源状态审查（X-10 等级修正）
- [x] 设计契约逻辑审查（退出码/租约/attempt/SSE/outbox × G1a 交互）
- [x] 未修改 P-028 归档文档
