---
id: arc-g3-fix-batch-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-12
depends: [arc-g3-fix-batch-RESEARCH]
upstream: arc-g3-fix-batch-RESEARCH
---

# 设计：G3 M1/M2 修复批（P-080）

> 基于 [RESEARCH.md](RESEARCH.md)。修复对象：D-1（并发注册丢节点）、O-1（torn tail 语义）、O-2（window 下界）、O-3（事件追加互斥）；D-3 撤回。

## 1. 修复矩阵

| ID | 来源 | 级 | 修法 | 验收 |
|---|---|---|---|---|
| FIX-1 | P-077 D-1 | P2 | 新增 `runtime/filelock.py`；注册全程持锁 | 150 轮 barrier 探针 0 丢失 0 异常 |
| FIX-2 | P-077 D-1 派生 | P2 | `_atomic_write` 的 `os.replace` 3 次短重试（Windows 瞬时共享冲突） | 探针零 `PermissionError` |
| FIX-3 | P-079 O-3 | P3 | `append_stage_event` 锁内算 `seq`/`attempt` | 8 线程并发 seq 唯一 |
| FIX-4 | P-079 O-1 | P3 | 读侧尾部**连续**坏行容忍，其前 fail-closed | 双行坏尾通过；中间坏行仍抛 |
| FIX-5 | P-079 O-2 | P3 | `evaluate_loop(window<1)` 抛 `ValueError` | 0/-5 均抛 |
| FIX-6 | P-077 D-3 | — | **撤回**，不改 `node_id` 公式 | 跨 stage 同内容两节点均保留 |

## 2. `runtime/filelock.py`

```python
class LockTimeout(RuntimeError): ...

@contextmanager
def exclusive_lock(path: str | Path, *, timeout: float = 30.0,
                   poll: float = 0.02) -> Iterator[None]: ...
```

- 打开/创建锁文件（`os.O_CREAT | os.O_RDWR`），锁定首字节。
- Windows：`msvcrt.locking(fd, LK_NBLCK, 1)`；POSIX：`fcntl.flock(fd, LOCK_EX | LOCK_NB)`。
- 失败 → `sleep(poll)` 重试至 `timeout`；超时抛 `LockTimeout`（携带路径与超时值）。
- 解锁：Windows 需 `lseek(0)` 后 `LK_UNLCK`；POSIX `LOCK_UN`；`finally` 关闭 fd。
- 锁文件路径约定：`run_dir/.locks/<name>.lock`（由调用方给出完整路径）。

## 3. 接线

| 位置 | 变更 |
|---|---|
| `register_stage_artifacts` | `with exclusive_lock(run_dir / ".locks" / "artifacts.lock")` 包住 load→merge→write |
| `_atomic_write` | `os.replace` 失败重试 3 次（间隔 10 ms），仍失败才抛 |
| `append_stage_event` | `attempt: int | None = None`；锁内重算 `seq` 与（缺省时）`attempt` |
| `record_stage_progress` | 不再预计算 attempt，交由 `append_stage_event` |
| `load_stage_events` | 尾部连续坏行丢弃；首个可解析行之前的坏行抛 `StageEventError` |
| `evaluate_loop` | `window < 1` → `ValueError` |

## 4. 关键决策与被拒绝方案

| # | 决策 | 被拒绝方案 | 拒绝理由 | 代价 |
|---|---|---|---|---|
| D-1 | 跨平台 advisory 文件锁 | (a) `threading.Lock`；(b) 仅 `O_APPEND` 追加；(c) 引入 `portalocker`/`filelock` | (a) 不跨进程，而 run 目录可被 CLI 与 server 同时持有；(b) 只解决交错，不解决 read-modify-write 覆盖与 `seq` 唯一（RESEARCH S-1）；(c) 新增依赖，违反 stdlib-only 约束 | 锁超时策略需自管；锁文件需清理策略（见 §6） |
| D-2 | 锁粒度 = 每文件一把 | 单 run 全局锁 | 注册与事件追加互不阻塞，减少长 Stage 期间的等待 | 两个锁文件 |
| D-3 | `os.replace` 短重试 | 加读锁 | 读锁会把 `verify_tree` 也拖入锁协议，改动面大；重试对瞬时冲突足够 | 极端并发下仍可能失败（U-1） |
| D-4 | 尾部**连续**坏行容忍 | (a) 仅单行容忍；(b) 任意坏行跳过 | (a) 与 `EventLog` 语义不一致（O-1）；(b) 放弃 fail-closed，中间损坏不可见 | 多行损坏被当作崩溃恢复，需在报告中声明 |
| D-5 | `window<1` 抛错 | clamp 到 1 / 回退默认 3 | 静默修正会掩盖调用错误；抛错在 runner 侧被 catch 成 warning，不会中断 run | 调用方需保证合法 |
| D-6 | D-3 撤回、不改 `node_id` | 纳入 `producer.stage` | locator 已含 stage（RESEARCH S-3 等价语义）；改公式会破坏 content-addressed 与既有节点 id | 无 |

## 5. 不变式

- I-1 `nodes.jsonl` 字段集、`node_id` 公式、去重语义不变。
- I-2 加锁只增加互斥，不改变单写者路径的行为（幂等/跳过缺文件保持）。
- I-3 读侧 fail-closed 取向保持：仅**尾部连续**坏行被容忍。
- I-4 锁失败/超时仍走 runner 的 warning 路径，不阻断 run。
- I-5 不新增三方依赖；`msvcrt`/`fcntl` 按平台懒加载。

## 6. 边界与残余风险

- **职责外**：分布式锁（跨主机）、读-写锁、多 run 并发治理（G7）。
- **能力边界**：advisory 锁只约束遵守协议的写者；绕过协议的第三方写入不受保护。
- 锁文件残留（`.locks/*.lock`）不影响正确性，仅占 0 字节；不纳入产物注册。
- `os.replace` 重试后仍失败 → 该 stage 注册整体失败（warning），与修复前同语义。

## 7. 验收映射

| 批次 | 验收 ID | 证据 |
|---|---|---|
| P-080 | FIX-1 | barrier 探针 150 轮；`test_register_concurrent_threads_no_loss` |
| P-080 | FIX-2 | 探针零 `PermissionError` |
| P-080 | FIX-3 | `test_stage_events_concurrent_append_unique_seq` |
| P-080 | FIX-4 | `test_load_tolerates_multiple_torn_tail_lines` + 中间坏行回归 |
| P-080 | FIX-5 | `test_evaluate_loop_rejects_non_positive_window` |
| P-080 | FIX-6 | `test_cross_stage_same_content_keeps_both_nodes` |

## 8. 派生需求

| ID | 需求 | 来源 |
|---|---|---|
| DR-1 | 锁超时默认 30 s、轮询 20 ms | 经验值（无公开阈值）；锁内仅本地 IO |
| DR-2 | `os.replace` 重试 3×10 ms | Windows 瞬时共享冲突；D-1 探针 40 轮异常 |
| DR-3 | 锁目录 `.locks/` | 不污染 stage 产物目录 |
