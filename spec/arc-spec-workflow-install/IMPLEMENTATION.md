---
id: arc-spec-workflow-install-IMPLEMENTATION
type: design
version: 1.0
status: draft
date: 2026-11-06
depends: [arc-spec-workflow-install-DESIGN]
upstream: arc-spec-workflow-install-DESIGN
---

# 实施：ARC 接入 Spec_Workflow / Spec_Runner

## 1. 复制清单（未修改框架源码）

| 源 | 目标 | 说明 |
|---|---|---|
| `F:\Spec_Workflow\SPEC_PROCESS.md` | `SPEC_PROCESS.md` | 流程宪法 |
| `F:\Spec_Workflow\spec\templates\*` | `spec/templates/` | 6 模板 |
| `F:\Spec_Workflow\scripts\dc_validator.py` | `scripts/dc_validator.py` | DC 校验 |
| `F:\Spec_Workflow\scripts\spec_map.py` | `scripts/spec_map.py` | feature↔P 映射 |
| `F:\Spec_Workflow\scripts\step_enforce.py` | `scripts/step_enforce.py` | 批次强制 |
| `F:\Spec_Workflow\scripts\console_gen.py` | `scripts/console_gen.py` | 派生控制台 |
| `F:\Spec_Workflow\scripts\rework_graph_check.py` | `scripts/rework_graph_check.py` | 返工图对账 |
| `F:\Spec_Workflow\tools\spec_runner\spec_runner.py` | `tools/spec_runner/spec_runner.py` | v1.11.0 唯一活动引擎 |
| `F:\Spec_Workflow\tools\spec_runner\templates\*` | `tools/spec_runner/templates/` | 接入样板 |
| `F:\Spec_Workflow\docs\ASSERTION_EVIDENCE_FRAMEWORK.md` | `docs/ASSERTION_EVIDENCE_FRAMEWORK.md` | 断言分级参考 |

## 2. 新建文件

| 文件 | 作用 |
|---|---|
| `docs/PROGRESS.md` | P 级任务真值（P-001 起） |
| `docs/rework-graph.json` | 返工图真值（初始为空） |
| `docs/CONSOLE.md` | 由 `console_gen.py` 生成（不手写） |
| `spec/arc-spec-workflow-install/{RESEARCH,DESIGN,IMPLEMENTATION,CHECKLIST}.md` | 本批次四文档 |
| `tools/spec_runner/sessions/specwf-p001-arc-bootstrap-20261106.jsonl` | 五步决策流 |
| `.pre-commit-config.yaml` | 5 道激活门禁 |

## 3. 安装命令

```powershell
# 1) 复制框架文件（见 §1）
# 2) 创建 PROGRESS / rework-graph / 四文档 / session
# 3) 安装 pre-commit
python -m pip install pre-commit
cd d:\AutoResearchClaw-main\AutoResearchClaw-main
pre-commit install

# 4) 基线校验
python scripts/dc_validator.py spec/arc-spec-workflow-install/RESEARCH.md spec/arc-spec-workflow-install/DESIGN.md spec/arc-spec-workflow-install/IMPLEMENTATION.md spec/arc-spec-workflow-install/CHECKLIST.md docs/PROGRESS.md docs/CONSOLE.md
python tools/spec_runner/spec_runner.py step-gate --session specwf-p001-arc-bootstrap-20261106 --expect research design implement verify finalize
python scripts/console_gen.py
python scripts/console_gen.py --check
python scripts/rework_graph_check.py

# 5) 钩子
pre-commit run dc-validator --all-files
pre-commit run console-gen --all-files
pre-commit run rework-graph --all-files

# 6) bootstrap 提交（仅首次；之后 step-enforce 强制）
#    PROGRESS 尚未进入 HEAD，step-enforce 会 fail-closed；
#    首个提交允许一次 SKIP=step-enforce，之后不得再跳过。
SKIP=step-enforce git commit -m "chore(spec): bootstrap Spec_Workflow gates"
pre-commit run --all-files
```

## 4. 不修改框架源码的边界

- 不修改 `dc_validator.py` / `step_enforce.py` / `console_gen.py` 的判定逻辑。
- 不新增 DC 词表；研究类文档统一用 `type: design`。
- 不修改 `SESSION_RE` / `P_ROW_RE` 等硬编码正则；ARC 采用框架既有命名。
- 不激活无载体的 3 道钩子（m7 / repo / blackbox）。

## 5. 回滚

| 操作 | 命令 |
|---|---|
| 卸载钩子 | `pre-commit uninstall` |
| 移除框架文件 | 删除 `SPEC_PROCESS.md`、`spec/`、`scripts/{dc_validator,spec_map,step_enforce,console_gen,rework_graph_check}.py`、`tools/spec_runner/`、`docs/{PROGRESS.md,CONSOLE.md,rework-graph.json}`、`.pre-commit-config.yaml` |

## 6. 已知风险

| 风险 | 处置 |
|---|---|
| 存量文档 front-matter 词表不合规 | 统一 `type: design`；无 front-matter 的文档被 skip |
| `dc_validator` 全仓扫描较慢 | 首次 `--check-all` 接受；日常由 pre-commit 只传 staged 文件 |
| `step_enforce` 在 `--all-files` 下把全量四文档当变更 | 框架已用 `_local_changed()` 求交；不改源码 |
| `console-gen --stage` 会 `git add` CONSOLE | 预期行为；CONSOLE 必须随源一起提交 |
