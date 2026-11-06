---
id: arc-spec-workflow-install-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-06
depends: [arc-spec-workflow-install-IMPLEMENTATION]
upstream: arc-spec-workflow-install-IMPLEMENTATION
---

# 验收清单：ARC 接入 Spec_Workflow / Spec_Runner

## 1. 安装完整性

- [x] `SPEC_PROCESS.md` 位于仓库根
- [x] `spec/templates/` 含 6 模板
- [x] `scripts/` 含 `dc_validator.py`、`spec_map.py`、`step_enforce.py`、`console_gen.py`、`rework_graph_check.py`
- [x] `tools/spec_runner/spec_runner.py` 为 v1.11.0（含 `step-gate`）
- [x] `docs/PROGRESS.md` 含 P-001 行且链接 `spec/arc-spec-workflow-install/`
- [x] `docs/rework-graph.json` 为合法空图
- [x] `.pre-commit-config.yaml` 含 4 道激活钩子

## 2. 机械验收

- [x] `python scripts/dc_validator.py` 对 Spec 工件退出码 0
- [x] `python tools/spec_runner/spec_runner.py step-gate --session specwf-p001-arc-bootstrap-20261106 --expect research design implement verify finalize` 退出码 0
- [x] `python scripts/console_gen.py` 生成 `docs/CONSOLE.md`
- [x] `python scripts/console_gen.py --check` 退出码 0
- [x] `python scripts/rework_graph_check.py` 退出码 0

## 3. 提交门禁

- [x] `pre-commit install` 成功
- [x] `pre-commit run dc-validator --all-files` 通过
- [x] `pre-commit run console-gen --all-files` 通过
- [x] `pre-commit run rework-graph --all-files` 通过
- [x] bootstrap 提交后 `pre-commit run step-enforce --all-files` 通过
- [x] 除首次 bootstrap 外不得使用 `SKIP=` 或 `--no-verify`

## 4. 文档与桥接

- [x] 四文档 front-matter 均为 DC1 七字段
- [x] 研究类文档统一 `type: design`
- [x] `RESEARCHCLAW_AGENTS.md` 含 "Spec Workflow (mandatory)" 节
- [x] 后续批次必须：先登记 P 行 → 四文档 → 决策流 → 门禁 → 提交

## 5. 负向验收

- [x] 删除 P-001 行后 `step_enforce` 必须失败
- [x] 伪造 session 步骤序后 `step-gate` 必须失败
- [x] 手改 `docs/CONSOLE.md` 后 `console_gen --check` 必须失败
- [x] 文档缺 `status` 字段后 `dc_validator` 必须失败
