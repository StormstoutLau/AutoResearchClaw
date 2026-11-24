---
id: arc-g4-midpoint-intake-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-g4-midpoint-intake-DESIGN]
upstream: null
---

# 实施：G4 中期盘点文档入库（P-135）

> **基于设计**：[DESIGN.md](./DESIGN.md)（v1.0 / verified）。
> **变更**：1 个文档入库（+横幅 2 行）+ 四文档；零代码、零测试、零 workflow。

---

## 1. 变更清单

| 文件 | 改动 | 说明 |
|---|---|---|
| `docs/arc-g4-midpoint-20261113.md` | 新增归档说明横幅（+2 行含空行） | 正文零改动 |
| `spec/arc-g4-midpoint-intake/` | 四文档 | 新增 |
| `docs/PROGRESS.md` | 追加 P-135 行 | 追加 |
| `tools/spec_runner/sessions/specwf-p135-g4-midpoint-intake.jsonl` | 五步决策流 | 新增 |

## 2. 取证读数（E 表）

| 编号 | 读数 | 来源 |
|---|---|---|
| E1-1 | 入库前 9,018 B，SHA-256 `2d91a950…` | `Get-Item` / `Get-FileHash` |
| E1-2 | 入库后 9,459 B，SHA-256 `5467604f…` | 同上 |
| E1-3 | 去掉第 3-4 行后 SHA-256 = `2d91a9506e77d754c5b455fe23afcb4254aa5f9e6d00b8f33ddcbbc54abc1ce6` ⇒ **正文逐字未变** | 本机脚本 |
| E1-4 | 横幅含 M4/M5 两个链接；目标文件均已被 Git 跟踪 | `git ls-files` |
| E1-5 | 干净检出 21 条 P2 的目标之一为本文件 | arc-ci-cd-research DESIGN §2.1.1 |

## 3. 机械校验

| 断言 | 结果 |
|---|---|
| 文件被跟踪 | `git ls-files docs/arc-g4-midpoint-20261113.md` 非空 |
| 横幅在第 3 行 | 含「归档说明（P-135」 |
| 两个链接目标存在 | `spec/arc-g4-midpoint-intake/../arc-g4-m4-sandbox-limits/RESEARCH.md`、M5 同名文件均在 `git ls-files` |
| 正文哈希 | 与入库前一致（E1-3） |
| 无 front-matter | 第 1 行仍是标题，未新增 `---` 块 |

## 4. 门禁读数

| 门禁 | 命令 | 读数 |
|---|---|---|
| dc_validator | `python scripts/spec/dc_validator.py --check-all` | 见 session 第 4 步 |
| grandfather_gate | `python scripts/spec/grandfather_gate.py` | 见 session 第 4 步 |
| step-gate | `python tools/spec_runner/spec_runner.py step-gate --session specwf-p135-g4-midpoint-intake --expect research design implement verify finalize` | 见 session 第 4 步 |
| verify-anchor | `python tools/spec_runner/spec_runner.py verify-anchor --session specwf-p135-g4-midpoint-intake` | 见 session 第 4 步 |
| step_enforce | `python scripts/spec/step_enforce.py <staged files>` | 见 session 第 4 步 |
| pre-commit | `pre-commit run --all-files` | 见 session 第 5 步 |

## 5. 未改动证明

- `researchclaw/`、`tests/`、`.github/workflows/`、`tests/ci_exclusions.yaml` 零改动。
- M4/M5 RESEARCH 与 PROGRESS 历史行零改动（只追加 P-135 行）。
- 批外 vendor CRLF 不纳入本批。
- 正文哈希与入库前一致（E1-3）。

## 6. 遗留与接缝

- U-1：旧「未入仓」措辞作为历史陈述保留。
- U-2：横幅只使用文件级链接，避免行号漂移。
- 本批合并押后至观察窗口 2 结束（用户裁决）。
