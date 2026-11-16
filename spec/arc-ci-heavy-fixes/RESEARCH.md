---
id: arc-ci-heavy-fixes-RESEARCH
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-ci-heavy-rootcause-DESIGN, arc-ci-heavy-rootcause-RESEARCH]
upstream: null
---

# 调研：heavy 两例根因修复的实施约束（P-134 实施批）

> **Feature**：P-134。承接 P-133 的根因与方案，落地 F-1/F-2 修复。
> **Spec 步骤**：Step 1-2（实施批的研究步）。
> **结论先行**：按 P-133 方案 A 实施——① F-1：新增 `atomic_write_text`（同目录 tmp + `fsync` + `os.replace`），`write_response` 与 `ws_adapter._write_response` 共用；读方把空/半截内容视为 not-ready，不删副本，仅当文件签名（size + mtime_ns）连续 5 次不变时才判为持久损坏并清理。② F-2：抽出 `_lease_lock`，`acquire` 与 `renew` 共用；`renew` 在锁内重读并校验 `owner + fencing`，锁被他人持有（`LeaseBusy`）时映射为 `LeaseLost`。TDD 先红 4 例、后绿 15/15；两例 heavy 压测 1000 次零失败。

## 1. 目标

1. 消除 F-1 的「空读 → 删副本 → 超时 ABORT」链，且不放弃对持久损坏文件的兜底清理。
2. 消除 F-2 的无锁 read-modify-write，保证 `renew` 在任何交错下都不降低 fencing。
3. 修复必须是确定性的、可回归的，不依赖概率。
4. 不改外部契约、不改 heavy 标记与 `tests/ci_exclusions.yaml`。

## 2. 实施前代码事实（E1）

| 编号 | 事实 | 位置 |
|---|---|---|
| E1-1 | `write_response` 用 `Path.write_text`，truncate 后写，非原子 | `researchclaw/hitl/file_wait.py` 改前 L43-L50 |
| E1-2 | `poll_for_response` 在解析异常分支 `unlink` 响应文件 | 同上改前 L101-L110 |
| E1-3 | `ws_adapter._write_response` 同样用 `write_text` | `researchclaw/hitl/adapters/ws_adapter.py` 改前 L437-L449 |
| E1-4 | `acquire` 持 `lease.lock`；`renew` 无锁 read-modify-write | `researchclaw/runtime/lease.py` 改前 L115-L196 |
| E1-5 | 仅 `LeaseKeeper._loop` 调用 `renew` | 同上 L294 |
| E1-6 | F-1/F-2 均已被 `heavy` marker 隔离，`ci_exclusions.yaml` 各一条五字段条目 | `tests/ci_exclusions.yaml` L3-L12 |

## 3. 测试与 TDD 读数

新增 6 个确定性用例（2 个 F-1、4 个 F-2），先对旧实现验红：

| 用例 | 旧实现读数 |
|---|---|
| `test_poll_does_not_delete_partial_response` | FAIL：`assert False = response_path.exists()` |
| `test_poll_recovers_after_empty_read` | FAIL：`ABORT == REJECT` |
| `test_renew_holds_lease_lock` | FAIL：`renew 读取租约时未持锁` |
| `test_renew_maps_busy_lock_to_lease_lost` | FAIL：`DID NOT RAISE LeaseLost` |
| `test_renew_after_takeover_raises` | PASS（回归基线） |
| `test_renew_same_owner_keeps_fencing` | PASS（回归基线） |

**先红合计**：`4 failed, 2 passed in 1.31s`（与预期一致，非假红）。

实现后同一组用例：`15 passed in 1.56s`（含 `TestFileWait` 全部用例与两条 heavy keeper 用例）。heavy 两例单独循环：**N=1000，F-1 0 失败、F-2 0 失败**。

## 4. 关键实现约束

### 4.1 原子发布

- 临时文件必须与目标**同目录**，否则 `os.replace` 可能跨文件系统。
- 写入后 `flush + os.fsync`，再 `os.replace`；`finally` 清理残留 tmp。
- 只改 `response.json` 写者；`waiting.json` 与 copilot feedback 的同类审计仍留在 P-133 U-3。

### 4.2 读方容忍

- `FileNotFoundError` = not-ready，重置错误计数与签名。
- 空/半截/语义非法：记录 `(st_size, st_mtime_ns)`；签名变化则重新计数，签名连续 5 次不变才清理并退出。
- 成功读取后仍保留原有的「消费即删除」。

### 4.3 锁内续约

- `_lease_lock` 完整继承 `acquire` 原有语义：`O_CREAT|O_EXCL`、陈旧锁按 `ttl` 年龄回收、锁内写 owner、`finally` 删除。
- `renew` 在锁内重读；`owner/fencing` 不匹配 → `LeaseLost`；`LeaseBusy` → `LeaseLost`。
- 不改变 `fencing` 生成规则与 `_write` 的 tmp+replace。

## 5. 与 P-133 设计映射

| P-133 决策 | 本批落点 |
|---|---|
| F-1 A：原子发布 + 容忍空读 | §4.1 + §4.2 |
| F-2 A：锁内续约 + 校验 fencing | §4.3 |
| J-1 空读不丢响应 | `test_poll_recovers_after_empty_read` |
| J-2 fencing 不回滚 | `test_renew_after_takeover_raises` + 1000 次压测 |
| J-3 同 owner 正常续约 | `test_renew_same_owner_keeps_fencing` |
| J-4 可重复通过 | 1000 次压测 0 失败 |
| J-5 外部契约不变 | 文件名/字段零变更；`ci_exclusions.yaml` 零改动 |

## 6. 未决项

| ID | 内容 | 判据 | 触发条件 | 当前倾向 | 证据等级 |
|---|---|---|---|---|---|
| U-1 | 何时把两例移出 heavy | 连续 10 次 CI 全绿 | 本批合并后观察两个窗口 | 暂不移出 | E1 |
| U-2 | Windows 下删除打开文件的行为差异是否仍可观测 | 平台对照 | 后续跨平台复现 | 修复后窗口消失，仅作记录 | E1 推论 |
| U-3 | `waiting.json` / copilot feedback 是否统一原子写 | 是否需要同一保证 | P-133 U-3 审计 | 本批不动 | E1 |
| U-4 | 1000 次压测是否进 CI | 默认 CI 时长预算 | 移出 heavy 时 | 先本地压测；移出时再评估 | E1 |

## 7. 诚实边界

- 本批修复的是两处被证实的机制缺陷；不宣称“从此绝不 flaky”，移出 heavy 仍需 U-1 的观察窗口。
- 全量 `-m "not heavy"` 本机回归为 `3670 passed, 108 skipped, 6 failed`；6 个失败均与本批零交集（Keras 3/tf-keras 环境 ×4、Windows WinError 193 ×1、Windows bash 路径 ×1），已逐条登记在 IMPLEMENTATION §4。
- 1000 次压测是本机 Windows 结果；Linux 四矩阵由本批 PR run 观察，不写成已证。
