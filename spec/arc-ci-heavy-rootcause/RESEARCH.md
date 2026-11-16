---
id: arc-ci-heavy-rootcause-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-ci-flaky-heavy-DESIGN, arc-ci-flaky-heavy-RESEARCH]
upstream: null
---

# 调研：heavy 两例时序 flaky 的根因（P-133 调研批）

> **Feature**：P-133。承接 arc-ci-flaky-heavy 的 U-1（根因专项），对已被 `heavy` marker 隔离的两例做代码级根因定位。
> **Spec 步骤**：Step 1-2（调研批）。
> **结论先行**：两例都不是“测试慢”，而是**测试暴露的真实并发缺陷**——
> ① F-1 = HITL 文件 IPC 的**非原子写 + 读方删除唯一副本**：写者 `write_text` 先 truncate，读方在解析失败时 `unlink`，一次空文件读取即可丢掉人工响应，最终走 5s 超时返回 `ABORT`（CI 日志逐字可见 `attempt 1/5`，排除“连续 5 次坏文件”路径）。
> ② F-2 = 租约续期的**无锁丢失更新**：`renew` 不加 `lease.lock`，可把并发 `acquire` 写入的 `fencing=2` 用过期读结果覆盖回 `fencing=1`，随后续约成功、`LeaseLost` 永不触发；确定性交错复现已复现该回滚。
> 本批只落档根因与修复方向，零代码、零测试、零 workflow 变更；实施建议单列 P-134。

## 1. 调研目标

1. 用一手证据回答“F-1 为什么从 REJECT 变成 ABORT”，而不是停在“时序竞争”。
2. 用代码级交错回答“F-2 为什么 `on_lost` 没有触发”。
3. 判断两例是**测试设计缺陷**还是**产品缺陷**，给出严重度与修复方向。
4. 给 P-134 提供可证伪的验收口径，不夹带实施。

## 2. 方法与证据来源

| 通道 | 用途 | 结果 |
|---|---|---|
| 仓内读码（E1） | `file_wait.py` / `ws_adapter.py` / `lease.py` / 两条测试 | ✅ |
| CI 失败日志（E1） | run `43718585981` job `132825377408`（Tests 3.14） | ✅ 取得 F-1 完整日志 |
| 历史登记（T3） | P-123/P-125 的失败记录与断言原文 | ✅ |
| 确定性交错复现（E1） | 临时目录内模拟 F-2 的 read-modify-write 交错 | ✅ 复现 fencing 回滚 |

**降级链记录（SPEC_PROCESS 反模式③）**：

1. P-123 记录的 F-2 失败 run `43715205467` 已被 rerun 覆盖，attempt 1 的失败 job 不再可读 → 改用 P-123 存档的断言原文（`keeper 必须在租约丢失时回调`）作为 T3 证据，并另做确定性交错复现补强。
2. F-1 的另一次失败 run `43714077075` 的失败 job 同样被 rerun 覆盖 → 本批只以仍可读的 `43718585981` 为逐字日志来源，并在 §8 标注样本量。

## 3. F-1：HITL 响应文件的非原子发布

### 3.1 测试与失败读数

