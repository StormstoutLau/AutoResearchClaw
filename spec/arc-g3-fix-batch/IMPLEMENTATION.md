---
id: arc-g3-fix-batch-IMPLEMENTATION
type: design
version: 1.0
status: in-review
date: 2026-11-12
depends: [arc-g3-fix-batch-DESIGN]
upstream: arc-g3-fix-batch-DESIGN
---

# 实施记录：G3 M1/M2 修复批（P-080）

> **状态**：施工中；接口按 [DESIGN.md](DESIGN.md) §2/§3 冻结，读数在 Step 9-10 回填。

## 1. 改动清单

| # | 文件 | 类型 | 内容 |
|---|---|---|---|
| 1 | `researchclaw/runtime/filelock.py` | 新增 | `LockTimeout`、`exclusive_lock()`（msvcrt/fcntl 双分支） |
| 2 | `researchclaw/evidence/artifact_node.py` | 修改 | 注册全程持锁；`_atomic_write` 的 `os.replace` 短重试 |
| 3 | `researchclaw/runtime/stage_events.py` | 修改 | 追加持锁 + 锁内算 seq/attempt；尾部连续坏行容忍；window 下界校验 |
| 4 | `tests/test_artifact_node.py` | 修改 | 并发注册回归 + 跨 stage 同内容回归（D-3 撤回证据） |
| 5 | `tests/test_stage_events.py` | 修改 | 并发追加、多行坏尾、中间坏行、window 非法 |
| 6 | `tests/test_filelock.py` | 新增 | 互斥、超时、嵌套释放 |
| 7 | `.github/workflows/ci.yml` | 修改 | 固定清单加入新测试文件 |

**不改**：`nodes.jsonl` 字段集、`node_id` 公式、`pipeline_summary` 字段、错误码集合、Stage 4/5 业务逻辑。

## 2. 接口与回退点

| 接口 | 签名 | 回退点 |
|---|---|---|
| `exclusive_lock` | `(path: str \| Path, *, timeout: float = 30.0, poll: float = 0.02) -> Iterator[None]` | 超时抛 `LockTimeout`；`finally` 必解锁 |
| `LockTimeout` | `RuntimeError` 子类 | 调用方决定是否降级 |
| `register_stage_artifacts` | 签名不变 | 锁内 load→merge→write；异常语义不变 |
| `append_stage_event` | `attempt: int \| None = None` | 缺省时锁内按已有事件数 +1 |
| `record_stage_progress` | 签名不变 | 不再预计算 attempt |
| `load_stage_events` | 签名不变 | 尾部连续坏行丢弃；其前坏行抛 `StageEventError` |
| `evaluate_loop` | 签名不变 | `window < 1` → `ValueError` |

## 3. 关键行为

- **锁**：非阻塞原语 + 20 ms 轮询；Windows `LK_NBLCK`/POSIX `LOCK_NB`；解锁前 `lseek(0)`（Windows 语义）。
- **注册**：锁覆盖「读全量 → 计算父边 → 合并去重 → 原子写」；并发下后写者能看到前写者结果。
- **替换重试**：`os.replace` 失败重试 3 次（10 ms），仍失败抛出，由 runner warning 兜底。
- **读侧**：从尾部向前跳过连续不可解析行；首个可解析行之前的任何坏行仍抛错。
- **window**：`< 1` 显式拒绝，避免「恒 pause」。

## 4. 版本与 API 兼容性核验（Step 6）

| 依赖 | 用法 | 下限可用性 | 状态 |
|---|---|---|---|
| `msvcrt.locking` / `LK_NBLCK` / `LK_UNLCK` | Windows 锁 | CPython 全版本 | ✅（3.11+ 文档一致） |
| `fcntl.flock` / `LOCK_NB` | POSIX 锁 | CPython 全版本 | ✅ |
| `os.open` / `os.lseek` / `os.replace` | 锁文件与原子写 | 3.11 全有 | ✅ |
| `contextlib.contextmanager` | 锁上下文 | 3.11 全有 | ✅ |
| 3.12+ stdlib API | 无 | — | ✅ |

## 5. 读数（Step 9-10 回填）

| 项 | 读数 |
|---|---|
| 新增/修改测试 | **+10**（filelock 4、artifact 2、stage_events 4）；四个相关套件合计 **52 passed** |
| 双环境 | 3.13.5 **52 passed**；3.11.15 **52 passed** |
| D-1 探针 | 修复前 **150/150 丢节点、40 轮异常**；修复后 **0 丢失 0 异常**（150 轮 barrier） |
| 跨进程锁探针 | **PASS**（子进程持锁，父进程 0.4 s 超时） |
| 性能 | 200 次注册 **169.8 ms**（本地，含锁与全量重写） |
| 回归 | 7 文件 **109 passed**（含 `test_rc_runner` / `test_event_stream`） |
| 门禁 | DC 6 文件 0 违规；step-gate 5/5；console 一致；repo_stats 一致；rework PASS；pre-commit **9/9 Passed** |
| 红→绿 | 红：`ModuleNotFoundError: filelock`；D-1 并发测试失败、多行坏尾抛错、`window=0` 不抛。绿：52 passed |

## 5.1 测试升级说明

- `test_artifact_node.py` 新增 2 项：并发注册（D-1 回归）、跨 stage 同内容（D-3 撤回证据）。
- `test_stage_events.py` 新增 4 项：多行坏尾、`window` 非法、`attempt` 自动递增、并发追加 seq 唯一。
- `test_filelock.py` 新增 4 项：互斥（20 线程 × 50 次）、超时、异常释放、目录自动创建。
- 既有 30 项 M2 + 13 项 M1 测试零修改零回归。

## 6. 验收边界（诚实口径）

- **D-1**：进程内多线程 + 跨进程 advisory 锁；不承诺抵抗绕过协议的写入。
- **D-3**：撤回，不改 `node_id`；以回归测试固化「跨 stage 同内容两节点均保留」。
- **O-1**：尾部连续坏行容忍是崩溃恢复语义；中间损坏仍 fail-closed。
- **O-4**：不修，保持登记（依赖上游 id 稳定性，M3 落地 `screen_meta` 时一并处理）。
- 读-写瞬时冲突未加读锁，以重试缓解，登记 U-1。
