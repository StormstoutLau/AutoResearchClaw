# PROGRESS 待办登记

> 依据 SPEC_PROCESS 约定建立（每步完成后更新）。状态词表：`pending / in-progress / blocked / done`。
> 登记日期：2026-11-06
> 编号口径：P-001 起；每个批次必须有一条 `specwf-pNNN-*.jsonl` 决策流（五步：research → design → implement → verify → finalize）。
> 真值源：本表 = P 级任务；`docs/CONSOLE.md` 为纯派生视图，禁止手改。

| ID | 事项 | 依据 | 状态 | 优先级 | 验收标准 |
|---|---|---|---|---|---|
| P-001 | 安装 Spec_Workflow + Spec_Runner，接入 ARC 并启用门禁 | [spec/arc-spec-workflow-install/](../spec/arc-spec-workflow-install/) | done | P0 | 适用 pre-commit 门禁全绿；决策流 5/5 通过 step-gate |
| P-002 | 审查 ARC 总纲及 14 份关联文档的事实底座、引用可信度与路线可行性 | [spec/arc-roadmap-review/](../spec/arc-roadmap-review/) | done | P0 | 8 条代码事实逐条核验；106 条验收覆盖检查；P1/P2/P3 分级含证据；step-gate 5/5 通过 |
| P-003 | 按审查结论订正总纲至 v0.2（H-4 前提、C-9 与生效起点、A2-3 口径、钩子数） | [spec/arc-roadmap-fix/](../spec/arc-roadmap-fix/) | done | P0 | 106 计数不变；H-1..H-4 全部进 C-9；矛盾表述清零；四道钩子全绿 |
