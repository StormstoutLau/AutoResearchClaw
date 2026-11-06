---
id: arc-spec-workflow-install-DESIGN
type: design
version: 1.0
status: draft
date: 2026-11-06
depends: [arc-spec-workflow-install-RESEARCH]
upstream: arc-spec-workflow-install-RESEARCH
---

# 设计：ARC 接入 Spec_Workflow / Spec_Runner

## 1. 架构

```text
Layer-0（纯文档，零依赖）
  SPEC_PROCESS.md           流程宪法：10 步 + 6 规则 + ADD + 取证矩阵
  spec/templates/           6 模板（四文档 + ADR + 决策矩阵）
  spec/<feature>/           每个批次四文档

Layer-1（按需激活，提交时触发）
  scripts/dc_validator.py   DC1–DC5 + 计数/链接
  scripts/step_enforce.py   批次 P 行 + 决策流 5/5
  scripts/console_gen.py    PROGRESS + 事件流 → docs/CONSOLE.md
  scripts/rework_graph_check.py  返工图对账
  tools/spec_runner/spec_runner.py  事件流 / gate / step-gate / replay / fork
  tools/spec_runner/sessions/        决策流真值（append-only JSONL）

真值边界
  docs/PROGRESS.md          P 级任务真值
  sessions/*.jsonl          决策流真值（append-only）
  docs/CONSOLE.md           纯派生视图（禁止手改）
  docs/rework-graph.json    返工边真值
```

## 2. 门禁集合

### 2.1 激活（4 道）

| Hook | Entry | 触发面 |
|---|---|---|
| `dc-validator` | `python scripts/dc_validator.py` | `spec/**` 四文档 + `docs/PROGRESS.md` + `docs/CONSOLE.md` |
| `step-enforce` | `python scripts/step_enforce.py` | `spec/**` 四文档 + sessions + PROGRESS |
| `console-gen` | `python scripts/console_gen.py --stage` | PROGRESS + sessions + 四文档 |
| `rework-graph` | `python scripts/rework_graph_check.py` | `docs/rework-graph.json` |

> `dc-validator` 不覆盖根级研究/调研报告：它们使用 `file:///` 绝对锚点做取证定位，DC3 相对链接规则不适用；DC 契约只约束 Spec 工件。

### 2.2 Deferred（4 道，登记不激活）

| Hook | 为什么暂不激活 | 激活条件 |
|---|---|---|
| `m7-stats` | ARC 的 M7 账本尚无样本 | 首批 M7 样本落档后 |
| `repo-stats` | ARC 无 `CODE_WIKI.md` / 视图计数体系 | 建立视图计数后 |
| `blackbox-tests` | ARC 用 pytest + GitHub Actions | 建立 Spec_Workflow 同构黑盒套件后 |
| `spec-runner-selftest` | 83 项中 4 项依赖 Spec_Workflow 自有 fixture（`spec/step-gate`、`ADR-0006`、`spec/independent-verify`），在 ARC 会因 fixture 缺失而红 | 复制对应 fixture 后 |

> 依据 ADR-0010 懒加载：**无触发即不实现，未激活副作用 = 0**。

### 2.3 引导例外（仅首次）

`step-enforce` 读取 `HEAD:docs/PROGRESS.md` 做基线对账；首次安装时 PROGRESS 尚未进入 HEAD，会 fail-closed。因此**首个 bootstrap 提交**允许一次 `SKIP=step-enforce`；提交后该钩子立即恢复强制，后续任何提交不得跳过。

## 3. 强制规则（后续每个批次）

1. 开工前在 `docs/PROGRESS.md` 登记 `P-NNN` 行，状态 `pending`，并链接 `spec/<feature>/`。
2. 建 `spec/<feature>/` 四文档：`RESEARCH → DESIGN → IMPLEMENTATION → CHECKLIST`，全部带 DC1 七字段 front-matter。
3. 开一条 `tools/spec_runner/sessions/specwf-pNNN-<slug>.jsonl`，五步决策事件按序写入。
4. 每个偶数步（research/design/implement/verify/finalize 中的 review 门）必须过 gate。
5. 提交前 `pre-commit run --all-files` 全绿；`step-enforce` 不过即阻断。
6. `docs/CONSOLE.md` 只读；手改即被 `console-gen --check` 判红。
7. 不得使用 `--no-verify` 跳过钩子；不得手改 session 事件流（append-only）。

## 4. 关键决策

| # | 决策 | 理由 |
|---|---|---|
| D1 | 使用 `F:\Spec_Workflow\tools\spec_runner\spec_runner.py` v1.11.0 作为唯一活动引擎 | Spec_Runner 已 P-019 归巢；v1.11.0 是含 `step-gate` 的超集 |
| D2 | `F:\Spec_Runner` 只保留模板作为接入样板 | 独立仓库已冻结为历史存档 |
| D3 | 研究类文档 `type: research` 改为 `type: design` | DC2 词表无 `research`；不为 ARC 扩词表（保持零新规则） |
| D4 | 不复制 M7 / repo-stats / blackbox 三道钩子 | 对应载体不存在，激活即永久红，违反懒加载原则 |
| D5 | session 命名沿用 `specwf-pNNN-` 前缀 | `step_enforce` 的 `SESSION_RE` 硬编码该形态 |

## 5. 不变式

- **I-1 单一真值**：PROGRESS 是任务真值，session 是决策真值，CONSOLE 是派生。
- **I-2 只追加**：session 事件流只允许 append，不允许 rewrite。
- **I-3 机械判定**：门禁只读，不改文档；失败必须给出文件与行号。
- **I-4 零新规则**：不为 ARC 修改框架的词表、schema 或判定逻辑。
