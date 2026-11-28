---
id: arc-stage10-symbol-recheck-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-28
depends: [arc-stage10-symbol-recheck-IMPLEMENTATION]
upstream: arc-stage10-symbol-recheck-IMPLEMENTATION
---

# 检查表：晚写入后的符号契约复检（P-229）

| ID | 检查项 | 判据 | 结果 |
|---|---|---|---|
| C-1 | 三个晚写入点均有复检 | #L1572 / #L2300 / #L2506 | ✅ |
| C-2 | 缺失可修复 | `repaired` + 符号恢复 + 写盘 | ✅ |
| C-3 | 修复失败不污染 | 返回原文件、不写盘、`still_missing` | ✅ |
| C-4 | 无蓝图零调用 | `llm.calls == []` | ✅ |
| C-5 | 截断升级 | `[16384, 32768]` | ✅ |
| C-6 | 仍受入口契约约束 | 复用 `_extract_valid_repair_files` | ✅ |
| C-7 | 遥测 | `symbol_contract` trace 含 missing/remaining | ✅ |
| C-8 | 回归 | `test_symbol_recheck` 4 + 五套 **65 passed** | ✅ |
| C-9 | 出口门不变 | 证据门代码未改 | ✅ |
| C-10 | 零部署 | B 站未改动 | ✅ |
