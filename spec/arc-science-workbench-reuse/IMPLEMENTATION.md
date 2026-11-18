---
id: arc-science-workbench-reuse-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-19
depends: [arc-science-workbench-reuse-DESIGN]
upstream: null
---

# 实施记录：P-140 调研批（零实施）

> **Feature**：P-140。
> **Spec 步骤**：Step 5-6（调研批）。
> **性质声明**：本批**不实施任何吸收项**；`researchclaw/`、`tests/`、`.github/workflows/`、`tests/ci_exclusions.yaml` 零改动。

## 1. 本批范围

| 类别 | 是否改动 | 说明 |
|---|---|---|
| `researchclaw/` | ❌ | 只读，用于组件映射 |
| `tests/` / workflow | ❌ | 零改动 |
| `spec/arc-science-workbench-reuse/` | ✅ | 新增四文档 |
| `docs/PROGRESS.md` | ✅ | 追加 P-140 行 |
| `tools/spec_runner/sessions/` | ✅ | 新增五步决策流 |

## 2. 仓内读数（E1）

| 编号 | 读数 | 来源 |
|---|---|---|
| E1-1 | 流水线 23 个阶段（Stage 1–23） | `researchclaw/pipeline/stages.py` |
| E1-2 | 内置技能 20 个 `SKILL.md`（domain/experiment/tooling） | `researchclaw/skills/builtin` |
| E1-3 | MCP 工具注册表 6 个工具 | `researchclaw/tools/registry.yaml` |
| E1-4 | 领域 profile 10+（生物/化学/临床/经济/数学等） | `researchclaw/domains/profiles` |
| E1-5 | 已有事件链与证据组件 | `researchclaw/runtime/event_log.py`、`researchclaw/evidence/` |
| E1-6 | HITL/CoPilot 组件 | `researchclaw/hitl/`、`researchclaw/copilot/` |

## 3. 外部读数（E1）

| 项目 | 许可证 | star | 语言 |
|---|---|---|---|
| Claude Science | 闭源 | — | — |
| OpenAI4S | MIT | 668 | Python |
| OpenScience（aipoch） | Apache-2.0 | 5,545 | TypeScript |
| Open Science Desktop | NOASSERTION | 2,105 | TypeScript |
| SciForge | Apache-2.0 | 84 | TypeScript |
| K-Dense BYOK | MIT | 1,455 | TypeScript |
| OpenClaudeScience | MIT | 112 | — |
| cscience | 无许可证 | 160 | — |
| claude-science-api-bridge | MIT | 54 | — |
| genomi | Apache-2.0 | 493 | — |

读数为 2026-11-19 GitHub API 快照，会变化。

## 4. 结论

- 最值得吸收：证据/动作账本、pipeline-as-skill（P0）；Plan 合同、模型路由、连接器、产物时间线（P1）。
- 持久内核与算力编排列 P2，单独立项。
- 社区逆向作品中，MIT/Apache 项目可做思路/接口/局部代码复用；无许可证与泄漏源码零复用。

## 5. 门禁读数

| 门禁 | 命令 | 读数 |
|---|---|---|
| dc_validator | `python scripts/spec/dc_validator.py --check-all` | 见 session 第 4 步 |
| grandfather_gate | `python scripts/spec/grandfather_gate.py` | 见 session 第 4 步 |
| step-gate | `python tools/spec_runner/spec_runner.py step-gate --session specwf-p140-science-workbench-reuse --expect research design implement verify finalize` | 见 session 第 4 步 |
| verify-anchor | `python tools/spec_runner/spec_runner.py verify-anchor --session specwf-p140-science-workbench-reuse` | 见 session 第 4 步 |
| step_enforce | `python scripts/spec/step_enforce.py <staged files>` | 见 session 第 4 步 |
| pre-commit | `pre-commit run --all-files` | 见 session 第 5 步 |

## 6. 未改动证明

- `researchclaw/`、`tests/`、`.github/workflows/`、`tests/ci_exclusions.yaml` 零改动。
- 批外 vendor CRLF 不纳入本批。
- 未复制任何第三方代码或资产。

## 7. 遗留与接缝

- P0 可作为下一实施批；P1 拆分；P2 单独立项。
- 合并按窗口 2 后的统一安排执行。
- 编号：本批占用 P-140，移出 heavy 顺延为 P-141。
