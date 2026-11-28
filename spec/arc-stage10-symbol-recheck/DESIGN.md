---
id: arc-stage10-symbol-recheck-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [arc-stage10-symbol-recheck-RESEARCH]
upstream: arc-stage10-symbol-recheck-RESEARCH
---

# 设计：晚写入后的符号契约复检（P-229）

## 1. 决策

| ID | 决策 | 依据 |
|---|---|---|
| S-1 | 新增 `_ensure_symbol_contract(files, stage_dir, exp_dir, llm, pm, topic)`：装载蓝图 → `check_symbol_contract` → 无缺失即返回 | L-1 |
| S-2 | 缺失时发一次定向修复（列出 `file: symbols`，只贴受影响文件全文），复用 `_extract_valid_repair_files` + `_merge_repair_files`，仍受入口契约校验 | P-222 |
| S-3 | 截断时 16 384 → 32 768 重发一次，与既有修复路径一致 | P-228 |
| S-4 | 修复后复检；仍缺则**保留原文件**、写 `symbol_contract` trace（`reason=still_missing`）并 ERROR，出口门继续兜底 | L-4 |
| S-5 | 修复成功时写盘并记录 `reason=repaired`，便于现场归因 | P-227 |

## 2. 调用点

1. 首个 `_ensure_entrypoint` 之后（校验循环之前）；
2. 对齐重生成写盘之后；
3. 末尾 `_ensure_entrypoint` 之后（运行 M 的实际失败点）。

三处均为「晚于既有符号检查」的写入点，统一由同一函数覆盖。

## 3. 验收

- 缺失 → 定向修复后符号恢复、文件写盘、trace `repaired`；
- 修复失败 → 返回原文件、不写盘、trace `still_missing`；
- 无蓝图 → 不调用 LLM；
- 截断 → 两次调用（16 384、32 768）；
- 既有回归全过。

## 4. 非目标

不改变出口门判定；不引入无限重试；不部署。
