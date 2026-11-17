---
id: arc-heavy-followups-fixes-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-17
depends: [arc-heavy-followups-fixes-DESIGN]
upstream: null
---

# 实施：U-3/U-2 最小修复（P-139）

> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **变更**：3 产品文件 + 3 测试文件；零 workflow、零 heavy marker、零 `ci_exclusions.yaml`。

---

## 1. 变更清单

| 文件 | 改动 | 行数 |
|---|---|---|
| `researchclaw/hitl/file_wait.py` | `write_waiting` 改 `atomic_write_text` | +1/−3 |
| `researchclaw/copilot/feedback.py` | 去掉 `exists()` 预检；新增 `FileNotFoundError` 分支 | +2/−2 |
| `researchclaw/runtime/lease.py` | `renew` 条件加 `current.released` | +6/−1 |
| `tests/test_hitl_advanced.py` | 原子写 spy 用例 | +17 |
| `tests/test_copilot.py` | 文件消失用例 | +12 |
| `tests/test_lease.py` | released 复活 + 正常续约用例 | +17 |

产品代码合计 +9/−6；测试 +46。批外 vendor CRLF 未纳入。

## 2. TDD 读数

**先红**（实现前）：

```text
FAILED test_write_waiting_uses_atomic_publish - assert [] == [waiting.json]
FAILED test_read_feedback_response_handles_disappearing_file - FileNotFoundError
FAILED test_renew_after_release_raises_lease_lost - DID NOT RAISE LeaseLost
3 failed, 1 passed in 0.58s
```

**后绿**（实现后）：

```text
4 passed in 0.31s
```

## 3. 回归读数

| 范围 | 读数 |
|---|---|
| 三个相关测试文件 | `96 passed, 1 failed`；失败为 `test_shell_hooks` 的 `[WinError 193]`，Windows 环境性，与本批零交集 |
| 全量 `-m "not heavy"` | `3674 passed, 108 skipped, 6 failed`；6 个失败与 P-134 同一组环境性（Keras3/tf-keras ×4、WinError 193 ×1、bash 路径 ×1） |
| 新增用例 | 4 条全部通过（其中 3 条先红后绿） |

## 4. 变更细节

### 4.1 waiting.json

```python
atomic_write_text(path, json.dumps(waiting.to_dict(), indent=2))
```

不再先 truncate；读者不会再看到 0 字节文件。

### 4.2 feedback

```python
try:
    data = json.loads(response_path.read_text(encoding="utf-8"))
    ...
except FileNotFoundError:
    return None
```

去掉了 `exists()` 与 `read_text()` 之间的检查-使用窗口。

### 4.3 renew

```python
if (current is None
        or current.released
        or current.owner != lease.owner
        or current.fencing != lease.fencing):
    raise LeaseLost(...)
```

`released` 成为不可被续约逆转的终态。

## 5. 门禁读数

| 门禁 | 命令 | 读数 |
|---|---|---|
| dc_validator | `python scripts/spec/dc_validator.py --check-all` | 见 session 第 4 步 |
| grandfather_gate | `python scripts/spec/grandfather_gate.py` | 见 session 第 4 步 |
| step-gate | `python tools/spec_runner/spec_runner.py step-gate --session specwf-p139-heavy-followups-fixes --expect research design implement verify finalize` | 见 session 第 4 步 |
| verify-anchor | `python tools/spec_runner/spec_runner.py verify-anchor --session specwf-p139-heavy-followups-fixes` | 见 session 第 4 步 |
| step_enforce | `python scripts/spec/step_enforce.py <staged files>` | 见 session 第 4 步 |
| pre-commit | `pre-commit run --all-files` | 见 session 第 5 步 |

## 6. 未改动证明

- `.github/workflows/`、`tests/ci_exclusions.yaml`、两条 heavy marker 零改动。
- `response.json` 路径零改动（P-134 已修）。
- 外部契约（文件名/字段）零变更。
- 批外 vendor CRLF 未纳入本批。

## 7. 遗留与接缝

- U-1：外部 UI 写 response 的原子性不在本仓。
- U-2：未做故障注入；J-2 通过异常注入覆盖。
- 合并：押后到窗口 2 结束；合并前需复跑门禁与 PR 检查。
