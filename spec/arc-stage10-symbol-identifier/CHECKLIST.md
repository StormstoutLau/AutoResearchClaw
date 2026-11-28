---
id: arc-stage10-symbol-identifier-CHECKLIST
type: design
version: 1.0
status: accepted
date: 2026-11-28
depends: [arc-stage10-symbol-identifier-IMPLEMENTATION]
upstream: arc-stage10-symbol-identifier-IMPLEMENTATION
---

# 检查表：符号契约只接受标识符（P-232）

| ID | 检查项 | 判据 | 结果 |
|---|---|---|---|
| C-1 | 伪符号被跳过 | `functions` 含 `if __name__ == "__main__"` → `declared_symbols == ["main"]` | ✅（`test_pseudo_symbol_is_ignored`） |
| C-2 | 正确 main.py 不再被拦 | 标准 guard → `check_symbol_contract == []` | ✅（`test_contract_does_not_require_guard_block`） |
| C-3 | 契约块干净 | `symbol_contract_block` 不含 `__main__` | ✅（`test_block_lists_only_identifiers`） |
| C-4 | 三处消费点同源 | 过滤位于 `_declared_symbols`，模块检查/证据门/契约块共用 | ✅（读码 #L261） |
| C-5 | 既有拼写行为不变 | `symbols` / `functions` / `classes` 夹具全过 | ✅（`test_symbol_recheck`、`test_codegen_evidence`） |
| C-6 | 回归 | 五套定向 **124 passed**；全量 `pytest tests` **4260 passed / 6 failed**（6 项均为环境类） | ✅ |
| C-7 | 零新门禁 | 未新增 hook / 校验器判据 | ✅ |
