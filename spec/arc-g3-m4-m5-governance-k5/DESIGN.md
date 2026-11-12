---
id: arc-g3-m4-m5-governance-k5-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-13
depends: [arc-g3-m4-m5-governance-k5-RESEARCH, arc-g3-m0-design-DESIGN]
upstream: arc-g3-m4-m5-governance-k5-RESEARCH
---

# 设计：G3 M4+M5 合并批

> 基于 [RESEARCH.md](RESEARCH.md) 与 [M0 §7/§8](../arc-g3-m0-design/DESIGN.md)。本批把治理三件套与 K5/retrieval 两件套一次落地，不改判定内核。

## 1. 架构

```text
execute_pipeline
  ├─ ensure_run_mandate(run_dir) ──> run_mandate.json（一次、不可变）
  ├─ execute_stage ──> PAUSED/BLOCKED
  │     └─ read_handback + validate_handback ──> 越界 => FAILED E_HANDBACK_SCOPE
  └─ _build_pipeline_summary ──> retrieval_degraded

PromptManager.for_stage ──> prompt_version(...) ──> RenderedPrompt.version + logger.info

Stage 22 ──> _apply_retrieval_notice（degraded）
         └─ _k5_refs_report ──> k5_refs.json；未解析 => FAILED E_K5_UNRESOLVED_REF
Stage 23 ──> _k5_refs_report ──> k5_refs.json；未解析 => FAILED
```

## 2. 模块与接口（冻结）

| 模块 | 接口 | 归属 |
|---|---|---|
| `runtime/mandate.py` | `RunMandate`、`ensure_run_mandate`、`StageHandback`、`write_handback`、`read_handback`、`validate_handback`、`prompt_version` | M4 |
| `knowledge/k5_refs.py` | `K5Ref`、`parse_refs`、`resolve_refs`、`check_k5_refs`、`bib_keys_from_text` | M5 |
| `prompts/manager.py` | `PROMPT_BANK_VERSION`、`RenderedPrompt.version` | M4 |
| `pipeline/runner.py` | mandate 写入、handback 校验、summary 字段 | M4/M5 |
| `_review_publish.py` | retrieval 注记、K5 双阶段阻断 | M5 |

错误码：`E_HANDBACK_SCOPE`、`E_K5_UNRESOLVED_REF`（不新增其他）。

## 3. 数据形态

### 3.1 `run_mandate.json`

```json
{"policy_version": 2, "scope": ["stage:1-23", "tool:literature"],
 "strength": "write", "requester": "user:local",
 "created_at": "2026-11-13T00:00:00+00:00", "run_id": "..."}
```

- 已存在 → 读取并校验 `run_id`；不一致抛 `MandateError`，**不覆盖**。
- 写入失败只 warning，不使 run 失败（治理 best-effort）。

### 3.2 `stage-NN/handback.json`

```json
{"reason": "...", "evidence": ["stage-07/report.json"], "requested_scope": ["stage:1-23"]}
```

- `requested_scope` 必须是 mandate.scope 子集；越界抛 `HandbackScopeError`（消息含 `E_HANDBACK_SCOPE`）。
- `reason` 为空即拒绝。
- runner 只在 `PAUSED` / `BLOCKED_APPROVAL` 且文件存在时校验；越界把结果改为 `FAILED`（`decision=handback_scope`）。

### 3.3 `prompt_version`

`sha256(JCS({system, user_template, model_role, prompt_bank_version}))`。

- 在 `PromptManager.for_stage` 渲染点计算，写入 `RenderedPrompt.version` 并 `logger.info`。
- `PROMPT_BANK_VERSION = "1.0"`；`export_yaml` 复用同一常量。
- 版本标识模板/角色，不随插值变量变化（与 M0 的 `user_template` 语义一致）。

### 3.4 K5 文法

- 有效：`tb:node-a`、`paper:smith2020`、`tb:a.b`。
- 键首字符 `[A-Za-z0-9]`，末字符 `[A-Za-z0-9_-]`，中间允许 `._-`——**句末 `.` 不计入键**（DR-1）。
- 解析：`tb:` → `kb_root/**/<key>.md`；`paper:` → `references.bib` 的 `key` 集合。
- `check_k5_refs` 返回 `[{file, line, ref}]`；空列表即通过。

### 3.5 `retrieval_degraded`

- `pipeline_summary.retrieval_degraded`：读 `stage-04*/retrieval_status.json`，缺失 → false。
- Stage 22 若为 true：论文前缀 `> **Retrieval note:** ...`，写 `stage-22/retrieval_degraded.json` 并入 artifacts。
- 不阻断；但论文与 summary 两处均显式。

## 4. 决策表（含拒绝方案）

| # | 决策 | 依据 | 拒绝方案与理由 |
|---|---|---|---|
| D-1 | mandate 循环前幂等写入 | R-1/R-2 | 拒绝每阶段写：嵌套执行会覆盖，破坏不可变 |
| D-2 | handback 文件存在才校验 | R-3 | 拒绝强制所有暂停写 handback：会改变既有暂停语义 |
| D-3 | prompt 版本在渲染点计算 | R-4 | 拒绝改 37 个调用点：收益低、回归面大 |
| D-4 | K5 键末字符收紧 | R-5 读码 + 句末标点 | 拒绝纯 `*` 贪婪：会把句号吃进 key，造成假未解析 |
| D-5 | Stage 22/23 双阻断且检查失败也阻断 | M0 §8 | 拒绝只警告：K5 是发布契约 |
| D-6 | retrieval 只注记不阻断 | M0 §8；既有 H-4 | 拒绝阻断：降级不等于失败，静默才是问题 |

## 5. 不变式

- I-1 不改 C4/AR/claim 判定与既有错误码。
- I-2 mandate/handback 写入原子；mandate 不可变。
- I-3 handback 校验只在暂停/阻塞路径；DONE 路径零影响。
- I-4 K5 检查只读；报告落盘不改变论文。
- I-5 retrieval 缺失/坏文件 → false（不新增失败面）。

## 6. 非目标

- 不实现外部锚点/签名（G7）。
- 不实现工具注册表/沙箱（G4）。
- 不实现逐请求 prompt 日志文件（U-2）。
- 不建 KB 索引（U-3）。

## 7. 验收映射

| 验收 ID | 落点 |
|---|---|
| A3-6 RunMandate | F-1/F-2 |
| A3-7 prompt_version | F-5/F-6 |
| A3-8 StageHandback | F-3/F-4 |
| A3-4 K5 | F-7..F-10 |
| A3-5 retrieval | F-11/F-12 |
