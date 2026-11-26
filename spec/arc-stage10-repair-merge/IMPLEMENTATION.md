---
id: arc-stage10-repair-merge-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-26
depends: [arc-stage10-repair-merge-DESIGN]
upstream: arc-stage10-repair-merge-DESIGN
---

# 实施记录：B-28 repair/review-fix 合并与截断重试

## 1. 改动

| 文件 | 改动 |
|---|---|
| `researchclaw/pipeline/stage_impls/_code_generation.py` | 新增 `_extract_valid_repair_files`、`_merge_repair_files`、`_request_repair_response`；repair 与 review-fix 两处改为"重试 → 提取有效文件 → 合并 → 整批写盘" |
| `tests/test_codegen_truncation.py` | 新增 `TestRepairMerge` 4 个用例：部分修复保留、截断/非法过滤、未闭合片段拒绝、8192→32768 重试 |

## 2. 关键行为

- repair 响应截断：先重试 32768；仍截断则只接受 AST 通过的完整文件。
- 模型只返回 `main.py`：`data.py`/`config.py` 保留原值并继续写盘。
- 模型返回未知文件或语法错误文件：忽略并记录 warning。
- 内存 `files` 与磁盘 `experiment/` 始终一致。

## 3. 验证

```bash
python -m pytest tests/test_codegen_truncation.py -q
# 14 passed

python -m pytest tests/test_code_agent.py tests/test_universal_codegen_integration.py tests/test_codegen_truncation.py -q
# 59 passed
```

## 4. 边界

- 本地单测通过；**B 站 Stage 10-12 复跑尚未执行**，B-11 仍待现场验收。
- 未改变 `code_agent.py` 的 "promoting first file" 行为；若后续仍无 `main.py`，需另立 B 项。
