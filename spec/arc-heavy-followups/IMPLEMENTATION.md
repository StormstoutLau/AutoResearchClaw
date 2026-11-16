---
id: arc-heavy-followups-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-heavy-followups-DESIGN]
upstream: null
---

# 实施记录：P-136 调研批（零实施）

> **Feature**：P-136。
> **Spec 步骤**：Step 5-6（调研批）。
> **性质声明**：本批**不实施任何修复**。`researchclaw/`、`tests/`、`.github/workflows/`、`tests/ci_exclusions.yaml` 零改动；只产出四文档、一条决策流与一行 PROGRESS。

## 1. 本批范围

| 类别 | 是否改动 | 说明 |
|---|---|---|
| `researchclaw/hitl/file_wait.py` | ❌ | 只读，U-3 证据 |
| `researchclaw/hitl/adapters/ws_adapter.py` | ❌ | 只读，U-3 读方证据 |
| `researchclaw/copilot/feedback.py` | ❌ | 只读，U-3 TOCTOU 证据 |
| `researchclaw/runtime/lease.py` | ❌ | 只读，U-2 证据 |
| `researchclaw/pipeline/runner.py` | ❌ | 只读，U-2 交错路径 |
| `tests/` / workflow / `ci_exclusions.yaml` | ❌ | 零改动 |
| `spec/arc-heavy-followups/` | ✅ | 新增四文档 |
| `docs/PROGRESS.md` | ✅ | 追加 P-136 行 |
| `tools/spec_runner/sessions/` | ✅ | 新增五步决策流 |

## 2. 取证读数（E 表）

| 编号 | 读数 | 来源 | 等级 |
|---|---|---|---|
| E1-1 | `write_waiting` 使用 `path.write_text`（非原子） | `file_wait.py` L54-L61 | E1 |
| E1-2 | `ws_adapter._read_json` 解析失败返回 `None`、不删文件 | `ws_adapter.py` L425-L436 | E1 |
| E1-3 | `write_feedback_request` 使用 `write_text` | `feedback.py` L45-L67 | E1 |
| E1-4 | `read_feedback_response` 先 `exists()` 再 `read_text`，未捕获 `FileNotFoundError` | `feedback.py` L69-L95 | E1 |
| E1-5 | `renew` 只校验 `owner + fencing`，不校验 `released` | `lease.py` L193-L217 | E1 |
| E1-6 | 复现：`after_release released=True` → `renew_after_release=SUCCEEDED released=False` | 临时目录脚本（本机） | E1 |
| E1-7 | `_runtime_end` 先停 keeper 再 release；`atexit` 只 release | `runner.py` L267 / L285-L296 | E1 |

## 3. 结论

- U-3：`waiting.json` 非原子但读方不删、可自愈；copilot feedback 读方存在 TOCTOU，需去掉 `exists()` 预检。
- U-2：`released` 可被 `renew` 复活，已确定性复现；推荐在锁内校验 `released`。
- 两项修复合并为一个后续实施批，按 DESIGN §3 的 J-1..J-5 验收。

## 4. 门禁读数

| 门禁 | 命令 | 读数 |
|---|---|---|
| dc_validator | `python scripts/spec/dc_validator.py --check-all` | 见 session 第 4 步 |
| grandfather_gate | `python scripts/spec/grandfather_gate.py` | 见 session 第 4 步 |
| step-gate | `python tools/spec_runner/spec_runner.py step-gate --session specwf-p136-heavy-followups --expect research design implement verify finalize` | 见 session 第 4 步 |
| verify-anchor | `python tools/spec_runner/spec_runner.py verify-anchor --session specwf-p136-heavy-followups` | 见 session 第 4 步 |
| step_enforce | `python scripts/spec/step_enforce.py <staged files>` | 见 session 第 4 步 |
| pre-commit | `pre-commit run --all-files` | 见 session 第 5 步 |

## 5. 未改动证明

- `git diff --stat` 只应出现 `docs/PROGRESS.md` 与新增 `spec/arc-heavy-followups/`、session、派生视图。
- 批外 vendor CRLF 不纳入本批。
- `response.json`（P-134 已修）零改动。

## 6. 遗留与接缝

- 后续实施批：按 DESIGN §4 实施 U-3/U-2，验收 J-1..J-5。
- 合并时机：窗口 2 结束（北京 2026-11-24 02:17 之后）。
