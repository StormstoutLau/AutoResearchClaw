---
id: arc-heavy-followups-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-ci-heavy-fixes-RESEARCH, arc-ci-heavy-rootcause-DESIGN]
upstream: null
---

# 调研：heavy 修复后的两项邻近缺陷（P-136）

> **Feature**：P-136。承接 P-133 U-3（文件 IPC 原子性审计）与 U-2（`renew` 的 released 校验），只做调研，不实施。
> **Spec 步骤**：Step 1-2（调研批）。
> **结论先行**：① **U-3 风险低但有两个具体缺口**——`waiting.json` 仍非原子；copilot feedback 读方存在 `exists()` → `read_text()` 的 TOCTOU，且该异常未被捕获。② **U-2 是真缺陷**——`renew` 不校验 `current.released`，实测「release 后续约」会成功并把 `released` 复活为 `False`；正常 `_runtime_end` 先停 keeper 再 release，但 `atexit` 路径没有停 keeper，存在真实交错。两项修复均押后到观察窗口 2 之后合并。

## 1. 调研目标

1. 把 U-3 从「同类缺陷」细化为**具体文件、具体读方、具体风险**。
2. 用可复现读数确认 U-2 的 released 复活路径。
3. 给出后续实施批的修复方案与验收口径。

## 2. U-3：文件 IPC 清单（E1）

| 文件 | 写方 | 原子性 | 读方 | 读方容错 | 风险 |
|---|---|---|---|---|---|
| `response.json` | `write_response` / `ws_adapter._write_response` | ✅ P-134 原子发布 | `poll_for_response` | ✅ 空读不删、签名重试 | 已修 |
| `waiting.json` | `write_waiting`（[file_wait.py](../../researchclaw/hitl/file_wait.py#L54-L61)） | ❌ `path.write_text` | `ws_adapter._read_json`（[L425-L436](../../researchclaw/hitl/adapters/ws_adapter.py#L425-L436)） | 解析失败返回 `None`，不删 | 低：一次 UI 状态闪烁，下一次轮询自愈 |
| `copilot_feedback_request.json` | `write_feedback_request`（[feedback.py](../../researchclaw/copilot/feedback.py#L45-L67)） | ❌ `write_text` | 外部 UI/CLI | 不在本仓 | 低：请求不可读时 UI 不展示，无数据丢失 |
| `copilot_feedback_response.json` | 外部 UI/CLI | 外部 | `read_feedback_response`（[L69-L95](../../researchclaw/copilot/feedback.py#L69-L95)） | 解析失败返回 `None`；但 `exists()` 与 `read_text()` 之间无捕获 `FileNotFoundError` | 低-中：TOCTOU 可让 `wait_for_feedback` 直接抛异常 |

**关键读数**：

- `waiting.json` 的读方在解析失败时只记 warning 并返回 `None`，不会删除文件；因此不会像 F-1 那样丢决策，只是短暂不可见。
- `read_feedback_response` 的 `exists()` 检查是 TOCTOU：文件在两次调用之间被删除时，`read_text` 抛 `FileNotFoundError`，而异常列表只捕获 `(json.JSONDecodeError, TypeError, ValueError)`。

## 3. U-2：released 复活路径（E1）

`renew`（[lease.py](../../researchclaw/runtime/lease.py#L193-L217)）只校验 `owner + fencing`，不校验 `current.released`。

确定性复现（临时目录）：

```text
after_release released=True
renew_after_release=SUCCEEDED released=False
```

即：已释放的租约可以被下一次 `renew` 重新变为「未释放」，并延长 `expires_at`。

**真实交错路径**：

1. `_runtime_end` 正常路径先 `keeper.stop()` 再 `release()`（[runner.py](../../researchclaw/pipeline/runner.py#L285-L296)），安全。
2. 但 `atexit.register(_atexit_release, run_dir, lease)`（[runner.py](../../researchclaw/pipeline/runner.py#L267)）只调用 `release()`，**不会停 keeper**；若进程异常退出，keeper 线程仍可能在下一次 tick 执行 `renew`，命中上述复活路径。
3. `supervisor` 对死 PID 的陈旧租约也会 `release()`；若原进程的 keeper 尚存活，同样可能复活。

## 4. 外部锚点

| 来源 | 结论 | 等级 |
|---|---|---|
| P-134 原子发布先例 | 同目录 tmp + `os.replace` 是本仓已验证的 IPC 写法 | E1 |
| `released` 作为终态 | 释放是单向状态迁移；终态不应被普通续约逆转（幂等/状态机原则） | T2（通用设计原则） |
| CWE-367 TOCTOU | `exists()` 后 `read` 的检查-使用竞态应按「直接读 + 捕获缺失」处理 | T2 |
| P-133 U-2/U-3 | 两项均由根因调研显式登记 | E1 |

## 5. 修复方向（供后续批）

### 5.1 U-3

| 方案 | 做法 | 判断 |
|---|---|---|
| **A（推荐）** | `write_waiting` 改用 `atomic_write_text`；`read_feedback_response` 去掉 `exists()` 预检并捕获 `FileNotFoundError` | 低成本、消除两个具体缺口 |
| B | 只改 `write_waiting` | TOCTOU 仍在 |
| C | 全部 IPC 加锁 | 过度设计 |

### 5.2 U-2

| 方案 | 做法 | 判断 |
|---|---|---|
| **A（推荐）** | `renew` 在锁内同时校验 `current.released`；为 `True` 时抛 `LeaseLost` | 单向状态机，最小改动 |
| B | `release` 负责停止 keeper | 需要跨模块持有 keeper 引用，耦合高 |
| C | `atexit` 先停 keeper 再 release | 只覆盖一条路径，supervisor 路径仍漏 |

## 6. 未决项

| ID | 内容 | 判据 | 触发条件 | 当前倾向 | 证据等级 |
|---|---|---|---|---|---|
| U-1 | U-3 是否需要在同一实现批完成 | 两项改动是否互相依赖 | 后续实施批 | 同一批完成 | E1 |
| U-2 | `renew` 校验 released 是否影响 keeper 正常退出 | 正常路径 keeper 先停 | 实施批测试 | 无影响 | E1 |
| U-3 | 外部 UI 写 `copilot_feedback_response.json` 是否也需要原子写 | 外部实现是否可控 | 若 UI 在本仓 | 不在本仓，读方容错即可 | E1 |
| U-4 | 是否把 released 校验补进 supervisor 的正式租约路径 | supervisor 只处理死 PID | 后续审计 | 否，supervisor 不 renew | E1 |

## 7. 诚实边界

- 本批零代码、零测试、零 workflow；所有结论来自读码与临时目录复现。
- U-3 的 UI 闪烁与 copilot TOCTOU 未做运行时故障注入；风险等级基于读方行为推断。
- U-2 的复活路径已确定性复现；atexit/supervisor 的具体触发概率未量化。
- 按用户裁决，本批与 U-3/U-2 的任何实施都押后到观察窗口 2 之后合并。
