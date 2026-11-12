---
id: arc-g3-fix-batch-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-12
depends: [arc-g3-m1-artifacts-DESIGN, arc-g3-m2-stage-events-DESIGN]
upstream: arc-g3-m2-stage-events-DESIGN
---

# 调研文档：G3 M1/M2 修复批（P-080）

> **Feature**：P-080，修复 P-077 遗留 **D-1**（并发注册丢节点）与 P-079 登记的 **O-1..O-4**；同时复验 **D-3**。
> **Spec 步骤**：Step 1-2。

## 1. 调研目标

1. **D-1/D-3 的真实性**：P-077 的两项缺陷在当前代码上能否复现？复现条件是什么？
2. **并发修复的形态**：文件锁、`O_APPEND` 原子追加、append-only 重构，哪一个与既有原子写/幂等语义兼容且不引入新依赖？
3. **O-1/O-2 的最小修法**：读侧 torn tail 语义如何与 `EventLog` 对齐而不放弃 fail-closed？

## 2. 调研方法

| 通道 | 用途 | 结果 |
|---|---|---|
| 仓内 barrier 探针（E2） | D-1 精确复现（150 轮独立 run） | ✅ 150/150 丢节点、40 轮 `PermissionError` |
| 仓内顺序探针（E2） | D-3 复验（stage-01/stage-03 同内容） | ✅ 不复现：两节点 id 不同、均保留 |
| `WebSearch` + POSIX 原文 | `O_APPEND` 原子性边界 | ✅ opengroup write() 原文 |
| `WebFetch`（docs.python.org） | `msvcrt.locking` 语义 | ✅ 取到 `LK_LOCK/LK_NBLCK/LK_UNLCK` 与 1s×10 重试 |
| `WebSearch`（Nix 官方手册） | 节点身份是否应含生产者 | ✅ input-addressing 原文 |
| 读码 | 注册/追加/读侧实现 | ✅ E1 |

> 本轮未触发降级链：学术检索未使用（本批为工程修复，无方法学结论需求）；所有外部断言均为标准/官方文档（T1）。

## 3. 调研发现

### 3.1 D-1 真实，且比 P-077 描述更严重

探针：两个线程 `Barrier` 同步后各调用一次 `register_stage_artifacts`（stage 1 / stage 2），独立 run 目录重复 150 轮。

| 读数 | 值 |
|---|---|
| 丢节点轮次 | **150 / 150** |
| 抛异常轮次 | **40 / 150**（`PermissionError(13)`，`os.replace` 与另一线程读文件冲突） |

- 根因与 P-077 一致：`load_nodes → merge → _atomic_write` 是无锁 read-modify-write，后写者覆盖前写者。
- 新增事实：除「覆盖」外还有「异常」形态——runner 的 `except → warning` 会把它变成**更彻底的静默丢节点**。
- P-077 称「双线程注册后 nodes=1」在多轮循环探针中会自愈；用 barrier + 单次注册才能稳定复现，本批探针已修正该构造。

### 3.2 D-3 不成立（撤回）

探针：stage-01 与 stage-03 各写一个内容相同的 `same.txt`，分别注册。

| 读数 | 值 |
|---|---|
| stage-01 节点 | `an-78a2b20859459cd4` |
| stage-03 节点 | `an-3c83fd23f130c2ff` |
| 持久化节点数 | 2（均保留） |

原因：`node_id = sha256({type, locator, content_hash})`，而 `locator` 已含 `stage-NN/` 前缀，跨 stage 天然不同 id。P-077 的 D-3 探针应是在同一 locator 或同一 stage 下构造，结论不成立。**本批撤回 D-3**，不改 `node_id` 公式。

### 3.3 O-1 / O-2 真实

- O-1：`load_stage_events` 仅容忍**最后一行**损坏；`EventLog.read_all` 对 active segment 容忍任意尾坏行。崩溃恢复语义不一致。
- O-2：`evaluate_loop(window=0)` 与 `window=-5` 均直接 `pause`（`consecutive >= window` 恒真）。
- O-3：`append_stage_event` 的 `seq = last + 1` 与写入之间无互斥；P-079 X-2 的零丢失是 GIL/单次写运气，非契约。

### 3.4 外部决策锚点

#### S-1 POSIX `write()`（T1，opengroup）

- **原文**：若设置 `O_APPEND`，每次写前把偏移置为文件末尾，且「changing the file offset and the write operation」之间不允许插入其它文件修改操作。
- **边界**：这只保证「偏移调整 + 写」原子，不保证多进程写入大块数据时整行不交错；普通文件无 `PIPE_BUF` 级保证。
- **结论**：`O_APPEND` 可降低交错概率，但**不能替代锁**来保证 `seq` 唯一；本批用锁。

#### S-2 CPython `msvcrt.locking`（T1，官方文档）

- `LK_LOCK`：拿不到锁每 1 s 重试，10 次后 `OSError`；`LK_NBLCK`：立即 `OSError`；`LK_UNLCK` 解锁。
- **结论**：Windows 用 `LK_NBLCK` + 自建轮询可实现与 POSIX `flock(LOCK_NB)` 一致的「带超时阻塞」语义。

