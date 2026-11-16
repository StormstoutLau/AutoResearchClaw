---
id: arc-ci-heavy-fixes-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-ci-heavy-fixes-DESIGN]
upstream: null
---

# 实施：heavy 两例根因修复（P-134）

> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **变更**：3 个产品文件 + 2 个测试文件，+198/−39。
> **TDD**：先红 `4 failed, 2 passed`，后绿 `15 passed`；heavy 1000 次压测零失败。

---

## 1. 变更清单

| 文件 | 改动 | 行数 |
|---|---|---|
| [researchclaw/hitl/file_wait.py](../../researchclaw/hitl/file_wait.py) | 新增 `atomic_write_text`；`write_response` 改原子写；读方签名重试、不删未就绪副本 | +42/−7 |
| [researchclaw/hitl/adapters/ws_adapter.py](../../researchclaw/hitl/adapters/ws_adapter.py) | `_write_response` 改用 `atomic_write_text` | +4/−2 |
| [researchclaw/runtime/lease.py](../../researchclaw/runtime/lease.py) | 抽出 `_lease_lock`；`acquire` 复用；`renew` 锁内校验并映射 `LeaseBusy→LeaseLost` | +50/−29 |
| [tests/test_hitl_advanced.py](../../tests/test_hitl_advanced.py) | 新增 2 个 F-1 确定性用例 | +44/−0 |
| [tests/test_supervisor.py](../../tests/test_supervisor.py) | 新增 4 个 F-2 用例 + 导入 | +58/−1 |

## 2. TDD 读数

**先红**（旧实现，6 个新用例）：

```text
FAILED ...test_poll_does_not_delete_partial_response - AssertionError: poll 不应删除尚未解析成功的响应文件
FAILED ...test_poll_recovers_after_empty_read - assert ABORT == REJECT
FAILED ...test_renew_holds_lease_lock - AssertionError: renew 读取租约时未持锁
FAILED ...test_renew_maps_busy_lock_to_lease_lost - Failed: DID NOT RAISE LeaseLost
4 failed, 2 passed in 1.31s
```

两条回归基线（`test_renew_after_takeover_raises`、`test_renew_same_owner_keeps_fencing`）旧实现即通过，用于证明修复未改变正常路径。

**后绿**：

```text
15 passed in 1.56s
```

覆盖 `TestFileWait` 全类、两条 heavy keeper 用例与 4 条新 F-2 用例。

## 3. 压测

两例 heavy 用例各循环 1000 次（临时目录，逐个独立）：

```text
progress=200  f1_fail=0 f2_fail=0
progress=400  f1_fail=0 f2_fail=0
progress=600  f1_fail=0 f2_fail=0
progress=800  f1_fail=0 f2_fail=0
progress=1000 f1_fail=0 f2_fail=0
FINAL N=1000 f1_fail=0 f2_fail=0
```

## 4. 全量回归

`python -m pytest tests -m "not heavy" -q` → `3670 passed, 108 skipped, 6 failed, 2 deselected`。6 个失败逐条登记：

| 失败 | 原因 | 与本批关系 |
|---|---|---|
| `test_hitl_advanced.py::TestHookRegistry::test_shell_hooks` | Windows `WinError 193`（执行 `.sh`） | 零交集（P-125 已登记同例） |
| `test_memory_system.py` ×4（`test_tfidf_fallback` / `test_tfidf_normalized` / `test_embed_batch` / `test_backend_detection`） | Keras 3 与 Transformers 不兼容（缺 `tf-keras`） | 零交集（环境） |
| `test_rc_sentinel.py::test_sentinel_script_is_valid_bash` | Windows bash 路径被吞反斜杠 | 零交集（环境） |

## 5. 未改动证明

- `tests/ci_exclusions.yaml` 两条条目原样保留；两条 heavy marker 未动。
- `.github/workflows/` 零改动；`researchclaw/` 其他模块零改动。
- `response.json` / `lease.json` 文件名与字段不变。
- 批外 vendor CRLF 与未跟踪 midpoint 文档未纳入本批。

## 6. 门禁读数

| 门禁 | 命令 | 读数 |
|---|---|---|
| dc_validator | `python scripts/spec/dc_validator.py --check-all` | 见 session 第 4 步 |
| grandfather_gate | `python scripts/spec/grandfather_gate.py` | 见 session 第 4 步 |
| step-gate | `python tools/spec_runner/spec_runner.py step-gate --session specwf-p134-ci-heavy-fixes --expect research design implement verify finalize` | 见 session 第 4 步 |
| verify-anchor | `python tools/spec_runner/spec_runner.py verify-anchor --session specwf-p134-ci-heavy-fixes` | 见 session 第 4 步 |
| step_enforce | `python scripts/spec/step_enforce.py <staged files>` | 见 session 第 4 步 |
| pre-commit | `pre-commit run --all-files` | 见 session 第 5 步 |

## 7. 遗留与接缝

- 移出 heavy：P-135（待 U-1 观察窗口）。
- U-3：`waiting.json` / copilot feedback 的原子写审计。
- 本机压测为 Windows；Linux 四矩阵由本批 PR run 观察。
