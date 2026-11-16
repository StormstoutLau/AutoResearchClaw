---
id: arc-ci-heavy-rootcause-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-ci-heavy-rootcause-DESIGN, arc-ci-heavy-rootcause-RESEARCH]
upstream: null
---

# 实施记录：P-133 调研批（零实施，仅取证与文档）

> **Feature**：P-133。
> **Spec 步骤**：Step 5-6（调研批）。
> **性质声明**：本批**不实施任何修复**。`researchclaw/`、`tests/`、`.github/workflows/`、`tests/ci_exclusions.yaml` 均零改动；只产出 `spec/` 四文档、一条决策流与一行 PROGRESS。

## 1. 本批范围

| 类别 | 是否改动 | 说明 |
|---|---|---|
| `researchclaw/hitl/file_wait.py` | ❌ | 只读，作为 F-1 根因证据 |
| `researchclaw/hitl/adapters/ws_adapter.py` | ❌ | 只读，同类非原子写者 |
| `researchclaw/runtime/lease.py` | ❌ | 只读，作为 F-2 根因证据 |
| `tests/test_hitl_advanced.py` / `tests/test_supervisor.py` | ❌ | 零改动，heavy marker 原样保留 |
| `tests/ci_exclusions.yaml` | ❌ | 零改动 |
| `.github/workflows/` | ❌ | 零改动 |
| `spec/arc-ci-heavy-rootcause/` | ✅ | 新增四文档 |
| `docs/PROGRESS.md` | ✅ | 追加 P-133 行 |
| `tools/spec_runner/sessions/` | ✅ | 新增五步决策流 |

## 2. 取证读数（E 表）

| 编号 | 读数 | 来源 | 等级 |
|---|---|---|---|
| E1-1 | `Invalid response file (attempt 1/5): Expecting value: line 1 column 1 (char 0)` 紧随 `HITL poll timeout after 5s`，断言 `ABORT == REJECT` 失败 | `gh run view 43718585981 --job 132825377408 --log` | E1 |
| E1-2 | `write_response` = `Path.write_text`（truncate 后写）；`poll_for_response` 在解析异常分支 `response_path.unlink(missing_ok=True)` | `researchclaw/hitl/file_wait.py` L43-L50 / L87-L120 | E1 |
| E1-3 | `ws_adapter._write_response` 同样使用 `write_text` | `researchclaw/hitl/adapters/ws_adapter.py` L437-L449 | E1 |
| E1-4 | `acquire` 持 `lease.lock`；`renew` 无锁，直接 `read_lease` → `_write` | `researchclaw/runtime/lease.py` L115-L174 / L177-L196 | E1 |
| E1-5 | 确定性交错复现：`after_stale_write owner=me:1 fencing=1`；`renew_after_takeover=SUCCEEDED owner=me:1 fencing=1` | 临时目录脚本（本机执行，不入库） | E1 |
| E1-6 | P-123 存档断言：`AssertionError: keeper 必须在租约丢失时回调`（`tests/test_supervisor.py:113`） | `docs/PROGRESS.md` P-123 行 | T3 |
| E1-7 | F-1 另一次失败 run 与 F-2 的失败 attempt 均被 rerun 覆盖，无法再取逐字日志 | GitHub run API 查询 | E1 |

**机制级复现命令（可复核）**：在临时目录执行 `acquire(me:1)` → `read_lease`（过期快照）→ `acquire(other:2, now=+1h)` → 用快照 `_write` → `renew(me:1)`，输出同 E1-5。

## 3. 根因结论

- **F-1**：非原子写（空读窗口）+ 读方 `unlink`（丢失唯一副本）→ 超时 `ABORT`；`attempt 1/5` 排除“连续 5 次坏文件”路径。
- **F-2**：`renew` 无锁 read-modify-write → 覆盖并发 `acquire` → fencing 回滚到 1 → 旧 owner 续约成功、`on_lost` 不触发；测试的 150ms 墙钟假设是次因。
- 详见 [RESEARCH.md](./RESEARCH.md) §3-§5。

## 4. 门禁读数

| 门禁 | 命令 | 读数 |
|---|---|---|
| dc_validator | `python scripts/spec/dc_validator.py --check-all` | 见 session 第 4 步 |
| grandfather_gate | `python scripts/spec/grandfather_gate.py` | 见 session 第 4 步 |
| step-gate | `python tools/spec_runner/spec_runner.py step-gate --session specwf-p133-ci-heavy-rootcause --expect research design implement verify finalize` | 见 session 第 4 步 |
| verify-anchor | `python tools/spec_runner/spec_runner.py verify-anchor --session specwf-p133-ci-heavy-rootcause` | 见 session 第 4 步 |
| step_enforce | `python scripts/spec/step_enforce.py <staged files>` | 见 session 第 4 步 |
| pre-commit | `pre-commit run --all-files` | 见 session 第 5 步 |

> 门禁读数写入 finalize 前的文档会造成 digest 失配，故结构化读数只记录在决策流第 4/5 步。

## 5. 未改动证明

- `git diff --stat` 对本批只应出现 `docs/PROGRESS.md` 与新增 `spec/arc-ci-heavy-rootcause/`、`tools/spec_runner/sessions/specwf-p133-*.jsonl`、派生视图。
- 批外既有状态保留：`researchclaw/vendor/auto_prover/datatypes/__init__.py`（CRLF 漂移）与 `docs/arc-g4-midpoint-20261113.md`（未跟踪）不得纳入本批。
- `tests/ci_exclusions.yaml` 两条条目原样保留（本轮不做移出）。

## 6. 遗留与接缝

- 实施接缝：DESIGN §4 的两处目标形态 + §3 的 J-1..J-5。
- 未决项：RESEARCH §7 U-1..U-5（U-3 文件 IPC 审计、U-4 移出 heavy 条件）。
- 建议下一批：P-134（T1）按 DESIGN §4 实施并验收 J-1..J-5。
