---
id: arc-ci-heavy-fixes-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-ci-heavy-fixes-RESEARCH]
upstream: null
---

# 设计：heavy 两例根因修复（P-134 实施批）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **变更面**：3 个产品文件 + 2 个测试文件；不改 workflow、不改 heavy 标记、不改 `ci_exclusions.yaml`。
> **承接**：[P-133 DESIGN](../arc-ci-heavy-rootcause/DESIGN.md) §4。

---

## 1. 目标与非目标

**目标**

1. HITL 响应文件读写两侧都具备原子性/容错性，空读不再丢人工决策。
2. 租约续约与接管共用同一互斥，fencing 单调性在任何交错下成立。
3. 两条修复都有确定性回归用例。

**非目标**

- 不把 `waiting.json`、copilot feedback 一并改造（P-133 U-3）。
- 不移出 `heavy`（P-133 U-4）。
- 不改 `response.json` / `lease.json` 的文件名与字段。

## 2. 决策

| 决策 | 内容 | 依据 |
|---|---|---|
| D-1 | F-1 采纳 P-133 方案 A：`atomic_write_text`（tmp + fsync + `os.replace`） | P-133 DESIGN D-2；RESEARCH §4.1 |
| D-2 | `write_response` 与 `ws_adapter._write_response` 共用 `atomic_write_text` | 两处写者同缺陷 |
| D-3 | 读方空/半截内容视为 not-ready，不删副本；仅签名稳定 5 次才清理 | RESEARCH §4.2 |
| D-4 | F-2 采纳 P-133 方案 A：抽出 `_lease_lock`，`acquire`/`renew` 共用 | P-133 DESIGN D-3；RESEARCH §4.3 |
| D-5 | `renew` 锁内校验 `owner + fencing`；`LeaseBusy` → `LeaseLost` | 保持 keeper 语义 |
| D-6 | 新增 6 个确定性用例；两条 heavy 用例原样保留 marker | RESEARCH §3 |

## 3. 验收不变式

| 编号 | 不变式 | 可观测读数 |
|---|---|---|
| J-1 | 空读不再导致响应丢失 | `test_poll_recovers_after_empty_read` 返回 REJECT；空文件在重试期间不被删除 |
| J-2 | 接管后 fencing 不回滚 | `test_renew_after_takeover_raises`；1000 次压测零失败 |
| J-3 | 同 owner 正常续约 | `test_renew_same_owner_keeps_fencing` |
| J-4 | 两例可重复通过 | 1000 次循环 F-1/F-2 均 0 失败；四矩阵由 PR run 观察 |
| J-5 | 外部契约零变更 | 文件名/字段不变；`ci_exclusions.yaml` diff 为空 |

## 4. 目标形态（已落地）

### 4.1 原子写

```python
def atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_name("%s.tmp.%d" % (path.name, os.getpid()))
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        ...
```

### 4.2 读方签名重试

```python
except (json.JSONDecodeError, KeyError, ValueError) as exc:
    signature = (stat.st_size, stat.st_mtime_ns)
    if signature == last_error_signature:
        consecutive_errors += 1
    else:
        consecutive_errors = 1
        last_error_signature = signature
    if consecutive_errors >= 5:
        unlink()  # 持久损坏才清理
        break
```

### 4.3 锁内续约

```python
with _lease_lock(run_dir, lease.owner, ttl=ttl, now=now):
    current = read_lease(run_dir)
    if current is None or current.owner != lease.owner \
       or current.fencing != lease.fencing:
        raise LeaseLost(...)
    _write(run_dir, updated)
```

## 5. 不采用形态

- **只改写侧**：读方仍会删除真正损坏的文件，且无法区分“未就绪”与“损坏”。
- **只改读侧**：仍会解析半截内容；写侧非原子窗口未消除。
- **renew 改用 acquire**：会 bump fencing，语义错误。
- **测试改用 `sleep` 加长**：不可证伪，且掩盖产品缺陷。

## 6. 风险与回退

| 风险 | 缓解 | 回退 |
|---|---|---|
| `os.replace` 跨盘失败 | tmp 与目标同目录 | 回退为直接写 + 读方容忍 |
| 锁内续约增加 IO | 锁持有仅一次读+一次写；续约频率 TTL/3 | 回退到无锁版（不推荐） |
| 持久损坏文件残留 | 签名连续 5 次不变即清理并告警 | 单点还原即时 unlink |
| 压测仅本机 Windows | PR run 四矩阵观察 | 保留 heavy 标记 |

## 7. 后续接口

- **P-135（建议）**：满足 U-1 后移出 heavy，更新 `tests/ci_exclusions.yaml` 与 marker。
- **U-3 审计**：`waiting.json` / copilot feedback 的原子写。

## 8. 验收对齐

实施读数见 [IMPLEMENTATION.md](./IMPLEMENTATION.md)；验收项见 [CHECKLIST.md](./CHECKLIST.md)（v1.0 / accepted）。
