---
id: arc-stage10-repair-merge-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-26
depends: [arc-stage10-repair-merge-RESEARCH]
upstream: arc-stage10-repair-merge-RESEARCH
---

# 设计：repair/review-fix 合并与截断重试（B-28）

## 1. 决策

| ID | 决策 | 被拒替代 | 理由 |
|---|---|---|---|
| D-1 | **合并而非替换**：`files.update(repaired)`，保留模型未返回的文件 | 继续 `files = repaired` | 部分响应会静默丢掉 `data.py` 等未返回文件 |
| D-2 | **截断重试**：repair/fix 响应 `truncated` 或 `finish_reason=length` 时，以 32768 重试一次 | 只靠 AST 过滤 | 过滤只能防止污染，不能拿到完整修复 |
| D-3 | **AST 校验**：只接受能 `ast.parse` 的文件；未知文件名忽略 | 接受任意 fence | 截断片段、闲聊、意外文件都不能落盘 |
| D-4 | **落盘合并后的全集**：`files` 合并后整批写 `experiment/` | 只写返回文件 | 保证内存与磁盘一致，避免旧 `data.py` 残留 |
| D-5 | **测试先行**：部分修复保留、截断片段拒绝、重试顺序、未知/非法文件过滤 | 只测正常路径 | B-28 是负向路径缺陷 |

## 2. 接口

```python
_extract_valid_repair_files(content, known_files) -> dict[str, str]
_merge_repair_files(original, repaired) -> dict[str, str]
_request_repair_response(llm, system, user, *, max_tokens) -> LLMResponse
```

- `known_files`：当前 `files` 的键；额外允许 `main.py`，支持"原本没有 main.py"的修复。
- 只合并已有文件名；不引入未知文件。
- 重试后仍截断时，只合并通过 AST 的完整文件；其余保留旧版。

## 3. 非目标

- 不改变 blueprint/单文件/single-shot 的既有 P-178 路径。
- 不改变 Stage 10 出口门判据。
- 不新增模型或依赖；不改变 `max_tokens` 缺省（仅 repair 重试时升到 32768）。
