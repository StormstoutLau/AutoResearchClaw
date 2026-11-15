---
id: arc-ci-concurrency-semantics-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-16
depends: [arc-ci-concurrency-semantics-DESIGN]
upstream: null
---

# 实施记录：P-128 调研批（零实施，仅取证与文档）

> **Feature**：P-128。
> **Spec 步骤**：Step 5-6（调研批）。
> **性质声明**：本批**不实施任何修复**。`ci.yml`、`tests/`、`researchclaw/`、分支保护设置均零改动；本批只产出 `spec/` 四文档、一条决策流与一行 PROGRESS。

## 1. 本批范围

| 类别 | 是否改动 | 说明 |
|---|---|---|
| `.github/workflows/ci.yml` | ❌ | 逐字未动（E1-1 为取证读数） |
| 新建 `heavy.yml` | ❌ | 仅在设计文档给出目标形态（DESIGN §4） |
| `tests/` / `researchclaw/` | ❌ | 零改动 |
| 分支保护必需检查 | ❌ | 未触碰远端设置 |
| `spec/arc-ci-concurrency-semantics/` | ✅ | 新增四文档 |
| `docs/PROGRESS.md` | ✅ | 追加 P-128 行 |
| `tools/spec_runner/sessions/` | ✅ | 新增五步决策流 |

## 2. 取证读数（E 表）

| 编号 | 读数 | 来源 | 等级 |
|---|---|---|---|
| E1-1 | `ci.yml` L1-L14：`name: CI`；`on.push.branches: [main]`、`pull_request`、`workflow_dispatch`；`group: ci-${{ github.workflow }}-${{ github.ref }}`；`cancel-in-progress: true` | 仓内读码 | E1 |
| E1-2 | `events-that-trigger-workflows.md` L957-L967：schedule 表 `GITHUB_SHA`=「Last commit on default branch」、`GITHUB_REF`=「Default branch」；NOTE「Scheduled workflows will only run on the default branch.」 | `gh api` raw 取 `github/docs` 官方仓（69,263 B） | T1 |
| E1-3 | 同文件 L780-L784：push 表 `GITHUB_REF`=「Updated ref」 | 同上 | T1 |
| E1-4 | `contexts.md` L191/L197/L215：`github.event_name`=事件名；`github.ref` 引用 `ref-description`「fully-formed … `refs/heads/<branch_name>`」；`github.workflow`=工作流名 | `gh api` raw（51,480 B） | T1 |
| E1-5 | `control-workflow-concurrency`：同组至多 1 个 running；`cancel-in-progress: true` 取消同组在跑者；默认仅 1 个 pending；组名大小写不敏感；`queue: max` 与 `cancel-in-progress: true` 互斥 | docs.github.com 渲染页（166 行） | T1 |
| E1-6 | 同页官方示例：`group: ${{ github.workflow }}-${{ github.ref }}` + `cancel-in-progress: true`（push→main 场景） | 同上 L53-L60 | T1 |
| E1-7 | `workflow-syntax.md` §`concurrency` 与 `section-using-concurrency.md`：顶层允许 `github`/`inputs`/`vars`，job 级另允许 `needs`/`strategy`/`matrix` | `gh api` raw（81,177 B / 805 B） | T1 |
| E1-8 | gh-aw 官方站点三行矩阵：Push `cancel=No`、Schedule/Other 组键不含 ref 且 `cancel=No` | github.github.io/gh-aw | T2 |
| E1-9 | `nativesoil/handover` `.github/workflows/ci.yml`（sha `84ddaa77…`）：`group: ci-${{ github.workflow }}-${{ github.event_name }}-${{ github.ref }}`，注释明示「the event in the group keeps a dispatched or scheduled rate run from being cancelled by an unrelated push」 | `gh api` raw 直读 | T3 |
| E1-10 | dev.to/robsonheals：139 仓扫描、129 个含 push/PR、97 个（75%）无 concurrency；批评 `cancel-in-progress: true` 并改用 `${{ github.event_name == 'pull_request' }}` | WebSearch + WebFetch | T3 |
| E1-11 | gha-utils PyPI 5.14.1：「Cross-event concurrency cancellation ✅ Addressed — event_name in changelog.yaml concurrency group」 | WebSearch | T3 |
| E1-12 | 降级链：raw.githubusercontent WebFetch 空 → `gh api` raw；docs contexts 旧路径 404 → 新路径；StackExchange MCP `quota_remaining=-1` → WebSearch；`gh search code` 空 → 直读仓文件 | 本会话执行记录 | E1 |

**推论标注**：`refs/heads/main` 由 E1-2 + E1-4 合成（E1 推论，RESEARCH §3.3 / U-1），不作为 T1 逐字事实。

## 3. 根因结论

- 组键缺事件维度（R-1）→ schedule 与 main push 解析同串（R-2）→ 同组互斥 + `cancel-in-progress` 双向互杀（R-3）→ 默认单 pending 位放大丢 run（R-4）→ schedule 只在默认分支使其成为必然（R-5）。
- 既有潜伏面：`workflow_dispatch`（D-4 引入）在 main 上同样撞组，P-127 未覆盖（RESEARCH §4 后果 3）。
- 详见 [RESEARCH.md](./RESEARCH.md) §4。

## 4. 门禁读数

| 门禁 | 命令 | 读数 |
|---|---|---|
| dc_validator | `python scripts/spec/dc_validator.py --check-all` | 本批四文档 0 违规（存量 P1 均位于 `.claude/skills/`，非本批引入；首轮 §10.1 模板提示已按 8 类行重排后清零） |
| grandfather_gate | `python scripts/spec/grandfather_gate.py` | `grandfathered=0 expired=0 violations=0`，exit 0 |
| step-gate | `python tools/spec_runner/spec_runner.py step-gate --session specwf-p128-ci-concurrency-semantics --expect research design implement verify finalize` | 见 session 第 4 步 |
| verify-anchor | `python tools/spec_runner/spec_runner.py verify-anchor --session specwf-p128-ci-concurrency-semantics` | 见 session 第 4 步 |
| step_enforce | `python scripts/spec/step_enforce.py --mode batch ...` | 见 session 第 4 步 |
| pre-commit | `pre-commit run --all-files` | 见 session 第 5 步 |

> 说明：门禁自身读数在 finalize 之前写回本文档会造成「验后改文档」的 digest 失配，故结构化读数记录在决策流第 4/5 步，本文档只保留可复现的命令与已稳定的两条读数。

## 5. 未改动证明

- `git diff --stat` 对本批只应出现 `docs/PROGRESS.md` 与新增 `spec/arc-ci-concurrency-semantics/`、`tools/spec_runner/sessions/specwf-p128-*.jsonl`。
- 批外既有状态保留：`researchclaw/vendor/auto_prover/datatypes/__init__.py`（CRLF 工作树漂移，未跟踪批）与 `docs/arc-g4-midpoint-20261113.md`（未跟踪）不得纳入本批。

## 6. 遗留与接缝

- 实施接缝：DESIGN §4 的 `heavy.yml` 目标形态 + §3 的 J-1..J-7 验收口径。
- 未决项：RESEARCH §8 U-1..U-5（其中 U-2 需探针实测，U-3 需用户裁决是否同批修 `workflow_dispatch`）。
