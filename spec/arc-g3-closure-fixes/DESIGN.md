---
id: arc-g3-closure-fixes-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-13
depends: [arc-g3-closure-fixes-RESEARCH, arc-g3-closure-review]
upstream: arc-g3-closure-fixes-RESEARCH
---

# 设计：G3 收口缺口修复

> 基于 [RESEARCH.md](RESEARCH.md) 与 [P-088 复核](../../docs/arc-g3-closure-review-20261113.md)。本批只补 A3-7/A3-8/A3-6 与编号映射，不改判定内核。

## 1. 修复映射

| # | 缺口 | 修复 | 验收 |
|---|---|---|---|
| D-1 | A3-7 仅渲染点日志、claim 无版本 | ContextVar + `LLMClient.chat` 请求日志 + Stage 17 侧车 + export 字段 | F-1..F-3 |
| D-2 | A3-8 无 handback 生产者/路由 | Stage 17 阻断分支产 handback；runner 抽出 `_apply_handback_guard` | F-4/F-5 |
| O-2 | A3-6 缺配置变更对照 | 补 mandate 不可变对照测试 | F-6 |
| D-3 | A3-7/A3-8 编号互换 | 以总纲为准修 P-087 文档 | F-7 |

## 2. 模块与接口

### 2.1 `runtime/prompt_context.py`（新增）

```python
set_prompt_version(version: str) -> None
get_prompt_version() -> str
log_prompt_version(model: str = "") -> str
```

- `ContextVar` 默认空串；`PromptManager.for_stage` 每次渲染后写入。
- `LLMClient.chat` 入口调用 `log_prompt_version(model)`，日志行 `llm.request prompt_version=... model=...`。
- 直接 `llm.chat` 调用因此也覆盖；未渲染提示词时记录 `-`。

### 2.2 Stage 17 侧车

`stage-17/claim_prompt_versions.json`：

```json
{"prompt_version": "sha256:...", "claims": ["c-1a2b3c4d"]}
```

- 来源：`_write_paper_sections` 返回 `(draft, version)`；对最终 `paper_draft.md` 提取 claim markers。
- 仅 LLM 路径写；无版本/无 markers 时仍写空 claims（版本存在时）。
- `export_claim_labels` 读取该文件，向每个导出条目附加 `prompt_version`；文件缺失则保持原样（向后兼容）。

### 2.3 Handback 生产者与路由

- `write_handback_file(stage_dir, handback)`：不做 scope 校验，原子写 `handback.json`。
- Stage 17 两个 PAUSED 分支写入：
  - `reason=blocked_simulated_data` / `blocked_no_metrics`
  - `evidence=("paper_meta.json",)`
  - `requested_scope=("stage:12-14",)`
- runner：`_apply_handback_guard(run_dir, stage_num, result, mandate)`
  - 仅 `PAUSED` / `BLOCKED_APPROVAL` 且 mandate 存在时校验；
  - 越界返回 `FAILED`（`decision=handback_scope`，error 含 `E_HANDBACK_SCOPE`）；
  - 范围内保持原结果。
- `execute_pipeline` 原内联块改为调用该函数。

### 2.4 编号映射

以总纲为准：**A3-7 = prompt_version，A3-8 = StageHandback**。修 P-087 DESIGN §7 与 IMPLEMENTATION §6。

## 3. 决策表

| # | 决策 | 依据 | 拒绝方案 |
|---|---|---|---|
| D-1 | ContextVar + LLM 入口单点日志 | R-2/R-3 | 拒绝改 37 个调用点：回归面大、收益相同 |
| D-2 | 侧车文件而非改 C4 schema | R-1/R-4 | 拒绝加 `prompt_version` 到 ClaimRecord：契约变更越界 |
| D-3 | Stage 17 阻断分支作为 handback 生产者 | R-5 | 拒绝新造暂停场景：会改变既有语义 |
| D-4 | 抽出 runner guard 并单测 | R-6 | 拒绝只测 `validate_handback`：不能证明路由 |
| D-5 | 编号以总纲为准 | R-7 | 拒绝改总纲：总纲是验收真值源 |

## 4. 不变式

- I-1 不改 C4 schema、AR 判定与既有错误码。
- I-2 无 sidecar 时 export 逐字段不变。
- I-3 handback 写入失败不改变 Stage 17 暂停结果。
- I-4 范围内 handback 不改变 runner 结果。
- I-5 日志只增；不改变请求内容。

## 5. 非目标

- 不实现逐请求 JSONL 文件（日志行即记录）。
- 不新增 handback UI/路由编排（只做校验与阻断）。
- 不修 P-083 O-3 / P-084 D-3..D-6 / P-086 O-2..O-3。

## 6. 验收映射

| 验收 | 落点 |
|---|---|
| A3-7 | F-1/F-2/F-3 |
| A3-8 | F-4/F-5 |
| A3-6 | F-6 |
| D-3 | F-7 |
| 向后兼容 | F-8 |
