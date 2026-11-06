# PROGRESS 待办登记

> 依据 SPEC_PROCESS 约定建立（每步完成后更新）。状态词表：`pending / in-progress / blocked / done`。
> 登记日期：2026-11-06
> 编号口径：P-001 起；每个批次必须有一条 `specwf-pNNN-*.jsonl` 决策流（五步：research → design → implement → verify → finalize）。
> 真值源：本表 = P 级任务；`docs/CONSOLE.md` 为纯派生视图，禁止手改。

| ID | 事项 | 依据 | 状态 | 优先级 | 验收标准 |
|---|---|---|---|---|---|
| P-001 | 安装 Spec_Workflow + Spec_Runner，接入 ARC 并启用门禁 | [spec/arc-spec-workflow-install/](../spec/arc-spec-workflow-install/) | done | P0 | 适用 pre-commit 门禁全绿；决策流 5/5 通过 step-gate |