#### S-3 Nix input-addressing（T1，官方手册）

- **原文**：input-addressed 输出的 store path 是**产生它的 derivation** 的函数；即使两个路径内容相同，生产方式不同则路径不同，且「guaranteed to not be the same」。
- **结论**：血缘节点的身份**本应**含生产者维度。本仓 `locator` 已含 stage 前缀，等价实现了该维度——这既解释了 D-3 不成立，也说明无需把 `producer` 再塞进 `node_id`（避免重复编码）。

#### S-4 nullprogram「Appending to a File from Multiple Processes」（T3）

- 多进程 `O_APPEND` 追加在实践中安全，但作者同时指出依赖单次写与平台实现。
- **结论**：仅作 T3 佐证，不与 S-1 并列作 A 类断言；本批仍以锁为准。

## 4. 综合分析

### 4.1 关键发现

1. D-1 真实且高发（100% 丢节点）；修复必须覆盖「覆盖」与「异常」两种形态。[E2]
2. D-3 不成立，撤回；`node_id` 公式保持不变。[E2 + S-3]
3. 锁是唯一能同时保证「不丢节点」与「`seq` 唯一」的形态；`O_APPEND` 不足（S-1/S-4）。[T1]
4. 跨平台锁可用 `msvcrt.LK_NBLCK` + `fcntl.LOCK_NB` 轮询，无新依赖（stdlib）。[T1/S-2]
5. O-1 应对齐为「尾部连续坏行全部丢弃，其前任何坏行 fail-closed」——既保留 DR-3 的 fail-closed 取向，又与崩溃多行半写现实兼容。

### 4.2 研究空白

- 仓内无跨平台文件锁工具；M1 注册与 M2 事件追加各自为政。
- 读侧与替换（`os.replace`）之间的瞬时共享冲突（Windows）未被任何锁保护。

## 5. 幻觉抑制审查（Step 2 Review）

| 引用 | ID | 验证方式 | 状态 |
|---|---|---|---|
| POSIX write() | opengroup 2016 edition | 原文片段逐字 | ✅ 已验证（T1） |
| CPython msvcrt | docs.python.org/3/library/msvcrt.html | 原文取到 | ✅ 已验证（T1） |
| Nix input-addressing | releases.nixos.org 2.34 manual | 原文片段逐字 | ✅ 已验证（T1） |
| nullprogram | nullprogram.com/blog/2016/08/03 | 摘录 | ✅ 存在（T3，仅佐证） |

- 无未验证断言进入设计；D-3 撤回基于本仓 E2 探针而非外部来源。

## 6. 对设计的输入

### 6.1 可用方案

1. `exclusive_lock(path, timeout)`：非阻塞轮询（20 ms 间隔），超时抛 `LockTimeout`。
2. 注册全程持锁；`_atomic_write` 的 `os.replace` 增加 3 次短重试（Windows 瞬时共享冲突）。
3. 事件追加持锁内算 `seq` 与 `attempt`。
4. 读侧尾部连续坏行容忍。
5. `evaluate_loop` 拒绝 `window < 1`。

### 6.2 约束

- 不新增三方依赖（stdlib only）。
- 不改变 `nodes.jsonl` 字段集与 `node_id` 公式。
- 注册/追加失败仍不阻断 run（runner 侧策略不变）。
- 锁文件不得污染 stage 产物（放 `run_dir/.locks/`）。

### 6.3 风险

- 锁超时（默认 30 s）在极端 IO 拥塞下可能触发；失败语义仍为 warning，不阻断。
- Windows `msvcrt.locking` 解锁必须同偏移，实现需每次 `lseek(0)`。
- 读侧（`load_nodes`）与替换的冲突未加读锁；用重试缓解，登记为残余。

### 6.4 未决项登记（四元块）

- **U-1 读-写瞬时冲突**
  - **判据**：并发 `load_nodes` 与 `os.replace` 1000 轮零 `PermissionError`
  - **触发条件**：出现真实并发读（verify 与 run 同时）需求
  - **当前倾向**：3 次短重试；不加读锁
  - **证据等级**：E2（D-1 探针 40 轮异常）

- **U-2 无 id 结果集兜底（P-079 O-4）**
  - **判据**：`row_ids_digest` 在 id 缺失时仍能区分内容
  - **触发条件**：M3 落地 Stage 5 `screen_meta.json`（U-2 of M2）
  - **当前倾向**：保持现状，由上游补稳定 id
  - **证据等级**：E2（P-079 X-4）

## 7. 参考文献

- The Open Group. *write() — POSIX.1-2008*. https://pubs.opengroup.org/onlinepubs/9699919799.2016edition/functions/write.html
- Python Software Foundation. *msvcrt — Useful routines from the MS VC++ runtime*. https://docs.python.org/3/library/msvcrt.html
- NixOS. *Input-addressing derivation outputs*（Nix 2.34 manual）.
- nullprogram. *Appending to a File from Multiple Processes*（2016-08-03，T3）.

---

**Review 签字**: 自查（单视角）+ 探针取证 日期: 2026-11-12