[test_hitl_advanced.py](../../tests/test_hitl_advanced.py#L73-L88)：子线程 `sleep(0.3)` 后写 `REJECT`，主线程 `poll_interval_sec=0.1`、`timeout_sec=5`。

CI 日志逐字（[run 43718585981 job 132825377408](https://github.com/StormstoutLau/AutoResearchClaw/actions/runs/43718585981/job/132825377408)）：

```
WARNING researchclaw.hitl.file_wait:file_wait.py:103 Invalid response file (attempt 1/5): Expecting value: line 1 column 1 (char 0)
WARNING researchclaw.hitl.file_wait:file_wait.py:117 HITL poll timeout after 5s
E AssertionError: assert <HumanAction.ABORT: 'abort'> == <HumanAction.REJECT: 'reject'>
```

### 3.2 生产者：非原子写

[write_response](../../researchclaw/hitl/file_wait.py#L43-L50) 使用 `Path.write_text`：先以 truncate 模式打开，再写入并在关闭时 flush。读方可在“已 truncate、未写入/未 flush”的窗口看到 **0 字节文件**。

同一缺陷存在于 [ws_adapter._write_response](../../researchclaw/hitl/adapters/ws_adapter.py#L437-L449)，因此不是测试辅助函数独有。

### 3.3 消费者：一次坏读即删掉唯一副本

[poll_for_response](../../researchclaw/hitl/file_wait.py#L87-L120) 的异常分支：

```python
except (json.JSONDecodeError, KeyError, ValueError) as exc:
    consecutive_errors += 1
    ...
    response_path.unlink(missing_ok=True)
```

关键不是计数，而是 `unlink`：一旦读到空文件，**唯一副本被删除**，后续轮询只会得到 `FileNotFoundError`，语义从“稍后重试”退化为“永久丢失”。

### 3.4 失败路径判定

- 日志显示 `attempt 1/5` 后直接出现 `HITL poll timeout after 5s`，排除“连续 5 次坏文件 → 提前 break”。
- 返回的 `ABORT` 来自超时分支（`message="timeout — no response"`），不是解析错误分支本身的返回值。
- 因此链条为：**空读 → unlink → 一直 FileNotFound → 5s 到期 → ABORT**。

### 3.5 影响面

- 生产默认 `DEFAULT_TIMEOUT_SEC = 86400`（24 小时）；一次撞窗会让流水线在人工已提交决策后仍以 `ABORT` 结束。
- 任何走 `response.json` 的外部写者（CLI/WS/attach）都可能撞窗；WS 适配器已有同样的非原子写。

## 4. F-2：租约续期的无锁丢失更新

### 4.1 测试与失败读数

[test_supervisor.py](../../tests/test_supervisor.py#L105-L116)：`interval=0.02`，接管后 `sleep(0.15)`，断言 `on_lost` 被调用。P-123 存档的失败断言为 `AssertionError: keeper 必须在租约丢失时回调`（`tests/test_supervisor.py:113`）。

### 4.2 互斥是非对称的

- [acquire](../../researchclaw/runtime/lease.py#L115-L174) 通过 `lease.lock`（`O_CREAT|O_EXCL`）串行化写入。
- [renew](../../researchclaw/runtime/lease.py#L177-L196) **完全不碰锁**：`read_lease` → 构造新 `Lease` → `_write`。

### 4.3 丢失更新交错

```
keeper: current = read_lease()            # me:1, fencing=1
other : acquire(now=+1h) -> _write        # other:2, fencing=2
keeper: _write(updated_from_stale_read)   # me:1, fencing=1  ← 覆盖
keeper: 下一次 renew 看到 owner/fencing 与自己一致 → 成功
```

确定性复现（临时目录，未改仓）：

```text
after_stale_write owner=me:1 fencing=1
renew_after_takeover=SUCCEEDED owner=me:1 fencing=1
```

第二行即缺陷本体：接管已发生，`renew` 本应 `LeaseLost`，实际成功并把 fencing 回滚。

### 4.4 后果

- 破坏 `lease.py` 头注释声明的「different owner increments fencing / writers reject lower token」不变量。
- 旧 owner 可继续自认持有租约，形成双写者窗口；这比测试红灯严重。
- 窗口宽度 = `read_lease` 到 `_write` 完成之间的时间（含 `fsync`），CI 慢盘会放大碰撞概率。

### 4.5 次因：测试的墙钟假设

[LeaseKeeper._loop](../../researchclaw/runtime/lease.py#L291-L301) 用 `self._stop.wait(self.interval)`；若线程启动或调度延迟超过 150ms，`stop()` 先置位，第一次 tick 不执行，`renew` 从未运行，`on_lost` 自然不触发。测试没有事件同步，也没有有界重试。

## 5. 共性判断

- 两例都是「**墙钟 sleep + 无同步线程**」的测试写法暴露出的 IPC/租约原子性缺陷；`heavy` marker 只是隔离噪声，不是治愈（P-125 已在诚实边界中声明）。
- 矩阵落点漂移（3.11/3.12/3.13/3.14 均出现过 F-1）与文件系统/调度差异一致：窗口越宽越容易撞上，不是某个 Python 版本特有。
- 两例的严重度不同：F-2 涉及 fencing 单调性与双写者风险，F-1 涉及人工决策被静默丢弃并触发 24h 级超时。

## 6. 修复方向比较

### 6.1 F-1

| 方案 | 做法 | 判断 |
|---|---|---|
| A（推荐） | 写侧 `tmp + os.replace` 原子发布（`write_response` 与 `ws_adapter` 两处）；读侧把空/解析失败视为 not-ready，不删文件、重置错误计数 | 同时消除“空读”与“删副本”；可证伪 |
| B | 只改写侧为原子发布 | 能消除空读，但读侧仍会在真正的损坏文件上删副本；防御纵深不足 |
| C | 只改读侧为“不删、重试” | 可恢复本竞态，但读方仍会解析到半截内容；Windows 上删除打开文件的行为差异仍在 |
| D | 写侧加文件锁 | 引入跨平台锁语义，成本高；`os.replace` 已足够 |

### 6.2 F-2

| 方案 | 做法 | 判断 |
|---|---|---|
| A（推荐） | `renew` 与 `acquire` 共用 `lease.lock`，锁内重读并校验 `owner + fencing`；拒绝降低 fencing 的写入；`LeaseBusy` 映射为 `LeaseLost` | 直接消除丢失更新，保持 fencing 单调 |
| B | 无锁 CAS：写临时文件后重读校验 fencing，冲突重试 | 可实现，但重试逻辑与锁等价且更难证伪 |
| C | 只改测试（事件等待/重试） | 掩盖双写者缺陷，不可接受 |
| D | keeper 改用 `acquire(owner=...)` | 语义不同（可能 bump fencing），且 `LeaseBusy` 需重新映射；不如专用 `renew` 清晰 |

## 7. 未决项

| ID | 内容 | 判据 | 触发条件 | 当前倾向 | 证据等级 |
|---|---|---|---|---|---|
| U-1 | F-2 在生产的实际碰撞概率 | keeper 默认 `interval=max(1.0, ttl/3)`、窗口含 fsync | P-134 压测 | 低但后果高，按缺陷修 | E1 机制证明 |
| U-2 | `renew` 是否还应校验 `released` 与过期 | 锁内重读后的一致性规则 | P-134 设计 | 校验 released；过期由 fencing 接管处理 | E1 |
| U-3 | 其余文件 IPC（`waiting.json`、copilot feedback 两文件）是否统一原子写 | 是否存在“读方删除/半截解析” | P-134 顺带审计 | `waiting.json` 非原子但无删副本；copilot 读方不删，风险低 | E1 |
| U-4 | 修复后何时移出 heavy | 连续 N 次（建议 10）CI 全绿 + 压测 1000 次 | P-134 验收后 | 先保留标记观察两个窗口再移出 | E1 |
| U-5 | Windows 与 POSIX 删除打开文件的差异是否影响可观测性 | 平台行为对照 | 复现需跨平台 | 仅解释矩阵漂移，不作为修法依据 | E1 推论 |

## 8. 诚实边界

- 本批零代码、零测试、零 workflow 变更；所有结论来自读码、仍可读的 CI 日志与确定性交错复现。
- F-1 只有一份仍可读的逐字失败日志（另一份被 rerun 覆盖）；不据此宣称失败率。
- F-2 的复现是**机制级**证明（用 `_write` 模拟过期读结果落盘），不是端到端概率测量；概率需 P-134 压测。
- 未做跨平台复现；Windows/POSIX 差异仅作为矩阵漂移的解释性假设（U-5）。
