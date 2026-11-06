---
id: arc-spec-workflow-install-RESEARCH
type: design
version: 1.0
status: draft
date: 2026-11-06
depends: []
upstream: null
---

# 调研：Spec_Workflow 与 Spec_Runner 接入 ARC

## 1. 调研目标

回答三个问题：

1. 两个框架的权威边界是什么，是否重复？
2. 接入 ARC 需要复制哪些资产、放弃哪些不适用资产？
3. 如何让后续开发在提交瞬间被强制，而不是靠口头纪律？

## 2. 调研发现

### 2.1 两个框架的关系

`F:\Spec_Workflow` 是方法论本体（Layer-0 纯文档）+ 按需激活的 Layer-1 门禁工具；`F:\Spec_Runner` 是 P-009 方案 B 的独立 runner。其 `F:\Spec_Workflow\tools\spec_runner\README.md` 明确记录：runner 已经 P-019 归巢进 Spec_Workflow，外部 `F:\Spec_Runner` 冻结为历史存档。

结论：**Spec_Workflow 的 `tools/spec_runner/spec_runner.py` v1.11.0 是超集**（含 `gate/run/status/replay/fork/step-gate/step-enforce`），应作为唯一活动引擎；`F:\Spec_Runner` 的模板作为接入样板保留，不再单独运行。

### 2.2 可机械强制的门禁

| 门禁 | 作用 | 是否适用 ARC |
|---|---|---|
| `dc-validator` | front-matter DC1–DC5 + 计数/链接 | 适用 |
| `step-enforce` | 批次必须有 P 行 + 决策流 5/5 | 适用 |
| `console-gen` | 由 PROGRESS + 事件流生成 `docs/CONSOLE.md` | 适用 |
| `rework-graph` | 返工图登记对账 | 适用（先空图） |
| `spec-runner-selftest` | runner 83 项内置自测 | 适用 |
| `m7-stats` | M7 证据账本 hits 对账 | 暂不适用（ARC 无该账本） |
| `repo-stats` | README/CODE_WIKI 计数对账 | 暂不适用（ARC 无该视图体系） |
| `blackbox-tests` | Spec_Workflow 自有 unittest | 暂不适用（ARC 用 pytest/CI） |

后三项按 ADR-0010 懒加载原则**登记但不激活**：等 ARC 产生对应载体（M7 账本 / 视图计数 / 自有黑盒套件）后再启用。

### 2.3 命名与契约

- P 行：`| P-001 | 事项 | 依据（含 spec/<feature>/ 链接） | 状态 | 优先级 | 验收标准 |`
- session：`tools/spec_runner/sessions/specwf-pNNN-<slug>.jsonl`
- 决策事件八字段：`category / scenario / reasoning / outcome / confidence + metadata.step_id / step_seq / evidence`
- 四文档：`spec/<feature>/{RESEARCH,DESIGN,IMPLEMENTATION,CHECKLIST}.md`

## 3. 风险

| 风险 | 处置 |
|---|---|
| 直接复制 6 道钩子会因 m7/repo/blackbox 不适用而永久红 | 只激活适用门禁，其余登记为 deferred |
| 存量文档无 front-matter 被判违规 | `dc_validator` 对无 front-matter 文档 skip；有 front-matter 的文档需统一词表 |
| `type: research` 不在 DC2 词表 | 统一改为 `type: design`（研究/设计同属 design 文档） |
| Windows 无 `/bin/sh` | 所有 hook 用 `python` 前缀（源框架已踩过坑） |

## 4. 结论

接入可行，且不需要修改框架源码；只需按 ARC 的载体激活适用门禁，并把不适用门禁显式登记为 deferred。
