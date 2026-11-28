---
id: arc-stage10-symbol-identifier-IMPLEMENTATION
type: design
version: 1.0
status: verified
date: 2026-11-28
depends: [arc-stage10-symbol-identifier-DESIGN]
upstream: arc-stage10-symbol-identifier-DESIGN
---

# 实施：符号契约只接受标识符（P-232）

## 1. 改动

| 文件 | 改动 |
|---|---|
| [codegen_evidence.py#L261](../../researchclaw/pipeline/codegen_evidence.py#L261) | `_declared_symbols` 增加 `symbol.isidentifier()` 过滤；伪代码/守卫形态跳过，其余不变 |
| [test_codegen_evidence.py](../../tests/test_codegen_evidence.py) | 新增 `TestDeclaredSymbolIdentifiers` 3 例 |

## 2. 测试

| 用例 | 判据 |
|---|---|
| `test_pseudo_symbol_is_ignored` | 蓝图 `functions` 含 `if __name__ == "__main__"` → `declared_symbols == ["main"]` |
| `test_contract_does_not_require_guard_block` | 标准 guard 的 main.py → `check_symbol_contract == []` |
| `test_block_lists_only_identifiers` | 契约块不含 `__main__` |

## 3. 读数

```
pytest tests/test_codegen_evidence.py tests/test_symbol_recheck.py \
       tests/test_entrypoint_contract.py tests/test_generation_budget_contract.py \
       tests/test_boundary_coverage.py -q
124 passed
```

红→绿记录：新增 3 例在过滤前会红（`declared_symbols` 返回伪符号、契约门报缺、契约块含 `__main__`），加入 `isidentifier()` 后转绿。

全量回归：

```
pytest tests -q
6 failed, 4260 passed, 108 skipped in 273.64s
```

6 项失败均为本机环境类（壳钩子 WinError 193、`test_memory_system` 4 项 Keras 3、`test_rc_sentinel` bash 路径），与本批改动无交集。

## 4. 现场预期

重跑后模块生成阶段不再出现：

```
main.py: declared symbols still missing after repair (if __name__ == "__main__")
```

## 5. 未做

不改出口门失败码集合；不改 `_declared_symbols` 的三种字段拼写支持；不新增告警。
