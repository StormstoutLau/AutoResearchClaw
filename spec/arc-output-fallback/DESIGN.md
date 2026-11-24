---
id: arc-output-fallback-DESIGN
type: design
version: 1.0
status: verified
date: 2026-11-24
depends: [arc-output-fallback-RESEARCH]
upstream: null
---

# 设计：零产物账本的回退（P-151）

> **基于调研**：[RESEARCH.md](./RESEARCH.md)（v1.0 / verified）。
> **变更面**：`run_equivalence.py` 条件判定 + 文档字符串；测试 2 条；API/CLI 不变。

---

## 1. 决策

| 决策 | 内容 |
|---|---|
| D-1 | 来源判定改为 `ledger_artifacts` 非空才用 `ledger`，不再看动作数 |
| D-2 | 账本零产物且存在 `artifacts/nodes.jsonl` → `node_index` |
| D-3 | 两者皆无 → `none`（有动作但零产物时不再标 `ledger`） |
| D-4 | 不合并两源；账本产物 ≥1 时整体以账本为准 |
| D-5 | API、报告结构、`checks=9`、CLI 退出码全部不变 |

## 2. API 与报告

`compare_runs` 签名、报告字段与 P-150 一致。唯一可见变化是 `artifacts_source` 在「有动作但零产物」时从 `ledger` 变为 `node_index` 或 `none`。

## 3. 判据实现

```python
if ledger_artifacts:            # 非空
    source = "ledger"
elif (run_dir / NODES_FILE).is_file():
    source = "node_index"
else:
    source = "none"
```

`ledger_artifacts` 由所有动作的 `outputs` 经 run 相对化后汇总；其空与非空是唯一分支条件。

## 4. 不变式

| 编号 | 不变式 | 测试 |
|---|---|---|
| J-1 | 判定器只读 | `test_is_read_only` |
| J-2 | 账本有产物时仍优先 | `test_ledger_preferred_over_node_index` |
| J-3 | 账本零产物时回退并识别差异 | `test_node_index_fallback_when_ledger_has_no_outputs` |
| J-4 | 两源皆无时标 `none` | `test_no_artifacts_source_none` |

## 5. Review 记录（Step 6）

- 只改一个分支条件与模块 docstring，不引入新参数或阈值。
- 保留「单一来源」原则，避免 P-150 已否决的合并语义。
- 回退后仍复用 `_node_artifacts` 的 fail-closed 解析。

## 6. 非目标

两源合并、动作级归属、目录扫描、真实 LLM 重跑、P-150 历史文档改写。
