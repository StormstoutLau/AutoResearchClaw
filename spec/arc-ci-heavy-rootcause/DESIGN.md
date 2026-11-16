---
id: arc-ci-heavy-rootcause-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-ci-heavy-rootcause-RESEARCH]
upstream: null
---

# 设计：heavy 两例根因的修复方案（P-133 调研批产出，供 P-134）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **本批不含实施**：只给修复方案、验收口径与回退，供后续实施批裁决。
> **上游**：[arc-ci-flaky-heavy DESIGN](../arc-ci-flaky-heavy/DESIGN.md) §11.1 U-1。

---

## 1. 目标与非目标

**目标**

1. 让 F-1 的响应文件读取在“空文件/半截文件”出现时可自愈，不丢人工决策。
2. 让 F-2 的续约在任何交错下都不降低 fencing，接管后必定 `LeaseLost`。
3. 两条修复都要有确定性回归用例，不依赖概率。
4. 修复后具备把两例移出 `heavy` 的可证伪条件。

**非目标**

- 本批不改任何代码、测试、workflow 或 `tests/ci_exclusions.yaml`。
- 不做文件 IPC 的全面重构；只处理被证实的缺陷面（另立 U-3 审计项）。
- 不改变 `response.json` / `lease.json` 的外部契约。

## 2. 决策

| 决策 | 内容 | 依据 |
|---|---|---|
| D-1 | 本批零实施；修复由 P-134 执行 | 调研批边界 |
| D-2 | F-1 采纳方案 A：写侧原子发布 + 读侧容忍空读（不删副本、重置错误计数） | RESEARCH §6.1；两处写者都改 |
| D-3 | F-2 采纳方案 A：`renew` 与 `acquire` 共用 `lease.lock`，锁内校验 `owner + fencing` | RESEARCH §6.2 |
| D-4 | 回归用例必须**确定性**：空读后写完整内容可恢复；接管与 renew 交错必 `LeaseLost` | RESEARCH §3.4、§4.3 |
| D-5 | 修复后先保留 `heavy` 标记观察两个窗口，再按 U-4 条件移出 | P-125 的「隔离≠治愈」 |

## 3. 验收不变式（P-134 口径）

| 编号 | 不变式 | 可观测读数 |
|---|---|---|
| J-1 | 响应文件空读不再导致永久丢失 | 构造“先 0 字节、后完整 JSON”的序列，`poll_for_response` 最终返回 REJECT 且文件被消费一次 |
| J-2 | 续约不降低 fencing | 交错用例后 `read_lease().fencing` 恒为接管者的 2；旧 owner 的 `renew` 抛 `LeaseLost` |
| J-3 | 同 owner 正常续约仍成功 | 无接管时 `renew` 返回新 `expires_at`，fencing 不变 |
| J-4 | 两例在默认 CI 下可重复通过 | 单测循环 ≥1000 次零失败；四矩阵全绿 |
| J-5 | 外部契约零变更 | `response.json` / `lease.json` 字段与文件名不变；`tests/ci_exclusions.yaml` 仅在移出时改动 |

## 4. 目标形态（示意，不实施）

### 4.1 F-1 原子发布

```python
def _atomic_write_json(path: Path, payload: str) -> None:
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)          # 同目录原子替换
```

- `write_response` 与 `ws_adapter._write_response` 都改走该函数。
- 读侧：`JSONDecodeError` / 空内容视为 **not-ready**，`continue` 重试；不 `unlink`；错误计数在成功或 `FileNotFoundError` 时重置；仅在“文件存在且内容稳定 N 次仍损坏”时才清理并告警。

### 4.2 F-2 锁内续约

```python
def renew(run_dir, lease, *, ttl=..., now=None):
    with _lease_lock(run_dir):                  # 与 acquire 同一把锁
        current = read_lease(run_dir)
        if current is None or current.owner != lease.owner \
           or current.fencing != lease.fencing:
            raise LeaseLost(...)
        updated = ...                           # expires_at = now + ttl
        _write(run_dir, updated)
        return updated
```

- 锁获取失败（`LeaseBusy`）在续约语义下映射为 `LeaseLost`，由 keeper 触发 `on_lost`。
- `_write` 内保持 `fsync + os.replace`。

### 4.3 测试形态

- F-1：用事件/队列控制“先写空文件、再写完整内容”的顺序，断言最终结果；不再用 `sleep(0.3)`。
- F-2：`on_lost` 写入 `threading.Event`，用 `event.wait(timeout=2)` 代替 `sleep(0.15)`；另加一条直接调用 `renew` 的交错用例。

## 5. 不采用形态

- **只改写侧**：读侧仍会删除真正损坏的文件，防御纵深不足（RESEARCH §6.1 B）。
- **只改读侧**：仍会解析半截内容，Windows 删除打开文件的行为差异未消除（§6.1 C）。
- **只改测试**：掩盖 F-2 的双写者风险（§6.2 C）。
- **keeper 改用 `acquire`**：语义会 bump fencing，且 `LeaseBusy` 映射不自然（§6.2 D）。

## 6. 风险与回退

| 风险 | 缓解 | 回退 |
|---|---|---|
| `os.replace` 在跨文件系统临时目录失败 | 临时文件与目标同目录（`path.with_name`） | 回退为直接写并保留读侧容忍 |
| 锁内 `renew` 增加 IO 延迟 | 续约频率为 TTL/3，锁持有时间仅一次读+一次写 | 回退到无锁版（不推荐，仅应急） |
| 读侧不删损坏文件导致残留 | 稳定损坏 N 次后清理并告警 | 单点还原 unlink 分支 |
| 修复后仍偶发 | J-4 要求 1000 次循环 + 四矩阵 | 保留 heavy 标记，暂不移出 |

## 7. 与后续批次接口

- **P-134（建议）**：按 §4 实施，验收 J-1..J-5。
- **移出 heavy**：满足 U-4 后单独批次修改 `tests/ci_exclusions.yaml` 并移除 marker。
- **U-3 审计**：`waiting.json`、copilot feedback 两文件的原子写可并入 P-134 或单列。

## 8. 验收对齐

本设计对应的调研验收项见 [CHECKLIST.md](./CHECKLIST.md)（v1.0 / accepted）；实施验收 J-1..J-5 是 P-134 的口径，不在本批执行。
