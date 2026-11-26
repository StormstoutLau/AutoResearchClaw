---
id: arc-stage10-repair-merge-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-26
depends: [arc-stage10-repair-merge-IMPLEMENTATION]
upstream: arc-stage10-repair-merge-IMPLEMENTATION
---

# 验收清单：B-28

| ID | 断言 | 结果 |
|---|---|---|
| C-1 | 部分修复（只返回 `main.py`）后，`data.py`/`config.py` 内容不变 | ✅ `test_partial_repair_preserves_untouched_files` |
| C-2 | 截断的 `main.py` 片段（未闭合字符串）被拒绝，不覆盖旧版 | ✅ `test_unterminated_fragment_is_rejected` |
| C-3 | 语法错误/未知文件名被过滤，只合并合法文件 | ✅ `test_truncated_or_invalid_files_are_rejected` |
| C-4 | repair 响应 `truncated=True` 时按 8192→32768 重试一次 | ✅ `test_truncated_repair_retries_with_32768` |
| C-5 | 相关回归全绿 | ✅ 59 passed（code_agent + universal_codegen + truncation） |
| C-6 | B 站 Stage 10-12 复跑通过 | ⏳ 待现场（B-11） |
| C-7 | 出口门仍能拒绝 config-only/语法错误入口 | ✅ P-178 既有 4 用例保持通过 |
